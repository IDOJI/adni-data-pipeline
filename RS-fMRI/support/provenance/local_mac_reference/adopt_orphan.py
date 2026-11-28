#!/usr/bin/env python3
"""Safely finalize an interrupted statMIND Docker invocation from observed evidence.

Run only after ``docker wait`` and ``docker logs --follow`` have completed.
The original record, original partial console, and stale locks are preserved in
a new recovery directory. The container is never stopped or restarted here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def expected_mounts(command):
    result = {}
    for index, value in enumerate(command):
        if value != '--mount':
            continue
        parts = command[index + 1].split(',')
        properties = dict(part.split('=', 1) for part in parts if '=' in part)
        if properties.get('type') != 'bind':
            raise ValueError('Unexpected non-bind mount')
        result[properties['dst']] = (properties['src'], 'readonly' not in parts)
    return result


def validate_inspect(record, inspect):
    cmd = record['command']
    image = record['image']
    image_index = cmd.index(image['resolved'])
    if inspect['Image'] != image['image_id'] or inspect['Config']['Cmd'] != cmd[image_index + 1:]:
        raise ValueError('Live image or container arguments differ from the saved run')
    actual = {m['Destination']: (m['Source'], m['RW']) for m in inspect['Mounts']}
    if actual != expected_mounts(cmd):
        raise ValueError('Live bind mounts differ from the saved run')
    if not inspect['State']['Running']:
        raise ValueError('Evidence must have been captured while the container was running')
    return inspect['Id']


def validate_wait_code(text):
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0].isdigit():
        raise ValueError('The captured docker-wait response must be one numeric exit code')
    return int(lines[0])


def assert_pid_absent(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    except PermissionError as exc:
        raise ValueError('Cannot establish whether the original owner is alive') from exc
    raise ValueError('The original owner PID is still alive or has been reused')


def recover(record_path, inspect_path, log_path, exit_path, expected_hash):
    record_path = Path(record_path).resolve()
    if digest(record_path) != expected_hash:
        raise ValueError('Original run record changed after recovery was planned')
    record = read_json(record_path)
    if record.get('status') != 'running' or record.get('stage') != 'fmriprep':
        raise ValueError('Expected an interrupted running fMRIPrep record')
    root = Path(record['config']['runtime']).resolve()
    if root not in record_path.parents or record_path.parent.parent != root / 'logs':
        raise ValueError('Run record must belong directly to this runtime logs tree')
    inspect_list = read_json(inspect_path)
    if len(inspect_list) != 1:
        raise ValueError('Expected one captured container')
    container_id = validate_inspect(record, inspect_list[0])
    exit_code = validate_wait_code(Path(exit_path).read_text())
    console = Path(log_path)
    if not console.is_file() or console.stat().st_size < 100:
        raise ValueError('Recovered container console is missing or empty')
    old_runner = record_path.parent / 'runner_source.py'
    if digest(old_runner) != record['runner_sha256']:
        raise ValueError('Frozen original runner source does not match its run record')

    lock = root / 'pipeline.lock'
    orchestration = root / 'orchestration.lock'
    lock_text, orchestration_text = lock.read_text(), orchestration.read_text()
    lock_record = json.loads(lock_text)
    pid = int(lock_record['pid'])
    if (int(orchestration_text.strip()) != pid or lock_record['case'] != record['case']
            or lock_record['stage'] != record['stage']):
        raise ValueError('Stale lock identities do not match the interrupted invocation')
    assert_pid_absent(pid)

    after = {}
    bids = (root / 'bids').resolve()
    for relative in record['input_before']:
        path = (bids / relative).resolve()
        if bids not in path.parents:
            raise ValueError('Input path escapes the BIDS directory')
        after[relative] = digest(path)
    unchanged = after == record['input_before']

    citations = root / 'derivatives/fmriprep/logs'
    sources = sorted(citations.glob('CITATION.*'))
    for source in sources:
        target = record_path.parent / 'citations' / source.name
        if target.exists() and digest(target) != digest(source):
            raise ValueError('Existing citation differs; refusing to overwrite')

    pilots = []
    for path in (root / 'logs').glob('pilot_*/run.json'):
        value = read_json(path)
        if value.get('status') == 'running' and value.get('pid') == pid:
            pilots.append((path, value))
    if len(pilots) != 1:
        raise ValueError('Expected one interrupted orchestration record for the stale owner')
    pilot_path, pilot = pilots[0]
    if (record_path.with_name('run.recovery-tmp.json').exists()
            or pilot_path.with_name('run.recovery-tmp.json').exists()):
        raise ValueError('A temporary recovery record already exists; refusing overwrite')

    folder = record_path.parent / ('orphan_recovery_' + uuid.uuid4().hex[:12])
    folder.mkdir()
    before_record = folder / 'run.before-recovery.json'
    shutil.copy2(record_path, before_record)
    shutil.copy2(pilot_path, folder / 'pilot.before-recovery.json')
    for source, name in ((inspect_path, 'container-inspect.json'), (log_path, 'docker-recovered-console.log'),
                         (exit_path, 'docker-wait-exit-code.txt'), (__file__, 'recovery_source.py')):
        shutil.copy2(source, folder / name)
    if (record_path.parent / 'console.log').exists():
        shutil.copy2(record_path.parent / 'console.log', folder / 'original-partial-console.log')
    evidence = {'container_id': container_id, 'original_owner_pid': pid,
                'observed_at': timestamp(), 'original_record_sha256': expected_hash,
                'input_unchanged': unchanged, 'exit_code': exit_code,
                'stale_lock_sha256': {'pipeline': digest(lock), 'orchestration': digest(orchestration)},
                'files_sha256': {p.name: digest(p) for p in folder.iterdir() if p.is_file()}}
    (folder / 'recovery.json').write_text(json.dumps(evidence, indent=2) + '\n')

    # Move only the exact stale locks; never delete their evidence.
    if lock.read_text() != lock_text or orchestration.read_text() != orchestration_text:
        raise ValueError('Lock contents changed during recovery')
    assert_pid_absent(pid)
    lock.rename(folder / 'pipeline.lock')
    orchestration.rename(folder / 'orchestration.lock')

    copied = []
    for source in sources:
        target = record_path.parent / 'citations' / source.name
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        copied.append({'file': str(target), 'sha256': digest(target)})

    record.update(container_ended_at=evidence['observed_at'], exit_code=exit_code,
                  input_after=after, input_unchanged=unchanged,
                  status='execution_completed_QC_required' if exit_code == 0 and unchanged else 'failed',
                  ended_at=timestamp(),
                  recovery={'method': 'observed_docker_wait_and_captured_logs_after_owner_exit',
                            'path': str(folder), 'evidence_sha256': digest(folder / 'recovery.json'),
                            'citations': copied,
                            'note': 'Completion time is the observation time; full scientific QC remains required.'})
    tmp = record_path.with_name('run.recovery-tmp.json')
    if tmp.exists():
        raise ValueError('Temporary record already exists; refusing overwrite')
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(record_path)
    pilot.update(status='interrupted_owner_exited', recovery_observed_at=evidence['observed_at'],
                 recovered_stage_record=str(record_path), recovery_evidence=str(folder / 'recovery.json'))
    pilot_tmp = pilot_path.with_name('run.recovery-tmp.json')
    if pilot_tmp.exists():
        raise ValueError('Temporary orchestration record exists; refusing overwrite')
    pilot_tmp.write_text(json.dumps(pilot, ensure_ascii=False, indent=2) + '\n')
    pilot_tmp.replace(pilot_path)
    print(json.dumps({'status': record['status'], 'record': str(record_path), 'recovery': str(folder)}))
    if record['status'] != 'execution_completed_QC_required':
        raise ValueError('Recovered execution failed or input hashes changed; inspect evidence')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('record', 'inspect', 'log', 'exit', 'expected-hash'):
        p.add_argument('--' + arg, required=True)
    a = p.parse_args()
    recover(a.record, a.inspect, a.log, a.exit, a.expected_hash)


if __name__ == '__main__':
    main()
