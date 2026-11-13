"""Volume-profile entry for new fixed-seed runs; preserve legacy source/cache IDs."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'04_workflow'))
from seed_policy import volume_backend

_backend = volume_backend(__file__)


def __getattr__(name):
    return getattr(_backend, name)


if __name__ == '__main__':
    _backend.main()
