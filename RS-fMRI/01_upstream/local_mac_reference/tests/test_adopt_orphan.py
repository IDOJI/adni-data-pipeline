import importlib.util
import json
import os
from pathlib import Path

import pytest

source = Path(os.environ.get('STATMIND_RECOVERY_SOURCE', str(Path(__file__).parents[1] / 'adopt_orphan.py')))
spec = importlib.util.spec_from_file_location('adopt_orphan', source)
adopt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adopt)


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / 'runtime'
    run_dir = root / 'logs' / '20261029_fmriprep_sub-998S9999_ses-20000101'
    run_dir.mkdir(parents=True)
    raw = root / 'bids/sub-998S9999/ses-20000101/func/rest.nii.gz'
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'unchanged image')
    frozen = run_dir / 'runner_source.py'
    frozen.write_text('original runner')
    (run_dir / 'console.log').write_text('partial previous console')
    case = {'subject': '998S9999', 'session': '20000101'}
    image = {'resolved': 'registry/tool@sha256:deadbeef', 'image_id': 'sha256:deadbeef'}
    cmd = ['docker', 'run', '--mount', f'type=bind,src={root}/bids,dst=/data,readonly',
           image['resolved'], '/data', '/out', 'participant']
    record = {'stage': 'fmriprep', 'status': 'running', 'case': case, 'config': {'runtime': str(root)},
              'image': image, 'command': cmd, 'runner_sha256': adopt.digest(frozen),
              'input_before': {str(raw.relative_to(root / 'bids')): adopt.digest(raw)}}
    run = run_dir / 'run.json'
    run.write_text(json.dumps(record))
    inspect = [{'Id': '123abc', 'Image': image['image_id'], 'Config': {'Cmd': cmd[-3:]},
                'Mounts': [{'Destination': '/data', 'Source': str(root / 'bids'), 'RW': False}],
                'State': {'Running': True}}]
    inspection = tmp_path / 'inspect.json'
    inspection.write_text(json.dumps(inspect))
    log = tmp_path / 'recovered.log'
    log.write_text('actual captured fmriprep console\n' * 10)
    code = tmp_path / 'exit.txt'
    code.write_text('0\n')
    pid = 99999999
    (root / 'pipeline.lock').write_text(json.dumps({'pid': pid, 'stage': 'fmriprep', 'case': case}))
    (root / 'orchestration.lock').write_text(str(pid))
    pilot = root / 'logs/pilot_20261029/run.json'
    pilot.parent.mkdir()
    pilot.write_text(json.dumps({'pid': pid, 'status': 'running'}))
    return root, run, inspection, log, code, pilot


def test_recovers_without_losing_original_records_or_locks(fixture):
    root, run, inspect, log, code, pilot = fixture
    old_hash = adopt.digest(run)
    adopt.recover(run, inspect, log, code, old_hash)
    record = json.loads(run.read_text())
    assert record['status'] == 'execution_completed_QC_required'
    assert record['exit_code'] == 0 and record['input_unchanged']
    evidence = Path(record['recovery']['path'])
    assert adopt.digest(evidence / 'run.before-recovery.json') == old_hash
    assert (evidence / 'original-partial-console.log').is_file()
    assert (evidence / 'pipeline.lock').is_file() and (evidence / 'orchestration.lock').is_file()
    assert not (root / 'pipeline.lock').exists()
    assert json.loads(pilot.read_text())['status'] == 'interrupted_owner_exited'


@pytest.mark.parametrize('bad', ['', '0\n0\n', '-1\n', 'failure\n'])
def test_invalid_wait_evidence_fails_closed(bad):
    with pytest.raises(ValueError):
        adopt.validate_wait_code(bad)


def test_running_owner_is_never_recovered():
    with pytest.raises(ValueError, match='still alive'):
        adopt.assert_pid_absent(os.getpid())


def test_changed_mount_rejected_before_modifying_run(fixture):
    root, run, inspect, log, code, pilot = fixture
    obj = json.loads(inspect.read_text())
    obj[0]['Mounts'][0]['RW'] = True
    inspect.write_text(json.dumps(obj))
    old_hash = adopt.digest(run)
    with pytest.raises(ValueError, match='mounts differ'):
        adopt.recover(run, inspect, log, code, old_hash)
    assert adopt.digest(run) == old_hash
    assert (root / 'pipeline.lock').exists()


def test_nonzero_container_exit_is_not_reported_as_success(fixture):
    root, run, inspect, log, code, pilot = fixture
    code.write_text('1\n')
    with pytest.raises(ValueError, match='execution failed'):
        adopt.recover(run, inspect, log, code, adopt.digest(run))
    record = json.loads(run.read_text())
    assert record['status'] == 'failed' and record['exit_code'] == 1


def test_changed_input_is_recorded_as_failure_not_success(fixture):
    root, run, inspect, log, code, pilot = fixture
    raw = root / 'bids/sub-998S9999/ses-20000101/func/rest.nii.gz'
    raw.write_bytes(b'changed')
    with pytest.raises(ValueError, match='input hashes changed'):
        adopt.recover(run, inspect, log, code, adopt.digest(run))
    record = json.loads(run.read_text())
    assert record['status'] == 'failed' and not record['input_unchanged']


def test_changed_original_record_is_not_overwritten(fixture):
    root, run, inspect, log, code, pilot = fixture
    old_hash = adopt.digest(run)
    run.write_text(run.read_text() + ' ')
    with pytest.raises(ValueError, match='record changed'):
        adopt.recover(run, inspect, log, code, old_hash)
    assert (root / 'pipeline.lock').exists()


def test_mismatched_orchestration_lock_is_not_moved(fixture):
    root, run, inspect, log, code, pilot = fixture
    (root / 'orchestration.lock').write_text('88888888')
    with pytest.raises(ValueError, match='lock identities'):
        adopt.recover(run, inspect, log, code, adopt.digest(run))
    assert (root / 'pipeline.lock').exists()
