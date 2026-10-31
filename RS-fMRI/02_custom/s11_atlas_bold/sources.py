#!/usr/bin/env python3
"""Explicit, pinned source installation and checksum-verified public atlas fetching."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def source_path(spec):
    p = ROOT / spec['path']
    if p.parent != ROOT / '01_sources':
        raise ValueError('Invalid source location')
    return p


def verify(name, spec):
    p = source_path(spec)
    if not (p / '.git').exists():
        raise ValueError('Source is not initialized: ' + name)
    if git(p, 'rev-parse', 'HEAD') != spec['commit']:
        raise ValueError('Source commit differs from lock: ' + name)
    if git(p, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Source checkout changed: ' + name)
    return p


def install(name, spec):
    p = source_path(spec)
    git(REPO, 'submodule', 'init', '--', str(p.relative_to(REPO)))
    if not (p / '.git').exists():
        if p.exists() and any(p.iterdir()):
            raise ValueError('Refusing to overwrite source directory: ' + name)
        p.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--filter=blob:none', '--depth', '1', '--no-checkout', spec['url'], str(p)], check=True)
        patterns = spec.get('sparse_patterns', [])
        if patterns:
            git(p, 'sparse-checkout', 'init', '--no-cone')
            git(p, 'sparse-checkout', 'set', '--no-cone', *patterns)
        if subprocess.run(['git', '-C', str(p), 'cat-file', '-e', spec['commit']], capture_output=True).returncode:
            git(p, 'fetch', '--depth', '1', 'origin', spec['commit'])
        git(p, 'checkout', '--detach', spec['commit'])
        git(REPO, 'submodule', 'absorbgitdirs', str(p.relative_to(REPO)))
    verify(name, spec)
    if name == 'templateflow':
        git(p, 'submodule', 'update', '--init', '--depth', '1', *[v['path'] for v in spec['templates'].values()])
        for template in spec['templates'].values():
            if git(p / template['path'], 'rev-parse', 'HEAD') != template['commit']:
                raise ValueError('Template dataset pin mismatch')


def fetch_payload(spec):
    path = ROOT / spec['cache_path']
    if not path.resolve().is_relative_to((ROOT / '02_atlases').resolve()):
        raise ValueError('Invalid atlas cache location')
    parsed = urllib.parse.urlparse(spec['url'])
    if parsed.scheme != 'https' or parsed.netloc != 'templateflow.s3.amazonaws.com':
        raise ValueError('Unexpected public atlas origin')
    def valid(p):
        return p.stat().st_size == spec['size'] and digest(p, spec['annex_hash_algorithm']) == spec['annex_digest'] and (not spec.get('sha256') or digest(p) == spec['sha256'])
    if path.exists():
        if not valid(path):
            raise ValueError('Existing atlas cache changed: ' + path.name)
        return path.name
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.fetch-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream, urllib.request.urlopen(spec['url'], timeout=60) as response:
            count = 0
            while block := response.read(1048576):
                count += len(block)
                if count > spec['size']:
                    raise ValueError('Atlas exceeds pinned byte size')
                stream.write(block)
        if not valid(Path(temporary)):
            raise ValueError('Atlas checksum mismatch: ' + path.name)
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path.name


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['status', 'install', 'fetch-templateflow'])
    p.add_argument('--source', action='append', choices=['neuroparc', 'CBIG', 'nilearn', 'templateflow'])
    a = p.parse_args()
    lock = json.loads((ROOT / 'sources.lock.json').read_text())['sources']
    selected = a.source or list(lock)
    if a.command == 'fetch-templateflow':
        verify('templateflow', lock['templateflow'])
        payloads = json.loads((ROOT / 'templateflow_payloads.json').read_text())['payloads']
        with ThreadPoolExecutor(max_workers=4) as pool:
            files = list(pool.map(fetch_payload, payloads))
        print(json.dumps({'verified_templateflow_files': len(files)}))
        return
    states = {}
    for name in selected:
        try:
            if a.command == 'install':
                install(name, lock[name])
            verify(name, lock[name])
            states[name] = {'status': 'pinned_clean', 'commit': lock[name]['commit']}
        except (ValueError, subprocess.CalledProcessError) as exc:
            if a.command == 'install':
                raise
            states[name] = {'status': 'unavailable_or_changed', 'reason': str(exc)}
    if 'templateflow' in selected:
        payloads = json.loads((ROOT / 'templateflow_payloads.json').read_text())['payloads']
        states['templateflow_cache'] = {'expected_files': len(payloads),
            'verified_sha256_files': sum((ROOT / v['cache_path']).is_file() and digest(ROOT / v['cache_path']) == v.get('sha256') for v in payloads)}
    print(json.dumps(states, indent=2))


if __name__ == '__main__':
    main()
