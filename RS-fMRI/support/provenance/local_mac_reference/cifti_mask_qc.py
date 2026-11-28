#!/usr/bin/env python3
"""Check constant CIFTI time series against subject-specific cortical masks.

This diagnostic does not alter fMRIPrep output or determine scientific inclusion.
It uses the fMRIPrep run's pinned image to resample native cortex masks to fsLR.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
import qc
import run as local


def disjoint(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a != b and a not in b.parents and b not in a.parents


def constants(data, chunk_size=24):
    if len(data.shape) != 2 or data.shape[0] < 2 or data.shape[1] < 1:
        raise ValueError('Expected a 2-D time series with at least two frames')
    first = np.asarray(data[0])
    constant = np.ones(data.shape[1], dtype=bool)
    for start in range(0, data.shape[0], chunk_size):
        values = np.asarray(data[start:start + chunk_size])
        if not np.isfinite(values).all():
            raise ValueError('Nonfinite CIFTI values')
        constant &= np.all(values == first, axis=0)
    return first, constant


def compare_cortex(vertices, zero_vertices, native_mask, template_roi, threshold=0.5):
    vertices = np.asarray(vertices, dtype=int)
    zero_vertices = np.asarray(zero_vertices, dtype=int)
    native_mask, template_roi = np.asarray(native_mask), np.asarray(template_roi)
    if native_mask.shape != (32492,) or template_roi.shape != (32492,) or not np.isfinite(native_mask).all():
        raise ValueError('Expected finite fsLR 32k individual and template masks')
    if ((vertices < 0) | (vertices >= 32492)).any() or not np.isin(zero_vertices, vertices).all():
        raise ValueError('Zero vertices do not belong to the cortical model')
    if not (template_roi[vertices] > 0).all():
        raise ValueError('CIFTI cortical model and template ROI differ')
    values = native_mask[zero_vertices]
    return {'cortical_grayordinates': len(vertices), 'constant_zero_vertices': len(zero_vertices),
            'standard_template_ROI_includes': int(np.count_nonzero(template_roi[zero_vertices] > 0)),
            'individual_cortex_interpolated_exact_zero': int(np.count_nonzero(values == 0)),
            'individual_cortex_interpolated_below_threshold': int(np.count_nonzero(values < threshold)),
            'individual_cortex_interpolated_max': float(values.max()) if len(values) else None,
            'all_standard_cortical_vertices_below_threshold': int(np.count_nonzero(native_mask[vertices] < threshold))}


def sample_nearest(image, coords):
    voxels = np.rint(nib.affines.apply_affine(np.linalg.inv(image.affine), coords)).astype(int)
    if not ((voxels >= 0) & (voxels < np.asarray(image.shape))).all():
        raise ValueError('Surface coordinates fall outside the anatomical grid')
    values = np.asarray(image.dataobj)
    return values[tuple(voxels.T)]


def examine(cfg, case, target, image_digest, source_record):
    root = local.runtime(cfg)
    sub, ses = 'sub-' + case['subject'], 'ses-' + case['session']
    anat = root / 'derivatives/fmriprep' / sub / ses / 'anat'
    func = root / 'derivatives/fmriprep' / sub / ses / 'func'
    template = root / 'templateflow/tpl-fsLR'
    stem = f'{sub}_{ses}'
    series = qc.one(func.glob(f'{stem}_task-rest*space-fsLR_den-91k_bold.dtseries.nii'), 'CIFTI time series')
    ribbon = qc.one(anat.glob(f'{stem}_desc-ribbon_mask.nii.gz'), 'anatomical ribbon')
    atlas = qc.one(anat.glob(f'{stem}_desc-aparcaseg_dseg.nii.gz'), 'anatomical segmentation')
    raw = local.paths_for(cfg, case)['bold']
    sidecar = local.paths_for(cfg, case)['bold_json']
    inputs = [series, ribbon, atlas, raw, sidecar]
    hemis = []
    for hemi, structure in (('L', 'CIFTI_STRUCTURE_CORTEX_LEFT'), ('R', 'CIFTI_STRUCTURE_CORTEX_RIGHT')):
        native = anat / f'{stem}_hemi-{hemi}_desc-cortex_mask.label.gii'
        sphere = anat / f'{stem}_hemi-{hemi}_space-fsLR_desc-msmsulc_sphere.surf.gii'
        target_sphere = template / f'tpl-fsLR_hemi-{hemi}_den-32k_sphere.surf.gii'
        roi = template / f'tpl-fsLR_hemi-{hemi}_den-32k_desc-nomedialwall_dparc.label.gii'
        surface = anat / f'{stem}_hemi-{hemi}_space-fsLR_den-32k_midthickness.surf.gii'
        paths = [native, sphere, target_sphere, roi, surface]
        if not all(p.is_file() for p in paths):
            raise ValueError(f'Missing {hemi} native or fsLR surface inputs')
        inputs.extend(paths)
        hemis.append((hemi, structure, native, sphere, target_sphere, roi, surface))
    before = {str(p): local.sha(p) for p in inputs}
    image = nib.load(series)
    if not isinstance(image, nib.Cifti2Image) or image.shape[1] != 91282:
        raise TypeError('Expected an fsLR 91k CIFTI time series')
    time_axis, brain_axis = image.header.get_axis(0), image.header.get_axis(1)
    if not isinstance(time_axis, nib.cifti2.SeriesAxis) or not isinstance(brain_axis, nib.cifti2.BrainModelAxis):
        raise TypeError('Unexpected CIFTI axes')
    tr = float(json.loads(sidecar.read_text())['RepetitionTime'])
    if time_axis.unit != 'SECOND' or not np.isclose(time_axis.step, tr, atol=1e-5) or image.shape[0] != nib.load(raw).shape[3]:
        raise ValueError('CIFTI time axis does not match the original BOLD series')
    first, constant = constants(image.dataobj)
    structures = {name: (sl, model) for name, sl, model in brain_axis.iter_structures()}
    ribbon_img, atlas_img = nib.load(ribbon), nib.load(atlas)
    for p in (anat, template, target):
        if ',' in str(p):
            raise ValueError('Docker bind paths containing commas are unsupported')
    rows, summaries, commands = [], [], []
    for hemi, structure, native, sphere, target_sphere, roi, surface in hemis:
        if structure not in structures:
            raise ValueError(f'Missing {structure} from CIFTI')
        sl, model = structures[structure]
        if brain_axis.nvertices[structure] != 32492:
            raise ValueError('CIFTI cortex does not use fsLR 32k vertices')
        output_name = f'hemi-{hemi}_desc-individualCortex_resampled.func.gii'
        command = ['docker', 'run', '--rm', '--pull', 'never', '--platform', 'linux/amd64',
                   '--network', 'none', '--cpus', '1', '--memory', '2g',
                   '--mount', f'type=bind,src={anat},dst=/anat,readonly',
                   '--mount', f'type=bind,src={template},dst=/tpl,readonly',
                   '--mount', f'type=bind,src={target},dst=/qc',
                   '--entrypoint', 'wb_command', image_digest, '-metric-resample',
                   '/anat/' + native.name, '/anat/' + sphere.name, '/tpl/' + target_sphere.name,
                   'BARYCENTRIC', '/qc/' + output_name]
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        commands.append({'command': command, 'exit_code': process.returncode,
                         'stdout': process.stdout, 'stderr': process.stderr})
        if process.returncode:
            raise ValueError(f'Workbench resampling failed for {sub}/{ses}/{hemi}: {process.stderr}')
        out_mask = target / output_name
        if not out_mask.is_file():
            raise ValueError('Workbench did not create the expected output mask')
        individual_values = np.asarray(nib.load(out_mask).darrays[0].data)
        standard_values = np.asarray(nib.load(roi).darrays[0].data)
        local_zero = constant[sl] & (first[sl] == 0)
        zero_vertices = model.vertex[local_zero]
        counts = compare_cortex(model.vertex, zero_vertices, individual_values, standard_values)
        coords = np.asarray(nib.load(surface).darrays[0].data)
        if coords.shape != (32492, 3) or not np.isfinite(coords).all():
            raise ValueError('Invalid fsLR surface coordinates')
        local_coords = coords[zero_vertices]
        ribbon_values = sample_nearest(ribbon_img, local_coords)
        atlas_values = sample_nearest(atlas_img, local_coords).astype(int)
        labels, counts_per_label = np.unique(atlas_values, return_counts=True)
        counts.update(hemisphere=hemi, constant_nonzero_vertices=int(np.count_nonzero(constant[sl] & (first[sl] != 0))),
                      constant_zero_outside_ribbon_nearest=int(np.count_nonzero(ribbon_values == 0)),
                      nearest_aparcaseg_label_counts={str(k): int(v) for k, v in zip(labels, counts_per_label)},
                      resampled_individual_mask=str(out_mask), resampled_individual_mask_sha256=local.sha(out_mask))
        summaries.append(counts)
        for vertex, val, rb, label in zip(zero_vertices, individual_values[zero_vertices], ribbon_values, atlas_values):
            rows.append({'hemisphere': hemi, 'vertex': int(vertex), 'individual_cortex_interpolated_value': float(val),
                         'template_roi_included': True, 'inside_anatomical_ribbon_nearest': bool(rb),
                         'nearest_aparcaseg_label': int(label)})
    counts_by_structure = []
    for name, sl, model in brain_axis.iter_structures():
        selected = constant[sl]
        counts_by_structure.append({'structure': name, 'grayordinates': len(model),
                                    'constant_zero': int(np.count_nonzero(selected & (first[sl] == 0))),
                                    'constant_nonzero': int(np.count_nonzero(selected & (first[sl] != 0)))})
    if before != {str(p): local.sha(p) for p in inputs}:
        raise ValueError('An input changed during the CIFTI coverage check')
    columns = ['hemisphere', 'vertex', 'individual_cortex_interpolated_value',
               'template_roi_included', 'inside_anatomical_ribbon_nearest', 'nearest_aparcaseg_label']
    table = target / 'constant_cortical_vertices.tsv'
    pd.DataFrame(rows, columns=columns).to_csv(table, sep='\t', index=False)
    value = {'time': local.now(), 'status': 'coverage_diagnostic_completed_researcher_review_required',
             'case': case, 'fmriprep_execution_record': str(source_record),
             'input_sha256': before, 'CIFTI_shape': list(image.shape),
             'time_axis_unit': time_axis.unit, 'TR_seconds': float(time_axis.step),
             'constant_grayordinates': int(constant.sum()), 'constant_zero_grayordinates': int(np.count_nonzero(constant & (first == 0))),
             'by_structure': counts_by_structure, 'hemispheres': summaries,
             'individual_mask_interpolation': 'Workbench metric-resample BARYCENTRIC using subject MSM-sulc registration',
             'exploratory_interpolated_mask_threshold': 0.5,
             'anatomical_sampling': 'Nearest voxel at subject fsLR surface coordinates; labels are not clinical diagnoses.',
             'commands': commands, 'table_sha256': local.sha(table), 'source_sha256': local.sha(__file__),
             'scope': 'QC evidence only; no masks or CIFTI values are changed and no scientific inclusion is decided.'}
    local.dump(target / 'coverage_qc.json', value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.local.yaml'))
    parser.add_argument('--subject', help='Optionally inspect one configured participant')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    cfg = local.load(args.config)
    root = local.runtime(cfg)
    output = args.output_dir.resolve()
    if any(not disjoint(output, root / name) for name in ('bids', 'derivatives', 'templateflow')):
        raise ValueError('QC output must be disjoint from input data and templates')
    if output.exists():
        raise ValueError('Use a new output directory; existing QC results are never overwritten')
    cases = [case for case in cfg['runs'] if not args.subject or case['subject'] == args.subject]
    if not cases:
        raise ValueError('No configured participant selected')
    for case in cases:
        if not re.fullmatch('[A-Za-z0-9]+', case['subject']) or not re.fullmatch('[A-Za-z0-9]+', case['session']):
            raise ValueError('Subject and session must be BIDS alphanumeric')
    records = [(case, *qc.latest_run(cfg, case, 'fmriprep')) for case in cases]
    output.mkdir(parents=True)
    completed = []
    try:
        for case, path, record in records:
            target = output / f"sub-{case['subject']}_ses-{case['session']}"
            target.mkdir()
            completed.append(examine(cfg, case, target, record['image']['resolved'], path))
        local.dump(output / 'run.json', {'time': local.now(), 'status': 'completed_researcher_review_required',
                                        'subjects': [v['case'] for v in completed], 'source_sha256': local.sha(__file__)})
    except Exception as exc:
        local.dump(output / 'run.json', {'time': local.now(), 'status': 'failed', 'error': f'{type(exc).__name__}: {exc}',
                                        'completed_cases': [v['case'] for v in completed]})
        raise
    print(json.dumps({'status': 'completed_researcher_review_required', 'visits': len(completed), 'output': str(output)}))


if __name__ == '__main__':
    main()
