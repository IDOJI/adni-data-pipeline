import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import pytest

repo_local = Path(os.environ.get('STATMIND_LOCAL_MODULE_DIR', str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(repo_local))
source = Path(os.environ.get('STATMIND_SUPERVISOR_SOURCE', str(repo_local / 'continue_pilot.py')))
spec = importlib.util.spec_from_file_location('continue_pilot_test', source)
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    case = {'subject': '998S9999', 'session': '20000101', 'phase': 'ADNI3'}
    case2 = {'subject': '999S99999', 'session': '20000102', 'phase': 'ADNI4'}
    cfg = {'runtime': str(root), 'runs': [case, case2]}
    directory = root / 'logs/20261029_fmriprep_sub-998S9999_ses-20000101'
    directory.mkdir(parents=True)
    (directory / 'runner_source.py').write_text('original runner')
    (directory / 'console.log').write_text('partial output')
    raw = root / 'bids/sub-998S9999/ses-20000101/func/rest.nii.gz'
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'synthetic input')
    image = {'resolved': 'image@sha256:abcdef', 'image_id': 'sha256:abcdef'}
    command = ['docker', 'run', '--name', 'fake-name', '--mount',
               f'type=bind,src={root}/bids,dst=/data,readonly', image['resolved'], '/data', '/out', 'participant']
    old = {'stage': 'fmriprep', 'status': 'running', 'case': case, 'config': cfg, 'image': image,
           'command': command, 'runner_sha256': supervisor.adoption.digest(directory / 'runner_source.py'),
           'input_before': {str(raw.relative_to(root / 'bids')): supervisor.adoption.digest(raw)}}
    record = directory / 'run.json'
    record.write_text(json.dumps(old))
    pid = 99999999
    (root / 'pipeline.lock').write_text(json.dumps({'pid': pid, 'stage': 'fmriprep', 'case': case}))
    (root / 'orchestration.lock').write_text(str(pid))
    old_pilot = root / 'logs/pilot_1/run.json'
    old_pilot.parent.mkdir()
    old_pilot.write_text(json.dumps({'pid': pid, 'status': 'running'}))
    group = root / 'logs/mriqc_group_1/run.json'
    group.parent.mkdir()
    group.write_text(json.dumps({'exit_code': 0, 'IQMs_unchanged': True}))
    cfg_path = tmp_path / 'config.yaml'
    cfg_path.write_text('synthetic config')
    inspect = [{'Id': 'synthetic-container-id', 'Image': image['image_id'],
                'Config': {'Cmd': command[-3:]},
                'Mounts': [{'Destination': '/data', 'Source': str(root / 'bids'), 'RW': False}],
                'State': {'Running': True}}]
    calls = []
    monkeypatch.setattr(supervisor.local, 'load', lambda path: cfg)
    monkeypatch.setattr(supervisor.local, 'runtime', lambda cfg: root)
    monkeypatch.setattr(supervisor.pilot, 'finished', lambda cfg, stage, item: item == case)
    monkeypatch.setattr(supervisor.pilot, 'profile_for', lambda cfg, item: 'technical-extension')
    monkeypatch.setattr(supervisor.local, 'run_stage', lambda cfg, stage, item, profile: calls.append(('run_stage', item, profile)))
    monkeypatch.setattr(supervisor.qc, 'latest_run', lambda cfg, item, stage: ('synthetic', {}))
    monkeypatch.setattr(supervisor.qc, 'check_fmriprep', lambda cfg: calls.append(('check_fmriprep',)))
    monkeypatch.setattr(supervisor.qc, 'final_qc', lambda cfg: calls.append(('final_qc',)))
    monkeypatch.setattr(supervisor.spatial_qc, 'inspect', lambda cfg: calls.append(('spatial_qc',)))
    monkeypatch.setattr(supervisor.shutil, 'disk_usage', lambda path: types.SimpleNamespace(free=100 * 1024**3))
    monkeypatch.setattr(sys, 'argv', ['continue_pilot.py', '--record', str(record), '--config', str(cfg_path)])

    class Follow:
        def __init__(self, argv, stdout, stderr):
            stdout.write(b'synthetic observed fmriprep console\n' * 10)
        def wait(self, timeout):
            return 0
        def poll(self):
            return 0
        def terminate(self):
            raise AssertionError('completed follower should not be terminated')

    state = {'exit_code': 0}
    def fake_run(argv, **kwargs):
        if argv[:2] == ['docker', 'inspect']:
            return types.SimpleNamespace(stdout=json.dumps(inspect), returncode=0)
        if argv[:2] == ['docker', 'wait']:
            return types.SimpleNamespace(stdout=str(state['exit_code']) + '\n', returncode=0)
        calls.append(('render_reports',))
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(supervisor.subprocess, 'run', fake_run)
    monkeypatch.setattr(supervisor.subprocess, 'Popen', Follow)
    return root, record, case2, calls, state


def test_recovery_continues_adni4_then_runs_checks(scenario):
    root, record, case2, calls, state = scenario
    supervisor.start()
    assert json.loads(record.read_text())['status'] == 'execution_completed_QC_required'
    assert ('run_stage', case2, 'technical-extension') in calls
    assert ('check_fmriprep',) in calls and ('final_qc',) in calls and ('spatial_qc',) in calls
    assert ('render_reports',) in calls
    summary = json.loads(next((root / 'logs').glob('supervisor_*/run.json')).read_text())
    assert summary['status'] == 'processing_and_numerical_checks_completed_visual_review_required'
    assert not (root / 'orchestration.lock').exists()
    assert not (root / 'statmind-supervisor.lock').exists()


def test_failed_first_container_never_starts_second(scenario):
    root, record, case2, calls, state = scenario
    state['exit_code'] = 1
    with pytest.raises(ValueError, match='execution failed'):
        supervisor.start()
    assert json.loads(record.read_text())['status'] == 'failed'
    assert not any(c[0] == 'run_stage' for c in calls)
    summary = json.loads(next((root / 'logs').glob('supervisor_*/run.json')).read_text())
    assert summary['status'] == 'failed'


def test_live_original_owner_stops_before_creating_supervisor(scenario):
    root, record, case2, calls, state = scenario
    lock = root / 'pipeline.lock'
    data = json.loads(lock.read_text())
    data['pid'] = os.getpid()
    lock.write_text(json.dumps(data))
    (root / 'orchestration.lock').write_text(str(os.getpid()))
    with pytest.raises(ValueError, match='still alive'):
        supervisor.start()
    assert json.loads(record.read_text())['status'] == 'running'
    assert not list((root / 'logs').glob('supervisor_*/run.json'))
