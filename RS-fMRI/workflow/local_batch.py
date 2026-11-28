#!/usr/bin/env python3
"""Host-local, bounded ADNI handoff processing. No model/API calls or offloading.

The external configuration and receipts contain all participant information.
Original bytes, source-review holds, failed attempts and caches are retained.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import datetime as dt
import fcntl
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

import yaml

LAB = Path(__file__).resolve().parents[1]
TERMINAL = {'completed_QC_pending', 'held_source_review', 'held_intake',
            'held_execution_failure', 'held_integrity', 'held_postprocessing'}
STAGES = ('mriqc', 'fmriprep')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.writing')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def module(name, relative):
    path = LAB / relative
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name + uuid.uuid4().hex, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def config(path):
    cfg = read(path)
    if cfg.get('schema') != 1 or cfg.get('max_subjects') != 5:
        raise ValueError('This authorized host-wide subject limit must remain five')
    root = Path(cfg['root'])
    if not root.is_absolute() or root.resolve().is_relative_to(LAB.parent):
        raise ValueError('Use an absolute private runtime outside the repository')
    if root.resolve().is_relative_to(Path.home() / 'Library/CloudStorage'):
        raise ValueError('Work and results must remain outside cloud storage')
    return cfg


def checked_member(source, relative):
    p = Path(source) / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or not p.resolve().is_relative_to(Path(source).resolve()):
        raise ValueError('Handoff path escapes the source folder')
    if p.is_symlink() or not p.is_file() or getattr(p.stat(), 'st_flags', 0) & 0x40000000:
        raise ValueError('Missing, symlinked or cloud-only source file')
    return p


def validate_handoff(source):
    source = Path(source)
    manifest = read(source / '_handoff/batch_manifest.json')
    cases = manifest['participants']
    ptids = [r['ptid'] for r in cases]
    if not cases or len(ptids) != len(set(ptids)) or len(cases) != manifest['participant_count']:
        raise ValueError('Empty or ambiguous handoff population')
    with (source / '_handoff/participants.tsv').open(encoding='utf-8-sig') as stream:
        listed = list(csv.DictReader(stream, delimiter='\t'))
    # A reservation file is a scope boundary, not scientific approval.
    if {r.get('ptid', r.get('PTID')) for r in listed} != set(ptids):
        raise ValueError('Participant reservation and manifest differ')
    checks = []
    for case in cases:
        if not re.fullmatch(r'\d{3}_S_\d{4,}', case['ptid']) or case['subject'] != 'ADNI' + case['ptid'].replace('_', ''):
            raise ValueError('Invalid participant identity')
        if len(case['files']) != 4 or len({x['relative_path'] for x in case['files']}) != 4:
            raise ValueError('Expected exactly four unique raw files per pair')
        for item in case['files']:
            p = checked_member(source, item['relative_path'])
            if p.stat().st_size != item['bytes'] or sha(p) != item['sha256']:
                raise ValueError('Handoff input size/hash mismatch: ' + item['relative_path'])
            checks.append({'relative_path': item['relative_path'], 'bytes': item['bytes'], 'sha256': item['sha256']})
    return manifest, checks


def normalize_sidecar(meta, modality):
    result = dict(meta)
    if modality == 'EPI':
        if result.get('TaskName') not in (None, 'rest'):
            raise ValueError('Contradictory task metadata')
        result['TaskName'] = 'rest'
    return result


def prepare(path):
    cfg = config(path)
    root = Path(cfg['root'])
    if root.exists():
        raise FileExistsError('Use a new batch root; never repurpose an existing runtime')
    source = Path(cfg['handoff'])
    manifest, verified = validate_handoff(source)
    policy = read(cfg['source_review_policy'])
    if sha(cfg['source_review_policy']) != cfg['source_review_policy_sha256']:
        raise ValueError('Source-review catalog changed')
    root.mkdir(parents=True)
    for name in ('config', 'inputs/original', 'inputs/bids', 'validation', 'runs', 'results', 'logs', 'control/jobs', 'continuous5'):
        (root / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, root / 'config/batch.json')
    shutil.copytree(source / '_handoff', root / 'inputs/original/_handoff')
    mapping, normalization, cases = [], [], []
    descriptor = {'Name': 'Mac assigned verified ADNI pairs', 'BIDSVersion': '1.10.0', 'DatasetType': 'raw'}
    save(root / 'inputs/bids/dataset_description.json', descriptor)
    for case in manifest['participants']:
        sub, ses = case['subject'], case['session']
        ident = {'subject': sub, 'ptid': case['ptid'], 'epi_image_id': case['epi_image_id'],
                 't1_image_id': case['t1_image_id'], 'epi_date': case['scan_date'], 't1_date': case['scan_date']}
        entry = policy['subjects'].get(sub)
        reasons = ['source_catalog_identity_mismatch'] if not entry or entry['identity'] != ident else entry['skip_reasons']
        for item in case['files']:
            raw = checked_member(source, item['relative_path'])
            target = root / 'inputs/original' / item['relative_path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw, target)
            if sha(target) != item['sha256']:
                raise ValueError('Local raw copy differs')
            modality = 'EPI' if '/EPI/' in item['relative_path'] else 'T1'
            folder, suffix = ('func', 'task-rest_bold') if modality == 'EPI' else ('anat', 'T1w')
            ext = '.json' if raw.name.endswith('.json') else '.nii.gz'
            dest = root / 'inputs/bids' / f'sub-{sub}/ses-{ses}/{folder}/sub-{sub}_ses-{ses}_{suffix}{ext}'
            dest.parent.mkdir(parents=True, exist_ok=True)
            if ext == '.json':
                original = read(target)
                converted = normalize_sidecar(original, modality)
                if converted == original:
                    shutil.copy2(target, dest)
                else:
                    save(dest, converted)
                normalization.append({'raw': str(target), 'bids': str(dest), 'raw_sha256': sha(target),
                                      'bids_sha256': sha(dest), 'changed_fields': ['TaskName'] if converted != original else []})
            else:
                shutil.copy2(target, dest)
                if sha(dest) != item['sha256']:
                    raise ValueError('BIDS NIfTI bytes changed')
                mapping.append({'ptid': case['ptid'], 'scan_date': case['scan_date'], 'modality': modality,
                                'image_id': case['epi_image_id'] if modality == 'EPI' else case['t1_image_id'],
                                'sha256': item['sha256'], 'raw_path': str(target), 'bids_path': str(dest),
                                'handoff_manifest_sha256': sha(root / 'inputs/original/_handoff/batch_manifest.json')})
        cases.append({**ident, 'session': ses, 'pair_id': 'EPI_' + ses + '_MT1_' + ses,
                      'status': 'held_source_review' if reasons else 'pending', 'reasons': reasons})
    save(root / 'validation/raw-files.json', {'at': now(), 'files': verified, 'all_hashes_match': True})
    save(root / 'validation/bids-normalization.json', normalization)
    save(root / 'source_mapping.json', mapping)
    bcfg = {**cfg['binding_inputs'], 'hash_evidence': [str(root / 'source_mapping.json')],
            'bids_roots': [str(root / 'inputs/bids')], 'output_dir': str(root / 'validation/binding')}
    save(root / 'config/binding.json', bcfg)
    binding = module('binding', 'pipeline/s5d_bids_identity/binding.py')
    binding.run(root / 'config/binding.json')
    receipt = root / 'validation/binding/07.binding-receipt.json'
    plans = {p['subject']: p for p in read(root / 'validation/binding/05.execution-plans.json')}
    save(root / 'continuous5/settings.json', {'target_concurrency': 5, 'global_compute_limit': 5,
         'source_review_policy': {'enabled': True, 'path': cfg['source_review_policy'],
                                  'sha256': cfg['source_review_policy_sha256']}})
    # Prepare only after both the existing scientific policy and exact-pair gate agree.
    template = {**cfg['preprocessing_template'], 'runtime': '/unused', 'runs': []}
    (root / 'config/preprocessing-template.yaml').write_text(yaml.safe_dump(template, sort_keys=False))
    guarded = module('guarded', 'pipeline/s5d_bids_identity/guarded_runner.py')
    routes = {}
    for case in cases:
        sub = case['subject']
        if case['status'] in TERMINAL:
            save(root / 'control/jobs' / (sub + '.json'), {**case, 'updated_at': now(), 'LLM_calls': 0})
            continue
        if sub not in plans:
            case.update(status='held_integrity', reasons=['Exact-pair binding did not establish readiness'])
            save(root / 'control/jobs' / (sub + '.json'), {**case, 'updated_at': now(), 'LLM_calls': 0})
            continue
        plan = plans[sub]
        cp = guarded.prepare(receipt, plan['epi_key'], root / 'cases' / sub, root / 'config/preprocessing-template.yaml')
        c = yaml.safe_load(cp.read_text())
        # Publish/read S10 through the standard runs/<subject> layout without changing internal paths.
        (root / 'runs' / sub).symlink_to(Path(c['runtime']), target_is_directory=True)
        guarded.dispatch(cp, 'intake')
        import pandas as pd
        decision = pd.read_csv(Path(c['runtime']) / 'results/step5/intake_decisions.tsv', sep='\t')
        if not bool(decision['strict_upstream_eligible'].all()):
            case.update(status='held_intake', reasons=decision['failed_checks'].fillna('').tolist())
        else:
            route = {'runtime': c['runtime'], 'config': str(cp), 'backend': str(LAB / 'pipeline/s7b_sessionwise_preprocessing/run.py'),
                     'launcher': str(LAB / 'pipeline/s7c_ants_iteration_logging/run.py'),
                     'receipt': str(receipt), 'epi_key': plan['epi_key'], 'allowed_stages': list(STAGES)}
            for k in ('config', 'backend', 'launcher', 'receipt'):
                route[k + '_sha256'] = sha(route[k])
            routes[sub] = route
        save(root / 'control/jobs' / (sub + '.json'), {**case, 'updated_at': now(), 'LLM_calls': 0})
    save(root / 'config/continuation.json', {'schema': 1, 'hold_unregistered': True, 'subjects': routes,
                                          'pinned_images': cfg['pinned_images'], 'scope': 'This reserved Mac batch only'})
    # Pin all owned Python execution modules; a future source edit holds new dispatch.
    sources = {str(p): sha(p) for d in ('04_workflow', 'pipeline') for p in (LAB / d).rglob('*.py')}
    wrapper = LAB / 'pipeline/s7c_ants_iteration_logging/antsRegistration'
    sources[str(wrapper)] = sha(wrapper)
    save(root / 'config/source-lock.json', sources)
    xc = read(cfg['xcpd_template'])
    xc.update(root=str(root), repo=None, run_id=cfg['batch_id'] + '-xcpd', templateflow=template['source_templateflow'],
              license=template['freesurfer_license'], resources=cfg['xcpd_resources'])
    if 'reference_xcpd' in cfg:
        for k, v in cfg['reference_xcpd'].items():
            xc[k] = v
    save(root / 'config/xcpd.json', xc)
    save(root / 'control/manifest.json', {'batch_id': cfg['batch_id'], 'created_at': now(), 'cases': cases,
                                        'scope_sha256': sha(root / 'config/batch.json'),
                                        'registry_sha256': sha(root / 'config/continuation.json'),
                                        'source_lock_sha256': sha(root / 'config/source-lock.json'),
                                        'xcpd_sha256': sha(root / 'config/xcpd.json'),
                                        'LLM_calls': 0})
    return {'root': str(root), 'total': len(cases), 'registered': len(routes),
            'initial_status': dict(Counter(read(root / 'control/jobs' / (x['subject'] + '.json'))['status'] for x in cases))}


def effective_command(argv, quota):
    """Retain scientific argv; keep terminal Docker evidence and apply host CPU quota."""
    result = list(argv)
    if result[:2] != ['docker', 'run'] or result.count('--cpus') != 1:
        raise ValueError('Expected the recorded preprocessing Docker command')
    image = result.index('/data') - 1
    if '@sha256:' not in result[image]:
        raise ValueError('Immutable Docker image required')
    if '--rm' in result[:image]:
        result.remove('--rm')
    i = result.index('--cpus')
    result[i + 1] = str(quota)
    return result


class LocalTransport:
    def __init__(self, logging, quota):
        self.logging, self.quota = logging, quota

    def __getattr__(self, key):
        return getattr(subprocess, key)

    def run(self, argv, *args, **kwargs):
        if list(argv[:2]) == ['docker', 'run']:
            folder = Path(kwargs['stdout'].name).parent
            logged = self.logging.augment(argv, folder)
            effective = effective_command(logged, self.quota)
            # A retained failed container must not collide with the next bounded attempt.
            i = effective.index('--name')
            effective[i + 1] += '-' + hashlib.sha256(str(folder).encode()).hexdigest()[:10]
            save(folder / 'local_execution.json', {'at': now(), 'base_docker_argv': list(argv),
                 'effective_docker_argv': effective, 'scope': 'Persistent per-attempt Docker exit evidence, unique attempt name and CPU quota only', 'LLM_calls': 0})
            argv = effective
        return subprocess.run(argv, *args, **kwargs)


def select_pending(cases, states, busy, free_gib, global_busy, floor=20, per_slot=12, limit=5):
    occupied = set(busy) | set(global_busy)
    chosen = []
    for case in cases:
        sub = case['subject']
        if sub in busy or states[sub]['status'] in TERMINAL:
            continue
        # Recover our own retained running container even when all five positions are occupied.
        if sub in global_busy and len(busy) + len(chosen) < limit:
            chosen.append(sub)
    for case in cases:
        sub = case['subject']
        if sub in busy or sub in chosen or states[sub]['status'] in TERMINAL:
            continue
        if len(occupied | set(chosen)) >= limit or free_gib < floor + per_slot * (len(busy) + len(chosen) + 1):
            break
        chosen.append(sub)
    return chosen


class Batch:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.cfg = config(path)
        self.root = Path(self.cfg['root'])
        self.manifest = read(self.root / 'control/manifest.json')
        for relative, key in [('config/batch.json', 'scope_sha256'), ('config/continuation.json', 'registry_sha256'),
                              ('config/source-lock.json', 'source_lock_sha256'), ('config/xcpd.json', 'xcpd_sha256')]:
            if sha(self.root / relative) != self.manifest[key]:
                raise ValueError('Frozen batch configuration changed: ' + relative)
        if sha(self.path) != self.manifest['scope_sha256']:
            raise ValueError('Invoked configuration differs from frozen batch scope')
        self.registry = read(self.root / 'config/continuation.json')
        self.cases = self.manifest['cases']
        self.slot = module('slots', '04_workflow/compute_slots.py')
        self.slot.configure(self.cfg['shared_compute_root'])
        self.post_lock = threading.Lock()
        self.event_lock = threading.Lock()
        self.continuation = module('continuation', 'pipeline/s5d_bids_identity/continuation.py')
        self.source_review = module('source_review', '04_workflow/source_review.py')

    def state(self, sub):
        return read(self.root / 'control/jobs' / (sub + '.json'))

    def update(self, sub, **values):
        save(self.root / 'control/jobs' / (sub + '.json'), {**self.state(sub), **values, 'updated_at': now(), 'LLM_calls': 0})

    def event(self, kind, **values):
        with self.event_lock, (self.root / 'control/events.jsonl').open('a') as stream:
            stream.write(json.dumps({'at': now(), 'kind': kind, **values, 'LLM_calls': 0}) + '\n')

    def check_sources(self):
        for p, h in read(self.root / 'config/source-lock.json').items():
            if sha(p) != h:
                raise ValueError('Pinned pipeline source changed: ' + p)

    def recover_stage(self, route, cfg, case, backend, stage, record_path, record):
        """Observe an interrupted controller's exact retained container; never duplicate it."""
        folder = Path(record_path).parent
        proof = read(folder / 'local_execution.json')
        cmd = proof['effective_docker_argv']
        name = cmd[cmd.index('--name') + 1]
        found = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        if found.returncode:
            raise ValueError('Started attempt has no retained container; manual evidence review required')
        info = json.loads(found.stdout)[0]
        image_index = cmd.index('/data') - 1
        if info['Config']['Cmd'] != cmd[image_index + 1:] or info['Config']['Image'] != cmd[image_index]:
            raise ValueError('Container does not match the exact recorded command')
        for i, token in enumerate(cmd[:image_index]):
            if token != '--mount':
                continue
            value = cmd[i + 1]
            fields = dict(x.split('=', 1) for x in value.split(',') if '=' in x)
            matches = [x for x in info.get('Mounts', []) if x['Destination'] == fields['dst']]
            if len(matches) != 1 or Path(matches[0]['Source']).resolve() != Path(fields['src']).resolve() or bool(matches[0]['RW']) == ('readonly' in value.split(',')):
                raise ValueError('Container mount differs from the recorded attempt')
        self.update(case['subject'], status=stage + '_recovering', container=name)
        if info['State']['Running']:
            subprocess.run(['docker', 'wait', name], capture_output=True, text=True, check=True)
            info = read_docker(name)
        with (folder / 'console.log').open('w') as stream:
            subprocess.run(['docker', 'logs', name], stdout=stream, stderr=subprocess.STDOUT, check=True)
        record.update(exit_code=info['State']['ExitCode'], container_ended_at=info['State']['FinishedAt'], ended_at=now())
        record['input_after'] = backend.selected_inputs(cfg, case)
        record['input_unchanged'] = record['input_before'] == record['input_after']
        record['status'] = 'execution_completed_QC_required' if record['exit_code'] == 0 and record['input_unchanged'] else 'failed'
        record['controller_recovery'] = {'at': now(), 'container_id': info['Id'], 'method': 'Exact command/image and retained Docker terminal state'}
        backend.add_timing(record)
        save(record_path, record)
        lock = Path(cfg['runtime']) / 'pipeline.lock'
        if lock.exists():
            owner = read(lock)
            try:
                os.kill(int(owner['pid']), 0)
            except ProcessLookupError:
                lock.unlink()
            else:
                raise ValueError('Another live stage owner still holds the runtime')
        backend.refresh_safely(Path(cfg['runtime']))

    def run_preprocessing(self, sub):
        for stage in STAGES:
            for attempt in range(self.cfg.get('new_attempts_per_stage', 2)):
                self.check_sources()
                self.source_review.enforce(self.root, sub)
                route, cfg, case, backend, records = self.continuation.verify_route(self.registry, sub)
                previous = records[stage]['record']
                if self.continuation.completed(previous):
                    break
                if stage == 'fmriprep' and not self.continuation.completed(records['mriqc']['record']):
                    raise ValueError('MRIQC has not completed successfully')
                if previous and previous['status'] == 'running':
                    with self.slot.lease(sub, 'S6_S7'):
                        self.recover_stage(route, cfg, case, backend, stage, records[stage]['path'], previous)
                    if self.continuation.completed(read(records[stage]['path'])):
                        break
                # Persisted attempts, not controller uptime, bound retries across restarts.
                attempts = list((Path(cfg['runtime']) / 'logs').glob(f'*_{stage}_sub-{sub}_ses-*/run.json'))
                if len(attempts) >= self.cfg.get('new_attempts_per_stage', 2):
                    raise RuntimeError('Persisted preprocessing retry budget exhausted')
                # The controller never changes an existing cache signature or successful attempt.
                with self.slot.lease(sub, 'S6_S7'):
                    self.update(sub, status=stage + '_running', stage=stage, controller_pid=os.getpid())
                    image = backend.image_record(cfg['images'][stage])
                    if image['resolved'] != self.registry['pinned_images'][stage]:
                        raise ValueError('Installed image differs from the pinned handoff method')
                    logging = module('logging', 'pipeline/s7c_ants_iteration_logging/run.py')
                    backend.subprocess = LocalTransport(logging, self.cfg['cpu_quota'])
                    original_dump = backend.dump
                    def dump_with_local_receipt(destination, value):
                        proof = Path(destination).with_name('local_execution.json')
                        if Path(destination).name == 'run.json' and proof.is_file():
                            value['local_execution'] = {'path': str(proof), 'sha256': sha(proof)}
                        return original_dump(destination, value)
                    backend.dump = dump_with_local_receipt
                    try:
                        backend.run_stage(cfg, stage, case, 'strict')
                    except RuntimeError:
                        self.event('stage_failed', subject=sub, stage=stage, new_attempt=attempt + 1)
                        if attempt + 1 >= self.cfg.get('new_attempts_per_stage', 2):
                            raise
                        time.sleep(self.cfg.get('retry_delay_seconds', 300))
                        continue
                    self.continuation.output_evidence(cfg['runtime'], sub, stage)
                    break
            else:
                raise RuntimeError('Bounded preprocessing attempts exhausted')

    def postprocess(self, sub):
        case = next(x for x in self.cases if x['subject'] == sub)
        plan = [{'ptid': case['ptid'], 'subject': sub, 'pair_id': case['pair_id'],
                 'epi_date': case['epi_date'], 'mt1_date': case['t1_date'],
                 'epi_image_id': case['epi_image_id'], 'mt1_image_id': case['t1_image_id'],
                 'execution_session_label': case['session'], 'pairing_basis': 'Verified handoff IDs, dates, UIDs and hashes',
                 'target': str(self.root / 'results' / case['ptid'] / case['pair_id'])}]
        publisher = module('publish', 'pipeline/s7b_sessionwise_preprocessing/publish_pairs.py')
        result = publisher.publish(self.root, plan)
        if result[0]['delivery_status'] not in ('processing_complete_QC_pending', 'previously_published'):
            raise ValueError('Preprocessing delivery is incomplete')
        self.update(sub, status='postprocessing_waiting', results=plan[0]['target'])
        # One S10 owner protects the shared pilot gate and manual-review table.
        with self.post_lock:
            self.check_sources()
            s10 = module('s10', 'pipeline/s10_xcpd_integrated_qc/pipeline.py')
            pipeline = s10.Pipeline(self.root / 'config/xcpd.json')
            with (pipeline.hub / 'worker.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                pair = Path(plan[0]['target'])
                rows = pipeline.prepare(pair)
                pilot = pipeline.hub / 'pilot_success.json'
                for row in rows:
                    if not row['candidate']:
                        continue
                    blocked = pipeline.hub / 'local_pilot_blocked.json'
                    if blocked.exists() and not pilot.exists() and read(blocked)['subject'] != sub:
                        raise RuntimeError('An earlier XCP-D pilot failed validation; retain results and hold expansion')
                    for attempt in range(pipeline.cfg['max_attempts']):
                        with self.slot.lease(sub, 'xcpd'):
                            self.update(sub, status='xcpd_running', stage='xcpd')
                            pipeline.run_one(row)
                        _, record = pipeline.latest(row)
                        if record and record['status'] in ('success', 'skipped_insufficient_time'):
                            break
                        time.sleep(pipeline.cfg['retry_delay_seconds'])
                    else:
                        if not pilot.exists():
                            save(blocked, {'subject': sub, 'at': now(), 'reason': 'Bounded first-pilot validation failure'})
                        raise RuntimeError('XCP-D failed its bounded execution/validation attempts')
                pipeline.aggregate()
                if not pipeline.mark_ready(pair, rows):
                    raise RuntimeError('S10 output validation has not completed')
                self.update(sub, status='completed_QC_pending', stage='complete', config_id=pipeline.config_id,
                            results=str(pair), scientific_inclusion='pending', finished_at=now())
                save(pair / 'local_retention.json', {'at': now(), 'storage': 'host_local', 'local_path': str(pair),
                     'offload_enabled': False, 'cache_cleanup_enabled': False, 'LLM_calls': 0,
                     'scope': 'Execution/QC complete or documented QC exclusion; human/cohort/clinical inclusion remains pending'})

    def process(self, sub):
        with (self.root / 'control/jobs' / (sub + '.lock')).open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            try:
                self.run_preprocessing(sub)
                self.postprocess(sub)
            except Exception as exc:
                status = 'held_execution_failure' if isinstance(exc, RuntimeError) else 'held_integrity'
                self.update(sub, status=status, error=f'{type(exc).__name__}: {exc}', failed_at=now())
                self.event('subject_held', subject=sub, status=status, error=str(exc))

    def report(self, busy=(), global_busy=(), error=None):
        states = {c['subject']: self.state(c['subject']) for c in self.cases}
        counts = dict(Counter(s['status'] for s in states.values()))
        done = all(s['status'] in TERMINAL for s in states.values())
        status = {'at': now(), 'batch_id': self.cfg['batch_id'], 'controller_pid': os.getpid(),
                  'status': 'finished_with_holds' if done and any(s['status'].startswith('held') for s in states.values()) else 'finished' if done else 'running',
                  'max_subjects': 5, 'active_subjects': sorted(busy), 'global_active_subjects': sorted(global_busy),
                  'free_gib': shutil.disk_usage(self.root).free / 2**30, 'counts': counts,
                  'subjects': states, 'error': error, 'LLM_calls': 0, 'results_root': str(self.root / 'results')}
        save(self.root / 'status.json', status)
        body = '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="60"><title>Local ADNI batch</title><h1>Local ADNI batch</h1>'
        body += '<p>Maximum five subjects; no model/API calls. Final research inclusion remains pending.</p>'
        body += '<p>Updated: ' + html.escape(status['at']) + '; free GiB: ' + str(round(status['free_gib'], 1)) + '</p><table><tr><th>Participant</th><th>Status</th><th>Reason / result</th></tr>'
        for sub, s in states.items():
            reason = s.get('error') or '; '.join(s.get('reasons', [])) or s.get('results', '')
            body += '<tr><td>' + html.escape(s['ptid']) + '</td><td>' + html.escape(s['status']) + '</td><td>' + html.escape(reason) + '</td></tr>'
        (self.root / 'status.html').write_text(body + '</table>')
        return status

    def watch(self):
        with (self.root / 'control/manager.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            futures = {}
            with ThreadPoolExecutor(max_workers=5) as pool:
                while True:
                    for sub, future in list(futures.items()):
                        if future.done():
                            future.result()
                            del futures[sub]
                    try:
                        self.check_sources()
                        global_busy = self.slot.running_subjects() | self.slot.live_reservations(self.slot.HERE / 'compute_slots')
                        states = {c['subject']: self.state(c['subject']) for c in self.cases}
                        chosen = select_pending(self.cases, states, futures, shutil.disk_usage(self.root).free / 2**30,
                                                global_busy, self.cfg.get('disk_floor_gib', 20), self.cfg.get('per_subject_reserve_gib', 12))
                        for sub in chosen:
                            self.update(sub, status='admitted')
                            futures[sub] = pool.submit(self.process, sub)
                        status = self.report(futures, global_busy)
                        if not futures and status['status'] in ('finished', 'finished_with_holds'):
                            return
                    except Exception as exc:
                        self.report(futures, error=f'{type(exc).__name__}: {exc}')
                    time.sleep(self.cfg.get('poll_seconds', 30))


def read_docker(name):
    return json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('action', choices=['prepare', 'watch', 'status'])
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.config)
    else:
        batch = Batch(args.config)
        if args.action == 'watch':
            batch.watch()
            return
        result = read(batch.root / 'status.json')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
