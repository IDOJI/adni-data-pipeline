from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
import pytest

source = Path(__file__).parents[1] / '02_custom/s8a_motion_duration_qc/run.py'
spec = importlib.util.spec_from_file_location('paper_motion_qc', source)
paper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper)


def test_exact_300_seconds_passes_but_dummy_sensitivity_fails():
    fd = np.zeros(200); fd[0] = np.nan
    dummy = np.zeros(200, dtype=bool); dummy[:3] = True
    result, mask = paper.summarize(fd, dummy, Decimal('1.5'))
    assert result['paper_motion_duration_gate_pass']
    assert result['retained_after_FD_only_seconds'] == 300
    assert result['retained_after_FD_and_nonsteady_seconds'] == 295.5
    assert not result['nonsteady_sensitivity_retained_duration_pass']
    assert result['first_FD_undefined_treated_as_zero']
    assert list(mask['original_frame_index_zero_based']) == list(range(200))


def test_threshold_boundaries_use_strict_greater_than():
    fd = np.zeros(200); fd[:60] = 0.50001; fd[60] = 0.5
    result, mask = paper.summarize(fd, np.zeros(200), 1.5, min_seconds=Decimal('1'))
    assert result['motion_censored_frames'] == 60
    assert result['paper_FD_fraction_criterion_pass']
    assert not bool(mask.loc[60, 'FD_above_threshold'])
    fd[60] = 0.50001
    result, _ = paper.summarize(fd, np.zeros(200), 1.5, min_seconds=Decimal('1'))
    assert not result['paper_FD_fraction_criterion_pass']


def test_overlapping_dummy_and_motion_frames_are_counted_only_once():
    fd = [np.nan, 0.6, 0.1, 0.7, 0.1]
    result, mask = paper.summarize(fd, [True, True, False, False, False], 1.5,
                                   min_seconds=Decimal('1'))
    assert result['retained_after_FD_only_frames'] == 3
    assert result['retained_after_FD_and_nonsteady_frames'] == 2
    assert mask['retain_FD_and_nonsteady'].tolist() == [False, False, True, False, True]


@pytest.mark.parametrize('fd', [[np.nan, np.nan], [0.1, float('inf')], [-0.1, 0.0]])
def test_invalid_fd_never_becomes_a_good_frame(fd):
    with pytest.raises(ValueError):
        paper.summarize(fd, [False, False], 1.5)


def make_inputs(tmp_path):
    bids, prep = tmp_path / 'bids', tmp_path / 'derivatives'
    sub, ses = 'sub-999S9999', 'ses-20200101'
    stem = f'{sub}_{ses}_task-rest'
    rawdir = bids / sub / ses / 'func'; rawdir.mkdir(parents=True)
    func = prep / sub / ses / 'func'; func.mkdir(parents=True)
    image = nib.Nifti1Image(np.zeros((2, 2, 2, 200), dtype=np.float32), np.eye(4))
    image.header.set_xyzt_units('mm', 'sec')
    image.header.set_zooms((1., 1., 1., 1.5))
    nib.save(image, rawdir / (stem + '_bold.nii.gz'))
    (rawdir / (stem + '_bold.json')).write_text(json.dumps({'RepetitionTime': 1.5}))
    f = np.zeros(200); f[0] = np.nan
    frame = pd.DataFrame({'framewise_displacement': f})
    for j in range(3):
        col = np.zeros(200); col[j] = 1
        frame[f'non_steady_state_outlier{j:02}'] = col
    frame.to_csv(func / (stem + '_desc-confounds_timeseries.tsv'), sep='\t', index=False)
    return bids, prep, rawdir


def test_actual_format_roundtrip_preserves_inputs_and_frame_indices(tmp_path):
    bids, prep, raw = make_inputs(tmp_path)
    before = paper.sha(next(raw.glob('*nii.gz')))
    out = tmp_path / 'fresh-qc'
    paper.process(bids, prep, out)
    table = pd.read_csv(out / 'paper_motion_summary.tsv', sep='\t')
    assert table.loc[0, 'retained_after_FD_only_seconds'] == 300
    assert table.loc[0, 'retained_after_FD_and_nonsteady_seconds'] == 295.5
    assert paper.sha(next(raw.glob('*nii.gz'))) == before
    mask = pd.read_csv(next(out.glob('*mask.tsv')), sep='\t')
    assert mask['original_frame_index_zero_based'].tolist() == list(range(200))
    assert json.loads((out / 'paper_motion_provenance.json').read_text())['results'][0]['nonsteady_frames'] == 3
    with pytest.raises(ValueError, match='never overwritten'):
        paper.process(bids, prep, out)


def test_mismatched_TR_and_output_inside_input_are_rejected(tmp_path):
    bids, prep, raw = make_inputs(tmp_path)
    sidecar = next(raw.glob('*.json'))
    sidecar.write_text(json.dumps({'RepetitionTime': 2.0}))
    with pytest.raises(ValueError, match='repetition times disagree'):
        paper.process(bids, prep, tmp_path / 'qc')
    assert not (tmp_path / 'qc').exists()
    with pytest.raises(ValueError, match='disjoint'):
        paper.process(bids, prep, bids / 'qc')
