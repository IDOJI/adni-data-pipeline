"""Synthetic clocks and containers; never launch imaging or alter scientific files."""
import importlib.util
import json
from pathlib import Path
import pytest

PATH=Path(__file__).resolve().parents[1]/'04_workflow/processing_timing.py'
spec=importlib.util.spec_from_file_location('processing_timing_under_test',PATH)
timing=importlib.util.module_from_spec(spec);spec.loader.exec_module(timing)
SUB='ADNI999S0001'


@pytest.fixture(autouse=True)
def forbid_live_observation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Timing unit tests must use fake Docker and host clocks')
    for name in ('json', 'inspect', 'containers', 'history'):
        monkeypatch.setattr(timing.Docker, name, forbidden)
    monkeypatch.setattr(timing.Observer, 'capture_sleep', forbidden)


class FakeDocker:
    def inspect(self,cid):return None
    def containers(self):return []


def fixture(tmp_path,stage='fmriprep',start=1000,end=None,status='running',folder='attempt1'):
    (tmp_path/'continuous5').mkdir(exist_ok=True)
    (tmp_path/'continuous5/settings.json').write_text('{}')
    p=tmp_path/'runs'/SUB/'logs'/folder/'run.json';p.parent.mkdir(parents=True,exist_ok=True)
    record={'stage':stage,'case':{'subject':SUB,'ptid':'999_S_0001','bold_image_id':'11'},
            'started_at':timing.iso(start),'status':status,'image':{'resolved':'pinned@sha256:test'}}
    if end is not None:record.update(container_ended_at=timing.iso(end),exit_code=0)
    timing.save(p,record)
    app=timing.Observer(tmp_path,FakeDocker());app.capture_sleep=lambda:None
    app.state.update(first_observed_at=timing.iso(900),host_sleep_tracking_supported=True,host_sleep_coverage_start=timing.iso(900))
    app.scan_records();return app,p


def event(action,when,cid='container1',code='0',name=None):
    return {'Type':'container','Action':action,'timeNano':int(when*1e9),
            'Actor':{'ID':cid,'Attributes':{'name':name or f'statmind-fmriprep-{SUB}-M000','exitCode':code}}}


def test_union_excludes_pauses_and_sleep_without_double_subtraction():
    assert timing.overlap_seconds(1000,1100,[(1020,1040),(1030,1050),(900,1005),(1095,1200)])==40
    assert timing.overlap_seconds(1000,1100,[])==0


def test_duration_is_saved_on_die_without_waiting_for_driver_or_user(tmp_path):
    app,source=fixture(tmp_path);before=source.read_bytes()
    app.state['host_sleep_intervals']=[[1030,1050]]
    for action,t in [('start',1000),('pause',1020),('unpause',1040),('die',1100)]:app.observe_event(event(action,t))
    item=next(iter(app.records.values()));p=app.attempt_path(item)
    assert p.is_file()
    d=timing.read(p);assert d['container_elapsed_seconds']==100 and d['observed_pause_sleep_seconds']==30
    assert d['execution_seconds']==70 and d['recording_mode']=='automatic_terminal_event'
    assert d['pause_sleep_history_complete'] is True
    assert d['failure_hold_and_queue_wait_included'] is False
    assert source.read_bytes()==before


def test_failed_execution_separate_and_inter_attempt_hold_is_not_added(tmp_path):
    app,source=fixture(tmp_path)
    app.observe_event(event('start',1000));app.observe_event(event('die',1100))
    p=source.parent.parent/'attempt2/run.json';p.parent.mkdir()
    record=timing.read(source);record['started_at']=timing.iso(2000);timing.save(p,record)
    app.observe_event(event('start',2000,cid='container2'))
    app.observe_event(event('die',2010,cid='container2',code='137'))
    app.summaries();d=timing.read(app.hub/'subjects'/(SUB+'.json'))['summary']
    assert d['fmriprep_seconds']==110 and d['successful_attempt_seconds']==100 and d['failed_attempt_seconds']==10
    assert d['preprocessing_postprocessing_seconds'] is None
    assert d['processing_status']=='in_progress_or_failed'


def test_replayed_events_do_not_double_count_pause(tmp_path):
    app,_=fixture(tmp_path)
    events=[event('start',1000),event('pause',1020),event('unpause',1040),event('die',1100)]
    for e in events+events:app.observe_event(e)
    d=timing.read(next((app.hub/'attempts').glob('*/*/*.json')))
    assert d['execution_seconds']==80 and len(list((app.hub/'attempts').glob('*/*/*.json')))==1


def test_historical_logs_are_explicit_estimates_and_never_rewritten(tmp_path):
    app,source=fixture(tmp_path,end=1100,status='execution_completed_QC_required');before=source.read_bytes()
    app.reconcile();d=timing.read(next((app.hub/'attempts').glob('*/*/*.json')))
    assert d['recording_mode']=='historical_reconstruction'
    assert d['pause_sleep_history_complete'] is False and d['failure_hold_and_queue_wait_included']=='not_fully_verifiable'
    assert source.read_bytes()==before


