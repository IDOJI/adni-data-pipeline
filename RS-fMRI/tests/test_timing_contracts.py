"""Both timing definitions keep their numbers while sharing only presentation."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

receipt=module('receipt_contract','04_workflow/processing_time.py')
observer=module('observer_contract','04_workflow/processing_timing.py')

@pytest.fixture(autouse=True)
def no_real_observation(monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('Synthetic timing tests must not observe the host')
    for method in ('json','inspect','containers','history'):
        monkeypatch.setattr(observer.Docker,method,forbidden)
    monkeypatch.setattr(observer.Observer,'capture_sleep',forbidden)

@pytest.mark.parametrize('value,expected',[(None,'미완료'),(0,'0시간 0분 0초'),
    (.49,'0시간 0분 0초'),(.5,'0시간 0분 1초'),(59.5,'0시간 1분 0초'),
    (9907.27995,'2시간 45분 7초'),(90061,'25시간 1분 1초')])
def test_shared_formatter_only_changes_display(value,expected):
    assert receipt.format_duration is observer.format_duration
    assert receipt.format_duration(value)==expected
    row={'status':'success','started_at':'2026-01-01T00:00:00Z',
         'finished_at':'2026-01-01T00:00:00.123456Z'}
    receipt.add_timing(row)
    assert row['timing']['elapsed_seconds']==.123456
    assert row['timing']['elapsed_display']=='0시간 0분 0초'

@pytest.mark.parametrize('value',[-1,float('nan'),float('inf')])
def test_invalid_display_input_is_not_a_valid_zero(value):
    with pytest.raises(ValueError):receipt.format_duration(value)


def test_pause_adjusted_observer_and_receipt_wall_span_are_distinct(tmp_path):
    # A 500-second driver window contains a 100-second Docker window and an
    # observed 30-second union of pause/sleep intervals. They are not additive.
    record={'stage':'fmriprep','case':{'subject':'ADNI999S0001','session':'M000'},
            'started_at':observer.iso(1000),'container_ended_at':observer.iso(1500),
            'status':'execution_completed_QC_required','exit_code':0,'input_unchanged':True}
    path=tmp_path/'runs/ADNI999S0001/logs/synthetic/run.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(record))
    (tmp_path/'continuous5').mkdir();(tmp_path/'continuous5/settings.json').write_text('{}')
    class FakeDocker: pass
    app=observer.Observer(tmp_path,FakeDocker())
    app.state.update(first_observed_at=observer.iso(900),host_sleep_tracking_supported=True,
                     host_sleep_coverage_start=observer.iso(900),host_sleep_intervals=[[1030,1050]])
    value={'id':'synthetic','subject':'ADNI999S0001','stage':'fmriprep',
           'started_at':observer.iso(1000),'finished_at':observer.iso(1100),'source':'docker_event',
           'pauses':[[observer.iso(1020),observer.iso(1040)]],'start_event_observed':True,
           'terminal_event_at':observer.iso(1100),'exit_code':1}
    active=app.timing(value,{'path':str(path)})
    elapsed=receipt.timing(record)
    assert active['execution_seconds']==70 and active['observed_pause_sleep_seconds']==30
    assert active['recording_mode']=='automatic_terminal_event' and active['pause_sleep_history_complete'] is True
    assert active['exit_code']==1 and active['execution_duration']=='0시간 1분 10초'
    assert elapsed['elapsed_seconds']==500 and elapsed['duration_source']=='runner_observation'
    assert receipt.summarize([receipt.normalize(record,path)])['stage_seconds_sum']==500


def test_receipt_human_sidecars_preserve_numeric_columns_and_precision(tmp_path):
    path=tmp_path/'logs/mriqc_execution.json';path.parent.mkdir()
    record={'stage':'mriqc','status':'success','returncode':0,'case':{'subject':'toy001','session':'M000'},
            'started_at':'2026-01-01T00:00:00Z','container_ended_at':'2026-01-01T02:45:07.279950Z'}
    path.write_text(json.dumps(record));before=path.read_bytes();out=receipt.collect(tmp_path)
    raw=list(csv.DictReader((tmp_path/'timing/attempts.tsv').open(),delimiter='\t'))[0]
    human=list(csv.DictReader((tmp_path/'timing/attempts.display.tsv').open(),delimiter='\t'))[0]
    assert float(raw['elapsed_seconds'])==9907.27995 and raw['elapsed_hms']=='02:45:07'
    assert 'elapsed_display' not in raw
    assert human['elapsed_display']=='2시간 45분 7초' and 'elapsed_seconds' not in human
    assert human['measurement_scope']=='receipt_interval_not_pause_adjusted'
    assert out['measurement_scope']=='receipt_intervals_and_observed_wall_span'
    assert out['display']['stage_seconds_sum']=='2시간 45분 7초'
    assert out['stage_seconds_sum']==9907.27995 and path.read_bytes()==before
    record.update(status='running',container_ended_at=None);path.write_text(json.dumps(record))
    out=receipt.collect(tmp_path)
    assert out['stage_seconds_sum'] is None and out['display']['stage_seconds_sum']=='미완료'



def test_observer_rejects_source_tree_before_writing():
    with pytest.raises(ValueError,match='outside the source repository'):
        observer.Observer(ROOT.parent)


def test_subject_observer_does_not_assign_multiple_visits_to_one_pair(tmp_path):
    path=tmp_path/'runs/ADNI999S0001/logs/one/run.json';path.parent.mkdir(parents=True)
    record={'stage':'fmriprep','case':{'subject':'ADNI999S0001'},'status':'execution_completed_QC_required',
            'started_at':observer.iso(1000),'container_ended_at':observer.iso(1100),'exit_code':0}
    path.write_text(json.dumps(record));(tmp_path/'continuous5').mkdir();(tmp_path/'continuous5/settings.json').write_text('{}')
    class FakeDocker:
        def containers(self):return []
    app=observer.Observer(tmp_path,FakeDocker());app.capture_sleep=lambda:None
    pairs=[]
    for date in ['20000101','20010101']:
        pair=tmp_path/f'results/999_S_0001/EPI_{date}_MT1_{date}';out=pair/'results';out.mkdir(parents=True)
        manifest=out/'export_manifest.json';manifest.write_text('{"synthetic": true}')
        (pair/'pair_metadata.json').write_text(json.dumps({'subject':'ADNI999S0001','ptid':'999_S_0001','pair_id':pair.name,'epi_image_id':'11','mt1_image_id':'12'}));pairs.append(pair)
    app.reconcile()
    raw=json.loads((app.hub/'subjects/ADNI999S0001.json').read_text())['summary']
    assert raw['fmriprep_seconds']==100 and raw['pair_id'] is None
    assert all(not (p/'results/processing_time.csv').exists() for p in pairs)
    assert all((p/'results/export_manifest.json').read_text()=='{"synthetic": true}' for p in pairs)
