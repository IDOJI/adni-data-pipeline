"""Create local links for the earlier RS-fMRI command paths."""
import json
import os
from pathlib import Path
import sys


def setup(root: Path) -> int:
    config = root / 'support/config'
    links = json.loads((config / 'legacy-paths.json').read_text())
    stages = json.loads((config / 'stage-paths.json').read_text())
    links.update({f'support/pipeline/{old}': new for old, new in stages.items()})

    pending = []
    for legacy, current in links.items():
        link, target = root / legacy, root / current
        if (link.parent.resolve() != link.parent or not link.parent.is_relative_to(root)
                or target.resolve() != target or not target.is_relative_to(root) or not target.exists()):
            raise ValueError(f'Invalid compatibility path: {legacy} → {current}')
        if link.is_symlink() and link.resolve() == target:
            continue
        if link.exists() or link.is_symlink():
            raise ValueError(f'Move the existing path before setting up compatibility: {link}')
        pending.append((link, target))

    for link, target in pending:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(os.path.relpath(target, link.parent))
    return len(pending)


if __name__ == '__main__':
    try:
        count = setup(Path(__file__).resolve().parents[1])
    except (OSError, ValueError) as error:
        sys.exit(f'RS-fMRI setup: {error}')
    print(f'RS-fMRI command paths ready ({count} links created).')
