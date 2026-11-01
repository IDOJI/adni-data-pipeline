#!/usr/bin/env python3
"""Describe mask exclusion versus EPI reference and anatomical tissue support; never change QC."""
import argparse
import json
from pathlib import Path
import sys
import nibabel as nb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import finish, new_output, read, sha, snapshot, write, verify_bundle
sys.path.insert(0, str(Path(__file__).resolve().parent))
from atlas_contracts import entities, grid_equal


def diagnose(extraction, mask, boldref, t1w, gm_probability, anatomical_mask, output_dir):
    folder = Path(extraction).resolve(); rec = verify_bundle(folder, 'atlas_bold_timeseries_v1')
    required = {'atlas_on_bold_grid.nii.gz', 'roi_coverage.tsv'}
    if not required <= set(rec['outputs_sha256']): raise ValueError('Missing extraction evidence')
    paths = [Path(__file__).with_name('atlas_contracts.py'), folder / 'artifact.json', *[folder / n for n in sorted(required)], mask, boldref, t1w, gm_probability, anatomical_mask]
    output = new_output(output_dir, paths); hashes = snapshot(paths)
    if hashes[str(Path(mask).resolve())] not in rec['inputs_sha256'].values():
        raise ValueError('Diagnostic mask was not used by extraction')
    atlas = nb.load(folder / 'atlas_on_bold_grid.nii.gz'); labels = atlas.get_fdata().astype(int)
    imgs = [nb.load(p) for p in (mask, boldref, t1w, gm_probability, anatomical_mask)]
    reference_entities = entities(boldref)
    for path, image in zip((mask, boldref, t1w, gm_probability, anatomical_mask), imgs):
        e = entities(path)
        if e.get('space') != rec['summary']['space'] or any(e.get(k) != reference_entities.get(k) for k in ('sub', 'ses')):
            raise ValueError('Diagnostic images require matching explicit space/subject/session')
        if len(image.shape) != 3 or not grid_equal(atlas, image) or image.header.get_xyzt_units()[0] != 'mm':
            raise ValueError('Diagnostic images must be 3-D on the atlas/BOLD grid in mm')
    brain, ref, t1, gm, anatomical = [im.get_fdata() for im in imgs]
    if not all(np.isfinite(v).all() for v in (brain, ref, t1, gm, anatomical)) or not np.isin(brain, [0, 1]).all() or not np.isin(anatomical, [0, 1]).all() or np.any((gm < 0) | (gm > 1)):
        raise ValueError('Finite images, binary masks and GM probabilities in [0,1] required')
    def stat(values, mean=False):
        return float(np.mean(values) if mean else np.median(values)) if values.size else None
    result = []
    for row in read(folder / 'roi_coverage.tsv'):
        roi = labels == int(row['label_id']); included = roi & (brain == 1); excluded = roi & (brain == 0)
        n, ni = int(roi.sum()), int(included.sum())
        if n != int(row['bold_grid_voxels']) or ni != int(row['mask_voxels']): raise ValueError('ROI coverage evidence differs from images')
        inside, outside = stat(ref[included]), stat(ref[excluded])
        ratio = outside / inside if outside is not None and inside is not None and inside > 0 else None
        result.append(dict(row, excluded_voxels=n-ni, included_reference_median=inside, excluded_reference_median=outside,
                           excluded_to_included_reference_ratio=ratio, included_gm_probability_mean=stat(gm[included], True),
                           excluded_gm_probability_mean=stat(gm[excluded], True), excluded_anatomical_mask_fraction=stat(anatomical[excluded], True),
                           included_t1_median=stat(t1[included]), excluded_t1_median=stat(t1[excluded]),
                           causal_status='unresolved_signal_mask_anatomy_registration_require_joint_review'))
    output.mkdir(parents=True); write(output / 'coverage_diagnostics.tsv', result)
    return finish(output, 'coverage_diagnostics_v1', hashes, {
        'roi_count': len(result), 'existing_failed_rois': sum(r['qc_status'] == 'fail' for r in result),
        'qc_policy_changed': False, 'causality_established': False, 'implementation_sha256': sha(__file__),
        'scope': 'Descriptive EPI-reference/T1/GM/mask comparison. No rescue, mask expansion, new threshold or registration proof.'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for f in ('extraction', 'mask', 'boldref', 't1w', 'gm-probability', 'anatomical-mask', 'output-dir'): p.add_argument('--'+f, required=True)
    a = vars(p.parse_args())
    try: print(json.dumps(diagnose(**a)['summary'], indent=2))
    except (ValueError, KeyError, FileNotFoundError) as e: p.exit(1, str(e)+'\n')

if __name__ == '__main__': main()
