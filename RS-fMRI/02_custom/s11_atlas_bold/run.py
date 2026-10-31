#!/usr/bin/env python3
"""Extract discrete-atlas BOLD means with explicit space, label and coverage audits."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re
import sys

import nibabel as nb
from nibabel.processing import resample_from_to
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from sources import verify
from _shared import finish, new_output, read, sha, snapshot, unchanged, verify_bundle, write


def expected_ids(entry):
    spec = entry['expected_labels']
    if 'range' in spec:
        start, stop = spec['range']
        if type(start) is not int or type(stop) is not int or not 1 <= start <= stop or stop - start >= 100000:
            raise ValueError('Invalid expected atlas label range')
        values = list(range(start, stop + 1))
    else:
        values = spec['ids']
    if not values or len(values) > 100000 or values != sorted(set(values)) or any(type(v) is not int or not 0 < v < 2147483647 for v in values):
        raise ValueError('Invalid expected atlas labels')
    return np.array(values, dtype=np.int32)


def registered(catalog, atlas_id):
    catalog = Path(catalog).resolve()
    data = json.loads(catalog.read_text())
    if data.get('kind') != 'discrete_label_catalog':
        raise ValueError('Unsupported atlas catalog')
    matches = [e for e in data['atlases'] if e['id'] == atlas_id]
    if len(matches) != 1:
        raise ValueError('Atlas ID must identify exactly one catalog entry')
    e = matches[0]
    if e.get('kind') != 'labels' or e.get('background') != 0:
        raise ValueError('Only 3-D discrete atlases with background 0 are supported')
    base = ROOT if catalog == (ROOT / 'catalog.json').resolve() else catalog.parent
    if base == ROOT:
        lock = json.loads((ROOT / 'sources.lock.json').read_text())['sources']
        verify(e['source'], lock[e['source']])
        if e['source'] == 'templateflow':
            template = lock['templateflow']['templates'][e['space']]
            path = ROOT / lock['templateflow']['path'] / template['path']
            from sources import git
            if git(path, 'rev-parse', 'HEAD') != template['commit'] or template['commit'] != e['source_commit']:
                raise ValueError('Template dataset commit mismatch')
        elif lock[e['source']]['commit'] != e['source_commit']:
            raise ValueError('Atlas commit differs from source lock')
    elif e.get('source') != 'external' or not e.get('citation'):
        raise ValueError('External catalogs require an explicit external source and provenance citation')
    atlas = (base / e['path']).resolve()
    if not atlas.is_relative_to(base.resolve()) or not atlas.is_file() or sha(atlas) != e['sha256']:
        raise ValueError('Atlas payload is absent, outside catalog root, or changed; initialize/fetch it explicitly')
    files = [catalog, atlas]
    metadata = None
    if e.get('metadata_path'):
        metadata = (base / e['metadata_path']).resolve()
        if not metadata.is_relative_to(base.resolve()) or not metadata.is_file() or sha(metadata) != e['metadata_sha256']:
            raise ValueError('Atlas label metadata changed')
        files.append(metadata)
    return e, atlas, metadata, files


def names_for(entry, metadata, ids):
    names = {}
    kind = entry.get('label_format', 'numeric')
    if metadata and kind == 'neuroparc_json':
        names = {k: v.get('label', '') for k, v in json.loads(metadata.read_text()).get('rois', {}).items()}
    elif metadata and kind == 'cbig_lut':
        for line in metadata.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0].isdigit():
                names[fields[0]] = fields[1]
    elif metadata and kind == 'templateflow_tsv':
        names = {r['index']: r['name'] for r in read(metadata, ['index', 'name'])}
    return {int(v): names.get(str(v)) or 'ROI_' + str(v) for v in ids}


def entities(path):
    return dict(re.findall(r'(?:^|_)(sub|ses|task|acq|run|echo|dir|rec|space)-([^_\.]+)', Path(path).name))


def check_inclusion(directory, image_id, bold):
    directory = Path(directory).resolve()
    record = verify_bundle(directory, 'final_inclusion_validation_v1')
    if 'inclusion_audit.tsv' not in record['outputs_sha256']:
        raise ValueError('Inclusion audit is not hash-covered')
    match = re.fullmatch(r'I?(\d+)', str(image_id))
    if not match:
        raise ValueError('An explicit image ID is required with inclusion evidence')
    iid = str(int(match[1]))
    rows = [r for r in read(directory / 'inclusion_audit.tsv') if r['IMAGE_ID'] == iid]
    if len(rows) != 1 or rows[0]['INCLUSION_STATUS'] not in {'eligible', 'pending'}:
        raise ValueError('Image is not uniquely retained by final inclusion validation')
    row, current = rows[0], entities(bold)
    if row.get('SOURCE_MODALITY') != 'EPI':
        raise ValueError('BOLD extraction requires a retained EPI image')
    for key in ('sub', 'ses', 'task', 'acq', 'run', 'echo', 'dir', 'rec'):
        expected = row.get(key, '').removeprefix(key + '-')
        actual = current.get(key, '')
        if key == 'sub':
            expected = expected.removeprefix('ADNI'); actual = actual.removeprefix('ADNI')
        if expected and expected != actual:
            raise ValueError('BOLD run identity differs from retained imaging/clinical row: ' + key)
    return row, [directory / 'artifact.json', directory / 'inclusion_audit.tsv']


def time_mask(path, n):
    if path is None:
        return np.arange(n)
    rows = read(path)
    if not rows:
        raise ValueError('Empty temporal mask')
    if 'original_frame_index_zero_based' in rows[0]:
        idx, flag = 'original_frame_index_zero_based', 'retain_FD_and_nonsteady'
    else:
        idx, flag = 'frame_index', 'keep'
    if len(rows) != n or [int(r[idx]) for r in rows] != list(range(n)):
        raise ValueError('Temporal mask must enumerate every input frame exactly in order')
    values = [r[flag].strip().lower() for r in rows]
    if not all(v in {'true', 'false', '1', '0'} for v in values):
        raise ValueError('Invalid temporal keep flag')
    return np.flatnonzero(np.array([v in {'true', '1'} for v in values]))


def tr_seconds(img, metadata):
    value = metadata.get('RepetitionTime')
    header = float(img.header.get_zooms()[3])
    unit = img.header.get_xyzt_units()[1]
    scale = {'sec': 1, 'msec': .001, 'usec': .000001}.get(unit)
    header = header * scale if scale is not None else None
    if value is None:
        value = header
    if value is None or not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError('A valid TR in seconds is required from JSON or known NIfTI temporal units')
    if header is not None and (not math.isfinite(header) or not np.isclose(header, float(value), rtol=1e-4, atol=1e-5)):
        raise ValueError('JSON and NIfTI TR disagree')
    return float(value)


def grid_equal(a, b):
    return a.shape[:3] == b.shape[:3] and np.allclose(a.affine, b.affine, rtol=0, atol=1e-5)


def labels(img):
    values = np.asanyarray(img.dataobj)
    if len(img.shape) != 3 or not np.isfinite(values).all() or np.any(values < 0) or not np.allclose(values, np.rint(values), atol=1e-6, rtol=0) or np.max(values) >= 2147483647:
        raise ValueError('Atlas must contain finite, nonnegative 3-D integer labels')
    return values.astype(np.int32)


def process(bold, mask, atlas_id, space, input_kind, output_dir, catalog=None, bold_json=None,
            sample_mask=None, resample_labels=False, min_coverage=.5, min_voxels=1,
            standardize='none', inclusion=None, image_id=None, max_workspace_mb=512):
    if input_kind not in {'preprocessed', 'denoised'} or standardize not in {'none', 'zscore'}:
        raise ValueError('Specify supported input kind and standardization')
    if not math.isfinite(min_coverage) or not 0 <= min_coverage <= 1 or min_voxels < 1 or not math.isfinite(max_workspace_mb) or max_workspace_mb <= 0:
        raise ValueError('Invalid coverage/voxel/workspace settings')
    catalog = Path(catalog or ROOT / 'catalog.json')
    e, atlas_path, metadata_path, files = registered(catalog, atlas_id)
    if e['space'] != space:
        raise ValueError('Atlas and BOLD spaces must match exactly; grid resampling is not registration')
    current = entities(bold)
    if current.get('space') and current['space'] != space:
        raise ValueError('BOLD filename space differs from declared space')
    paths = files + [Path(bold), Path(mask)] + [Path(p) for p in (bold_json, sample_mask) if p]
    retained = None
    if inclusion:
        retained, evidence_files = check_inclusion(inclusion, image_id, bold)
        paths.extend(evidence_files)
    elif image_id:
        raise ValueError('Image ID requires an inclusion artifact')
    output = new_output(output_dir, paths)
    hashes = snapshot(paths)
    image = nb.load(bold, mmap=True, keep_file_open=True)
    brain = nb.load(mask)
    atlas = nb.load(atlas_path)
    if len(image.shape) != 4 or image.shape[3] < 2 or len(brain.shape) != 3 or len(atlas.shape) != 3:
        raise ValueError('Expected 4-D volumetric BOLD, 3-D brain mask and 3-D discrete atlas; surfaces/CIFTI/probability maps are unsupported')
    for img in (image, brain, atlas):
        if img.header.get_xyzt_units()[0] != 'mm' or not np.isfinite(img.affine).all() or abs(np.linalg.det(img.affine[:3, :3])) < 1e-9:
            raise ValueError('Images require valid millimetre affines')
    if not grid_equal(brain, image):
        raise ValueError('Brain mask must use the BOLD grid')
    ids = expected_ids(e)
    estimate = int(np.prod(image.shape[:3])) * 64 + int(np.prod(atlas.shape)) * 16 + len(ids) * image.shape[3] * 8
    if estimate > max_workspace_mb * 1048576:
        raise ValueError('Estimated extraction workspace exceeds the requested memory cap')
    metadata = json.loads(Path(bold_json).read_text()) if bold_json else {}
    spatial_reference = metadata.get('SpatialReference')
    if spatial_reference and isinstance(spatial_reference, str) and spatial_reference.startswith('MNI') and spatial_reference != space:
        raise ValueError('JSON spatial reference differs from declared space')
    tr = tr_seconds(image, metadata)
    frames = time_mask(sample_mask, image.shape[3])
    if len(frames) < 2:
        raise ValueError('At least two retained input frames are required')
    source = labels(atlas)
    source_voxel_volume = abs(float(np.linalg.det(atlas.affine[:3, :3])))
    target_voxel_volume = abs(float(np.linalg.det(image.affine[:3, :3])))
    observed, counts = np.unique(source[source > 0], return_counts=True)
    if set(observed) - set(ids):
        raise ValueError('Atlas contains labels outside the registered expected set')
    source_counts = dict(zip(observed, counts))
    resampled = not grid_equal(atlas, image)
    if resampled:
        if not resample_labels:
            raise ValueError('Atlas grid differs; explicitly request nearest-neighbor label resampling')
        atlas = resample_from_to(nb.Nifti1Image(source, atlas.affine), (image.shape[:3], image.affine), order=0, mode='constant', cval=0)
    target = labels(atlas)
    grid_ids, grid_counts = np.unique(target[target > 0], return_counts=True)
    target_counts = dict(zip(grid_ids, grid_counts))
    mask_data = np.asanyarray(brain.dataobj)
    if not np.isfinite(mask_data).all() or not np.isin(mask_data, [0, 1]).all():
        raise ValueError('Brain mask must be finite and binary')
    selected = (target > 0) & (mask_data == 1)
    positions = np.searchsorted(ids, target[selected])
    masked_counts = np.bincount(positions, minlength=len(ids))
    series = np.full((len(frames), len(ids)), np.nan)
    nonfinite_frames = np.zeros(len(ids), dtype=int)
    for j, frame_index in enumerate(frames):
        frame = np.asanyarray(image.dataobj[..., int(frame_index)], dtype=np.float64)
        values = frame[selected]; good = np.isfinite(values)
        finite_counts = np.bincount(positions[good], minlength=len(ids))
        totals = np.bincount(positions[good], weights=values[good], minlength=len(ids))
        usable = (masked_counts > 0) & (finite_counts == masked_counts)
        series[j, usable] = totals[usable] / masked_counts[usable]
        nonfinite_frames += finite_counts < masked_counts
    complete = np.isfinite(series).all(axis=0)
    variance = np.full(len(ids), np.nan)
    variance[complete] = np.std(series[:, complete], axis=0, ddof=1)
    if standardize == 'zscore':
        valid = np.isfinite(series).all(axis=0) & (variance > 0)
        series[:, valid] = (series[:, valid] - series[:, valid].mean(axis=0)) / variance[valid]
        series[:, ~valid] = np.nan
    names = names_for(e, metadata_path, ids)
    coverage_rows = []
    for k, iid in enumerate(ids):
        n_grid, n_mask = int(target_counts.get(iid, 0)), int(masked_counts[k])
        coverage = n_mask / n_grid if n_grid else 0.
        source_volume = int(source_counts.get(iid, 0)) * source_voxel_volume
        grid_volume = n_grid * target_voxel_volume
        source_coverage = min(1., n_mask * target_voxel_volume / source_volume) if source_volume else 0.
        reasons = []
        if not source_counts.get(iid, 0): reasons.append('absent_in_registered_source')
        if not n_grid: reasons.append('lost_on_bold_grid')
        if n_mask < min_voxels: reasons.append('insufficient_mask_voxels')
        if coverage < min_coverage: reasons.append('low_mask_coverage')
        if source_coverage < min_coverage: reasons.append('low_source_volume_coverage')
        if nonfinite_frames[k]: reasons.append('nonfinite_input_frames')
        if not np.isfinite(variance[k]) or variance[k] == 0: reasons.append('undefined_or_constant_signal')
        coverage_rows.append({'label_id': int(iid), 'name': names[int(iid)], 'source_voxels': int(source_counts.get(iid, 0)),
                              'bold_grid_voxels': n_grid, 'mask_voxels': n_mask, 'mask_coverage': coverage,
                              'source_volume_mm3': source_volume, 'bold_grid_volume_mm3': grid_volume,
                              'masked_source_volume_fraction': source_coverage,
                              'nonfinite_input_frames': int(nonfinite_frames[k]), 'qc_status': 'fail' if reasons else 'pass', 'qc_reasons': ';'.join(reasons)})
    source_count_discrepancy = bool(e.get('declared_regions') and e['declared_regions'] != len(ids))
    failed = any(r['qc_status'] == 'fail' for r in coverage_rows) or source_count_discrepancy
    unchanged(hashes)
    output.mkdir(parents=True)
    registered_atlas = nb.Nifti1Image(target.astype(np.int32), image.affine)
    registered_atlas.header.set_xyzt_units('mm')
    registered_atlas.header.set_intent('label')
    nb.save(registered_atlas, output / 'atlas_on_bold_grid.nii.gz')
    with (output / 'timeseries.tsv').open('w') as stream:
        stream.write('\t'.join('roi_' + str(i) for i in ids) + '\n')
        np.savetxt(stream, series, delimiter='\t', fmt='%.10g')
    write(output / 'frames.tsv', [{'output_row': j, 'input_frame_index_zero_based': int(v), 'input_frame_time_seconds': float(v * tr)} for j, v in enumerate(frames)])
    write(output / 'roi_coverage.tsv', coverage_rows)
    write(output / 'labels.tsv', [{'column': 'roi_' + str(i), 'label_id': int(i), 'name': names[int(i)]} for i in ids])
    return finish(output, 'atlas_bold_timeseries_v1', hashes, {
        'status': 'failed_qc' if failed else 'extracted_qc_pass', 'atlas_id': atlas_id, 'space': space,
        'atlas_source': e['source'], 'atlas_source_commit': e.get('source_commit'), 'atlas_sha256': e['sha256'],
        'source_warnings': e.get('source_warnings', []), 'source_declared_count_discrepancy': source_count_discrepancy,
        'roi_count': len(ids), 'roi_qc_status': dict(Counter(r['qc_status'] for r in coverage_rows)),
        'input_frames': image.shape[3], 'retained_frames': len(frames), 'tr_seconds': tr,
        'input_kind': input_kind, 'denoising_assessment': 'caller_declared_no_additional_temporal_cleaning',
        'standardization': standardize, 'resampled_atlas': resampled, 'interpolation': 'nearest' if resampled else 'none',
        'min_coverage': min_coverage, 'min_voxels': min_voxels, 'estimated_workspace_bytes': estimate,
        'maximum_loaded_bold_frames': 1, 'inclusion_status': retained['INCLUSION_STATUS'] if retained else 'not_checked',
        'spatial_registration_verified': False, 'implementation_sha256': sha(__file__),
        'scope': 'Volumetric label means and QC only; no atlas warping, denoising, FC, or final research-readiness claim.'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    l = sub.add_parser('list'); l.add_argument('--space'); l.add_argument('--source'); l.add_argument('--catalog', type=Path, default=ROOT / 'catalog.json')
    x = sub.add_parser('extract')
    for flag in ('bold', 'mask', 'atlas', 'space', 'input-kind', 'output-dir'): x.add_argument('--' + flag, required=True)
    for flag in ('catalog', 'bold-json', 'sample-mask', 'inclusion', 'image-id'): x.add_argument('--' + flag)
    x.add_argument('--resample-labels', action='store_true'); x.add_argument('--min-coverage', type=float, default=.5)
    x.add_argument('--min-voxels', type=int, default=1); x.add_argument('--max-workspace-mb', type=float, default=512)
    x.add_argument('--standardize', choices=['none', 'zscore'], default='none')
    a = p.parse_args()
    try:
        if a.command == 'list':
            entries = json.loads(a.catalog.read_text())['atlases']
            print('atlas_id\tsource\tspace\texpected_regions\tobserved_regions\tsource_missing_regions')
            for e in entries:
                if (not a.space or a.space == e['space']) and (not a.source or a.source == e['source']):
                    print('\t'.join(str(e.get(k, '')) for k in ['id', 'source', 'space', 'expected_regions', 'observed_regions', 'source_missing_regions']))
            return
        result = process(a.bold, a.mask, a.atlas, a.space, a.input_kind, a.output_dir, a.catalog, a.bold_json,
                         a.sample_mask, a.resample_labels, a.min_coverage, a.min_voxels, a.standardize,
                         a.inclusion, a.image_id, a.max_workspace_mb)
        print(json.dumps(result['summary'], indent=2))
        if result['summary']['status'] == 'failed_qc': p.exit(2, 'Extraction artifacts written; ROI/source QC failed\n')
    except (ValueError, KeyError, FileNotFoundError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
