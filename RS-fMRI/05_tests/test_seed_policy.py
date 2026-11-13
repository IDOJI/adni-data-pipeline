"""Seed propagation, frozen-run protection and real command-builder integration."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB/'04_workflow'))
import seed_policy as policy


def load(relative, name):
    return policy.load_backend(LAB/relative, name)


def arguments(stage):
    image = policy.MRIQC_IMAGE if stage == 'mriqc' else 'example@sha256:synthetic'
    args = ['docker', 'run', '--rm', '--env', 'OMP_NUM_THREADS=8', image,
            '/data', '/out', 'participant', '--omp-nthreads', '1', '--nprocs', '4']
    if stage != 'mriqc':
        args += ['--random-seed', '357']
    return args


@pytest.mark.parametrize('seed', [None, True, -1, 2**32, '357', 3.5])
def test_invalid_seed_fails_closed(seed):
    with pytest.raises(ValueError, match='integer'):
        policy.require({'seed_policy':policy.POLICY, 'random_seed':seed, 'resources':{'omp_nthreads':1}})


def test_new_run_examples_use_master_seed_1123():
    assert policy.DEFAULT_SEED == 1123
    for name in ('03_config/local_batch.example.json', '03_config/local_batch.seeded.example.json',
                 '03_config/xcpd_linc.example.json', '03_config/xcpd_linc.seeded.example.json',
                 'pipeline/s7a_volume_workflow/config.example.json',
                 'pipeline/s7a_volume_workflow/config.seeded.example.json'):
        cfg = json.loads((LAB / name).read_text())
        cfg = cfg.get('preprocessing_template', cfg)
        if isinstance(cfg, str):
            cfg = json.loads((LAB / cfg).read_text())
        assert cfg['random_seed'] == policy.DEFAULT_SEED, name


def test_fmriprep_skullstripping_and_thread_environment(tmp_path):
    base = arguments('fmriprep')
    command = policy.docker(base, 'fmriprep', 357, tmp_path/'fresh')
    assert '--skull-strip-fixed-seed' in command
    assert 'OMP_NUM_THREADS=8' not in command
    for value in ['ANTS_RANDOM_SEED=357', 'PYTHONHASHSEED=357', 'OMP_NUM_THREADS=1',
                  'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1', 'OPENBLAS_NUM_THREADS=1']:
        assert command.count(value) == 1
    assert command[command.index('--nprocs')+1] == '4'
    assert '--skull-strip-fixed-seed' not in base
    assert policy.docker(base, 'fmriprep', 357, tmp_path/'fresh') == command


def test_old_execution_seed_change_and_tampering_rejected(tmp_path):
    old = tmp_path/'old/logs/attempt/run.json'
    old.parent.mkdir(parents=True)
    old.write_text('{}')
    with pytest.raises(ValueError, match='Historical execution'):
        policy.docker(arguments('fmriprep'), 'fmriprep', 357, tmp_path/'old')
    policy.freeze(tmp_path/'new', 357)
    with pytest.raises(ValueError, match='Seed policy changed'):
        policy.freeze(tmp_path/'new', 358)
    code, _, _ = policy.freeze(tmp_path/'new', 357)
    (code/'mriqc_bootstrap.py').write_text('tampered')
    with pytest.raises(ValueError, match='Frozen seed'):
        policy.freeze(tmp_path/'new', 357)


def test_mriqc_adapter_has_no_unsupported_cli_option(tmp_path):
    cmd = policy.docker(arguments('mriqc'), 'mriqc', 357, tmp_path)
    assert '--random-seed' not in cmd
    assert cmd[cmd.index('--entrypoint')+1] == '/opt/adni-seed/mriqc_bootstrap.py'
    assert cmd[cmd.index('/data')-1] == policy.MRIQC_IMAGE
    code, _, _ = policy.freeze(tmp_path, 357)
    assert (code/'mriqc_bootstrap.py').stat().st_mode & 0o111
    assert any('dst=/opt/adni-seed,readonly' in item for item in cmd)
    bad = arguments('mriqc')
    bad[bad.index(policy.MRIQC_IMAGE)] = 'mriqc@sha256:unreviewed'
    with pytest.raises(ValueError, match='audited image'):
        policy.docker(bad, 'mriqc', 357, tmp_path)
    boot = load('04_workflow/seed_runtime/mriqc_bootstrap.py', 'seed_test_boot')
    with pytest.raises(ValueError, match='audited image'):
        boot.transform(b'not the reviewed source')


def session_config(root):
    return {'runtime':str(root), 'seed_policy':policy.POLICY, 'random_seed':357,
            'resources':{'cpus':4, 'omp_nthreads':1, 'workflow_memory_mb':6000, 'docker_memory':'8g'},
            'output_spaces':['MNI152NLin6Asym:res-2'], 'freesurfer_license':'/external/license.txt',
            'work_revision':'fixed-seed-v1'}


def test_session_wrapper_and_legacy_builder_stay_separate(tmp_path):
    seeded = load('pipeline/s7b_sessionwise_preprocessing/run_seeded.py', 'seed_test_session')
    legacy = load('pipeline/s7b_sessionwise_preprocessing/run.py', 'seed_test_legacy')
    cfg = session_config(tmp_path/'new')
    case = {'subject':'ADNI999S9999', 'session':'20000101'}
    seeded_cmd, _ = seeded.command(cfg, 'fmriprep', case, 'example@sha256:test')
    legacy_cmd, _ = legacy.command(cfg, 'fmriprep', case, 'example@sha256:test')
    assert '--skull-strip-fixed-seed' in seeded_cmd and '--skull-strip-fixed-seed' not in legacy_cmd
    assert Path(seeded._backend.__file__).name == 'run_seeded.py'
    assert '--random-seed' not in seeded.command(cfg, 'mriqc', case, policy.MRIQC_IMAGE)[0]
    cfg['resources']['omp_nthreads'] = 2
    with pytest.raises(ValueError, match='omp_nthreads'):
        seeded.command(cfg, 'fmriprep', case, 'example@sha256:test')


def test_batch_rebinds_only_unexecuted_routes_and_selects_seeded_postprocessing(tmp_path):
    batch = load('04_workflow/local_batch_seeded.py', 'seed_test_batch')
    root = tmp_path/'batch'
    (root/'config').mkdir(parents=True)
    (root/'control').mkdir()
    registry = {'subjects':{'ADNI999S9999':{'runtime':str(root/'case'), 'backend':'old', 'backend_sha256':'old'}}}
    batch.base.save(root/'config/continuation.json', registry)
    batch.base.save(root/'control/manifest.json', {'registry_sha256':'old'})
    batch.bind_prepared_routes(root)
    new = batch.base.read(root/'config/continuation.json')
    assert new['subjects']['ADNI999S9999']['backend'].endswith('/run_seeded.py')
    assert batch.base.read(root/'control/manifest.json')['registry_sha256'] == batch.base.sha(root/'config/continuation.json')
    post = batch.module('test_post', 'pipeline/s10_xcpd_integrated_qc/pipeline.py')
    assert Path(post.__file__).name == 'pipeline_seeded.py'
    log = root/'case/logs/old/run.json'
    log.parent.mkdir(parents=True)
    log.write_text('{}')
    with pytest.raises(ValueError, match='previously executed'):
        batch.bind_prepared_routes(root)


def test_r_wrapper_requires_isotree_seed_support_and_new_output(tmp_path):
    r = load('04_workflow/iqm_seeded.py', 'seed_test_r')
    cmd = r.command('/external/config.yaml', tmp_path/'new')
    expression = cmd[cmd.index('-e')+1]
    assert 'set.seed(1123)' in expression and 'iso_seed' in expression
    assert 'compat.R' not in expression
    (tmp_path/'existing').mkdir()
    (tmp_path/'existing/result.tsv').write_text('preserve')
    with pytest.raises(ValueError, match='new output'):
        r.command('/external/config.yaml', tmp_path/'existing')


def test_actual_session_receipt_cache_and_transport_include_seed_controls(tmp_path, monkeypatch):
    from types import SimpleNamespace
    seeded = load('pipeline/s7b_sessionwise_preprocessing/run_seeded.py', 'seed_receipt_session')
    cfg = session_config(tmp_path/'run')
    case = {'subject':'ADNI999S9999', 'session':'20000101'}
    intake = Path(cfg['runtime'])/'results/step5/intake_decisions.tsv'
    intake.parent.mkdir(parents=True)
    intake.write_text('sub\tses\tstrict_upstream_eligible\nsub-ADNI999S9999\tses-20000101\tTrue\n')
    base = seeded._backend
    monkeypatch.setattr(base, 'image_record', lambda image: {'resolved':image})
    monkeypatch.setattr(base, 'selected_inputs', lambda *a: {'synthetic':'fixed'})
    monkeypatch.setattr(base, 'inspect_protocol', lambda *a: {'upstream_commit':'synthetic'})
    monkeypatch.setattr(base, 'add_timing', lambda *a: None)
    monkeypatch.setattr(base, 'refresh_safely', lambda *a: None)
    cfg['images'] = {'fmriprep':'example@sha256:synthetic'}
    commands = []
    seeded.subprocess = SimpleNamespace(STDOUT=-2, run=lambda argv, **kw: (commands.append(argv) or SimpleNamespace(returncode=0)))
    seeded.dump = base.dump
    seeded.run_stage(cfg, 'fmriprep', case, 'strict')
    records = list(Path(cfg['runtime']).glob('logs/*/run.json'))
    assert len(records) == 1 and len(commands) == 1
    record = json.loads(records[0].read_text())
    assert record['runner_sha256'] == policy.sha(seeded.__file__)
    assert '--skull-strip-fixed-seed' in record['command'] == commands[0]
    signatures = list(Path(cfg['runtime']).glob('work/**/.cache-signature.json'))
    assert json.loads(signatures[0].read_text())['command'] == commands[0]
    before = signatures[0].read_bytes()
    cfg['random_seed'] = 358
    with pytest.raises(ValueError, match='Seed policy changed'):
        seeded.run_stage(cfg, 'fmriprep', case, 'strict')
    assert len(commands) == 1 and signatures[0].read_bytes() == before


def test_volume_and_xcpd_real_builders_propagate_fixed_seed(tmp_path):
    volume = load('pipeline/s7a_volume_workflow/pipeline_seeded.py', 'seed_volume')
    cfg = json.loads((LAB/'pipeline/s7a_volume_workflow/config.seeded.example.json').read_text())
    cfg['paths'] = {key:str(tmp_path/key) for key in volume.PATH_KEYS}
    cfg['fs_license'] = str(tmp_path/'license.txt')
    cfg['random_seed'] = 357
    run = {'subject':'999S9999', 'session':'M000'}
    config_path = tmp_path/'volume.json'
    config_path.write_text(json.dumps(cfg))
    cfg = volume.read_config(config_path)
    # The original executor writes a preparing receipt before building its command.
    preparing = Path(cfg['paths']['logs'])/'first/run.json'
    preparing.parent.mkdir()
    preparing.write_text('{"status":"preparing"}')
    args = volume.build_command(cfg, 'fmriprep', run)
    assert '--skull-strip-fixed-seed' in args and 'ANTS_RANDOM_SEED=357' in args
    args = volume.build_command(cfg, 'xcpd', run, 'example@sha256:synthetic')
    assert '--skull-strip-fixed-seed' not in args and 'PYTHONHASHSEED=357' in args
    post = load('pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py', 'seed_xcpd')
    cfg = json.loads((LAB/'03_config/xcpd_linc.seeded.example.json').read_text())
    cfg.update(random_seed=357, root=str(tmp_path/'post'), _config_id='synthetic', license='/external/license.txt', templateflow='/external/templateflow')
    row = {'sub':'sub-ADNI999S9999', 'ses':'ses-M000', 'task':'task-rest', 'source_pair':str(tmp_path/'pair')}
    args = post.command(cfg, row, tmp_path/'attempt', 'synthetic')
    assert args[args.index('--random-seed')+1] == '357'
    assert args[args.index('--omp-nthreads')+1] == '1'
    assert 'ANTS_RANDOM_SEED=357' in args


def test_volume_refuses_historical_log_root_before_initializing_policy(tmp_path):
    volume = load('pipeline/s7a_volume_workflow/pipeline_seeded.py', 'seed_old_volume')
    cfg = json.loads((LAB/'pipeline/s7a_volume_workflow/config.seeded.example.json').read_text())
    cfg['paths'] = {key:str(tmp_path/key) for key in volume.PATH_KEYS}
    cfg['fs_license'] = str(tmp_path/'license.txt')
    cfg['random_seed'] = 357
    old = Path(cfg['paths']['logs'])/'old/run.json'
    old.parent.mkdir(parents=True)
    old.write_text('{}')
    path = tmp_path/'config.json'
    path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match='Historical execution'):
        volume.read_config(path)
    assert not (old.parent.parent/'seed_policy').exists()


def test_guarded_entry_preserves_gates_and_selects_seeded_backend(tmp_path):
    gate = load('pipeline/s5d_bids_identity/guarded_runner_seeded.py', 'seed_guard')
    assert Path(gate.backend().__file__).name == 'run_seeded.py'
    template = tmp_path/'template.yaml'
    template.write_text('random_seed: 357\nresources:\n  omp_nthreads: 1\n')
    with pytest.raises(ValueError, match='seed_policy'):
        gate.prepare(tmp_path/'missing-receipt', 'synthetic', tmp_path/'runtime', template)
    assert not (tmp_path/'runtime').exists()
