"""Exercise normal XCP-D filenames, archive evidence, selection and upstream ComBat."""
from collections import Counter
from pathlib import Path
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pipeline'))
from _shared import finish, read, sha, write
from s10_xcpd_integrated_qc import pipeline as s10
from s14_fc_harmonization import connectome, model, run as stage

LABELS = [f'region-{i:03}' for i in range(256)]


def archive(base, profile, index):
    site = '998' if index < 8 else '999'
    sub = f'{site}S{9000 + index}'
    ptid = f'{site}_S_{9000 + index}'
    date = '2020-03-17'
    image = str(90000 + index)
    pair = base / 'pairs' / sub
    cid = profile['_config_id']
    row = dict.fromkeys(s10.KEYS, '')
    row.update(sub='sub-' + sub, ses='ses-visit', task='task-rest', ptid=ptid, site=site,
               config_id=cid, epi_image_id=image, epi_date=date, pair_id='pair-' + image,
               final_qc_status='include', final_include='True', xcpd_status='success',
               functional_outputs_valid='True', source_pair=str(pair))
    folder = pair / 's10' / cid
    attempt = folder / 'runs' / s10.run_key(row) / 'attempt-001'
    row['xcpd_attempt'] = str(attempt)
    derivatives = attempt / 'derivatives'
    func = derivatives / row['sub'] / row['ses'] / 'func'
    func.mkdir(parents=True)
    prefix = '_'.join([row['sub'], row['ses'], row['task'], 'atlas-4S256Parcels'])
    fc = func / (prefix + '_stat-pearsoncorrelation_relmat.tsv')
    coverage = func / (prefix + '_stat-coverage_bold.tsv')
    rng = np.random.default_rng(index)
    data = rng.normal(size=(100, 256))
    data += rng.normal(size=(100, 1)) * (0.2 + 0.65 * (site == '999') + 0.12 * (index % 3))
    pd.DataFrame(np.corrcoef(data.T), index=LABELS, columns=LABELS).to_csv(fc, sep='\t', float_format='%.8f')
    pd.DataFrame({'coverage': np.ones(256)}, index=LABELS).to_csv(coverage, sep='\t')
    metadata = dict(ptid=ptid, subject=sub, epi_image_id=image, epi_date=date, pair_id=row['pair_id'],
                    execution_session_label='visit', execution_identity={'fmriprep': {
                        'runner_sha256': '0' * 64, 'image': {'resolved': 'example@sha256:' + '1' * 64}}})
    s10.save(pair / 'pair_metadata.json', metadata)
    s10.save(folder / 'configuration.json', profile)
    execution = dict(row=row, status='success', input_unchanged=True, exit_code=0, config_id=cid)
    valid = {k:row[k] for k in s10.KEYS}
    valid.update(config_id=cid, xcpd_status='success', functional_outputs_valid=True)
    s10.save(attempt / 'execution.json', execution)
    s10.save(attempt / 'output_validation.json', valid)
    s10.save(attempt / 'output_manifest.json', {str(p.relative_to(derivatives)):sha(p) for p in (fc, coverage)})
    evidence = {str(p.relative_to(pair)):sha(p) for p in attempt.glob('*.json')}
    s10.save(folder / 'archive_ready.json', dict(subject=sub, config_id=cid, evidence=evidence,
             runs=[{**valid, 'xcpd_attempt':str(attempt)}]))
    clinical = dict(PTID=ptid, sub=row['sub'], ses=row['ses'], IMAGE_ID='I'+image, MRI_STUDY_DATE=date,
                    SOURCE_MODALITY='EPI', SOURCE_QC_STATUS='pass', CLINICAL_STATUS='pass',
                    INCLUSION_STATUS='eligible', BIOLOGICAL_SEX=('Female','Male')[index % 2],
                    MRI_AGE_YEARS=str(60 + (index * 7) % 13), DIAGNOSIS=str(1 + index % 3))
    scanner = dict(ptid=ptid, date=date, image_id=image, site=site, scanner='system',
                   review_ref='review/' + image, preprocessing_profile='synthetic-profile')
    return clinical, row, scanner


def profile():
    cfg = json.loads((ROOT / '03_config/xcpd_linc.seeded.example.json').read_text())
    return {**cfg, '_config_id':cfg['run_id'] + '-' + s10.digest(cfg)[:12]}


def config(tmp_path, records):
    clinical, qc, scanner = zip(*records)
    inc = tmp_path / '9b'
    inc.mkdir()
    write(inc / 'inclusion_audit.tsv', clinical)
    finish(inc, 'final_inclusion_validation_v1', {}, {})
    master = tmp_path / 'final_qc_master.tsv'
    write(master, qc)
    s10.save(master.with_name('summary.json'), dict(cohort_finalization_deferred=False, runs=len(qc),
             counts={'final_qc_status':dict(Counter(r['final_qc_status'] for r in qc))}))
    mapping = tmp_path / 'scanner_map.tsv'
    write(mapping, scanner)
    conf = tmp_path / 'config.json'
    s10.save(conf, dict(inclusion_dir=str(inc), final_qc=str(master), scanner_map=str(mapping),
                        config_id=qc[0]['config_id'], min_batch_size=5, output_dir=str(tmp_path / 'result')))
    return conf


def cli(cfg, *opts):
    return subprocess.run([sys.executable, ROOT / '04_workflow/lab.py', 'harmonize-fc',
                           '--config', cfg, *opts], text=True, capture_output=True)


