"""Synthetic continuation safety boundaries; no real participant data."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
import yaml

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / 'pipeline/s5d_bids_identity'))
sys.path.insert(0, str(LAB / '04_workflow'))
import continuation as gate
import queue_service as queue
import queue_watchdog as watchdog


def test_registry_requires_preserved_scope(tmp_path):
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps({'schema': 1, 'hold_unregistered': False}))
    with pytest.raises(ValueError, match='hold unregistered'):
        gate.load_registry(path, gate.binding.sha(path))
    with pytest.raises(ValueError, match='changed'):
        gate.load_registry(path, '0' * 64)


def evidence(tmp_path):
    paths = {}; plan = {'ptid': 'TEST', 'epi_image_id': '101', 'epi': {}, 't1': {}}
    for key, (role, field) in gate.FIELDS.items():
        path = tmp_path / key; path.write_text(key)
        paths[key] = path; plan[role][field] = gate.binding.sha(path)
    hashes = {p.name: gate.binding.sha(p) for p in paths.values()}
    record = {'case': {'ptid': 'TEST', 'bold_image_id': '101'}, 'input_before': hashes,
              'input_after': hashes.copy(), 'input_unchanged': True, 'exit_code': 0,
              'status': 'execution_completed_QC_required'}
    return paths, plan, record


@pytest.mark.parametrize('fault', ['epi', 't1', 'after'])
def test_reuse_proves_both_recorded_images(tmp_path, fault):
    paths, plan, record = evidence(tmp_path)
    gate.check_record(record, paths, plan, tmp_path)
    if fault == 'epi': record['case']['bold_image_id'] = '202'
    elif fault == 't1': record['input_before']['t1w'] = 'wrong'
    else: record['input_after']['bold'] = 'wrong'
    with pytest.raises(ValueError): gate.check_record(record, paths, plan, tmp_path)


def test_reuse_needs_actual_outputs(tmp_path):
    with pytest.raises(ValueError, match='missing required output'):
        gate.output_evidence(tmp_path, 'TEST', 'fmriprep')


@pytest.mark.parametrize('fault', ['extra_t1', 'runtime_json', 'config_t1', 'backend'])
def test_existing_runtime_cannot_bypass_pairing(tmp_path, monkeypatch, fault):
    runtime = tmp_path / 'runtime'; source = tmp_path / 'source'
    names = {'bold': 'func/bold.nii.gz', 'bold_json': 'func/bold.json',
             't1w': 'anat/T1w.nii.gz', 't1w_json': 'anat/T1w.json'}
    plan = {'ptid': 'TEST', 'epi_image_id': '101', 't1_image_id': '201', 'phase': 'ADNI3', 'epi': {}, 't1': {}}
    for key, (role, field) in gate.FIELDS.items():
        for root in [runtime / 'bids', source]:
            path = root / 'sub-TEST/ses-S' / names[key]
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(key)
        plan[role][field] = gate.binding.sha(path)
    backend = tmp_path / 'backend.py'
    backend.write_text('from pathlib import Path\ndef paths_for(cfg, case):\n    return {k: Path(cfg["runtime"])/"bids/sub-TEST/ses-S"/v for k,v in '+repr(names)+'.items()}\n')
    cfg = {'runtime': str(runtime), 'source_bids': str(source), 'runs': [
        {'subject': 'TEST', 'session': 'S', 'ptid': 'TEST', 'bold_image_id': '101', 'phase': 'ADNI3'}]}
    config = tmp_path / 'cfg.yaml'; config.write_text(yaml.safe_dump(cfg))
    receipt = tmp_path / 'receipt.json'; receipt.write_text('{}')
    launcher = tmp_path / 'launcher.py'; launcher.write_text('# launcher')
    route = {'epi_key': 'TEST:EPI', 'config': str(config), 'backend': str(backend),
             'receipt': str(receipt), 'launcher': str(launcher), 'allowed_stages': ['mriqc', 'fmriprep']}
    for key in ['config', 'backend', 'receipt', 'launcher']: route[key+'_sha256'] = gate.binding.sha(route[key])
    registry = {'subjects': {'TEST': route}}
    monkeypatch.setattr(gate.binding, 'verify_plan', lambda *_: plan)
    gate.verify_route(registry, 'TEST')
    if fault == 'extra_t1': (source / 'sub-TEST/ses-S/anat/extra_T1w.nii.gz').write_text('extra')
    elif fault == 'runtime_json': (runtime / 'bids/sub-TEST/ses-S/func/bold.json').write_text('changed')
    elif fault == 'config_t1':
        cfg['runs'][0]['t1_image_id'] = '999'; config.write_text(yaml.safe_dump(cfg))
        route['config_sha256'] = gate.binding.sha(config)
    else: backend.write_text('# changed')
    with pytest.raises(ValueError): gate.verify_route(registry, 'TEST')


def dispatch_fixture(tmp_path, monkeypatch, record=None):
    runtime = tmp_path / 'runtime'; runtime.mkdir()
    route = {'allowed_stages': ['mriqc', 'fmriprep'], 'launcher': 'logging.py',
             'backend': 'frozen.py', 'config': 'unchanged.yaml', 'backend_sha256': 'runner-sha'}
    cfg = {'runtime': str(runtime), 'images': {'mriqc': 'pinned-tag'}}
    backend = SimpleNamespace()
    records = {'mriqc': {'record': record}, 'fmriprep': {'record': None}}
    monkeypatch.setattr(gate, 'verify_route', lambda *_: (route, cfg, {'subject': 'TEST', 'session': 'S'}, backend, records))
    return runtime, route, cfg, backend, records


def test_completed_stage_never_starts_docker(tmp_path, monkeypatch):
    _, _, _, _, records = dispatch_fixture(tmp_path, monkeypatch)
    records['mriqc']['record'] = {'status': 'execution_completed_QC_required', 'exit_code': 0, 'input_unchanged': True}
    result = gate.dispatch({}, 'TEST', 'mriqc', runner=lambda *_a, **_k: pytest.fail('Must reuse'))
    assert result['action'] == 'reuse_completed'


@pytest.mark.parametrize('owner', ['lock', 'container', 'running_record'])
def test_existing_owner_is_not_duplicated(tmp_path, monkeypatch, owner):
    runtime, _, _, _, records = dispatch_fixture(tmp_path, monkeypatch)
    if owner == 'lock': (runtime / 'pipeline.lock').touch()
    if owner == 'running_record': records['mriqc']['record'] = {'status': 'running'}
    def run(argv, **kwargs):
        assert argv[:2] == ['docker', 'ps']
        return SimpleNamespace(stdout='statmind-mriqc-TEST-S\n' if owner == 'container' else '')
    with pytest.raises(ValueError): gate.dispatch({}, 'TEST', 'mriqc', runner=run)


def test_mriqc_is_required_before_fmriprep(tmp_path, monkeypatch):
    dispatch_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='MRIQC must complete'):
        gate.dispatch({}, 'TEST', 'fmriprep')


def test_frozen_cache_and_logging_backend_preserved(tmp_path, monkeypatch):
    runtime, route, cfg, backend, _ = dispatch_fixture(tmp_path, monkeypatch)
    work = tmp_path / 'existing-work'; work.mkdir()
    filters = runtime / 'filters'; filters.mkdir()
    filt = filters / 'sub-TEST_ses-S_mriqc.json'; filt.write_text('{}')
    backend.command = lambda *_: (['original', 'scientific', 'argv'], work)
    backend.selected_inputs = lambda *_: {'raw': 'same-sha'}
    backend.image_record = lambda *_: {'resolved': 'pinned@sha256:abc'}
    signature = {'command': ['original', 'scientific', 'argv'], 'input_sha256': {'raw': 'same-sha'},
                 'filter_sha256': gate.binding.sha(filt), 'runner_sha256': 'runner-sha'}
    sig = work / '.cache-signature.json'; sig.write_text(json.dumps(signature))
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout='', returncode=0)
    gate.dispatch({'pinned_images': {'mriqc': 'pinned@sha256:abc'}}, 'TEST', 'mriqc', runner=run)
    assert calls[-1][1:] == ['logging.py', '--runner', 'frozen.py', '--', '--config', 'unchanged.yaml', 'run', '--stage', 'mriqc', '--subject', 'TEST']
    assert json.loads(sig.read_text()) == signature
    signature['runner_sha256'] = 'changed'; sig.write_text(json.dumps(signature))
    with pytest.raises(ValueError, match='Cache signature differs'):
        gate.dispatch({'pinned_images': {'mriqc': 'pinned@sha256:abc'}}, 'TEST', 'mriqc', runner=run)


def test_queue_scope_holds_unregistered_and_renews_only_once(monkeypatch):
    q = queue.Queue.__new__(queue.Queue)
    q.plan = [{'subject': s} for s in ['UNVERIFIED', 'COMPLETE', 'DEFERRED', 'RETRY']]
    q.state = {'COMPLETE': {'status': 'completed_QC_pending'}, 'DEFERRED': {'status': 'deferred_or_failed'}, 'RETRY': {'status': 'retry_queued'}}
    registry = {'subjects': {'DEFERRED': {'allowed_stages': ['fmriprep']}, 'RETRY': {'allowed_stages': ['mriqc']}}}
    q.verified_continuations = lambda: (gate, registry)
    remaining = [1]
    q.retry_request = lambda *_: remaining[0] > 0
    assert {r['subject'] for r in q.pending_rows({})} == {'DEFERRED', 'RETRY'}
    remaining[0] = 0
    assert [r['subject'] for r in q.pending_rows({})] == ['RETRY']


def test_queue_without_binding_scope_keeps_existing_dispatch():
    q = queue.Queue.__new__(queue.Queue)
    q.verified_continuations = lambda: (None, None)
    assert q.execution_command('original.py', 'config.yaml', 'mriqc', 'TEST') == queue.stage_command('original.py', 'config.yaml', 'mriqc', 'TEST')


def test_finished_verified_scope_does_not_restart_controller(tmp_path):
    directory = tmp_path / 'continuous5'; directory.mkdir()
    (directory / 'status.json').write_text(json.dumps({'mode': 'verified_scope_finished', 'updated_at': '2020-01-01T00:00:00+00:00'}))
    result = watchdog.check(tmp_path, 'com.codex.adni-test', runner=lambda *_a, **_k: pytest.fail('Finished scope must stay held'))
    assert result['status'] == 'verified_scope_finished'
