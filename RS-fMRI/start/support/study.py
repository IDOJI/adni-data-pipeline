"""Shared file layout and command handling for the four study scripts."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

LAB = Path(__file__).resolve().parents[2]
PIPELINE = LAB / 'pipeline'
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(LAB / '04_workflow'))


def parser(description, actions=()):
    cli = argparse.ArgumentParser(description=description)
    cli.add_argument('study', type=Path, help='Your private study folder')
    if actions:
        cli.add_argument('action', choices=actions)
    return cli


def run(cli, entry):
    args = cli.parse_args()
    root = args.study.expanduser().resolve()
    if not root.is_dir() or root.is_relative_to(LAB.parent) or LAB.parent.is_relative_to(root):
        cli.error('Choose an existing study folder outside the code repository.')
    args.study = root
    try:
        entry(args)
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        cli.exit(1, f'Stopped: {exc}\n')


@contextmanager
def stage_folder(study, name):
    folder = study / name
    folder.mkdir(mode=0o700, exist_ok=True)
    with (folder / '.running.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f'Another command is running in {folder}') from exc
        yield folder


def fixed_text(path, content):
    """Install an entire settings file once. A retry must supply the same content."""
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(content)
            f.flush()
            try:
                os.link(temp, path)
            except FileExistsError:
                if path.read_text() != content:
                    raise ValueError(f'Inputs differ from {path}. Use a fresh output or study folder.')
        finally:
            temp.unlink()
    return path


def settings(path, values):
    return fixed_text(path, json.dumps(values, indent=2, sort_keys=True, default=str) + '\n')


def template(name):
    return json.loads((LAB / '03_config' / name).read_text())


def existing(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Missing input file: {path}')
    return path


def selection_receipt(study, override=None):
    from s5d_bids_identity.binding import proof_files
    path = existing(override or study / '01-selection/images/07.run-manifest.json')
    return path, proof_files(path)


def finalized_master(study, override=None):
    from _shared import sha
    if override:
        path = existing(override)
    else:
        receipt = json.loads(existing(study / '03-imaging/finalization.json').read_text())
        path = existing(receipt['final_qc'])
        if sha(path) != receipt['sha256']:
            raise ValueError(f'Final QC master changed: {path}')
    summary = json.loads(existing(path.with_name('summary.json')).read_text())
    if (path.name != 'final_qc_master.tsv'
            or summary.get('cohort_finalization_deferred') is not False):
        raise ValueError('Choose a cohort-finalized final_qc_master.tsv.')
    return path