def test_full_cli_and_upstream_agreement(tmp_path):
    upstream = pytest.importorskip('neuroCombat').neuroCombat
    cfg = profile()
    records = [archive(tmp_path, cfg, i) for i in range(16)]
    conf = config(tmp_path, records)
    proc = cli(conf)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary['status'] == 'fitted' and summary['selected_participants'] == 16
    out = tmp_path / 'result'
    cohort = read(out / 'cohort.tsv')
    edges = read(out / 'edges.tsv')
    assert len(edges) == 32640 and edges[0]['roi_j'] == LABELS[1] and edges[-1]['roi_j'] == LABELS[-1]
    fc = np.load(out / 'fc.npz')
    first_source = next(Path(records[0][1]['xcpd_attempt']).rglob('*relmat.tsv'))
    ref = pd.read_csv(first_source, sep='\t', index_col=0).values
    assert fc['raw_r'].shape == (16, 32640)
    np.testing.assert_allclose(fc['raw_r'][0], ref[np.triu_indices(256, 1)])
    np.testing.assert_allclose(fc['raw_z'], np.arctanh(fc['raw_r']))
    frame = pd.DataFrame(cohort)[['batch','age','sex','diagnosis']].astype({'age':float})
    expected = upstream(fc['raw_z'].T, frame, 'batch', categorical_cols=['sex','diagnosis'],
                        continuous_cols=['age'])['data'].T
    np.testing.assert_allclose(fc['adjusted_z'], expected)
    np.testing.assert_allclose(fc['adjusted_r'], np.tanh(expected))
    assert np.median(np.abs(fc['adjusted_z'][8:].mean(0) - fc['adjusted_z'][:8].mean(0))) < 0.5 * np.median(
        np.abs(fc['raw_z'][8:].mean(0) - fc['raw_z'][:8].mean(0)))
    assert all(sha(out / name) == digest for name, digest in s10.load(out / 'artifact.json')['outputs_sha256'].items())
    assert 'gamma.star' in np.load(out / 'model.npz') and read(out / 'batch_design.tsv')
    assert cli(conf).returncode != 0


def test_audit_only_reports_missing_and_exits_without_fit(tmp_path):
    cfg = config(tmp_path, [archive(tmp_path, profile(), 0)])
    settings = s10.load(cfg)
    settings['final_qc'] = str(tmp_path / 'unavailable.tsv')
    s10.save(cfg, settings)
    proc = cli(cfg, '--audit-only')
    assert proc.returncode == 0, proc.stderr
    assert 'missing_final_qc' in json.loads(proc.stdout)['problems']
    assert not (tmp_path / 'result/fc.npz').exists()
    row, = read(tmp_path / 'result/attrition.tsv')
    assert row['reason'] == 'missing_or_ambiguous_final_qc_run' and row['scanner'] == 'system'


@pytest.mark.parametrize('error,reason', [('tampered','changed_evidence'), ('pending','final_qc_pending_review'),
                        ('threshold','roi_coverage_below'), ('site','scanner_site_conflict'),
                        ('dup','missing_or_ambiguous_final_qc_run'), ('clinical','step9b_pending'),
                        ('covariate','incomplete_biological_covariates')])
def test_fail_closed_evidence(tmp_path, error, reason):
    cfg = profile()
    c,q,m = archive(tmp_path, cfg, 0)
    if error == 'tampered':
        p = next(Path(q['xcpd_attempt']).rglob('*relmat.tsv'))
        with p.open('a') as stream:
            stream.write('\n')
    elif error == 'threshold':
        p = next(Path(q['xcpd_attempt']).rglob('*coverage_bold.tsv'))
        p.write_text(p.read_text().replace('1.0','0.4',1))
        fc = next(p.parent.glob('*relmat.tsv'))
        with pytest.raises(ValueError, match=reason):
            connectome.read_edges(fc,p,.5)
        return
    elif error == 'pending':
        q.update(final_qc_status='pending_review',final_include='False')
    elif error == 'clinical':
        c['INCLUSION_STATUS'] = 'pending'
    elif error == 'covariate':
        c['BIOLOGICAL_SEX'] = ''
    elif error == 'site':
        q['site'] = '001'
    audit, candidates = stage.assemble([c], [q,q] if error == 'dup' else [q], [m], cfg['_config_id'], {})
    assert candidates == [] and reason in audit[0]['reason']


def test_earliest_requires_documented_tie_choice():
    def candidate(day, ref=''):
        return (dict(ptid='synthetic', date=day, tie_choice_ref=ref),)
    a,b,c = candidate('2020-01-01'),candidate('2020-01-01'),candidate('2021-01-01')
    assert not stage.earliest([c,a,b])
    assert a[0]['reason'] == 'unresolved_earliest_day_tie' and c[0]['reason'] == 'later_eligible_visit'
    b[0]['tie_choice_ref'] = 'review/decision'
    assert stage.earliest([c,a,b]) == [b]


def test_design_confounds_and_zero_variance():
    cohort = [dict(batch=str(i//3), age=i+60, sex=str(i%2), diagnosis=str(i//3)) for i in range(6)]
    _,_,matrix,problems = model.design(cohort, 5)
    assert {'undersized_batch','confounded_or_rank_deficient_design'} <= set(problems)
    assert model.feature_check(np.ones((6,10)),matrix)
