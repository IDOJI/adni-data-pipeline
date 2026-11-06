"""Wall-clock processing times from immutable MRIQC/fMRIPrep/XCP-D receipts.

Only sidecar reports are written. Imaging outputs, source receipts and admission
or scientific decisions are never changed by collection.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import warnings

STAGES = ('mriqc', 'fmriprep', 'xcpd')
LIVE = {'running', 'prepared'}
REPOSITORY = Path(__file__).resolve().parents[2]


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if value.tzinfo is None or value.year < 1970:
            return None
        return value.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def timing(record):
    """Prefer recorded Docker times, then runner execution/observation bounds."""
    candidates = [
        ('docker_state', 'container_started_at', 'container_finished_at'),
        ('runner_execution', 'execution_started_at', 'container_ended_at'),
        ('runner_observation', 'started_at', 'container_ended_at'),
        ('runner_interval_including_validation', 'started_at', 'finished_at'),
        ('runner_interval_including_validation', 'started_at', 'ended_at'),
    ]
    result = {'started_at': None, 'finished_at': None, 'elapsed_seconds': None,
              'duration_source': None, 'timing_issue': None}
    terminal = record.get('status') not in LIVE
    for source, a, b in candidates:
        start, end = timestamp(record.get(a)), timestamp(record.get(b))
        if start is not None and end is not None and terminal:
            result.update(started_at=start.isoformat(), finished_at=end.isoformat(), duration_source=source)
            seconds = (end - start).total_seconds()
            if seconds < 0:
                result['timing_issue'] = 'negative_interval'
            else:
                result['elapsed_seconds'] = seconds
            return result
    start = timestamp(record.get('container_started_at')) or timestamp(record.get('execution_started_at')) or timestamp(record.get('started_at'))
    result['started_at'] = start.isoformat() if start else None
    result['timing_issue'] = 'in_progress' if not terminal else 'missing_or_invalid_timestamp'
    return result


def add_timing(record):
    record['timing'] = timing(record)
    return record


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def table(path, rows, fields):
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', newline='') as stream:
            writer = csv.DictWriter(stream, fields, delimiter='\t', extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                                 for k, v in row.items()})
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def discover(roots):
    records, metadata = set(), set()
    patterns = ('runs/*/logs/*/run.json', 'logs/*/run.json',
                'results/*/*/s10/*/runs/*/attempt-*/execution.json',
                '*/*/s10/*/runs/*/attempt-*/execution.json',
                '*/*/_runtime/logs/*/run.json', 'logs/*_execution.json')
    for root in roots:
        for pattern in patterns:
            records.update(p.resolve() for p in root.glob(pattern) if p.is_file())
        for pattern in ('results/*/*/pair_metadata.json', '*/*/pair_metadata.json'):
            metadata.update(p.resolve() for p in root.glob(pattern) if p.is_file())
    return sorted(records), sorted(metadata)


def normalize(record, path):
    if not isinstance(record, dict):
        raise ValueError('Execution receipt must be a JSON object')
    stage = record.get('stage')
    row, case = record.get('row') or {}, record.get('case') or {}
    if not isinstance(row, dict) or not isinstance(case, dict):
        raise ValueError('Invalid execution identity object')
    if path.name == 'execution.json' and row:
        stage = 'xcpd'
    elif path.name.endswith('_execution.json'):
        stage = path.name.removesuffix('_execution.json')
    if stage not in STAGES:
        return None
    subject = str(case.get('subject') or row.get('sub') or 'public-demo').removeprefix('sub-')
    session = str(case.get('session') or row.get('ses') or '').removeprefix('ses-')
    pair = Path(row['source_pair']).name if row.get('source_pair') else ''
    born = record.get('created_at') or record.get('started_at')
    token = path.parent.name if path.name in ('run.json', 'execution.json') else path.name
    identity = [stage, subject, session, pair, record.get('config_id'), token, born,
                path.parent.parent.name if path.name == 'execution.json' else '',
                [row.get(k) for k in ('task', 'run', 'acq', 'dir', 'echo', 'rec')]]
    uid = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    status = str(record.get('status', 'unknown'))
    exit_code = record.get('exit_code', record.get('returncode'))
    success = (status == 'success' and exit_code == 0) or (
        status == 'execution_completed_QC_required' and exit_code == 0 and record.get('input_unchanged') is True)
    inputs = record.get('input_before') or {}
    if not isinstance(inputs, dict): inputs = {}
    named = {Path(name).name: value for name, value in inputs.items()}
    input_identity = hashlib.sha256(json.dumps(named, sort_keys=True).encode()).hexdigest() if inputs and len(named) == len(inputs) else None
    measured = timing(record)
    seconds = measured['elapsed_seconds']
    return {'attempt_id': uid, 'stage': stage, 'subject': subject, 'session': session,
            'selected_input_identity': input_identity,
            'elapsed_hours': seconds / 3600 if seconds is not None else None,
            'elapsed_hms': hms(seconds),
            'pair_id': pair, 'run': str(row.get('run', '')), 'status': status,
            'exit_code': exit_code, 'execution_success': success,
            'record_started_at': record.get('started_at'),
            'record_finished_at': (record.get('finished_at') or record.get('ended_at') or record.get('container_ended_at')) if status not in LIVE else None,
            'runner_sha256': record.get('runner_sha256'),
            **measured, 'source_paths': [str(path)]}


def hms(seconds):
    if seconds is None:
        return None
    hours, left = divmod(int(seconds), 3600)
    minutes, seconds = divmod(left, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}'


def union_seconds(intervals):
    intervals = sorted((a, b) for a, b in intervals if a is not None and b is not None and b >= a)
    if not intervals:
        return 0.0
    total, (start, end) = 0.0, intervals[0]
    for left, right in intervals[1:]:
        if left <= end:
            end = max(end, right)
        else:
            total += (end - start).total_seconds()
            start, end = left, right
    return total + (end - start).total_seconds()


def summarize(rows):
    valid = [r for r in rows if r['elapsed_seconds'] is not None and not r.get('source_conflict')]
    intervals = [(timestamp(r['started_at']), timestamp(r['finished_at'])) for r in valid]
    starts = [timestamp(r.get('record_started_at')) or timestamp(r['started_at']) for r in rows]
    starts = [value for value in starts if value is not None]
    ends = [timestamp(r.get('record_finished_at')) or timestamp(r['finished_at']) for r in valid]
    start, end = min(starts) if starts else None, max(ends) if ends else None
    totals = {}
    for stage in STAGES:
        items = [r for r in rows if r['stage'] == stage]
        known = [r for r in valid if r['stage'] == stage]
        totals[stage + '_seconds'] = sum(r['elapsed_seconds'] for r in known) if items and len(items) == len(known) else None
    observed = {r['stage'] for r in rows}
    terminal = {r['stage'] for r in valid}
    success = {r['stage'] for r in valid if r['execution_success']}
    known_sum = sum(r['elapsed_seconds'] for r in valid)
    stage_sum = known_sum if rows and len(valid) == len(rows) else None
    return {**totals, 'preprocessing_seconds': totals['mriqc_seconds'] + totals['fmriprep_seconds'] if totals['mriqc_seconds'] is not None and totals['fmriprep_seconds'] is not None else None,
            'postprocessing_seconds': totals['xcpd_seconds'], 'stage_seconds_sum': stage_sum,
            'stage_hours_sum': stage_sum / 3600 if stage_sum is not None else None,
            'known_stage_seconds_sum': known_sum,
            'stage_time_hms': hms(stage_sum), 'known_stage_time_hms': hms(known_sum),
            'observed_wall_hms': hms((end - start).total_seconds()) if start and end and end >= start else None,
            'wall_time_complete_for_observed_attempts': bool(rows) and len(valid) == len(rows),
            'first_started_at': start.isoformat() if start else None,
            'latest_finished_at': end.isoformat() if end else None,
            'observed_wall_seconds': (end - start).total_seconds() if start and end and end >= start else None,
            'active_interval_union_seconds': union_seconds(intervals) if valid else None, 'attempts': len(rows),
            'timed_attempts': len(valid), 'untimed_attempts': len(rows) - len(valid),
            'running_attempts': sum(r['status'] in LIVE for r in rows),
            'unsuccessful_terminal_attempts': sum(r['status'] not in LIVE and not r['execution_success'] for r in rows),
            'observed_stages': sorted(observed), 'terminal_stages': sorted(terminal),
            'successful_stages': sorted(success), 'all_three_stages_observed': observed == set(STAGES),
            'scope': 'Observed attempts only; not proof that all cohort runs or QC decisions are complete.'}


def validate_output(path):
    path = Path(path).expanduser().resolve()
    if path == Path('/') or path == REPOSITORY or REPOSITORY in path.parents or path in REPOSITORY.parents:
        raise ValueError('Timing output must be outside the source repository')
    return path


def collect(root, output=None, archives=()):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError('Existing runtime root required')
    output = validate_output(output or root / 'timing')
    roots = [root, *(Path(p).expanduser().resolve() for p in archives)]
    output.mkdir(parents=True, exist_ok=True)
    with (output / '.collection.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = output / 'ledger.json'
        ledger = json.loads(previous.read_text())['attempts'] if previous.exists() else {}
        records, metadata = discover(roots)
        problems, links, seen, current = [], {}, set(), {}
        for path in metadata:
            try:
                meta = json.loads(path.read_text())
                for stage, identity in meta.get('execution_identity', {}).items():
                    key = (meta['subject'].removeprefix('sub-'), stage, identity.get('started_at'), identity.get('runner_sha256'))
                    links.setdefault(key, set()).add(meta['pair_id'])
            except (OSError, ValueError, KeyError) as exc:
                problems.append({'path': str(path), 'error': str(exc)})
        for path in records:
            try:
                item = normalize(json.loads(path.read_text()), path)
                if item is None:
                    continue
                key = (item['subject'], item['stage'], item['record_started_at'], item['runner_sha256'])
                pair_ids = links.get(key, set())
                if not item['pair_id'] and len(pair_ids) == 1:
                    item['pair_id'] = next(iter(pair_ids))
                elif len(pair_ids) > 1:
                    item['pairing_issue'] = 'ambiguous_published_execution_identity'
                uid = item['attempt_id']
                old = ledger.get(uid, {})
                item['source_paths'] = sorted(set(item['source_paths'] + old.get('source_paths', [])))
                item['last_seen_at'] = utcnow()
                if uid in current:
                    earlier = current[uid]
                    signature = lambda x: [x.get(k) for k in ('status', 'started_at', 'finished_at', 'elapsed_seconds')]
                    if signature(item) != signature(earlier):
                        item['source_conflict'] = True
                        problems.append({'attempt_id': uid, 'error': 'Conflicting duplicate execution receipts'})
                current[uid] = item
                seen.add(uid)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                problems.append({'path': str(path), 'error': str(exc)})
        # Link retries only through identical selected input bytes belonging to
        # the same subject/session and an exact published execution identity.
        input_pairs = {}
        for item in [*ledger.values(), *current.values()]:
            if item.get('selected_input_identity') and item['pair_id']:
                key = (item['subject'], item['session'], item['selected_input_identity'])
                input_pairs.setdefault(key, set()).add(item['pair_id'])
        for item in current.values():
            key = (item['subject'], item['session'], item.get('selected_input_identity'))
            pairs = input_pairs.get(key, set())
            if not item['pair_id'] and len(pairs) == 1:
                item['pair_id'] = next(iter(pairs))
                item['pairing_basis'] = 'exact_selected_input_hashes_match_published_execution'
        ledger.update(current)
        # A temporary unmount or relocation must not erase previously recorded times.
        for uid, item in ledger.items():
            item['seen_this_scan'] = uid in seen
        rows = sorted(ledger.values(), key=lambda r: (r['subject'], r['pair_id'], r['stage'], r['record_started_at'] or '', r['attempt_id']))
        groups = {}
        for item in rows:
            pair = item['pair_id'] or 'session:' + item['session']
            groups.setdefault((item['subject'], pair), []).append(item)
        cases = [{'subject': subject, 'pair_id': pair, **summarize(items)}
                 for (subject, pair), items in sorted(groups.items())]
        at = utcnow()
        summary = {'schema_version': 1, 'updated_at': at, 'runtime_root': str(root),
                   **summarize(rows), 'cases': len(cases), 'source_records_seen': len(records),
                   'unseen_attempts': sum(not x['seen_this_scan'] for x in rows), 'diagnostics': problems,
                   'definition': 'Wall-clock seconds. Overall observed wall time includes runner validation and waiting; active union uses timed execution intervals. Durations include including failed/retried attempts. Stage sums count parallel jobs separately; observed wall spans waiting/gaps; union removes overlap. Missing times are never filled with zero.'}
        atomic_json(output / 'ledger.json', {'schema_version': 1, 'updated_at': at, 'attempts': ledger})
        atomic_json(output / 'summary.json', summary)
        atomic_json(output / 'cases.json', {'updated_at': at, 'cases': cases})
        fields = ['subject', 'session', 'pair_id', 'run', 'stage', 'attempt_id', 'status', 'exit_code',
                  'started_at', 'finished_at', 'elapsed_seconds', 'elapsed_hours', 'elapsed_hms', 'duration_source', 'timing_issue',
                  'execution_success', 'source_conflict', 'seen_this_scan', 'source_paths']
        table(output / 'attempts.tsv', rows, fields)
        table(output / 'cases.tsv', cases, ['subject', 'pair_id', 'mriqc_seconds', 'fmriprep_seconds', 'xcpd_seconds',
              'preprocessing_seconds', 'postprocessing_seconds', 'stage_seconds_sum', 'stage_hours_sum',
              'first_started_at', 'latest_finished_at', 'observed_wall_seconds', 'active_interval_union_seconds',
              'known_stage_seconds_sum', 'stage_time_hms', 'known_stage_time_hms', 'observed_wall_hms', 'wall_time_complete_for_observed_attempts',
              'attempts', 'timed_attempts', 'untimed_attempts', 'running_attempts', 'unsuccessful_terminal_attempts',
              'observed_stages', 'terminal_stages', 'successful_stages', 'all_three_stages_observed'])
        return summary


def refresh_safely(runtime):
    """Timing export failures must never change an imaging result or retry state."""
    root = Path(runtime)
    if root.parent.name == 'runs' and (root.parent.parent / 'continuous5').is_dir():
        root = root.parent.parent
    try:
        return collect(root)
    except Exception as exc:
        warnings.warn('Timing sidecar export failed: ' + str(exc), RuntimeWarning)
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--archive-root', type=Path, action='append', default=[])
    p.add_argument('--watch', action='store_true')
    p.add_argument('--interval', type=float, default=30)
    args = p.parse_args(argv)
    if args.interval < 1:
        p.error('Use a positive interval of at least one second')
    while True:
        summary = collect(args.root, args.output_dir, args.archive_root)
        print(json.dumps({k: summary[k] for k in ('updated_at', 'attempts', 'timed_attempts', 'stage_seconds_sum', 'observed_wall_seconds')}) + '\n', end='', flush=True)
        if not args.watch:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
