"""Identify repository-owned protocol sources without an upstream Git checkout.

The import manifest records origin, not a permanent ban on editing the code.
Reviewed source changes become the ordinary parent-repository Git baseline.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


def _git(repository, *args):
    return subprocess.check_output(['git', '-C', str(repository), *args])


def inspect_protocol(root=None, *, require_clean=True):
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    repository = root.parent
    origin = json.loads((root / '03_config/upstream.lock.json').read_text())
    if origin.get('distribution') != 'integrated-source':
        raise ValueError('Expected the integrated protocol source distribution')
    relative = Path(origin['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Protocol source path must remain inside RS-fMRI')
    protocol = root / relative
    if protocol.is_symlink() or not protocol.is_dir():
        raise ValueError('Integrated protocol source directory is missing or redirected')
    prefix = protocol.relative_to(repository).as_posix()
    rows = _git(repository, 'ls-files', '--stage', '-z', '--', prefix).split(b'\0')
    entries = {}
    optional_sources = {}
    for row in rows:
        if not row:
            continue
        fields, path = row.split(b'\t', 1)
        mode, blob, stage = fields.decode().split()
        if mode == '160000':
            local_name = path.decode()[len(prefix) + 1:]
            if not local_name.startswith('s11_atlas_bold/01_sources/') or stage != '0':
                raise ValueError('Unexpected submodule inside the owned pipeline')
            optional_sources[local_name] = blob
            continue
        if mode not in {'100644', '100755'} or stage != '0':
            raise ValueError('Protocol contains an unsupported entry or unresolved Git conflict')
        entries[path.decode()] = (mode, blob)
    if not entries:
        raise ValueError('Integrated protocol files are not tracked by the parent repository')
    # Compare with HEAD as well as the index: staging an edit must not make an
    # uncommitted runner eligible for a deployment receipt.
    changed = _git(repository, 'diff', 'HEAD', '--name-only', '-z', '--', prefix)
    untracked = _git(repository, 'ls-files', '--others', '--exclude-standard', '-z', '--', prefix)
    dirty_names = {name.decode()[len(prefix) + 1:]
                   for name in (changed + untracked).split(b'\0') if name}
    import_manifest = json.loads((root / origin['source_manifest']).read_text())
    history = json.loads((root / origin['history_index']).read_text())
    if (import_manifest['upstream_commit'] != origin['commit']
            or history['baseline_commit'] != origin['commit']
            or history['commit_count'] != len(history['commits'])):
        raise ValueError('Protocol origin/history metadata disagree')
    history_commits = {item['commit'] for item in history['commits']}
    if origin['commit'] not in history_commits:
        raise ValueError('Protocol baseline is absent from the preserved history index')
    source_hashes = {}
    modified = []
    dirty = set(dirty_names)
    for name, (mode, expected_blob) in sorted(entries.items()):
        path = repository / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Integrated protocol file is missing or redirected: ' + name)
        data = path.read_bytes()
        local_name = path.relative_to(protocol).as_posix()
        digest = hashlib.sha256(data).hexdigest()
        source_hashes[local_name] = {'mode': mode, 'sha256': digest}
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        executable = bool(path.stat().st_mode & 0o111)
        if blob != expected_blob or executable != (mode == '100755'):
            dirty.add(local_name)
        original = import_manifest['files'].get(local_name)
        if original is None or digest != original['sha256']:
            modified.append(local_name)
    for name in ('LICENSE', 'CITATION.cff'):
        if name not in source_hashes:
            raise ValueError('Required protocol attribution is missing: ' + name)
    if source_hashes['LICENSE']['sha256'] != import_manifest['files']['LICENSE']['sha256']:
        raise ValueError('Preserve the original protocol GPL license text')
    # Old initialized clones may retain their inert .git pointer for an active
    # legacy worker. It is not consulted for identity, source selection or Git IO.
    if require_clean and dirty:
        raise ValueError('Integrated protocol has uncommitted source changes: ' + ', '.join(sorted(dirty)))
    identity = hashlib.sha256(json.dumps({'owned_files': source_hashes, 'optional_sources': optional_sources}, sort_keys=True).encode()).hexdigest()
    return {
        'distribution': 'integrated-source',
        'upstream_commit': origin['commit'],
        'repository_commit': _git(repository, 'rev-parse', 'HEAD').decode().strip(),
        'protocol_clean': not dirty,
        'protocol_source_sha256': identity,
        'protocol_files': len(source_hashes),
        'optional_source_commits': optional_sources,
        'modified_from_import': modified,
        'uncommitted_protocol_files': sorted(dirty),
        'original_history_commits': history['commit_count'],
        'legacy_git_metadata_present': (protocol / '.git').exists(),
        'scientific_validation': 'not_established_by_source_checks',
    }
