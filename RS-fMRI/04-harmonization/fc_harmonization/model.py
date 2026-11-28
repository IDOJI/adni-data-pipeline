"""Cross-sectional ComBat design, fitted estimates and descriptive diagnostics."""
from collections import Counter
from contextlib import redirect_stdout
import sys
from importlib.metadata import version

import numpy as np
import pandas as pd


def design(cohort, minimum):
    problems = []
    frame = pd.DataFrame(cohort, columns=['batch', 'age', 'sex', 'diagnosis'])
    counts = Counter(frame.batch)
    if len(counts) < 2:
        problems.append('fewer_than_two_batches')
    if any(n < minimum for n in counts.values()):
        problems.append('undersized_batch')
    if frame.empty:
        return frame, [], np.empty((0, 0)), problems + ['empty_cohort']
    columns = {'intercept': np.ones(len(frame)), 'age': frame.age.astype(float).to_numpy()}
    for term in ('sex', 'diagnosis', 'batch'):
        levels = sorted(frame[term].unique())
        if len(levels) < 2 and term != 'batch':
            problems.append('no_variation_in_' + term)
        for level in levels[1:]:
            columns[term + '=' + level] = (frame[term] == level).astype(float).to_numpy()
    matrix = np.column_stack(list(columns.values()))
    if np.linalg.matrix_rank(matrix) < matrix.shape[1]:
        problems.append('confounded_or_rank_deficient_design')
    if len(frame) <= matrix.shape[1]:
        problems.append('no_residual_degrees_of_freedom')
    return frame, list(columns), matrix, problems


def feature_check(z, matrix):
    beta = np.linalg.lstsq(matrix, z, rcond=None)[0]
    residual = z - matrix @ beta
    # neuroCombat divides by featurewise pooled residual variance.
    return bool(np.any(np.max(np.abs(residual), axis=0)
                       <= 1e-12 * np.maximum(1, np.max(np.abs(z), axis=0))))


def fit(raw_z, frame, matrix, terms, output):
    try:
        from neuroCombat import neuroCombat
    except ImportError as exc:
        raise ValueError('Install pipeline/s14_fc_harmonization/requirements.txt before fitting') from exc
    if version('neuroCombat') != '0.2.12':
        raise ValueError('Install the Step 14 software lock')
    with redirect_stdout(sys.stderr), np.errstate(over='raise', divide='raise', invalid='raise'):
        result = neuroCombat(dat=raw_z.T, covars=frame, batch_col='batch',
                             categorical_cols=['sex', 'diagnosis'], continuous_cols=['age'],
                             eb=True, parametric=True, mean_only=False)
    adjusted = np.asarray(result['data']).T
    if adjusted.shape != raw_z.shape or not np.isfinite(adjusted).all():
        raise ValueError('Invalid adjusted FC returned by neuroCombat')
    estimates = {k: np.asarray(v, dtype=str if k == 'batches' else float)
                 for k, v in result['estimates'].items()}
    if any(not np.isfinite(v).all() for k, v in estimates.items() if k != 'batches'):
        raise ValueError('Nonfinite fitted ComBat estimate')
    np.savez_compressed(output / 'model.npz', **estimates)
    coefficients = {}
    diagnostics = {}
    for name, values in [('before', raw_z), ('after', adjusted)]:
        beta = np.linalg.lstsq(matrix, values, rcond=None)[0]
        coefficients[name] = beta
        residual = values - matrix @ beta
        diagnostics[name] = {
            'median_absolute_edge_coefficient': dict(zip(terms, np.median(np.abs(beta), axis=1).tolist())),
            'median_residual_sd_by_batch': {batch: float(np.median(residual[frame.batch == batch].std(axis=0, ddof=1)))
                                            for batch in sorted(frame.batch.unique())},
        }
    np.savez_compressed(output / 'edge_coefficients.npz', terms=np.asarray(terms), **coefficients)
    return adjusted, diagnostics
