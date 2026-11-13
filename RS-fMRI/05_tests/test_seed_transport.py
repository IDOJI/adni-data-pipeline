"""Exercise seeded launchers through actual logging, batch and recovery adapters."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB/'04_workflow'))
import seed_policy


def load(relative, name):
    return seed_policy.load_backend(LAB/relative, name)


@pytest.mark.parametrize('stage', ['mriqc', 'fmriprep'])
@pytest.mark.parametrize('entry', ['run_stage', 'main'])
def test_real_session_logging_batch_transport_and_recovery(tmp_path, monkeypatch, stage, entry):
    session = load('02_custom/s7b_sessionwise_preprocessing/run_seeded.py', 'seed_transport_session')
    batch = load('04_workflow/local_batch_seeded.py', 'seed_transport_batch')
    logging = batch.module('logging', '02_custom/s7c_ants_iteration_logging/run.py')
    root = tmp_path/'runtime'
    case = {'subject':'ADNI999S9999', 'session':'20000101'}
    image = seed_policy.MRIQC_IMAGE if stage == 'mriqc' else 'example@sha256:synthetic'
    cfg = {'runtime':str(root), 'source_bids':str(tmp_path/'source'),
           'seed_policy':seed_policy.POLICY, 'random_seed':357, 'runs':[case],
           'resources':{'cpus':2, 'omp_nthreads':1, 'workflow_memory_mb':4000, 'docker_memory':'8g'},
           'images':{stage:image}, 'output_spaces':['MNI152NLin6Asym:res-2'],
           'freesurfer_license':'/external/license.txt', 'work_revision':'fixed-seed-v1'}
    intake = root/'results/step5/intake_decisions.tsv'
    intake.parent.mkdir(parents=True)
    intake.write_text('sub\tses\tstrict_upstream_eligible\nsub-ADNI999S9999\tses-20000101\tTrue\n')
    cp = tmp_path/'config.yaml'
    cp.write_text(yaml.safe_dump(cfg))
    backend = session._backend
    monkeypatch.setattr(backend, 'image_record', lambda value: {'resolved':value})
    monkeypatch.setattr(backend, 'selected_inputs', lambda *a: {'synthetic':'fixed'})
    monkeypatch.setattr(backend, 'inspect_protocol', lambda *a: {'upstream_commit':'synthetic'})
    monkeypatch.setattr(backend, 'add_timing', lambda *a: None)
    monkeypatch.setattr(backend, 'refresh_safely', lambda *a: None)
    image_queries = []

    def inspect_image(argv, **kwargs):
        image_queries.append(argv)
        assert argv == ['docker', 'image', 'inspect', image]
        return json.dumps([{'Config':{'Env':['PATH=/opt/conda/bin:/usr/bin']}}])

    monkeypatch.setattr(logging.subprocess, 'check_output', inspect_image)
    launched = []
    fake_process = SimpleNamespace(STDOUT=-2, run=lambda argv, **kw:
                                   (launched.append(argv) or SimpleNamespace(returncode=0)))
    monkeypatch.setattr(batch.base, 'subprocess', fake_process)
    session.subprocess = batch.LocalTransport(logging, 1.5)
    if entry == 'main':
        session.main(['--config',str(cp),'run','--stage',stage,'--subject',case['subject']])
    else:
        session.run_stage(cfg, stage, case, 'strict')
    assert len(launched) == len(image_queries) == 1
    actual = launched[0]
    index = actual.index('/data')-1
    assert actual[index] == image
    assert actual[actual.index('--cpus')+1] == '1.5' and '--rm' not in actual[:index]
    assert 'ANTS_RANDOM_SEED=357' in actual and 'OMP_NUM_THREADS=1' in actual
    if stage == 'mriqc':
        assert actual[actual.index('--entrypoint')+1] == '/opt/adni-seed/mriqc_bootstrap.py'
        assert '--random-seed' not in actual
    else:
        assert '--skull-strip-fixed-seed' in actual and actual[-1] == '--skull-strip-fixed-seed'
    record_path = next(root.glob('logs/*/run.json'))
    record = json.loads(record_path.read_text())
    folder = record_path.parent
    proof = json.loads((folder/'local_execution.json').read_text())
    logging_proof = json.loads((folder/'ants_logging.json').read_text())
    assert proof['base_docker_argv'] == record['command'] == logging_proof['base_docker_argv']
    assert proof['effective_docker_argv'] == actual
    assert logging_proof['image'] == image
    cache = next(root.glob('work/**/.cache-signature.json'))
    before = cache.read_bytes()
    assert json.loads(before)['command'] == record['command']

    # Re-enter the production recovery path with this exact retained container.
    mounts = []
    for i, arg in enumerate(actual[:index]):
        if arg == '--mount':
            fields = actual[i+1].split(',')
            values = dict(x.split('=',1) for x in fields if '=' in x)
            mounts.append({'Source':values['src'], 'Destination':values['dst'], 'RW':'readonly' not in fields})
    info = {'Id':'synthetic-container', 'Config':{'Image':image, 'Cmd':actual[index+1:]},
            'Mounts':mounts, 'State':{'Running':False, 'ExitCode':0, 'FinishedAt':'2000-01-01T00:00:00Z'}}
    recovered = []

    def run(argv, **kwargs):
        recovered.append(argv)
        if argv[:2] == ['docker','inspect']:
            return SimpleNamespace(returncode=0, stdout=json.dumps([info]))
        assert argv[:2] == ['docker','logs']
        return SimpleNamespace(returncode=0)

    fake_process.run = run
    owner = object.__new__(batch.Batch)
    owner.update = lambda *a, **kw: None
    owner.recover_stage({}, cfg, case, session, stage, record_path, record)
    assert [x[:2] for x in recovered] == [['docker','inspect'], ['docker','logs']]
    assert json.loads(record_path.read_text())['controller_recovery']['container_id'] == 'synthetic-container'
    assert cache.read_bytes() == before


def test_logging_cli_transports_reach_the_seeded_backend(tmp_path, monkeypatch):
    session = load('02_custom/s7b_sessionwise_preprocessing/run_seeded.py', 'seed_cli_adapter')
    logging = load('02_custom/s7c_ants_iteration_logging/run.py', 'seed_cli_logging')
    calls = []
    original = SimpleNamespace(run=lambda argv, **kw:calls.append(argv))
    session.subprocess = logging.Transport(original)
    monkeypatch.setattr(session._backend, 'main', lambda argv:session._backend.subprocess.run(['synthetic']))
    session.main([])
    assert calls == [['synthetic']]


def test_r_paths_and_interpreter_survive_working_directory_change(tmp_path, monkeypatch):
    iqm = load('04_workflow/iqm_seeded.py', 'seed_r_environment')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PATH', '/system/bin')
    monkeypatch.setenv('R_LIBS_USER', '/external/user-r-library')
    argv = iqm.command('config.yaml', 'new-results')
    assert argv[argv.index('--config')+1] == str(tmp_path/'config.yaml')
    assert argv[argv.index('--out-dir')+1] == str(tmp_path/'new-results')
    env = iqm.environment()
    assert env['PATH'].split(os.pathsep)[0] == str(Path(sys.executable).parent)
    assert env['R_LIBS_USER'].split(os.pathsep)[-1] == '/external/user-r-library'
