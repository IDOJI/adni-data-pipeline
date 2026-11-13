"""Opt-in fixed seeds for new runs; never alter a frozen live runner or cache."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

POLICY = 'fixed-seed-v1'
DEFAULT_SEED = 1123
HERE = Path(__file__).resolve().parent
MRIQC_IMAGE = 'nipreps/mriqc@sha256:dabe930dd0d1180c565a42f2c6a34f2b23026d9642db5d110f05b427413b829f'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(cfg, resources='resources'):
    if cfg.get('seed_policy') != POLICY:
        raise ValueError('Use a new configuration with seed_policy: ' + POLICY)
    seed = cfg.get('random_seed')
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('random_seed must be an integer in [0, 2**32)')
    threads = cfg if resources is None else cfg[resources]
    if type(threads.get('omp_nthreads')) is not int or threads['omp_nthreads'] != 1:
        raise ValueError('The fixed-seed profile requires omp_nthreads: 1')
    return seed


def runtime_files():
    return [HERE/'seed_policy.py', *sorted((HERE/'seed_runtime').glob('*.py'))]


def identity():
    files = {p.name: sha(p) for p in runtime_files()}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'policy': POLICY, 'implementation_sha256': digest, 'files': files}


def freeze(root, seed):
    """Persist policy identity and immutable bootstrap code outside work caches."""
    root = Path(root).resolve()
    lab = HERE.parent.resolve()
    if root == Path('/') or root == lab.parent or root.is_relative_to(lab.parent) or lab.parent.is_relative_to(root):
        raise ValueError('Use an external runtime for seeded execution')
    marker = root/'seed_policy/policy.json'
    contract = {**identity(), 'random_seed': seed, 'omp_nthreads': 1}
    if marker.exists():
        if json.loads(marker.read_text()) != contract:
            raise ValueError('Seed policy changed; retain this runtime and use a new root')
    else:
        # Preparing BIDS/intake is allowed. Existing calculations are never adopted.
        old = list(root.glob('logs/**/run.json')) + list(root.glob('logs/*_execution.json'))
        old += list(root.glob('*/run.json'))  # 7.A stores policy under its logs root.
        old += list(root.glob('postprocessing/*/configuration.json'))
        old += list(root.glob('work/**/.cache-signature.json'))
        if old:
            raise ValueError('Historical execution exists; use a new runtime for fixed seeds')
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open('x') as stream:
            json.dump(contract, stream, indent=2)
            stream.write('\n')
    code = marker.parent/'code'/contract['implementation_sha256']
    code.mkdir(parents=True, exist_ok=True)
    for source in runtime_files():
        dest = code/source.name
        if dest.exists():
            if sha(dest) != sha(source):
                raise ValueError('Frozen seed implementation changed')
            if source.name == 'mriqc_bootstrap.py' and not os.access(dest, os.X_OK):
                raise ValueError('Frozen MRIQC entrypoint is not executable')
        else:
            with dest.open('xb') as stream:
                stream.write(source.read_bytes())
            if source.name == 'mriqc_bootstrap.py':
                dest.chmod(0o755)
    records = marker.parent/'records'
    records.mkdir(exist_ok=True)
    return code, records, contract


def docker(argv, stage, seed, root, sources=()):
    """Add supported seed controls before execution; argv is the cache identity."""
    if stage not in ('mriqc', 'fmriprep', 'xcpd'):
        raise ValueError('Unknown seeded stage')
    argv = [str(x) for x in argv]
    if argv[:2] not in (['docker', 'run'], ['docker', 'create']):
        raise ValueError('The seeded local profile requires Docker')
    positions = [i for i, value in enumerate(argv) if '@sha256:' in value and not value.startswith(('type=', '/'))]
    if len(positions) != 1:
        raise ValueError('Exactly one immutable image digest is required')
    at = positions[0]
    if stage == 'mriqc' and argv[at] != MRIQC_IMAGE:
        raise ValueError('MRIQC seed adapter only supports the audited image digest')
    options, application = argv[:at], argv[at:]
    if '--omp-nthreads' not in application or application[application.index('--omp-nthreads')+1] != '1':
        raise ValueError('The actual command must use --omp-nthreads 1')
    if stage != 'mriqc':
        if '--random-seed' not in application or application[application.index('--random-seed')+1] != str(seed):
            raise ValueError('Command seed differs from the fixed-seed configuration')
    code, records, contract = freeze(root, seed)
    evidence = {str(Path(p).relative_to(HERE.parent)): sha(p) for p in sources}
    source_hash = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    for source in sources:
        source = Path(source)
        snapshot = records.parent/'runner_sources'/source_hash/source.relative_to(HERE.parent)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if snapshot.exists():
            if sha(snapshot) != sha(source):
                raise ValueError('Frozen runner source changed')
        else:
            with snapshot.open('xb') as stream:
                stream.write(source.read_bytes())
    env = {'ANTS_RANDOM_SEED': str(seed), 'PYTHONHASHSEED': str(seed),
           'ADNI_RANDOM_SEED': str(seed), 'ADNI_SEED_POLICY': POLICY,
           'ADNI_SEED_IMPLEMENTATION': contract['implementation_sha256'],
           'ADNI_SEEDED_RUNNER_SHA256': source_hash,
           'OMP_NUM_THREADS': '1', 'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1',
           'PYTHONDONTWRITEBYTECODE': '1'}
    cleaned = []
    i = 0
    while i < len(options):
        value = options[i]
        if value in ('-e', '--env'):
            setting = options[i+1]
            if setting.split('=', 1)[0] in env:
                i += 2
                continue
        cleaned.append(value)
        i += 1
    for key, value in env.items():
        cleaned += ['--env', key+'='+value]
    if stage == 'mriqc':
        if '--entrypoint' in cleaned or '--random-seed' in application:
            raise ValueError('MRIQC uses the version-checked bootstrap, not a nonexistent seed CLI flag')
        for source, dest, mode in [(code, '/opt/adni-seed', ',readonly'),
                                   (records, '/adni-seed-records', '')]:
            if ',' in str(source):
                raise ValueError('Docker bind paths cannot contain commas')
            cleaned += ['--mount', f'type=bind,src={source},dst={dest}{mode}']
        # Keep image immediately before /data: existing logging, local transport
        # and recovery parse that stable application boundary.
        cleaned += ['--env', 'PYTHONPATH=/opt/adni-seed',
                    '--entrypoint', '/opt/adni-seed/mriqc_bootstrap.py']
    if stage == 'fmriprep' and '--skull-strip-fixed-seed' not in application:
        application += ['--skull-strip-fixed-seed']
    receipt = records/(stage+'-'+source_hash+'.json')
    value = {'policy': contract, 'stage': stage, 'runner_sources': evidence,
             'effective_command': cleaned+application, 'scope': 'Command preparation, not completed imaging'}
    if not receipt.exists():
        with receipt.open('x') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    return cleaned+application


def load_backend(path, name):
    path = Path(path)
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def session_backend(entry):
    entry = Path(entry).resolve()
    base = load_backend(entry.with_name('run.py'), 'seeded_session_backend')
    command, load = base.command, base.load
    base.__file__ = str(entry)

    def seeded_command(cfg, stage, case, image):
        seed = require(cfg)
        argv, work = command(cfg, stage, case, image)
        return docker(argv, stage, seed, cfg['runtime'], [entry, entry.with_name('run.py')]), work

    def seeded_load(path):
        cfg = load(path)
        require(cfg)
        return cfg

    base.command, base.load = seeded_command, seeded_load
    return base


def volume_backend(entry):
    entry = Path(entry).resolve()
    base = load_backend(entry.with_name('pipeline.py'), 'seeded_volume_backend')
    build, read = base.build_command, base.read_config

    def seeded_build(cfg, stage, run, image=None):
        seed = require(cfg, None)
        return docker(build(cfg, stage, run, image), stage, seed, cfg['paths']['logs'],
                      [entry, entry.with_name('pipeline.py')])

    def seeded_read(path):
        cfg = read(path)
        seed = require(cfg, None)
        # Freeze before the original executor creates its first preparing receipt.
        freeze(cfg['paths']['logs'], seed)
        return cfg

    base.build_command, base.read_config = seeded_build, seeded_read
    return base


def xcpd_backend(entry):
    entry = Path(entry).resolve()
    base = load_backend(entry.with_name('pipeline.py'), 'seeded_xcpd_backend')
    command, original_init = base.command, base.Pipeline.__init__

    def seeded_init(self, config_path):
        cfg = base.load(config_path)
        seed = require(cfg)
        freeze(cfg['root'], seed)
        original_init(self, config_path)

    def seeded_command(cfg, row, attempt, name, create=True):
        return docker(command(cfg, row, attempt, name, create), 'xcpd', require(cfg), cfg['root'],
                      [entry, entry.with_name('pipeline.py')])

    base.Pipeline.__init__, base.command = seeded_init, seeded_command
    return base
