"""Sessionwise entry for new fixed-seed runs. Existing run.py remains immutable."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'04_workflow'))
from seed_policy import session_backend

_backend = session_backend(__file__)


def __getattr__(name):
    return getattr(_backend, name)


def run_stage(*args, **kwargs):
    # Preserve the existing timing/logging/transport adapters used by local batches.
    for name in ('subprocess', 'dump'):
        if name in globals():
            setattr(_backend, name, globals()[name])
    return _backend.run_stage(*args, **kwargs)


def main(argv=None):
    return _backend.main(argv)


if __name__ == '__main__':
    main()
