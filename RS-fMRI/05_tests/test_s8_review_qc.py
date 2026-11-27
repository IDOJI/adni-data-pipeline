"""Synthetic checks for per-reconstruction quality and incomplete evidence."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1] / 'pipeline/s8_final_qc'


def load(name):
    spec = importlib.util.spec_from_file_location('review_' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qc = load('finalize_inclusion')
motion = load('summarize_motion_from_confounds')


@pytest.mark.parametrize('bad', [-324, -576])
def test_bad_visit_neither_hidden_nor_spread_to_good_visit(bad):
    rows = [dict(sub=f'synthetic-{i}', ses='ses-1', site='site', avg_en=-100) for i in range(9)]
    rows += [dict(sub='target', ses='ses-1', site='site', avg_en=-100),
             dict(sub='target', ses='ses-2', site='site', avg_en=bad)]
    result = qc.assess_sessionwise_euler(pd.DataFrame(rows))
    assert result[result['sub'] == 'target'].exclude_euler.tolist() == [0, 1]


def test_duplicate_bold_runs_do_not_expand_euler_reference():
    rows = [dict(sub=f'synthetic-{i}', ses='ses-1', site='site', avg_en=-100) for i in range(3)]
    result = qc.assess_sessionwise_euler(pd.DataFrame(rows * 10))
    assert len(result) == 3
    assert result.euler_reference_subjects.tolist() == [3, 3, 3]
    assert set(result.euler_qc_status) == {'insufficient_reference'}
    assert result.exclude_euler.isna().all()


def test_invalid_euler_is_held_and_conflicting_session_is_rejected():
    rows = [dict(sub='target', ses='ses-1', site='site', avg_en=np.nan)]
    result = qc.assess_sessionwise_euler(pd.DataFrame(rows))
    assert result.iloc[0].euler_qc_status == 'invalid_metric'
    rows += [dict(sub='target', ses='ses-1', site='site', avg_en=-100)]
    with pytest.raises(ValueError, match='Conflicting Euler'):
        qc.assess_sessionwise_euler(pd.DataFrame(rows))


def test_noninitial_missing_fd_cannot_be_counted_as_low_motion(tmp_path):
    confounds = tmp_path / 'sub-synthetic_ses-1_task-rest_desc-confounds_timeseries.tsv'
    pd.DataFrame({'framewise_displacement': [np.nan, np.nan, np.nan, .6]}).to_csv(confounds, sep='\t', index=False)
    with pytest.raises(ValueError, match='only the first'):
        motion.process_confounds(confounds, .5)


def test_missing_mriqc_is_nullable_even_if_excluded_false():
    flags = qc.mriqc_exclude_column(pd.DataFrame({'excluded_any': [False, True],
                                                'qc_metrics_complete': [False, False]}))
    assert pd.isna(flags.iloc[0]) and flags.iloc[1] == 1


def test_standalone_missing_qc_is_pending_and_tsv_is_supported(tmp_path):
    rows = [dict(sub='target', ses='ses-1', mean_fd_p=.1, prop_fd_p_over_thresh=.1)]
    pd.DataFrame(rows).to_csv(tmp_path / 'motion.tsv', sep='\t', index=False)
    pd.DataFrame([dict(sub='other', ses='ses-1', site='site', avg_en=-100)]).to_csv(tmp_path / 'euler.tsv', sep='\t', index=False)
    pd.DataFrame([dict(sub='other', ses='ses-1', excluded_any=False)]).to_csv(tmp_path / 'iqm.tsv', sep='\t', index=False)
    command = [sys.executable, str(ROOT / 'finalize_inclusion.py'), '--motion-summary', str(tmp_path / 'motion.tsv'),
               '--euler-summary', str(tmp_path / 'euler.tsv'), '--iqm-outliers', str(tmp_path / 'iqm.tsv'),
               '--output-dir', str(tmp_path / 'output')]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert pd.read_csv(tmp_path / 'output/included_sessions.tsv', sep='\t').empty
    pending = pd.read_csv(tmp_path / 'output/pending_review.tsv', sep='\t')
    assert len(pending) == 1 and pending.iloc[0].qc_status == 'pending_review'
    (tmp_path / 'iqm.tsv').unlink()
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
