"""Keep the exact-pair gates and use fixed seeds only in a newly prepared runtime."""
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'04_workflow'))
import seed_policy

base = seed_policy.load_backend(Path(__file__).with_name('guarded_runner.py'), 'seeded_pair_gate')
original_prepare, original_dispatch = base.prepare, base.dispatch


def backend():
    return seed_policy.load_backend(Path(__file__).resolve().parents[1]/'s7b_sessionwise_preprocessing/run_seeded.py',
                                    'guarded_seeded_session')


def prepare(receipt, epi_key, runtime, template):
    seed_policy.require(yaml.safe_load(Path(template).read_text()))
    return original_prepare(receipt, epi_key, runtime, template)


def dispatch(config, action, stage=None):
    seed_policy.require(yaml.safe_load(Path(config).read_text()))
    return original_dispatch(config, action, stage)


base.backend, base.prepare, base.dispatch = backend, prepare, dispatch


def __getattr__(name):
    return getattr(base, name)


if __name__ == '__main__':
    base.main()
