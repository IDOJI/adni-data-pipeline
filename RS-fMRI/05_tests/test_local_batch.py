"""Safety checks for local unattended handoff execution, without Docker/data."""
import importlib.util
from pathlib import Path
import json

import pytest

P = Path(__file__).resolve().parents[1] / '04_workflow/local_batch.py'
spec = importlib.util.spec_from_file_location('local_batch_test', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_shared_window_and_disk_reserve():
    cases = [{'subject': f'ADNI001S{i:04}'} for i in range(10)]
    states = {x['subject']: {'status': 'pending'} for x in cases}
    external = {'ADNI002S0001', 'ADNI002S0002'}
    assert len(m.select_pending(cases, states, {}, 200, external)) == 3
    assert len(m.select_pending(cases, states, {}, 43, set())) == 1
    assert not m.select_pending(cases, states, {}, 31, set())
    busy = {cases[0]['subject']: object()}
    assert len(m.select_pending(cases, states, busy, 200, set(busy))) == 4


def test_success_and_source_review_hold_are_not_readmitted():
    cases = [{'subject': 'ADNI001S0001'}, {'subject': 'ADNI001S0002'}, {'subject': 'ADNI001S0003'}]
    states = {'ADNI001S0001': {'status': 'completed_QC_pending'},
              'ADNI001S0002': {'status': 'held_source_review'},
              'ADNI001S0003': {'status': 'pending'}}
    assert m.select_pending(cases, states, {}, 200, set()) == ['ADNI001S0003']


def test_download_scope_rejects_path_escape_and_symlink(tmp_path):
    root = tmp_path / 'input'
    root.mkdir()
    raw = tmp_path / 'outside.nii.gz'
    raw.write_bytes(b'original')
    (root / 'link').symlink_to(raw)
    for relative in ['../outside.nii.gz', str(raw), 'link']:
        with pytest.raises(ValueError):
            m.checked_member(root, relative)


def test_bids_sidecar_only_adds_task_name():
    raw = {'SeriesInstanceUID': '1.2.3', 'RepetitionTime': 3, 'SliceTiming': [0, 1.5], 'PhaseEncodingDirection': 'j-'}
    converted = m.normalize_sidecar(raw, 'EPI')
    assert converted == {**raw, 'TaskName': 'rest'}
    assert 'TaskName' not in raw
    assert m.normalize_sidecar(raw, 'T1') == raw
    with pytest.raises(ValueError):
        m.normalize_sidecar({**raw, 'TaskName': 'other'}, 'EPI')


def test_effective_transport_preserves_scientific_options():
    base = ['docker', 'run', '--rm', '--name', 'statmind-fmriprep-ADNI001S0001-20000101',
            '--cpus', '4', '--memory', '16g', 'nipreps/fmriprep@sha256:fixed',
            '/data', '/out', 'participant', '--nprocs', '4', '--omp-nthreads', '2',
            '--force', 'syn-sdc', '--cifti-output', '91k', '--random-seed', '357']
    actual = m.effective_command(base, 1.5)
    assert actual[actual.index('/data') - 1:] == base[base.index('/data') - 1:]
    assert actual[actual.index('--memory') + 1] == '16g'
    assert actual[actual.index('--cpus') + 1] == '1.5'
    assert '--rm' not in actual
    assert '--rm' in base


def test_changed_source_holds_before_dispatch(tmp_path):
    file = tmp_path / 'backend.py'
    file.write_text('original')
    (tmp_path / 'config').mkdir()
    m.save(tmp_path / 'config/source-lock.json', {str(file): m.sha(file)})
    batch = object.__new__(m.Batch)
    batch.root = tmp_path
    batch.check_sources()
    file.write_text('changed')
    with pytest.raises(ValueError, match='Pinned pipeline source changed'):
        batch.check_sources()


def test_changed_handoff_payload_blocks_before_runtime_creation(tmp_path):
    root = tmp_path / 'handoff'
    (root / '_handoff').mkdir(parents=True)
    (root / '_handoff/participants.tsv').write_text('ptid\n001_S_0001\n')
    files = []
    for i in range(4):
        p = root / f'raw{i}'
        p.write_bytes(b'raw')
        files.append({'relative_path': p.name, 'bytes': 3, 'sha256': m.sha(p)})
    m.save(root / '_handoff/batch_manifest.json', {'participant_count': 1, 'participants': [
        {'ptid': '001_S_0001', 'subject': 'ADNI001S0001', 'files': files}]})
    assert len(m.validate_handoff(root)[1]) == 4
    (root / 'raw2').write_bytes(b'bad')
    with pytest.raises(ValueError, match='size/hash mismatch'):
        m.validate_handoff(root)


def test_recovery_requires_persistent_exact_container_evidence(tmp_path, monkeypatch):
    folder = tmp_path / 'attempt'
    folder.mkdir()
    m.save(folder / 'local_execution.json', {'effective_docker_argv': [
        'docker', 'run', '--name', 'expected', 'image@sha256:fixed', '/data', '/out']})
    class Result:
        returncode = 0
        stdout = json.dumps([{'Config': {'Cmd': ['/wrong'], 'Image': 'image@sha256:fixed'}}])
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: Result())
    batch = object.__new__(m.Batch)
    with pytest.raises(ValueError, match='exact recorded command'):
        batch.recover_stage({}, {}, {}, None, 'fmriprep', folder / 'run.json', {})


def test_restart_recovers_five_own_containers_without_sixth_admission():
    cases = [{'subject': f'ADNI001S{i:04}'} for i in range(6)]
    states = {x['subject']: {'status': 'mriqc_running'} for x in cases}
    active = {x['subject'] for x in cases[:5]}
    assert set(m.select_pending(cases, states, {}, 10, active)) == active
