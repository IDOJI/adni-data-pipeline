"""Docker XCP-D entry for new fixed-seed configurations, never historical workers."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'04_workflow'))
from seed_policy import xcpd_backend

_backend = xcpd_backend(__file__)


def __getattr__(name):
    return getattr(_backend, name)


if __name__ == '__main__':
    if 'slurm' in sys.argv:
        raise SystemExit('Use the documented seeded Docker profile; historical Slurm exports are unchanged.')
    _backend.main()
