"""Verify existing single-pair runtimes before reusing results or continuing work."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent))
import binding

STAGES = ('mriqc', 'fmriprep')
FIELDS = {'bold': ('epi', 'NIFTI_SHA256'), 'bold_json': ('epi', 'JSON_SHA256'),
          't1w': ('t1', 'NIFTI_SHA256'), 't1w_json': ('t1', 'JSON_SHA256')}


def load_registry(path, digest):
    if binding.sha(path) != digest:
        raise ValueError('Continuation registry changed')
    data = binding.read_json(path)
    if data.get('schema') != 1 or not data.get('hold_unregistered', False):
        raise ValueError('Continuation scope must hold unregistered pairs')
    return data


def latest(runtime, subject, stage):
    paths = sorted((Path(runtime) / 'logs').glob(f'*_{stage}_sub-{subject}_ses-*/run.json'))
    return (paths[-1], binding.read_json(paths[-1])) if paths else (None, None)


def completed(record):
    return bool(record and record.get('status') == 'execution_completed_QC_required'
                and record.get('exit_code') == 0 and record.get('input_unchanged') is True)


def check_record(record, paths, plan, runtime):
    """Prove pair identity from recorded inputs, independently of visit labels."""
    case = record['case']
    if case.get('ptid') != plan['ptid'] or str(case.get('bold_image_id')) != plan['epi_image_id']:
        raise ValueError('Recorded execution belongs to a different EPI')
    before = record.get('input_before', {})
    expected = {str(p.resolve().relative_to(Path(runtime).resolve())): plan[FIELDS[k][0]][FIELDS[k][1]] for k, p in paths.items()}
    if any(before.get(k) != v for k, v in expected.items()):
        raise ValueError('Recorded EPI/T1 input fingerprints differ')
    if completed(record) and (record.get('input_after') != before):
        raise ValueError('Completed execution lacks matching final input evidence')


def output_evidence(runtime, subject, stage):
    root = Path(runtime) / 'derivatives' / stage
    patterns = (['**/*_T1w.json', '**/*_bold.json', '*_T1w.html', '*_bold.html']
                if stage == 'mriqc' else
                ['**/*desc-preproc_bold.nii.gz', '**/*desc-confounds_timeseries.tsv',
                 '**/*desc-preproc_T1w.nii.gz', f'sub-{subject}.html'])
    evidence = []
    for pattern in patterns:
        matches = sorted(p for p in root.glob(pattern) if p.is_file() and p.stat().st_size > 0)
        if not matches:
            raise ValueError('Completed execution is missing required output: ' + pattern)
        evidence.extend({'path': str(p), 'bytes': p.stat().st_size} for p in matches)
    return evidence


def verify_route(registry, subject, config=None, script=None, row=None):
    route = registry['subjects'][subject]
    if route.get('runtime'):
        workflow = Path(__file__).resolve().parents[2]/'04_workflow'
        if str(workflow) not in sys.path:sys.path.insert(0,str(workflow))
        import source_review
        source_review.enforce(Path(route['runtime']).resolve().parents[1],subject,row)
    for key, digest in [('config', 'config_sha256'), ('backend', 'backend_sha256'),
                        ('receipt', 'receipt_sha256'), ('launcher', 'launcher_sha256')]:
        if binding.sha(route[key]) != route[digest]:
            raise ValueError('Frozen continuation file changed: ' + key)
    if config is not None and Path(config).resolve() != Path(route['config']).resolve():
        raise ValueError('Queue configuration differs from registered continuation')
    if script is not None and Path(script).resolve() != Path(route['backend']).resolve():
        raise ValueError('Queue backend differs from registered continuation')
    if route.get('receipt_type') == 'technical_review_continuation':
        import review_continuation
        plan = review_continuation.verify_plan(route['receipt'], route['epi_key'])
    else:
        plan = binding.verify_plan(route['receipt'], route['epi_key'])
    if row is not None:
        for key, expected in [('ptid', plan['ptid']), ('epi_image_id', plan['epi_image_id']),
                              ('t1_image_id', plan['t1_image_id']), ('epi_date', plan['date']),
                              ('t1_date', plan['date']),
                              ('epi_series_uid', plan['epi']['SERIES_UID']),
                              ('t1_series_uid', plan['t1']['SERIES_UID'])]:
            if str(row.get(key)) != str(expected):
                raise ValueError('Queue pair differs from verified plan: ' + key)
    cfg = yaml.safe_load(Path(route['config']).read_text())
    if len(cfg['runs']) != 1:
        raise ValueError('Continuation requires one isolated pair')
    case = cfg['runs'][0]
    if (case['subject'], case['ptid'], str(case['bold_image_id'])) != (subject, plan['ptid'], plan['epi_image_id']):
        raise ValueError('Configuration EPI identity differs')
    if case.get('phase') != plan['phase']:
        raise ValueError('Configuration phase differs')
    if 't1_image_id' in case and str(case['t1_image_id']) != plan['t1_image_id']:
        raise ValueError('Configuration T1 identity differs')
    spec = importlib.util.spec_from_file_location('continuation_original_backend', route['backend'])
    backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
    paths = backend.paths_for(cfg, case)
    runtime = Path(cfg['runtime']).resolve()
    for key, path in paths.items():
        role, field = FIELDS[key]
        if binding.sha(path) != plan[role][field]:
            raise ValueError('Current runtime EPI/T1 differs: ' + key)
    # An exact four-file view prevents additional T1 images entering a template.
    for root in [runtime / 'bids', Path(cfg['source_bids'])]:
        actual = {p.relative_to(root): binding.sha(p) for p in root.glob('sub-*/ses-*/*/*')
                  if p.name.endswith(('.nii', '.nii.gz', '.json'))}
        expected = {p.relative_to(runtime / 'bids'): plan[FIELDS[k][0]][FIELDS[k][1]] for k, p in paths.items()}
        if actual != expected:
            raise ValueError('Extra, missing or changed BIDS inputs in continuation')
    records = {}
    for stage in STAGES:
        path, record = latest(runtime, subject, stage)
        if record:
            check_record(record, paths, plan, runtime / 'bids')
            if completed(record):
                output_evidence(runtime, subject, stage)
            elif record.get('status') == 'failed':
                if record.get('input_unchanged') is not True or record.get('config') != cfg:
                    raise ValueError('Failed stage configuration/input evidence changed')
                if record.get('runner_sha256') != route['backend_sha256']:
                    raise ValueError('Failed stage backend changed; preserve unknown cache')
        records[stage] = {'path': str(path) if path else None, 'record': record}
    return route, cfg, case, backend, records


def dispatch(registry, subject, stage, runner=subprocess.run):
    route, cfg, case, backend, records = verify_route(registry, subject)
    record = records[stage]['record']
    if completed(record):
        return {'action': 'reuse_completed', 'subject': subject, 'stage': stage, 'analysis_ready': False}
    if stage not in route['allowed_stages']:
        raise ValueError('Stage is outside the authorized missing-stage scope')
    if stage == 'fmriprep' and not completed(records['mriqc']['record']):
        raise ValueError('MRIQC must complete before continuing fMRIPrep')
    if (Path(cfg['runtime']) / 'pipeline.lock').exists():
        raise ValueError('Existing runtime is locked; do not duplicate work')
    names = runner(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True,
                   text=True, timeout=30, check=True).stdout.splitlines()
    if any(n.startswith('statmind-') and f'-{subject}-' in n for n in names):
        raise ValueError('An existing container owns this subject')
    if record and record.get('status') != 'failed':
        raise ValueError('Existing execution must be observed, not relaunched')
    image = backend.image_record(cfg['images'][stage])
    if image['resolved'] != registry['pinned_images'][stage]:
        raise ValueError('Container image differs from the frozen pipeline')
    # Original module/path, config and scientific command preserve cache identity.
    argv, work = backend.command(cfg, stage, case, image['resolved'])
    signature = {'command': argv, 'input_sha256': backend.selected_inputs(cfg, case),
                 'filter_sha256': binding.sha(Path(cfg['runtime']) / 'filters' /
                    f"sub-{case['subject']}_ses-{case['session']}_{stage}.json"),
                 'runner_sha256': route['backend_sha256']}
    sigfile = work / '.cache-signature.json'
    if sigfile.exists() and binding.read_json(sigfile) != signature:
        raise ValueError('Cache signature differs; preserve work and hold')
    if not sigfile.exists() and any(work.iterdir()):
        raise ValueError('Unknown cache; preserve work and hold')
    cmd = [sys.executable, route['launcher'], '--runner', route['backend'], '--',
           '--config', route['config'], 'run', '--stage', stage, '--subject', subject]
    result = runner(cmd, check=False)
    if result.returncode:
        raise RuntimeError('Guarded continuation failed; retain all logs and cache')
    return {'action': 'continued_existing_runtime', 'subject': subject, 'stage': stage, 'analysis_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--registry-sha256', required=True)
    parser.add_argument('--subject', required=True)
    parser.add_argument('--stage', choices=STAGES)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    registry = load_registry(args.registry, args.registry_sha256)
    if args.check:
        verify_route(registry, args.subject)
        result = {'verified_existing_runtime': args.subject, 'analysis_ready': False}
    else:
        if not args.stage:
            parser.error('--stage is required for execution')
        result = dispatch(registry, args.subject, args.stage)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
