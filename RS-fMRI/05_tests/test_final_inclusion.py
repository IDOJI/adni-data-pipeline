"""Clinical-only pass and absent ST evidence cannot override confirmed problems."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    out = importlib.util.module_from_spec(spec); spec.loader.exec_module(out)
    return out
clinical = module('clinical_for_final', '02_custom/s9a_validate_clinical/run.py')
gate = module('final_gate', '02_custom/s9b_validate_inclusion/run.py')


def table(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t' if path.suffix == '.tsv' else ',')
        w.writeheader(); w.writerows(rows)
    return path


def fixture(tmp_path, quality_state='pass'):
    inc = table(tmp_path / 'included.tsv', [dict(sub='sub-ADNI999S9999', ses='ses-M000', run='1')])
    links = table(tmp_path / 'links.csv', [dict(sub='sub-ADNI999S9999', ses='ses-M000', run='1', Image_ID='101', Scan_Date='2020-01-01', SERIES_UID='1.2.3')])
    dx = table(tmp_path / 'dx.csv', [dict(PTID='999_S_9999', PHASE='ADNI3', EXAMDATE='2020-01-01', DIAGNOSIS='1')])
    pt = table(tmp_path / 'pt.csv', [dict(PTID='999_S_9999', PHASE='ADNI3', VISDATE='2020-01-01', PTGENDER='1')])
    cl = tmp_path / 'clinical'; clinical.process(inc, links, dx, pt, cl)
    qc = tmp_path / 'qc'; qc.mkdir()
    table(qc / 'image_qc.tsv', [dict(IMAGE_ID='101', PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01', MODALITY='EPI', SERIES_UID='1.2.3', SOURCE_QC_STATUS=quality_state)])
    gate.finish(qc, 'source_qc_v1', {}, {})
    st = table(tmp_path / 'st.csv', [], ['IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'ST_STATUS', 'EVIDENCE_REF'])
    return qc, cl, st


def refresh(directory, name):
    p = directory / 'artifact.json'; record = json.loads(p.read_text())
    record['outputs_sha256'][name] = gate.sha(directory / name); p.write_text(json.dumps(record))


def result(path):
    return gate.read(path / 'inclusion_audit.tsv')[0]


@pytest.mark.parametrize('state,expected,retained', [('pass', 'eligible', True), ('pending', 'pending', True), ('blocked', 'excluded', False)])
def test_pending_retained_source_fail_blocked(tmp_path, state, expected, retained):
    args = fixture(tmp_path, state); record = gate.process(*args, tmp_path / 'out')
    out = result(tmp_path / 'out')
    assert out['INCLUSION_STATUS'] == expected and out['ANALYSIS_READY'] == 'False'
    assert record['summary']['retained'] == int(retained)
    assert len(gate.read(tmp_path / 'out/retained_sessions.tsv')) == int(retained)
    assert record['summary']['dx_direction'] == 'nearest' and record['summary']['max_dx_days'] == 28


@pytest.mark.parametrize('native', [False, True])
def test_confirmed_st_overrides_pending_and_clinical_pass(tmp_path, native):
    args = fixture(tmp_path, 'pending'); row = dict(PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01')
    if native:
        row.update(EPI_IMAGE_ID='I101', final_analysis_status='no_slice_timing_any_source', final_slice_timing_class='no_slice_timing', full_dicom_recheck='TRUE', nfq_usable_st='FALSE', st_evidence_class='not_found_anywhere')
    else:
        row.update(IMAGE_ID='I101', ST_STATUS='confirmed_absent', EVIDENCE_REF='review/log-1')
    table(args[2], [row]); gate.process(*args, tmp_path / 'out')
    out = result(tmp_path / 'out')
    assert out['INCLUSION_STATUS'] == 'excluded' and out['ST_CONFIRMED_ABSENT'] == 'True'
    assert 'confirmed_st_absence' in out['INCLUSION_REASONS']


@pytest.mark.parametrize('status,reference', [('pending', 'log'), ('confirmed_absent', '')])
def test_st_requires_explicit_confirmation(tmp_path, status, reference):
    args = fixture(tmp_path)
    table(args[2], [dict(IMAGE_ID='101', PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01', ST_STATUS=status, EVIDENCE_REF=reference)])
    with pytest.raises(ValueError, match='explicitly confirmed'): gate.process(*args, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_conversion_failure_gate(tmp_path):
    args = fixture(tmp_path)
    conversion = table(tmp_path / 'conversion.csv', [dict(IMAGE_ID='101', PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01', MODALITY='EPI', SELECTION_ACTION='exclude_before_date_and_image_selection', ERROR_CLASS='source_incomplete', ERROR_REASON='Reviewed incomplete source')])
    gate.process(*args, tmp_path / 'out', conversion)
    assert 'confirmed_conversion_failure' in result(tmp_path / 'out')['INCLUSION_REASONS']


@pytest.mark.parametrize('field,value', [('PTID', '998_S_9999'), ('MRI_STUDY_DATE', '2020-02-01'), ('SERIES_UID', 'different')])
def test_identity_conflicts_are_held(tmp_path, field, value):
    args = fixture(tmp_path); p = args[0] / 'image_qc.tsv'; row = gate.read(p)[0]; row[field] = value
    table(p, [row]); refresh(args[0], p.name); gate.process(*args, tmp_path / 'out')
    assert result(tmp_path / 'out')['INCLUSION_STATUS'] == 'hold'
    assert not gate.read(tmp_path / 'out/retained_sessions.tsv')


def test_exclusion_identity_conflict_cannot_be_ignored(tmp_path):
    args = fixture(tmp_path)
    table(args[2], [dict(IMAGE_ID='101', PTID='998_S_9999', MRI_STUDY_DATE='2020-01-01', ST_STATUS='confirmed_absent', EVIDENCE_REF='review/log-1')])
    gate.process(*args, tmp_path / 'out')
    assert 'exclusion_ledger_identity_conflict' in result(tmp_path / 'out')['INCLUSION_REASONS']
    assert result(tmp_path / 'out')['INCLUSION_STATUS'] == 'hold'


@pytest.mark.parametrize('field,value', [('dx_direction', 'past'), ('max_dx_days', 30)])
def test_changed_clinical_policy_rejected(tmp_path, field, value):
    args = fixture(tmp_path); p = args[1] / 'artifact.json'; m = json.loads(p.read_text()); m['summary'][field] = value; p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='nearest/28-day'): gate.process(*args, tmp_path / 'out')


def test_old_artifact_requires_regeneration(tmp_path):
    args = fixture(tmp_path); p = args[1] / 'artifact.json'; m = json.loads(p.read_text()); m['kind'] = 'clinical_validation_v1'; p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='kind'): gate.process(*args, tmp_path / 'out')


def test_tampered_and_unhashed_outputs_rejected(tmp_path):
    args = fixture(tmp_path); p = args[0] / 'image_qc.tsv'; original = p.read_text(); p.write_text(original + '\n')
    with pytest.raises(ValueError, match='artifact changed'): gate.process(*args, tmp_path / 'out')
    p.write_text(original)
    p = args[0] / 'artifact.json'; m = json.loads(p.read_text()); del m['outputs_sha256']['image_qc.tsv']; p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='not hash-covered'): gate.process(*args, tmp_path / 'out')


@pytest.mark.parametrize('status,expected', [('include', 'eligible'), ('exclude', 'excluded'), ('pending_review', 'hold')])
def test_s10_decision_not_promoted(tmp_path, status, expected):
    args = fixture(tmp_path); p = args[1] / 'clinical_validation.tsv'; row = gate.read(p)[0]; row['final_qc_status'] = status
    table(p, [row]); refresh(args[1], p.name); gate.process(*args, tmp_path / 'out')
    assert result(tmp_path / 'out')['INCLUSION_STATUS'] == expected


def test_clinical_hold_cli_and_no_overwrite(tmp_path):
    args = fixture(tmp_path); p = args[1] / 'clinical_validation.tsv'; row = gate.read(p)[0]; row['CLINICAL_STATUS'] = 'hold'
    table(p, [row]); refresh(args[1], p.name)
    command = [sys.executable, str(ROOT / '02_custom/s9b_validate_inclusion/run.py'), '--source-qc', str(args[0]), '--clinical', str(args[1]), '--confirmed-st-absence', str(args[2]), '--output-dir', str(tmp_path / 'out')]
    proc = subprocess.run(command, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    assert result(tmp_path / 'out')['INCLUSION_STATUS'] == 'excluded' and json.loads(proc.stdout)['retained'] == 0
    with pytest.raises(ValueError, match='new output'): gate.process(*args, tmp_path / 'out')


@pytest.mark.parametrize('gap', ['nan', '-1', '29'])
def test_invalid_date_gap_cannot_pass(tmp_path, gap):
    args = fixture(tmp_path); p = args[1] / 'clinical_validation.tsv'; row = gate.read(p)[0]; row['DX_DATE_DIFF_DAYS'] = gap
    table(p, [row]); refresh(args[1], p.name)
    with pytest.raises(ValueError, match='28-day'): gate.process(*args, tmp_path / 'out')


def test_missing_session_cannot_be_retained(tmp_path):
    args = fixture(tmp_path); p = args[1] / 'clinical_validation.tsv'; row = gate.read(p)[0]; row['ses'] = ''
    table(p, [row]); refresh(args[1], p.name); gate.process(*args, tmp_path / 'out')
    assert result(tmp_path / 'out')['INCLUSION_STATUS'] == 'hold'


@pytest.mark.parametrize('status', ['', 'include'])
def test_explicit_imaging_not_included_cannot_be_promoted(tmp_path, status):
    args = fixture(tmp_path); p = args[1] / 'clinical_validation.tsv'; row = gate.read(p)[0]
    row.update(final_qc_status=status, final_include='False')
    table(p, [row]); refresh(args[1], p.name); gate.process(*args, tmp_path / 'out')
    assert result(tmp_path / 'out')['INCLUSION_STATUS'] == 'hold'
