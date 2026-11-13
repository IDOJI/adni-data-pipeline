"""Synthetic run-level clinical fixtures, with ties, longitudinal visits and missing fields."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('clinical_step', ROOT / 'pipeline/s9a_validate_clinical/run.py')
clinical = importlib.util.module_from_spec(spec); spec.loader.exec_module(clinical)


def write(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t' if path.suffix == '.tsv' else ',')
        w.writeheader(); w.writerows(rows)
    return path


def fixture(tmp_path):
    included = write(tmp_path / 'included.tsv', [dict(sub='sub-ADNI999S9999', ses='ses-M000', task='rest', run='1')])
    links = write(tmp_path / 'links.csv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01', Phase='ADNI3', Age='70')])
    dx = write(tmp_path / 'dx.csv', [dict(PTID='999_S_9999', RID='9999', PHASE='ADNI3', EXAMDATE='2020-01-02', DIAGNOSIS='3', DXDDUE='2', DXMDUE='1', HAS_QC_ERROR='0')])
    pt = write(tmp_path / 'pt.csv', [dict(PTID='999_S_9999', RID='9999', VISDATE='2020-01-01', PTEDUCAT='', PTGENDER='1', PTDOB='01/1950')])
    return included, links, dx, pt


def test_dementia_not_ad_and_optional_missing_values_do_not_drop_runs(tmp_path):
    inputs = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in inputs}
    result = clinical.process(*inputs, tmp_path / 'out')
    row = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert row['CLINICAL_STAGE'] == 'Dementia'
    assert row['DIAGNOSIS_NEW'] == 'Dementia_other_suspected'
    assert row['CLINICAL_STATUS'] == 'pass' and row['ANALYSIS_READY'] == 'False'
    assert row['EDUCATION_MISSING'] == row['APOE_MISSING'] == 'True'
    assert row['BIOLOGICAL_AD_STATUS'] == 'not_inferred'
    assert row['DX_USES_FUTURE_VISIT'] == 'True' and row['MRI_AGE_YEARS'] == '70.0'
    assert row['MRI_AGE_FROM_PTDOB_APPROX'] == '70.0'
    assert result['summary']['runs'] == 1
    assert all(p.read_bytes() == before[str(p)] for p in inputs)


def test_all_nearest_ties_preserved_and_conflicting_diagnoses_held(tmp_path):
    inputs = fixture(tmp_path)
    dx = clinical.read(inputs[2])[0]
    write(inputs[2], [dx, {**dx, 'DIAGNOSIS': '2'}])
    clinical.process(*inputs, tmp_path / 'out')
    row = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert row['CLINICAL_STATUS'] == 'hold' and row['DXSUM_TIE_COUNT'] == '2'
    assert 'conflicting' in row['CLINICAL_REASONS']
    raw = [r for r in clinical.read(tmp_path / 'out/clinical_source_rows.tsv') if r['TABLE'] == 'DXSUM']
    assert len(raw) == 2 and {r['SOURCE_ROW'] for r in raw} == {'1', '2'}
    assert clinical.read(tmp_path / 'out/clinically_validated_sessions.tsv') == []


def test_repeated_dates_and_runs_can_share_one_clinical_visit(tmp_path):
    included, links, dx, pt = fixture(tmp_path)
    rows = clinical.read(included)
    write(included, [rows[0], {**rows[0], 'run': '2'}, {**rows[0], 'ses': 'ses-M012'}])
    rawlink = clinical.read(links)[0]
    write(links, [{**rawlink, 'run': '1'}, {**rawlink, 'run': '2', 'Image_ID': '103'}, {**rawlink, 'run': '1', 'VISCODE': 'm12', 'Image_ID': '102', 'Scan_Date': '2020-01-02'}])
    clinical.process(included, links, dx, pt, tmp_path / 'out')
    rows = clinical.read(tmp_path / 'out/clinical_validation.tsv')
    assert len(rows) == 3 and all(r['CLINICAL_STATUS'] == 'pass' for r in rows)
    assert [r['run'] for r in rows] == ['1', '2', '1']


def test_duplicate_run_identity_is_rejected(tmp_path):
    inputs = fixture(tmp_path)
    row = clinical.read(inputs[0])[0]
    write(inputs[0], [row, row])
    with pytest.raises(ValueError, match='Duplicate included'):
        clinical.process(*inputs, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_ambiguous_scan_date_never_uses_first_source_row(tmp_path):
    inputs = fixture(tmp_path)
    row = clinical.read(inputs[1])[0]
    links = [row, {**row, 'Scan_Date': '2021-01-01'}]
    for name, values in [('forward', links), ('reverse', list(reversed(links)))]:
        write(inputs[1], values)
        clinical.process(*inputs, tmp_path / name)
        output = clinical.read(tmp_path / name / 'clinical_validation.tsv')[0]
        assert output['CLINICAL_STATUS'] == 'hold' and output['IMAGE_ID'] == ''


def test_date_window_and_past_direction_are_separate_policies(tmp_path):
    inputs = fixture(tmp_path)
    d = clinical.read(inputs[2])[0]
    write(inputs[2], [d, {**d, 'EXAMDATE': '2019-12-30', 'DIAGNOSIS': '2'}])
    clinical.process(*inputs, tmp_path / 'past', direction='past')
    row = clinical.read(tmp_path / 'past/clinical_validation.tsv')[0]
    assert row['DIAGNOSIS'] == '2' and row['DX_USES_FUTURE_VISIT'] == 'False'
    clinical.process(*inputs, tmp_path / 'strict', max_days=0)
    assert clinical.read(tmp_path / 'strict/clinical_validation.tsv')[0]['CLINICAL_STATUS'] == 'hold'


def test_qc_error_source_is_not_used_as_the_nearest_diagnosis(tmp_path):
    inputs = fixture(tmp_path)
    d = clinical.read(inputs[2])[0]
    write(inputs[2], [{**d, 'EXAMDATE': '2020-01-01', 'HAS_QC_ERROR': '1'}, d])
    clinical.process(*inputs, tmp_path / 'out')
    row = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert row['DX_SOURCE_ROWS'] == '2' and row['DX_DATE_DIFF_DAYS'] == '1'


def test_demographic_tie_missing_education_and_sex_conflict_preserve_run(tmp_path):
    inputs = fixture(tmp_path)
    p = clinical.read(inputs[3])[0]
    write(inputs[3], [{**p, 'PTEDUCAT': '16'}, {**p, 'PTGENDER': '2', 'PTDOB': '01/1951'}])
    clinical.process(*inputs, tmp_path / 'out')
    row = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert row['PTDEMOG_TIE_COUNT'] == '2' and row['EDUCATION_RESOLUTION'] == 'partial_missing_tie'
    assert row['BIOLOGICAL_SEX'] == '' and row['PTDOB_CONFLICT'] == 'True'
    assert row['CLINICAL_STATUS'] == 'pass'


def test_apoe_and_cross_source_sex_consensus_are_not_eligibility_gates(tmp_path):
    inputs = fixture(tmp_path)
    apoe = write(tmp_path / 'apoe.csv', [dict(RID='9999', GENOTYPE='3/4')])
    adsl = write(tmp_path / 'adsl.csv', [dict(SUBJID='9999', SEX='Female')])
    dm = write(tmp_path / 'dm.csv', [dict(SUBJID='9999', SEX='Male')])
    clinical.process(*inputs, tmp_path / 'out', apoe=apoe, adsl=adsl, dm=dm)
    row = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert row['APOE4_ALLELE_COUNT'] == '1' and row['BIOLOGICAL_SEX'] == ''
    assert row['CLINICAL_STATUS'] == 'pass'
    with pytest.raises(ValueError, match='new output'):
        clinical.process(*inputs, tmp_path / 'out')


def test_clinical_id_conflicts_are_rejected_before_outputs(tmp_path):
    inputs = fixture(tmp_path)
    row = clinical.read(inputs[2])[0]
    write(inputs[2], [{**row, 'RID': '9998'}])
    with pytest.raises(ValueError, match='identity conflict'):
        clinical.process(*inputs, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_same_image_cannot_be_silently_reused_for_distinct_runs(tmp_path):
    inputs = fixture(tmp_path)
    row = clinical.read(inputs[0])[0]
    write(inputs[0], [row, {**row, 'run': '2'}])
    clinical.process(*inputs, tmp_path / 'out')
    rows = clinical.read(tmp_path / 'out/clinical_validation.tsv')
    assert len(rows) == 2
    assert all(r['CLINICAL_STATUS'] == 'hold' for r in rows)
    assert all('image_id_reused' in r['CLINICAL_REASONS'] for r in rows)


def test_adni1_dementia_cause_is_not_mapped_using_later_phase_rules(tmp_path):
    inputs = fixture(tmp_path)
    row = clinical.read(inputs[2])[0]
    write(inputs[2], [{**row, 'PHASE': 'ADNI1', 'DXDDUE': '1'}])
    clinical.process(*inputs, tmp_path / 'out')
    row = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert row['CLINICAL_STAGE'] == 'Dementia' and row['CLINICAL_ETIOLOGY'] == 'unknown'
    assert row['ETIOLOGY_RESOLUTION'] == 'unsupported_ADNI1_dementia_mapping'


def test_scan_link_subject_and_rid_conflict_is_rejected(tmp_path):
    inputs = fixture(tmp_path)
    row = clinical.read(inputs[1])[0]
    write(inputs[1], [{**row, 'RID': '9998'}])
    with pytest.raises(ValueError, match='identity conflict|disagrees'):
        clinical.process(*inputs, tmp_path / 'out')


def test_clinical_cli_matches_direct_function_and_has_reproducible_artifacts(tmp_path):
    included, links, dx, pt = fixture(tmp_path)
    result = subprocess.run([sys.executable, str(ROOT / 'pipeline/s9a_validate_clinical/run.py'),
                             '--included', str(included), '--scan-links', str(links), '--dxsum', str(dx),
                             '--ptdemog', str(pt), '--output-dir', str(tmp_path / 'cli')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['clinical_status'] == {'pass': 1}
    artifact = json.loads((tmp_path / 'cli/artifact.json').read_text())
    assert len(artifact['inputs_sha256']) == 4 and artifact['analysis_ready'] is False


def test_rid_match_cannot_override_a_conflicting_source_ptid(tmp_path):
    inputs = fixture(tmp_path)
    row = clinical.read(inputs[2])[0]
    write(inputs[2], [{**row, 'PTID': '998_S_9999'}])
    with pytest.raises(ValueError, match='PTID disagrees'):
        clinical.process(*inputs, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('within_row', [False, True])
def test_native_mastersheet_uid_conflicts_are_held(tmp_path, within_row):
    inputs = fixture(tmp_path)
    row = {**clinical.read(inputs[1])[0], 'dicom_SeriesInstanceUID': '1.2.3'}
    rows = [{**row, 'SERIES_UID': '1.2.4'}] if within_row else [row, {**row, 'dicom_SeriesInstanceUID': '1.2.4'}]
    write(inputs[1], rows)
    clinical.process(*inputs, tmp_path / 'out')
    output = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert output['CLINICAL_STATUS'] == 'hold'
    reason = 'scan_link_uid' if within_row else 'ambiguous_scan_identity'
    assert reason in output['CLINICAL_REASONS']


def test_included_rid_cannot_override_imaging_subject(tmp_path):
    inputs = fixture(tmp_path)
    write(inputs[0], [{**clinical.read(inputs[0])[0], 'RID': '9998'}])
    with pytest.raises(ValueError, match='RID disagrees'):
        clinical.process(*inputs, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_static_sex_fill_keeps_provenance_and_missing_education(tmp_path):
    inputs = fixture(tmp_path); row = clinical.read(inputs[3])[0]
    write(inputs[3], [{**row, 'PHASE': 'ADNI3', 'PTGENDER': ''},
                      {**row, 'PHASE': 'ADNI2', 'VISDATE': '2015-01-01', 'PTEDUCAT': '16'}])
    clinical.process(*inputs, tmp_path / 'out')
    out = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert out['BIOLOGICAL_SEX'] == 'Male' and out['EDUCATION_PTEDUCAT'] == ''
    assert out['SEX_SUBJECT_STATIC_FILL_COUNT'] == '1'
    audit = clinical.read(tmp_path / 'out/sex_derivation.tsv')[0]
    assert audit['METHOD'] == 'subject_static_fill' and audit['EVIDENCE_SOURCE_ROWS'] == '2'
    assert any(r['TABLE'] == 'PTDEMOG_SEX_EVIDENCE' and r['SOURCE_ROW'] == '2' for r in clinical.read(tmp_path / 'out/clinical_source_rows.tsv'))


def test_team_never_supplies_nearest_or_static_evidence(tmp_path):
    inputs = fixture(tmp_path); row = clinical.read(inputs[3])[0]
    write(inputs[3], [{**row, 'PHASE': 'TEAM', 'PTGENDER': '2'},
                      {**row, 'PHASE': 'ADNI3', 'VISDATE': '2020-01-02', 'PTGENDER': ''},
                      {**row, 'PHASE': 'ADNI2', 'VISDATE': '2015-01-01'}])
    clinical.process(*inputs, tmp_path / 'out')
    out = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert out['PTDEMOG_SOURCE_ROWS'] == '2' and out['BIOLOGICAL_SEX'] == 'Male'
    assert out['SEX_EVIDENCE_SOURCE_ROWS'] == '3'
    audit = [r for r in clinical.read(tmp_path / 'out/clinical_source_eligibility.tsv') if r['TABLE'] == 'PTDEMOG']
    assert audit[0]['ELIGIBLE'] == 'False' and 'team_phase_excluded' in audit[0]['REASONS']


def test_conflicting_subject_values_do_not_impute_or_drop(tmp_path):
    inputs = fixture(tmp_path); row = clinical.read(inputs[3])[0]
    write(inputs[3], [{**row, 'PHASE': 'ADNI3', 'PTGENDER': ''},
                      {**row, 'PHASE': 'ADNI2', 'VISDATE': '2015-01-01', 'PTGENDER': '1'},
                      {**row, 'PHASE': 'ADNI2', 'VISDATE': '2016-01-01', 'PTGENDER': '2'}])
    clinical.process(*inputs, tmp_path / 'out')
    out = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert out['BIOLOGICAL_SEX'] == '' and out['CLINICAL_STATUS'] == 'pass'
    assert out['SEX_SUBJECT_PROFILE_CONFLICT'] == 'True' and out['SEX_SUBJECT_STATIC_FILL_COUNT'] == '0'


@pytest.mark.parametrize('evidence_phase,expected', [('ADNI3', ''), ('ADNI4', 'Male')])
def test_adni4_does_not_borrow_legacy_gender(tmp_path, evidence_phase, expected):
    inputs = fixture(tmp_path); row = clinical.read(inputs[3])[0]
    write(inputs[3], [{**row, 'PHASE': 'ADNI4', 'PTGENDER': '', 'LEGACY_PARTICIPANT_GENDER_FILLED': '2'},
                      {**row, 'PHASE': evidence_phase, 'VISDATE': '2015-01-01'}])
    clinical.process(*inputs, tmp_path / 'out')
    out = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert out['BIOLOGICAL_SEX'] == expected
    assert clinical.read(tmp_path / 'out/sex_derivation.tsv')[0]['SCOPE'] == 'adni4_sex_assigned_at_birth'


def test_qc_error_cannot_supply_static_value(tmp_path):
    inputs = fixture(tmp_path); row = clinical.read(inputs[3])[0]
    write(inputs[3], [{**row, 'PHASE': 'ADNI3', 'PTGENDER': ''},
                      {**row, 'PHASE': 'ADNI3', 'VISDATE': '2015-01-01', 'HAS_QC_ERROR': '1'}])
    clinical.process(*inputs, tmp_path / 'out')
    out = clinical.read(tmp_path / 'out/clinical_validation.tsv')[0]
    assert out['BIOLOGICAL_SEX'] == '' and out['SEX_SUBJECT_STATIC_FILL_COUNT'] == '0'
