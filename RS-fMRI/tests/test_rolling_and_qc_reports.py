import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'04_workflow'))
import rolling

spec=importlib.util.spec_from_file_location('qc_reports',ROOT/'pipeline/s10_xcpd_integrated_qc/qc_report.py')
reports=importlib.util.module_from_spec(spec);spec.loader.exec_module(reports)


def test_one_archived_subject_refills_one_slot_while_four_remain():
    subjects={'ADNI999S0001','ADNI999S0002','ADNI999S0003','ADNI999S0004','ADNI999S0005'}
    assert rolling.vacancies(subjects,set())==0
    assert rolling.vacancies(subjects,{'ADNI999S0001'})==1
    assert rolling.vacancies(subjects,{'ADNI999S0001','ADNI999S0002'})==2


def test_finished_preprocessing_does_not_free_slot_before_archival(tmp_path):
    h=tmp_path/'continuous5';receipts=h/'offload_receipts';receipts.mkdir(parents=True)
    target=tmp_path/'external';target.mkdir();(target/'archive_manifest.json').write_text('{}')
    p=receipts/'pair.json';p.write_text(json.dumps({'subject':'ADNI999S0001','status':'verified_external_copy_local_cleanup_pending','external_path':str(target)}))
    assert rolling.archived(h)==set()
    p.write_text(json.dumps({'subject':'ADNI999S0001','status':'archived_and_local_space_reclaimed','external_path':str(target)}))
    assert rolling.archived(h)=={'ADNI999S0001'}
    (target/'archive_manifest.json').unlink();assert rolling.archived(h)==set()


def test_worker_state_cannot_overwrite_legacy_controller(tmp_path):
    q=rolling.SubjectQueue.__new__(rolling.SubjectQueue);q.subject='ADNI999S0001';q.job=tmp_path/'job.json';q.state={}
    canonical=tmp_path/'state.json';canonical.write_text('{"legacy":"running"}')
    q.update(q.subject,'running_mriqc');assert json.loads(q.job.read_text())['status']=='running_mriqc'
    assert canonical.read_text()=='{"legacy":"running"}'
    with pytest.raises(ValueError,match='Cross-subject'):q.update('ADNI999S0002','running')


def test_new_worker_launch_does_not_wait_for_legacy_subject(tmp_path,monkeypatch):
    calls=[];monkeypatch.setattr(rolling.subprocess,'Popen',lambda argv,**kw:calls.append((argv,kw)))
    registry={'subjects':{'ADNI999S0001':{},'ADNI999S0002':{}}}
    rolling.launch_workers(tmp_path,tmp_path/'deployment.json',registry,{'ADNI999S0001'},set())
    assert len(calls)==1 and calls[0][0][-1]=='ADNI999S0002' and calls[0][1]['start_new_session'] is True


def test_locked_worker_is_never_launched_again(tmp_path,monkeypatch):
    monkeypatch.setattr(rolling,'locked',lambda path:True)
    monkeypatch.setattr(rolling.subprocess,'Popen',lambda *a,**k:pytest.fail('Duplicate worker'))
    rolling.launch_workers(tmp_path,tmp_path/'deployment.json',{'subjects':{'ADNI999S0001':{}}},set(),set())


def test_qc_failure_has_individual_reason_metric_and_threshold_without_deleting_data(tmp_path):
    (tmp_path/'pair_metadata.json').write_text(json.dumps({'subject':'ADNI999S0001','pair_id':'EPI_20000101_MT1_20000101'}))
    data=tmp_path/'image.nii.gz';data.write_bytes(b'preserved synthetic image')
    cfg={k:0.5 for k in reports.THRESHOLDS};cfg['pre_fd_proportion_threshold']=.3;cfg['min_time']=240
    rows=[{'sub':'sub-ADNI999S0001','ses':'ses-M000','task':'task-rest','pre_xcpd_qc_status':'fail','pre_xcpd_reason':'mean_fd_above_threshold;fd_proportion_above_threshold','mean_fd':.500061,'fd_over_threshold_proportion':.41624,'xcpd_status':'skipped_pre_qc_fail'}]
    files=reports.write(tmp_path,rows,cfg,'fixed-config')
    document=json.loads(files[0].read_text());assert len(document['runs'][0]['reasons'])==2
    assert document['runs'][0]['metrics']['mean_fd']==.500061 and document['thresholds']['pre_mean_fd_threshold']==.5
    assert document['final_research_inclusion']=='pending_review' and '0.500061' in files[1].read_text()
    assert data.read_bytes()==b'preserved synthetic image'
    before=[p.read_bytes() for p in files];reports.write(tmp_path,rows,cfg,'fixed-config');assert before==[p.read_bytes() for p in files]


def test_insufficient_time_gets_explicit_report_and_html_escaping(tmp_path):
    (tmp_path/'pair_metadata.json').write_text(json.dumps({'subject':'<synthetic>','pair_id':'synthetic'}))
    cfg={k:0.5 for k in reports.THRESHOLDS};cfg['min_time']=240
    files=reports.write(tmp_path,[{'xcpd_status':'skipped_insufficient_time','remaining_duration_sec':210}],cfg,'id')
    d=json.loads(files[0].read_text());assert d['runs'][0]['reasons']==['skipped_insufficient_time']
    assert '&lt;synthetic&gt;' in files[1].read_text() and '<synthetic>' not in files[1].read_text()


def test_busy_legacy_controller_is_not_retired_or_signalled(tmp_path,monkeypatch):
    h=tmp_path/'continuous5';h.mkdir();state={'ADNI999S0001':{'status':'running_fmriprep'}}
    (h/'state.json').write_text(json.dumps(state))
    monkeypatch.setattr(rolling.subprocess,'run',lambda *a,**k:pytest.fail('Active legacy controller must not be signalled'))
    monkeypatch.setattr(rolling.subprocess,'check_output',lambda *a,**k:pytest.fail('Active legacy controller must not be replaced'))
    assert rolling.reconcile(tmp_path,{'subjects':{'ADNI999S0001':{}}})=={'ADNI999S0001'}
    assert json.loads((h/'rolling/legacy-controller.json').read_text())['retired'] is False
    assert json.loads((h/'state.json').read_text())==state


def test_retrying_registered_legacy_subject_still_holds_its_controller(tmp_path,monkeypatch):
    h=tmp_path/'continuous5';h.mkdir();(h/'state.json').write_text(json.dumps({'ADNI999S0001':{'status':'retry_queued'}}))
    monkeypatch.setattr(rolling.subprocess,'run',lambda *a,**k:pytest.fail('Legacy retry must be allowed to finish'))
    rolling.reconcile(tmp_path,{'subjects':{'ADNI999S0001':{}}})
    assert json.loads((h/'rolling/legacy-controller.json').read_text())['retired'] is False
