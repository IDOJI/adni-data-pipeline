#!/usr/bin/env python3
"""Evaluate Rutherford et al. (2026 v3) FD and five-minute criteria.

This is separate from the repository's final-QC script, which does not compute
post-censoring retained duration. It writes frame masks and summary evidence;
it never modifies or physically removes time points from the input images.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inputs_are_separate(output, *inputs):
    output = Path(output).resolve()
    for value in inputs:
        path = Path(value).resolve()
        if output == path or output in path.parents or path in output.parents:
            raise ValueError('QC output directory must be disjoint from each input tree')


def summarize(fd, nonsteady, tr, threshold=0.5, max_fraction=Decimal('0.30'),
              min_seconds=Decimal('300')):
    fd = np.asarray(fd, dtype=float).copy()
    nonsteady = np.asarray(nonsteady, dtype=bool)
    if fd.ndim != 1 or len(fd) == 0 or nonsteady.shape != fd.shape:
        raise ValueError('FD and non-steady-state masks must be nonempty and aligned')
    if not np.isfinite(fd[1:]).all() or (np.isfinite(fd) & (fd < 0)).any():
        raise ValueError('FD may be undefined only at the first frame and cannot be negative')
    first_undefined = bool(np.isnan(fd[0]))
    if first_undefined:
        fd[0] = 0.0  # Same first-frame convention as the upstream motion script.
    if not np.isfinite(fd).all() or not np.isfinite(threshold) or threshold < 0:
        raise ValueError('FD and threshold must be finite and nonnegative')
    tr = Decimal(str(tr))
    if not tr.is_finite() or tr <= 0 or not (Decimal(0) <= max_fraction <= Decimal(1)):
        raise ValueError('Invalid TR or censoring fraction')
    if not min_seconds.is_finite() or min_seconds <= 0:
        raise ValueError('Minimum retained seconds must be positive and finite')
    high = fd > threshold
    n = len(fd)
    n_high = int(high.sum())
    n_low = n - n_high
    n_sensitivity = int((~high & ~nonsteady).sum())
    proportion = Decimal(n_high) / Decimal(n)
    seconds = Decimal(n_low) * tr
    sensitivity_seconds = Decimal(n_sensitivity) * tr
    result = {'total_frames': n, 'first_FD_undefined_treated_as_zero': first_undefined,
              'motion_censored_frames': n_high, 'motion_censored_fraction': float(proportion),
              'retained_after_FD_only_frames': n_low, 'retained_after_FD_only_seconds': float(seconds),
              'paper_FD_fraction_criterion_pass': proportion <= max_fraction,
              'paper_retained_duration_criterion_pass': seconds >= min_seconds,
              'paper_motion_duration_gate_pass': proportion <= max_fraction and seconds >= min_seconds,
              'nonsteady_frames': int(nonsteady.sum()),
              'retained_after_FD_and_nonsteady_frames': n_sensitivity,
              'retained_after_FD_and_nonsteady_seconds': float(sensitivity_seconds),
              'nonsteady_sensitivity_retained_duration_pass': sensitivity_seconds >= min_seconds}
    mask = pd.DataFrame({'original_frame_index_zero_based': np.arange(n),
                         'framewise_displacement_mm': fd, 'FD_above_threshold': high,
                         'nonsteady_state': nonsteady, 'retain_FD_only': ~high,
                         'retain_FD_and_nonsteady': ~high & ~nonsteady})
    return result, mask


def process(bids_root, derivatives_root, output_dir):
    bids, derivatives, output = (Path(x).resolve() for x in (bids_root, derivatives_root, output_dir))
    inputs_are_separate(output, bids, derivatives)
    if not bids.is_dir() or not derivatives.is_dir():
        raise ValueError('Both BIDS and fMRIPrep input directories must exist')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Use a new or empty output directory; existing files are never overwritten')
    paths = sorted(derivatives.glob('sub-*/ses-*/func/*_desc-confounds_timeseries.tsv'))
    if not paths:
        raise ValueError('No session-level fMRIPrep confounds were found')
    rows, records, masks = [], [], []
    ending = '_desc-confounds_timeseries.tsv'
    for confounds in paths:
        subject, session = confounds.parents[2].name, confounds.parents[1].name
        stem = confounds.name[:-len(ending)]
        if not stem.startswith(subject + '_' + session + '_') or '_task-' not in stem:
            raise ValueError(f'Confounds name does not match its BIDS subject/session: {confounds}')
        raw_dir = bids / subject / session / 'func'
        sidecar = raw_dir / (stem + '_bold.json')
        raw = raw_dir / (stem + '_bold.nii.gz')
        if not raw.is_file() or not sidecar.is_file():
            raise ValueError(f'Missing matching BIDS BOLD image or JSON: {stem}')
        metadata = json.loads(sidecar.read_text(), parse_float=Decimal)
        try:
            tr = Decimal(str(metadata['RepetitionTime']))
        except (KeyError, InvalidOperation) as exc:
            raise ValueError(f'Missing or invalid RepetitionTime for {stem}') from exc
        image = nib.load(raw)
        if len(image.shape) != 4 or image.header.get_xyzt_units()[1] != 'sec':
            raise ValueError(f'Expected a 4-D BOLD image with seconds as time units: {raw}')
        if not np.isclose(float(tr), image.header.get_zooms()[3], rtol=0, atol=1e-5):
            raise ValueError(f'BIDS JSON and NIfTI repetition times disagree: {raw}')
        df = pd.read_csv(confounds, sep='\t')
        if len(df) != image.shape[3] or 'framewise_displacement' not in df:
            raise ValueError(f'Confounds row count or FD column mismatch: {confounds}')
        fd = pd.to_numeric(df['framewise_displacement'], errors='raise').to_numpy(dtype=float)
        first_undefined = bool(np.isnan(fd[0]))
        dummy_cols = [name for name in df if name.startswith('non_steady_state_outlier')]
        if dummy_cols:
            dummy_values = df[dummy_cols].apply(pd.to_numeric, errors='raise').to_numpy(dtype=float)
            if not np.isfinite(dummy_values).all() or not np.isin(dummy_values, [0, 1]).all():
                raise ValueError(f'Invalid non-steady-state indicators: {confounds}')
            nonsteady = (dummy_values != 0).any(axis=1)
        else:
            nonsteady = np.zeros(len(df), dtype=bool)
        values, mask = summarize(fd, nonsteady, tr)
        values['first_FD_undefined_treated_as_zero'] = first_undefined
        values = {'participant_id': subject, 'session_id': session, 'bids_stem': stem,
                  'TR_seconds': float(tr), **values}
        rows.append(values)
        name = stem + '_desc-paper_motion_mask.tsv'
        masks.append((name, mask))
        records.append({'confounds': str(confounds), 'confounds_sha256': sha(confounds),
                        'BOLD': str(raw), 'BOLD_sha256': sha(raw),
                        'BOLD_JSON': str(sidecar), 'BOLD_JSON_sha256': sha(sidecar),
                        'nonsteady_columns': dummy_cols, 'mask': name})
    output.mkdir(parents=True, exist_ok=True)
    for name, mask in masks:
        mask.to_csv(output / name, sep='\t', index=False)
    pd.DataFrame(rows).to_csv(output / 'paper_motion_summary.tsv', sep='\t', index=False)
    evidence = {'source': 'https://arxiv.org/pdf/2602.03278v3',
                'status': 'motion_and_duration_evaluated_research_inclusion_pending',
                'paper_rules': {'FD_cutoff_mm_strictly_above': 0.5, 'maximum_motion_censored_fraction': 0.30,
                                'minimum_low_motion_seconds': 300},
                'frame_convention': 'All fMRIPrep output frames and first undefined FD=0, matching the repository motion utility.',
                'nonsteady_sensitivity': 'Separately excludes non-steady-state frames; the paper does not specify this detail in its final-QC paragraph.',
                'scope': 'Flags and masks only; images and time points are not modified. Upstream mean-FD criterion, representative-cohort MRIQC/Euler calibration, and visual QC remain separate.',
                'inputs': records, 'results': rows, 'tool_sha256': sha(__file__)}
    (output / 'paper_motion_provenance.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'visits': len(rows), 'output': str(output), 'status': evidence['status']}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bids-root', required=True, type=Path)
    p.add_argument('--derivatives-root', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    a = p.parse_args()
    process(a.bids_root, a.derivatives_root, a.output_dir)


if __name__ == '__main__':
    main()