def test_docker_end_overrides_late_driver_observation(tmp_path):
    app,source=fixture(tmp_path,end=1500,status='execution_completed_QC_required')
    info={'Id':'docker1','Name':f'/statmind-fmriprep-{SUB}-M000',
          'Config':{'Image':'pinned@sha256:test','Labels':{}},
          'State':{'Status':'exited','StartedAt':timing.iso(1001),'FinishedAt':timing.iso(1101),'ExitCode':0}}
    app.reconcile();app.remember(info);app.reconcile()
    d=timing.read(next((app.hub/'attempts').glob('*/*/*.json')))
    assert d['execution_seconds']==100 and d['measurement_source']=='docker_state'
    assert timing.read(source)['container_ended_at']==timing.iso(1500)


def test_missing_start_never_manufactures_a_complete_duration(tmp_path):
    app,_=fixture(tmp_path);app.observe_event(event('die',1100))
    assert not list((app.hub/'attempts').glob('*/*/*.json'))


def test_destroy_events_without_a_known_start_never_create_ghost_running_jobs(tmp_path):
    app,_=fixture(tmp_path)
    for action in ['die','stop','destroy']:app.observe_event(event(action,1100))
    assert app.state['containers']=={}


def test_unknown_images_and_unrelated_containers_are_not_bound(tmp_path):
    app,_=fixture(tmp_path)
    info={'Id':'unknown','Name':f'/statmind-fmriprep-{SUB}-M000',
          'Config':{'Image':'other:image','Labels':{}},
          'State':{'Status':'running','StartedAt':timing.iso(1001)}}
    assert app.remember(info) is None
    assert timing.classify('unrelated-service') is None
    app.observe_event(event('start',1000,name='statmind-fmriprep-ADNI888S0001-M000'))
    assert not app.state['containers']


def test_new_attempt_discovered_at_start_even_between_poll_cycles(tmp_path):
    app,p=fixture(tmp_path);app.records={}
    app.observe_event(event('start',1000));app.observe_event(event('die',1100))
    assert app.attempt_path(next(iter(app.records.values()))).exists()


def test_result_timing_waits_for_s12_owned_output_directory(tmp_path):
    app,_=fixture(tmp_path,end=1100,status='execution_completed_QC_required')
    pair=tmp_path/'results/999_S_0001/EPI_20000101_MT1_20000101';pair.mkdir(parents=True)
    timing.save(pair/'pair_metadata.json',{'subject':SUB,'ptid':'999_S_0001','pair_id':pair.name,'epi_image_id':'11','mt1_image_id':'12'})
    app.reconcile();assert not (pair/'results').exists()
    out=pair/'results';out.mkdir();timing.save(out/'export_manifest.json',{'outputs':{}})
    app.summaries();assert (out/'processing_time.csv').exists() and (out/'processing_time.json').exists()


def test_selftest_is_not_added_to_participant_totals(tmp_path):
    app,_=fixture(tmp_path)
    for action,t in [('start',1000),('die',1002)]:
        e=event(action,t,name='adni-timing-selftest-example');e['Actor']['Attributes'][timing.SELFTEST]='true';app.observe_event(e)
    assert len(list((app.hub/'selftests').glob('*.json')))==1
    assert not list((app.hub/'attempts').glob('*/*/*.json'))


def test_summaries_have_identical_columns_for_published_and_unpublished_cases(tmp_path):
    app,_=fixture(tmp_path,end=1100,status='execution_completed_QC_required')
    app.reconcile()
    import csv
    rows=list(csv.DictReader((app.hub/'processing_times.csv').open()))
    assert len(rows)==1 and rows[0]['표시 단위']=='시간·분·초'
    assert rows[0]['전처리(fMRIPrep)']=='0시간 1분 40초'
    raw=list(csv.DictReader((app.hub/'processing_times.raw.csv').open()))
    assert raw[0]['units']=='seconds' and float(raw[0]['fmriprep_seconds'])==100


@pytest.mark.parametrize('seconds,text',[(0,'0시간 0분 0초'),(61,'0시간 1분 1초'),
    (9907.27995,'2시간 45분 7초'),(90061,'25시간 1분 1초'),(None,'미완료')])
def test_visible_duration_units_are_explicit(seconds,text):
    assert timing.format_duration(seconds)==text


def test_invalid_duration_cannot_be_formatted_as_a_valid_time():
    with pytest.raises(ValueError):timing.format_duration(-1)


def test_qc_skip_is_labeled_instead_of_looking_like_instant_processing():
    row={'subject':SUB,'processing_status':'completed_or_qc_skipped',
         'historically_reconstructed_attempts':0,'xcpd_seconds':0}
    assert timing.human_summary(row,{'xcpd':'skipped_pre_qc_fail'})['후처리(XCP-D)']=='QC 스킵'
