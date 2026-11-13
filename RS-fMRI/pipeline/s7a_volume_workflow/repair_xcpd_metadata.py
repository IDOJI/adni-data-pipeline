#!/usr/bin/env python3
"""Repair only known missing NIfTI metadata in an existing XCP-D output.

This does not patch XCP-D/Nilearn source or modify voxel values. In the observed
26.2.0 output, pixdim[4] already contains the correct TR (1.5 s), while xyzt_units
is zero. DenoiseNifti's unmask creates unspecified units; the smoothed data sink
disables check_hdr. Restore units from the matching valid denoised derivative.
Only an unspecified-unit header with matching TR or the default TR=1 is eligible.
All qform/sform fields and the decompressed voxel payload are preserved exactly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile
import uuid

SOURCE_BYTES = Path(__file__).resolve().read_bytes()
SOURCE_SHA256 = hashlib.sha256(SOURCE_BYTES).hexdigest()
VERSION = '1.0.0'
CHUNK = 2**20


class RepairError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def contained_file(root, path):
    """Reject symlink aliases, including a parent directory redirected elsewhere."""
    root, path = Path(root), Path(path)
    if path == root or root not in path.parents:
        raise RepairError(f'Path is outside its allowed root: {path}')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise RepairError(f'Symlink is not accepted: {part}')
        if part == root:
            break
    if not path.is_file():
        raise RepairError(f'Missing file: {path}')
    return path


def nifti_prefix(path):
    with gzip.open(path, 'rb') as f:
        header = f.read(348)
        if len(header) != 348:
            raise RepairError('Truncated NIfTI-1 header')
        ends = [e for e in '<>' if struct.unpack_from(e + 'i', header)[0] == 348]
        if len(ends) != 1 or header[344:348] != b'n+1\0':
            raise RepairError('Only single-file NIfTI-1 is supported')
        endian = ends[0]
        dims = struct.unpack_from(endian + '8h', header, 40)
        pixdim = struct.unpack_from(endian + '8f', header, 76)
        offset = struct.unpack_from(endian + 'f', header, 108)[0]
        datatype, bitpix = struct.unpack_from(endian + '2h', header, 70)
        if dims[0] != 4 or any(n <= 0 for n in dims[1:5]):
            raise RepairError('Expected a nonempty 4D BOLD image')
        if not math.isfinite(offset) or offset != int(offset) or not 352 <= offset <= 2**24:
            raise RepairError('Invalid or unsupported voxel offset')
        if (datatype, bitpix) not in ((16, 32), (64, 64)):
            raise RepairError('Expected a floating-point XCP-D image')
        if not all(math.isfinite(z) and z > 0 for z in pixdim[1:5]):
            raise RepairError('Invalid spatial or temporal zoom')
        if struct.unpack_from(endian + 'h', header, 254)[0] <= 0:
            raise RepairError('A valid sform is required for an unambiguous affine comparison')
        affine = struct.unpack_from(endian + '12f', header, 280)
        if not all(math.isfinite(x) for x in affine):
            raise RepairError('Nonfinite affine')
        prefix = header + f.read(int(offset) - 348)
        if len(prefix) != int(offset):
            raise RepairError('Truncated header/extensions')
    return {'prefix': prefix, 'endian': endian, 'shape': list(dims[1:5]),
            'zooms': list(pixdim[1:5]), 'affine': list(affine), 'units': header[123],
            'datatype': datatype, 'bitpix': bitpix, 'vox_offset': int(offset),
            'payload_bytes_expected': math.prod(dims[1:5]) * bitpix // 8,
            'header_sha256': digest(header), 'prefix_sha256': digest(prefix)}


def close(a, b):
    return abs(a - b) <= 1e-5


def describe(info):
    return {key: value for key, value in info.items() if key not in ('prefix', 'endian')}


def choose_files(root, subject, session):
    func = root / f'sub-{subject}' / f'ses-{session}' / 'func'
    base = f'sub-{subject}_ses-{session}_task-rest_'
    selected = {}
    for desc in ('denoised', 'denoisedSmoothed'):
        files = sorted(func.glob(base + '*desc-' + desc + '_bold.nii.gz'))
        if len(files) != 1:
            raise RepairError(f'Expected one {desc} BOLD file; found {len(files)}')
        selected[desc] = contained_file(root, files[0])
    ref, target = selected['denoised'], selected['denoisedSmoothed']
    if target.name.replace('desc-denoisedSmoothed_', 'desc-denoised_') != ref.name:
        raise RepairError('Reference and target BIDS entities do not match')
    return ref, target


def prepare(root, subject, session):
    reference, target = choose_files(root, subject, session)
    rh, th = nifti_prefix(reference), nifti_prefix(target)
    rjson = contained_file(root, reference.with_name(reference.name[:-7] + '.json'))
    tjson = contained_file(root, target.with_name(target.name[:-7] + '.json'))
    rm, tm = json.loads(rjson.read_text()), json.loads(tjson.read_text())
    tr = rm.get('RepetitionTime')
    if not isinstance(tr, (int, float)) or not math.isfinite(tr) or tr <= 0:
        raise RepairError('Reference JSON must contain a finite positive RepetitionTime')
    if rh['units'] != 10 or not close(rh['zooms'][3], tr):
        raise RepairError('Reference must have matching mm/sec units and JSON/header TR')
    if 'RepetitionTime' in tm and (not isinstance(tm['RepetitionTime'], (int, float)) or
                                  not math.isfinite(tm['RepetitionTime']) or not close(tm['RepetitionTime'], tr)):
        raise RepairError('Target JSON RepetitionTime conflicts with reference')
    if rh['shape'] != th['shape'] or not all(close(a, b) for a, b in zip(rh['affine'], th['affine'])):
        raise RepairError('Reference/target shape or affine mismatch')
    if not all(close(a, b) for a, b in zip(rh['zooms'][:3], th['zooms'][:3])):
        raise RepairError('Reference/target spatial zoom mismatch')
    if (rh['datatype'], rh['bitpix']) != (th['datatype'], th['bitpix']):
        raise RepairError('Reference/target datatypes differ')
    if th['units'] == 10:
        if not close(th['zooms'][3], tr):
            raise RepairError('Target already has valid units but a conflicting TR; refusing repair')
        patched = th['prefix']
    elif th['units'] == 0:
        if not (close(th['zooms'][3], tr) or th['zooms'][3] == 1.0):
            raise RepairError('Unknown units with unexpected non-default TR; refusing repair')
        patched = bytearray(th['prefix'])
        patched[123] = 10
        if not close(th['zooms'][3], tr):
            struct.pack_into(th['endian'] + 'f', patched, 92, rh['zooms'][3])
        patched = bytes(patched)
    else:
        raise RepairError('Unexpected specified or partially specified units; refusing repair')
    changes = [i for i, (a, b) in enumerate(zip(th['prefix'], patched)) if a != b]
    if not set(changes).issubset({123, 92, 93, 94, 95}):
        raise RepairError('Attempted modification outside the allowed header fields')
    result = {'repair_version': VERSION, 'repair_source_sha256': SOURCE_SHA256,
              'operation': 'existing_output_header_metadata_repair_not_software_source_patch',
              'reference': str(reference), 'target': str(target),
              'reference_header': describe(rh), 'before_header': describe(th),
              'reference_json_sha256': file_hash(rjson), 'target_json_sha256': file_hash(tjson),
              'reference_json_TR': tr, 'changed_prefix_byte_offsets': changes,
              'TR_numeric_value_preserved': close(th['zooms'][3], tr),
              'voxel_values_modified': False, 'qform_sform_modified': False,
              'JSON_modified': False, 'status': 'would_repair' if changes else 'already_valid_no_op'}
    return reference, target, rh, th, patched, result


def write_record(path, record):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    os.replace(temporary, path)


def stream_patch(original, destination, prefix, old_prefix):
    """Copy all bytes after vox_offset unchanged through a deterministic gzip stream."""
    payload = hashlib.sha256()
    count = 0
    with gzip.open(original, 'rb') as src, destination.open('wb') as raw:
        if src.read(len(old_prefix)) != old_prefix:
            raise RepairError('Backed-up source header changed unexpectedly')
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=6, mtime=0) as dst:
            dst.write(prefix)
            for block in iter(lambda: src.read(CHUNK), b''):
                payload.update(block)
                count += len(block)
                dst.write(block)
        raw.flush()
        os.fsync(raw.fileno())
    return payload.hexdigest(), count


def payload_proof(path, offset):
    h, count = hashlib.sha256(), 0
    with gzip.open(path, 'rb') as f:
        f.read(offset)
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
            count += len(block)
    return h.hexdigest(), count


def repair_run(xcpd_root, subject, session, provenance_root, apply=False):
    """Audit or atomically repair one output; compatible with a post-XCP-D hook.

    provenance_root must be separate from the derivative tree. Each applied
    repair stores the full original compressed image under a unique subject /
    session directory. Dry runs and already-valid files produce no backup.
    """
    subject, session = subject.removeprefix('sub-'), session.removeprefix('ses-')
    if not all(re.fullmatch('[A-Za-z0-9]+', x) for x in (subject, session)):
        raise RepairError('Subject/session must be alphanumeric BIDS labels')
    root, proot = Path(xcpd_root).absolute(), Path(provenance_root).absolute()
    for path in (root, proot):
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise RepairError(f'Symlink in output/provenance path: {path}')
    root, proot = root.resolve(), proot.resolve()
    if not root.is_dir() or root == proot or root in proot.parents or proot in root.parents:
        raise RepairError('Existing derivative root and separate provenance root required')
    reference, target = choose_files(root, subject, session)
    lock = target.with_name('.' + target.name + '.metadata-repair.lock')
    locked, temporary, record_path, result = False, None, None, None
    try:
        if apply:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise RepairError(f'Repair lock exists: {lock}; verify no repair is active before recovery') from exc
            with os.fdopen(fd, 'w') as f:
                json.dump({'pid': os.getpid(), 'target': str(target)}, f)
            locked = True
        reference, target, rh, th, patched, result = prepare(root, subject, session)
        if not apply or not result['changed_prefix_byte_offsets']:
            return result
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        provenance = proot / f'sub-{subject}' / f'ses-{session}' / (stamp + '_' + uuid.uuid4().hex[:8])
        provenance.mkdir(parents=True, exist_ok=False)
        backup = provenance / ('original_' + target.name)
        shutil.copyfile(target, backup)
        original_hash = file_hash(backup)
        if file_hash(target) != original_hash:
            raise RepairError('Target changed while creating the original compressed backup')
        (provenance / 'original_nifti_prefix.bin').write_bytes(th['prefix'])
        (provenance / 'repair_source.py').write_bytes(SOURCE_BYTES)
        result.update({'status': 'preparing', 'provenance_directory': str(provenance),
                       'original_compressed_backup': str(backup), 'before_file_sha256': original_hash,
                       'started_at': dt.datetime.now(dt.timezone.utc).isoformat()})
        record_path = provenance / 'repair.json'
        write_record(record_path, result)
        fd, name = tempfile.mkstemp(prefix='.' + target.name + '.', suffix='.repair.tmp', dir=target.parent)
        os.close(fd)
        temporary = Path(name)
        before_payload, before_count = stream_patch(backup, temporary, patched, th['prefix'])
        after_payload, after_count = payload_proof(temporary, th['vox_offset'])
        if before_count != th['payload_bytes_expected'] or (before_payload, before_count) != (after_payload, after_count):
            raise RepairError('Voxel payload length/hash verification failed')
        after_header = nifti_prefix(temporary)
        if after_header['prefix'] != patched:
            raise RepairError('Written header differs from the whitelisted patch')
        # Detect a concurrently changed target/reference/JSON before replacement.
        current = prepare(root, subject, session)
        if current[3]['prefix'] != th['prefix'] or current[2]['prefix'] != rh['prefix'] or \
                current[5]['reference_json_sha256'] != result['reference_json_sha256'] or \
                current[5]['target_json_sha256'] != result['target_json_sha256'] or file_hash(target) != original_hash:
            raise RepairError('Output metadata or target changed during repair')
        result.update({'after_header': describe(after_header), 'after_file_sha256': file_hash(temporary),
                       'before_payload_sha256': before_payload, 'after_payload_sha256': after_payload,
                       'payload_bytes': before_count, 'payload_unchanged': True, 'status': 'ready_to_replace'})
        (provenance / 'corrected_nifti_prefix.bin').write_bytes(patched)
        write_record(record_path, result)
        os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
        os.replace(temporary, target)
        temporary = None
        result.update({'status': 'applied', 'ended_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                       'record': str(record_path)})
        write_record(record_path, result)
        return result
    except BaseException as exc:
        if record_path is not None and result is not None:
            result.update({'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
            write_record(record_path, result)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if locked:
            lock.unlink(missing_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['dry-run', 'apply'])
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--data-root', type=Path)
    group.add_argument('--xcpd-root', type=Path)
    p.add_argument('--provenance-root', type=Path)
    p.add_argument('--subject', required=True)
    p.add_argument('--session', required=True)
    a = p.parse_args(argv)
    if a.xcpd_root and not a.provenance_root:
        p.error('--xcpd-root requires a separate --provenance-root')
    xroot = a.xcpd_root or a.data_root / 'derivatives/xcp_d'
    proot = a.provenance_root or a.data_root / 'metadata_repairs'
    try:
        result = repair_run(xroot, a.subject, a.session, proot, apply=a.command == 'apply')
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (RepairError, OSError, ValueError, KeyError, struct.error) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
