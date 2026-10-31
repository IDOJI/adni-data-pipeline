"""Original ADNI raw-table schemas; all identifiers and records are synthetic."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import subprocess

import yaml

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '02_custom/s3a_source_qc'))
spec = importlib.util.spec_from_file_location('source_qc_step', ROOT / '02_custom/s3a_source_qc/run.py')
step = importlib.util.module_from_spec(spec); spec.loader.exec_module(step)
handoff_spec = importlib.util.spec_from_file_location('source_handoff', ROOT / '02_custom/s5c_validate_handoff/run.py')
handoff = importlib.util.module_from_spec(handoff_spec); handoff_spec.loader.exec_module(handoff)


def write(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t' if path.suffix == '.tsv' else ',')
        w.writeheader(); w.writerows(rows)
    return path


def spine(iid='101', day='2020-01-01'):
    return dict(image_id=iid, ParticipantID='999_S_9999', StudyDate=day, SeriesType='BOLD',
                SeriesInstanceUID='synthetic.' + iid, StudyInstanceUID='study.synthetic', LONIStudy='S99',
                LONISeries='S' + iid, SeriesNumber=iid, MRIProtocolPhase='ADNI3', SeriesTime='12:00:00')


def quality(iid='101', grade='2', **overrides):
    r = dict(LONI_IMAGE='I' + iid, PTID='999_S_9999', RID='9999', SERIES_DATE='2020-01-01', SERIES_TYPE='BOLD',
             SERIESINSTANCEUID='synthetic.' + iid, STUDYINSTANCEUID='study.synthetic', LONI_STUDY='S99',
             LONI_SERIES='S' + iid, SERIES_QUALITY=grade, SERIES_SELECTED='TRUE', STUDY_OVERALLPASS='1',
             PROTOCOL_STATUS='1', STUDY_PROTOCOL_STATUS='1', SERIES_COMMENTS='', PROTOCOL_COMMENTS='',
             STUDY_COMMENTS='', STUDY_PROTOCOL_COMMENT='')
    r.update(overrides); return r


def fixture(tmp_path, grades=('2',), nfq_grade='2', **quality_override):
    raw = write(tmp_path / 'MRIQC.csv', [spine()])
    mayo = write(tmp_path / 'MAYO.csv', [quality(grade=g, **quality_override) for g in grades])
    nfq = write(tmp_path / 'NFQ.csv', [dict(LONIImage='I101', RID='9999', StudyDate='2020-01-01',
                                           SeriesInstanceUID='synthetic.101', OVERALLQC=nfq_grade, SLICETIMING='')])
    return {'MRIQC': raw, 'ADNI3_QC': mayo}, {'synthetic_nfQ': nfq}


@pytest.mark.parametrize('grade,expected', [('1', 'pass'), ('3', 'pass'), ('4', 'blocked'), ('-1', 'blocked')])
def test_quality_and_chosen_are_independent(tmp_path, grade, expected):
    sources, nfq = fixture(tmp_path, (grade,))
    result = step.process(sources, nfq, tmp_path / 'out')
    assert result['summary']['source_qc_status'] == {expected: 1}
    assert result['analysis_ready'] is False


def test_nfq_fail_is_checked_when_slice_timing_is_empty(tmp_path):
    sources, nfq = fixture(tmp_path, nfq_grade='4')
    step.process(sources, nfq, tmp_path / 'out')
    row = step.read(tmp_path / 'out/image_qc.tsv')[0]
    assert row['SOURCE_QC_STATUS'] == 'blocked'
    assert row['NFQ_RAW_REASON'] == 'raw_overallqc_4'


def test_conflicts_and_deleted_scans_never_pass(tmp_path):
    sources, nfq = fixture(tmp_path, ('2', '3'))
    step.process(sources, nfq, tmp_path / 'conflict')
    assert step.read(tmp_path / 'conflict/image_qc.tsv')[0]['QC_STATUS'] == 'conflict'
    sources, nfq = fixture(tmp_path)
    sources['DELETED'] = write(tmp_path / 'deleted.csv', [dict(IMAGEID='I101', SUBJECTID='999_S_9999', SCANDATE='2020-01-01', DELETEDATE='2020-01-03')])
    step.process(sources, nfq, tmp_path / 'deleted')
    assert step.read(tmp_path / 'deleted/image_qc.tsv')[0]['SOURCE_QC_STATUS'] == 'blocked'


def test_unknown_is_pending_and_existing_outputs_are_rejected(tmp_path):
    sources, _ = fixture(tmp_path)
    step.process({'MRIQC': sources['MRIQC']}, {}, tmp_path / 'out')
    assert step.read(tmp_path / 'out/image_qc.tsv')[0]['SOURCE_QC_STATUS'] == 'pending'
    with pytest.raises(ValueError, match='new output'):
        step.process(sources, {}, tmp_path / 'out')


def test_source_gate_connects_to_handoff_without_new_selection_table(tmp_path):
    sources, nfq = fixture(tmp_path)
    write(sources['MRIQC'], [spine(), spine('102')])
    write(sources['ADNI3_QC'], [quality(), quality('102', '4')])
    q = tmp_path / 'qc'; step.process(sources, nfq, q)
    source = write(tmp_path / 'step5.tsv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01'),
                                         dict(Subject_ID='999_S_9999', VISCODE='m12', Image_ID='102', Scan_Date='2020-01-01')])
    result = handoff.process(source, tmp_path / 'handoff', q)
    assert result['sessions'] == 1 and result['source_qc_excluded_sessions'] == 1
    assert result['status'] == 'source_qc_validated_handoff'
    assert step.read(tmp_path / 'handoff/valid_sessions.tsv')[0]['ses'] == 'ses-M000'
    (q / 'image_qc.tsv').write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        handoff.process(source, tmp_path / 'bad', q)


def test_all_blocked_preserves_audit_but_cannot_feed_downstream(tmp_path):
    sources, nfq = fixture(tmp_path, ('4',))
    q = tmp_path / 'qc'; step.process(sources, nfq, q)
    source = write(tmp_path / 'step5.tsv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01')])
    result = handoff.process(source, tmp_path / 'handoff', q)
    assert result['status'] == 'no_surviving_sessions'
    assert step.read(tmp_path / 'handoff/source_qc_audit.tsv')[0]['PROCEED'] == 'False'


def test_nfq_uid_identity_conflict_is_quarantined(tmp_path):
    sources, nfq = fixture(tmp_path)
    write(next(iter(nfq.values())), [dict(LONIImage='I101', RID='9999', StudyDate='2020-01-01', SeriesInstanceUID='wrong.uid', OVERALLQC='2')])
    step.process(sources, nfq, tmp_path / 'out')
    assert step.read(tmp_path / 'out/image_qc.tsv')[0]['SOURCE_QC_STATUS'] == 'blocked'


def test_go2_missing_image_id_can_use_only_unique_composite_identity(tmp_path):
    sources, nfq = fixture(tmp_path)
    raw = dict(loni_image='', RID='9999', series_date='2020-01-01', series_type='BOLD', loni_study='S99',
               loni_series='S101', series_number='101', series_quality='3', series_selected='FALSE',
               study_overallpass='1', series_comments='', study_comments='')
    go = write(tmp_path / 'GO2.csv', [raw])
    step.process({'MRIQC': sources['MRIQC'], 'GO2_QC': go}, nfq, tmp_path / 'out')
    row = step.read(tmp_path / 'out/image_qc.tsv')[0]
    assert row['SOURCE_QC_STATUS'] == 'pass'
    assert row['QC_MATCH_METHODS'] == 'loni-series-study-rid-date-modality'


def test_pending_can_preprocess_but_is_never_research_pass(tmp_path):
    sources, _ = fixture(tmp_path)
    q = tmp_path / 'qc'; step.process({'MRIQC': sources['MRIQC']}, {}, q)
    source = write(tmp_path / 'step5.tsv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01')])
    result = handoff.process(source, tmp_path / 'permissive', q)
    assert result['sessions'] == result['source_qc_pending_sessions'] == 1
    result = handoff.process(source, tmp_path / 'strict', q, require_confirmed=True)
    assert result['status'] == 'no_surviving_sessions'


def test_handoff_source_date_or_uid_mismatch_blocks_record(tmp_path):
    sources, nfq = fixture(tmp_path)
    q = tmp_path / 'qc'; step.process(sources, nfq, q)
    source = write(tmp_path / 'step5.tsv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2021-01-01')])
    assert handoff.process(source, tmp_path / 'date', q)['sessions'] == 0
    write(source, [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01', SERIES_UID='incorrect')])
    assert handoff.process(source, tmp_path / 'uid', q)['sessions'] == 0


def test_gated_handoff_config_and_its_audit_are_bound_to_sources(tmp_path):
    spec = importlib.util.spec_from_file_location('source_qc_workflow', ROOT / '04_workflow/lab.py')
    workflow = importlib.util.module_from_spec(spec); spec.loader.exec_module(workflow)
    sources, nfq = fixture(tmp_path)
    q = tmp_path / 'qc'; step.process(sources, nfq, q)
    source = write(tmp_path / 'step5.tsv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01')])
    h = tmp_path / 'handoff'; handoff.process(source, h, q)
    config = tmp_path / 'lab.yaml'
    config.write_text(yaml.safe_dump(dict(data_root=str(tmp_path / 'data'), scratch_root=str(tmp_path / 'scratch'),
                                        containers_root=str(tmp_path / 'containers'), freesurfer_license=str(tmp_path / 'license.txt'),
                                        mriqc_image='mriqc.sif', fmriprep_image='fmriprep.sif')))
    workflow.render_config(config, tmp_path / 'generated', h)
    (h / 'source_qc_audit.tsv').write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        workflow.render_config(config, tmp_path / 'bad', h)


def test_all_blocked_handoff_cli_fails_closed_with_an_audit(tmp_path):
    sources, nfq = fixture(tmp_path, ('4',))
    q = tmp_path / 'qc'; step.process(sources, nfq, q)
    source = write(tmp_path / 'step5.tsv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01')])
    result = subprocess.run([sys.executable, str(ROOT / '02_custom/s5c_validate_handoff/run.py'),
                             '--input', str(source), '--source-qc', str(q), '--output-dir', str(tmp_path / 'out')], capture_output=True, text=True)
    assert result.returncode == 2
    assert (tmp_path / 'out/source_qc_audit.tsv').is_file()


def test_native_source_qc_cli_accepts_explicit_raw_files(tmp_path):
    sources, nfq = fixture(tmp_path)
    result = subprocess.run([sys.executable, str(ROOT / '02_custom/s3a_source_qc/run.py'), '--mriqc-table', str(sources['MRIQC']),
                             '--adni3-qc', str(sources['ADNI3_QC']), '--nfq', 'synthetic=' + str(next(iter(nfq.values()))),
                             '--output-dir', str(tmp_path / 'cli')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['source_qc_status'] == {'pass': 1}
