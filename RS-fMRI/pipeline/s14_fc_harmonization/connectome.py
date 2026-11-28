"""Read a single archive-verified XCP-D 4S256 Pearson connectome."""
import json
import re
from pathlib import Path

import numpy as np

from _shared import sha
from s3b_image_selection.selection_identity import image_id, scan_date
from s9b_validate_inclusion.run import participant
from s10_xcpd_integrated_qc import pipeline as s10

ATLAS = '4S256Parcels'
N_ROI = 256
UPPER = np.triu_indices(N_ROI, 1)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_edges(fc_path, coverage_path, threshold):
    fc = s10.read_xcp_tsv(fc_path, index_col=0)
    coverage = s10.read_xcp_tsv(coverage_path, index_col=0)
    labels = list(fc.columns)
    require(len(labels) == N_ROI and list(fc.index) == labels
            and list(coverage.index) == labels and 'coverage' in coverage, 'roi_schema_mismatch')
    cov = coverage['coverage'].to_numpy(dtype=float)
    require(np.all(np.isfinite(cov) & (cov >= threshold) & (cov > 0) & (cov <= 1)),
            'roi_coverage_below_profile_threshold')
    matrix = fc.to_numpy(dtype=float)
    require(np.isfinite(matrix).all() and np.allclose(matrix, matrix.T, atol=1e-7, rtol=0)
            and np.allclose(np.diag(matrix), 1, atol=1e-7, rtol=0), 'invalid_pearson_matrix')
    edges = matrix[UPPER]
    require(np.all(np.abs(edges) < 1), 'undefined_off_diagonal_fisher_z')
    return tuple(labels), edges.copy()


def archived_edges(qc, scanner, config_id, inputs):
    """Resolve relocated evidence by the run key and attempt in the S10 receipt."""
    pair = Path(scanner.get('pair_dir') or qc['source_pair'])
    require(pair.is_absolute(), 'missing_absolute_pair_path')
    stage = pair / 's10' / config_id

    def evidence(path, expected=None):
        digest = sha(path)
        if expected is not None:
            require(digest == expected, 'changed_evidence_' + path.name)
        inputs[str(path.resolve())] = digest
        return path

    def load(path, expected=None):
        return json.loads(evidence(path, expected).read_text())

    meta = load(pair / 'pair_metadata.json')
    require(participant(meta['ptid']) == participant(qc['ptid']) == participant(meta['subject'])
            and image_id(meta['epi_image_id']) == image_id(qc['epi_image_id'])
            and scan_date(meta['epi_date']) == scan_date(qc['epi_date'])
            and qc['ses'] == 'ses-' + meta['execution_session_label']
            and meta['pair_id'] == qc['pair_id'], 'pair_identity_conflict')
    cfg = load(stage / 'configuration.json')
    base = {k: v for k, v in cfg.items() if k != '_config_id'}
    require(config_id == cfg['_config_id'] == cfg['run_id'] + '-' + s10.digest(base)[:12],
            'xcpd_configuration_mismatch')
    require(cfg['task'] == 'rest' and not cfg['combine_runs'] and cfg['input_type'] == 'fmriprep'
            and ATLAS in cfg['atlases'] and cfg['expected_rois'][ATLAS] == N_ROI
            and 0 <= cfg['min_coverage'] <= 1, 'incompatible_xcpd_profile')
    receipt = load(stage / 'archive_ready.json')
    require(receipt['config_id'] == config_id and participant(receipt['subject']) == participant(qc['sub']),
            'archive_identity_conflict')
    run = s10.exact_one((r for r in receipt['runs'] if s10.key(r) == s10.key(qc)), 'archived_run')
    require(run['xcpd_status'] == 'success' and run['functional_outputs_valid'] is True,
            'archived_run_incomplete')
    old = Path(run['xcpd_attempt'])
    relative = Path('s10') / config_id / 'runs' / s10.run_key(qc) / old.name
    require(re.fullmatch(r'attempt-[0-9]+', old.name) and old.parts[-5:] == relative.parts
            and Path(qc['xcpd_attempt']).parts[-5:] == relative.parts, 'attempt_identity_conflict')
    attempt = pair / relative

    def verified(name):
        return load(attempt / name, receipt['evidence'][str(relative / name)])

    execution = verified('execution.json')
    require(execution['status'] == 'success' and execution['exit_code'] == 0
            and execution['input_unchanged'] is True and execution['config_id'] == config_id
            and s10.key(execution['row']) == s10.key(qc)
            and image_id(execution['row']['epi_image_id']) == image_id(qc['epi_image_id'])
            and participant(execution['row']['ptid']) == participant(qc['ptid'])
            and scan_date(execution['row']['epi_date']) == scan_date(qc['epi_date']), 'execution_identity_conflict')
    validation = verified('output_validation.json')
    require(validation['xcpd_status'] == 'success' and validation['functional_outputs_valid'] is True
            and validation['config_id'] == config_id and s10.key(validation) == s10.key(qc), 'xcpd_validation_failed')
    manifest = verified('output_manifest.json')
    root = attempt / 'derivatives'

    def product(suffix):
        path = s10.file_for(root, qc, '*_atlas-' + ATLAS + suffix)
        return evidence(path, manifest[str(path.relative_to(root))])

    labels, edges = read_edges(product('_stat-pearsoncorrelation_relmat.tsv'),
                               product('_stat-coverage_bold.tsv'), cfg['min_coverage'])
    prep = meta['execution_identity']['fmriprep']
    runner, image = prep['runner_sha256'], prep['image']['resolved']
    require(re.fullmatch(r'[a-f0-9]{64}', runner) and re.search(r'@sha256:[a-f0-9]{64}$', image),
            'unverified_preprocessing_identity')
    return labels, edges, (runner, image, scanner['preprocessing_profile'])
