#!/usr/bin/env python3
"""Verify fMRIPrep fsnative functional surfaces without changing outputs."""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import qc
import run as local


def validate_frames(arrays, vertices, frames):
    if frames < 2 or vertices < 1 or len(arrays) != frames:
        raise ValueError('Native surface frame count mismatch')
    first = np.asarray(arrays[0].data)
    if first.shape != (vertices,):
        raise ValueError('Native surface vertex count mismatch')
    constant = np.ones(vertices, dtype=bool)
    nonfinite = 0
    for item in arrays:
        data = np.asarray(item.data)
        if data.shape != (vertices,):
            raise ValueError('Native surface vertex count mismatch')
        nonfinite += int(np.count_nonzero(~np.isfinite(data)))
        constant &= data == first
    if nonfinite:
        raise ValueError(f'Native functional surface has {nonfinite} nonfinite values')
    return {'frames': frames, 'vertices': vertices, 'nonfinite_values': nonfinite,
            'constant_vertices': int(constant.sum()),
            'constant_zero_vertices': int(np.count_nonzero(constant & (first == 0)))}


def disjoint(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a != b and a not in b.parents and b not in a.parents


def examine(cfg, case):
    root = local.runtime(cfg)
    execution, _ = qc.latest_run(cfg, case, 'fmriprep')
    sub, ses = 'sub-' + case['subject'], 'ses-' + case['session']
    prefix = f'{sub}_{ses}'
    folder = root / 'derivatives/fmriprep' / sub / ses
    raw_paths = local.paths_for(cfg, case)
    raw = nib.load(raw_paths['bold'])
    tr = float(json.loads(raw_paths['bold_json'].read_text())['RepetitionTime'])
    records = []
    for hemi in ('L', 'R'):
        gifti = qc.one((folder / 'func').glob(f'{prefix}_task-rest*hemi-{hemi}_space-fsnative_bold.func.gii'), 'fsnative BOLD')
        sidecar = gifti.with_name(gifti.name.replace('.func.gii', '.json'))
        white = qc.one((folder / 'anat').glob(f'{prefix}_hemi-{hemi}_white.surf.gii'), 'native white surface')
        if not sidecar.is_file():
            raise ValueError('Missing functional surface JSON sidecar')
        inputs = [gifti, sidecar, white, raw_paths['bold'], raw_paths['bold_json']]
        before = {str(p): local.sha(p) for p in inputs}
        metadata = json.loads(sidecar.read_text())
        if not np.isclose(float(metadata['RepetitionTime']), tr, atol=1e-5):
            raise ValueError('Functional surface TR mismatch')
        vertices = nib.load(white).darrays[0].data.shape[0]
        image = nib.load(gifti)
        stats = validate_frames(image.darrays, vertices, raw.shape[3])
        if before != {str(p): local.sha(p) for p in inputs}:
            raise ValueError('An input changed during fsnative validation')
        records.append({'hemisphere': hemi, 'surface': str(gifti), 'TR_seconds': tr,
                        'slice_timing_corrected': metadata.get('SliceTimingCorrected'),
                        'input_sha256': before, **stats})
        del image
        gc.collect()
    return {'case': case, 'fmriprep_execution': str(execution), 'hemispheres': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.local.yaml'))
    parser.add_argument('--subject', help='Optionally inspect one configured participant')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cfg = local.load(args.config)
    root = local.runtime(cfg)
    output = args.output.resolve()
    if any(not disjoint(output, root / name) for name in ('bids', 'derivatives', 'templateflow')):
        raise ValueError('QC output must be disjoint from input data and templates')
    if output.exists():
        raise ValueError('Refusing to overwrite an existing QC report')
    cases = [case for case in cfg['runs'] if not args.subject or case['subject'] == args.subject]
    if not cases:
        raise ValueError('No configured participant selected')
    visits = [examine(cfg, case) for case in cases]
    value = {'time': local.now(), 'status': 'fsnative_technical_checks_completed_researcher_review_required',
             'visits': visits, 'source_sha256': local.sha(__file__),
             'scope': 'Dimensions, TR and finite values only; no scientific inclusion decision or data modification.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
    print(json.dumps({'status': value['status'], 'visits': len(visits), 'output': str(output)}))


if __name__ == '__main__':
    main()
