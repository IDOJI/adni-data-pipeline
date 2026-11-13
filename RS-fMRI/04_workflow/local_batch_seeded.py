"""New fixed-seed batches; original live batch source and registries stay frozen."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seed_policy

base = seed_policy.load_backend(Path(__file__).with_name('local_batch.py'), 'seeded_local_batch')
original_module, original_prepare, original_config = base.module, base.prepare, base.config


def config(path):
    cfg = original_config(path)
    seed = seed_policy.require(cfg['preprocessing_template'])
    if cfg['xcpd_resources']['omp_nthreads'] != 1:
        raise ValueError('Seeded XCP-D requires omp_nthreads: 1')
    template = {**base.read(cfg['xcpd_template']), 'resources':cfg['xcpd_resources'], **cfg.get('reference_xcpd', {})}
    if seed_policy.require(template) != seed:
        raise ValueError('Preprocessing and XCP-D must share the configured seed')
    return cfg


def module(name, relative):
    if relative == '02_custom/s5d_bids_identity/guarded_runner.py':
        relative = '02_custom/s5d_bids_identity/guarded_runner_seeded.py'
    if relative == '02_custom/s10_xcpd_integrated_qc/pipeline.py':
        relative = '02_custom/s10_xcpd_integrated_qc/pipeline_seeded.py'
    return original_module(name, relative)


def bind_prepared_routes(root):
    """Rebind only freshly prepared, never executed routes before first dispatch."""
    root = Path(root)
    registry_path = root/'config/continuation.json'
    registry = base.read(registry_path)
    for route in registry['subjects'].values():
        if list(Path(route['runtime']).glob('logs/**/run.json')):
            raise ValueError('Cannot rebind a previously executed route')
        backend = base.LAB/'02_custom/s7b_sessionwise_preprocessing/run_seeded.py'
        route.update(backend=str(backend), backend_sha256=base.sha(backend))
    base.save(registry_path, registry)
    manifest_path = root/'control/manifest.json'
    manifest = base.read(manifest_path)
    manifest['registry_sha256'] = base.sha(registry_path)
    manifest['seed_policy'] = seed_policy.identity()
    base.save(manifest_path, manifest)


def prepare(path):
    cfg = config(path)
    result = original_prepare(path)
    bind_prepared_routes(cfg['root'])
    return result


base.config, base.module, base.prepare = config, module, prepare


def __getattr__(name):
    return getattr(base, name)


if __name__ == '__main__':
    base.main()
