#!/usr/bin/env python3
"""Preflight simple sessionwise BIDS inputs and create a source hash manifest.

This adapter deliberately accepts one exact T1w and task-rest BOLD per visit.
It does not convert BIDS layouts or infer ADNI phase from participant labels.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import nibabel as nib
import numpy as np
import yaml


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def overlap(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a in b.parents or b in a.parents


def inspect(cfg):
    source = Path(cfg['source_bids']).resolve()
    output = Path(cfg['source_manifest']).resolve()
    runtime = Path(cfg['runtime']).resolve()
    if not source.is_dir() or not (source / 'dataset_description.json').is_file():
        raise ValueError('A BIDS source with dataset_description.json is required')
    if overlap(source, runtime) or overlap(source, output):
        raise ValueError('Source, runtime and source manifest must not overlap the BIDS tree')
    descriptor = json.loads((source / 'dataset_description.json').read_text())
    if not isinstance(descriptor, dict) or not descriptor.get('Name') or not descriptor.get('BIDSVersion'):
        raise ValueError('dataset_description.json requires Name and BIDSVersion')
    runs = cfg.get('runs')
    if not isinstance(runs, list) or not runs:
        raise ValueError('Provide at least one selected visit in runs')
    evidence_path = Path(cfg['source_phase_evidence']).resolve()
    evidence = json.loads(evidence_path.read_text())
    if not isinstance(evidence, list):
        raise TypeError('Phase evidence must be a list of independently documented visits')
    seen, records, details = set(), [], []
    for case in runs:
        sub, ses = str(case['subject']), str(case['session'])
        phase = str(case['phase'])
        if not re.fullmatch('[A-Za-z0-9]+', sub) or not re.fullmatch('[A-Za-z0-9]+', ses):
            raise ValueError('Subject and session labels must be BIDS alphanumeric')
        if (sub, ses) in seen:
            raise ValueError('Duplicate subject/session selected')
        seen.add((sub, ses))
        if phase not in {'ADNIGO', 'ADNI2', 'ADNI3', 'ADNI4'}:
            raise ValueError('Unsupported or unverified ADNI phase')
        if not str(case.get('ptid', '')).strip() or not str(case.get('bold_image_id', '')).strip():
            raise ValueError('Each selected visit requires ptid and bold_image_id')
        folder = source / f'sub-{sub}' / f'ses-{ses}'
        stem = f'sub-{sub}_ses-{ses}'
        t1 = folder / 'anat' / f'{stem}_T1w.nii.gz'
        t1_json = folder / 'anat' / f'{stem}_T1w.json'
        bold = folder / 'func' / f'{stem}_task-rest_bold.nii.gz'
        bold_json = folder / 'func' / f'{stem}_task-rest_bold.json'
        paths = (t1, t1_json, bold, bold_json)
        if not all(path.is_file() for path in paths):
            raise ValueError(f'{stem}: expected one exact T1w/BOLD NIfTI and sidecar per visit')
        t1_candidates = list((folder / 'anat').glob('*_T1w.nii*'))
        bold_candidates = list((folder / 'func').glob('*_task-rest*_bold.nii*'))
        t2_candidates = list((folder / 'anat').glob('*_T2w.nii*'))
        if t1_candidates != [t1] or bold_candidates != [bold] or t2_candidates:
            raise ValueError(f'{stem}: multiple, entity-labelled, or T2w inputs need a different adapter')
        if any(source not in path.resolve().parents for path in paths):
            raise ValueError(f'{stem}: input symlink escapes BIDS root')
        anat, func = nib.load(t1), nib.load(bold)
        if len(anat.shape) != 3 or len(func.shape) != 4 or func.shape[3] < 1:
            raise ValueError(f'{stem}: expected a 3-D T1w and nonempty 4-D BOLD')
        json.loads(t1_json.read_text())
        meta = json.loads(bold_json.read_text())
        tr = float(meta.get('RepetitionTime', 0))
        if not np.isfinite(tr) or tr <= 0 or func.header.get_xyzt_units()[1] != 'sec':
            raise ValueError(f'{stem}: invalid BOLD RepetitionTime or NIfTI time units')
        if not np.isclose(tr, func.header.get_zooms()[3], rtol=0, atol=1e-5):
            raise ValueError(f'{stem}: NIfTI and JSON repetition times differ')
        ped = meta.get('PhaseEncodingDirection')
        if ped not in {'i', 'i-', 'j', 'j-', 'k', 'k-'}:
            raise ValueError(f'{stem}: SyN requires a valid PhaseEncodingDirection')
        slicedirection = meta.get('SliceEncodingDirection', 'k')
        if slicedirection not in {'i', 'i-', 'j', 'j-', 'k', 'k-'}:
            raise ValueError(f'{stem}: invalid SliceEncodingDirection')
        axis = {'i': 0, 'j': 1, 'k': 2}[slicedirection[0]]
        timing = meta.get('SliceTiming')
        if not isinstance(timing, list) or len(timing) != func.shape[axis]:
            raise ValueError(f'{stem}: SliceTiming must match the slice axis')
        try:
            finite_timing = np.isfinite(np.asarray(timing, dtype=float)).all()
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{stem}: invalid SliceTiming') from exc
        if not finite_timing:
            raise ValueError(f'{stem}: nonfinite SliceTiming')
        match = [item for item in evidence if item.get('subject') == sub and str(item.get('session')) == ses]
        if len(match) != 1 or match[0].get('phase') != phase:
            raise ValueError(f'{stem}: exactly one matching independent phase-evidence record required')
        entry = match[0]
        if not entry.get('matched_row') or not entry.get('phase_match_basis'):
            raise ValueError(f'{stem}: phase evidence must describe the matched source row and basis')
        proof = Path(entry.get('evidence_file', ''))
        if not proof.is_file() or sha(proof) != entry.get('evidence_file_sha256'):
            raise ValueError(f'{stem}: phase-evidence source file is missing or has changed')
        if sha(bold_json) != entry.get('bids_metadata_sha256'):
            raise ValueError(f'{stem}: phase evidence does not match this BOLD JSON')
        for path in paths:
            records.append({'path': str(path.relative_to(source)), 'phase': phase,
                            'bytes': path.stat().st_size, 'sha256': sha(path)})
        details.append({'subject': sub, 'session': ses, 'phase': phase, 'TR_seconds': tr,
                        'BOLD_shape': list(func.shape), 'slice_axis': slicedirection,
                        'readout_metadata_present': bool(meta.get('TotalReadoutTime') or meta.get('EffectiveEchoSpacing'))})
    return {'source': str(source), 'created_at': dt.datetime.now(dt.UTC).isoformat(),
            'files': records, 'phase_evidence': str(evidence_path),
            'phase_evidence_sha256': sha(evidence_path),
            'scope': 'Input identity/shape/metadata preflight; phase interpretation and scientific QC remain researcher responsibilities.'}, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true', help='Inspect without writing or replacing a manifest')
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    output = Path(cfg['source_manifest']).resolve()
    if output.exists() and not args.check_only:
        raise ValueError('Refusing to overwrite the existing source manifest')
    manifest, visits = inspect(cfg)
    if not args.check_only:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({'status': 'input_preflight_completed', 'visits': visits,
                      'manifest_written': not args.check_only, 'manifest': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
