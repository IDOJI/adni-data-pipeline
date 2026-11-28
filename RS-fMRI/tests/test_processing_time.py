"""Timing arithmetic, retries, relocation, missing values and read-only sources."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('timing_for_test', ROOT/'04_workflow/processing_time.py')
t = importlib.util.module_from_spec(spec);spec.loader.exec_module(t)

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True);path.write_text(json.dumps(value));return path

def pre(root, stage='mriqc', token='one', start='2026-01-01T00:00:00+00:00', end='2026-01-01T00:10:00+00:00', status='execution_completed_QC_required'):
    return save(root/'runs/ADNI999S9999/logs'/token/'run.json',dict(stage=stage,case=dict(subject='ADNI999S9999',session='M000'),started_at=start,container_ended_at=end,status=status,exit_code=0 if status!='failed' else 1,input_unchanged=True,runner_sha256='synthetic'))

def post(root, number='001', **changes):
    record=dict(config_id='synthetic',created_at='2026-01-01T00:00:00Z',started_at='2026-01-01T00:20:00Z',finished_at='2026-01-01T00:30:00Z',status='success',exit_code=0,row=dict(sub='sub-ADNI999S9999',ses='ses-M000',run='1',source_pair=str(root/'results/999_S_9999/EPI_20200101_MT1_20200101')))
    record.update(changes)
    return save(root/f'results/999_S_9999/EPI_20200101_MT1_20200101/s10/synthetic/runs/run-1/attempt-{number}/execution.json',record)

def test_stage_sum_parallel_wall_and_union_differ(tmp_path):
    root=tmp_path/'runtime';pre(root);pre(root,'fmriprep','two',end='2026-01-01T00:20:00Z');post(root)
    out=t.collect(root)
    assert out['preprocessing_seconds']==1800 and out['postprocessing_seconds']==600
    assert out['stage_seconds_sum']==2400 and out['observed_wall_seconds']==1800
    assert out['active_interval_union_seconds']==1800 and out['wall_time_complete_for_observed_attempts']

def test_timezone_and_docker_state_precedence():
    rec=dict(status='success',started_at='2026-01-01T09:00:00+09:00',finished_at='2026-01-01T09:20:00+09:00',container_started_at='2026-01-01T00:01:00.123456789Z',container_finished_at='2026-01-01T00:11:00.123456789Z')
    value=t.timing(rec);assert value['elapsed_seconds']==600 and value['duration_source']=='docker_state'

@pytest.mark.parametrize('end,issue',[('2025-12-31T23:59:00Z','negative_interval'),(None,'missing_or_invalid_timestamp'),('invalid','missing_or_invalid_timestamp'),('2026-01-01T01:00:00','missing_or_invalid_timestamp')])
def test_invalid_missing_times_are_not_zero(end,issue):
    value=t.timing(dict(status='success',started_at='2026-01-01T00:00:00Z',finished_at=end))
    assert value['elapsed_seconds'] is None and value['timing_issue']==issue

def test_running_attempt_and_prepared_start_do_not_duplicate(tmp_path):
    root=tmp_path/'runtime';path=post(root,status='prepared',started_at=None,finished_at=None)
    assert t.collect(root)['timed_attempts']==0
    data=json.loads(path.read_text());data.update(status='running',started_at='2026-01-01T00:20:00Z');save(path,data)
    value=t.collect(root);assert value['attempts']==1 and value['running_attempts']==1 and value['stage_seconds_sum'] is None
    data.update(status='success',finished_at='2026-01-01T00:30:00Z');save(path,data)
    assert t.collect(root)['attempts']==1 and t.collect(root)['stage_seconds_sum']==600

def test_failed_retries_are_included(tmp_path):
    root=tmp_path/'runtime';pre(root,status='failed');pre(root,token='retry',start='2026-01-01T00:15:00Z',end='2026-01-01T00:25:00Z')
    out=t.collect(root)
    assert out['mriqc_seconds']==1200 and out['attempts']==2 and out['unsuccessful_terminal_attempts']==1
    assert out['observed_wall_seconds']==1500 and out['active_interval_union_seconds']==1200

def test_archives_deduplicate_and_ledger_survives_unmount(tmp_path):
    root=tmp_path/'runtime';original=pre(root);archive=tmp_path/'archive'
    copied=archive/'999_S_9999/EPI_20200101_MT1_20200101/_runtime/logs/one/run.json';copied.parent.mkdir(parents=True);shutil.copy2(original,copied)
    before=original.read_bytes();out=t.collect(root,archives=[archive])
    assert out['attempts']==1 and out['mriqc_seconds']==600 and original.read_bytes()==before
    original.unlink();copied.unlink();out=t.collect(root,archives=[archive])
    assert out['attempts']==1 and out['mriqc_seconds']==600 and out['unseen_attempts']==1

def test_published_exact_identity_links_preprocessing(tmp_path):
    root=tmp_path/'runtime';pre(root);post(root);pair=root/'results/999_S_9999/EPI_20200101_MT1_20200101'
    save(pair/'pair_metadata.json',dict(subject='ADNI999S9999',pair_id=pair.name,execution_identity=dict(mriqc=dict(started_at='2026-01-01T00:00:00+00:00',runner_sha256='synthetic'))))
    t.collect(root);rows=json.loads((root/'timing/cases.json').read_text())['cases']
    assert len(rows)==1 and rows[0]['pair_id']==pair.name

def test_conflicting_duplicates_are_reported(tmp_path):
    root=tmp_path/'runtime';path=pre(root);archive=tmp_path/'archive';value=json.loads(path.read_text());value['container_ended_at']='2026-01-01T00:20:00Z'
    save(archive/'999_S_9999/EPI_20200101_MT1_20200101/_runtime/logs/one/run.json',value)
    out=t.collect(root,archives=[archive]);assert out['attempts']==1 and out['timed_attempts']==0 and out['stage_seconds_sum'] is None and out['diagnostics']

def test_malformed_receipt_keeps_previous_ledger(tmp_path):
    root=tmp_path/'runtime';path=pre(root);t.collect(root);path.write_text('{');out=t.collect(root)
    assert out['mriqc_seconds']==600 and out['diagnostics']

def test_public_receipt_cli(tmp_path):
    root=tmp_path/'runtime';save(root/'logs/mriqc_execution.json',dict(status='success',returncode=0,stage='mriqc',case=dict(subject='toy001',session='M000'),started_at='2026-01-01T00:00:00Z',container_ended_at='2026-01-01T00:01:00Z'))
    result=subprocess.run([sys.executable,str(ROOT/'pipeline/s7d_processing_timing/run.py'),'--root',str(root)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['stage_seconds_sum']==60
    assert (root/'timing/attempts.tsv').is_file() and (root/'timing/cases.tsv').is_file()

def test_output_guard_and_sidecar_failure_preserve_execution(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='outside'):t.validate_output(ROOT/'reports')
    record=dict(status='success',started_at='2026-01-01T00:00:00Z',finished_at='2026-01-01T00:01:00Z');t.add_timing(record)
    assert record['status']=='success' and record['timing']['elapsed_seconds']==60
    def fail(*a,**k):raise OSError('synthetic unavailable disk')
    monkeypatch.setattr(t,'collect',fail)
    with pytest.warns(RuntimeWarning,match='sidecar'):assert t.refresh_safely(tmp_path) is None

def test_retry_pair_link_requires_exact_input_hashes(tmp_path):
    root=tmp_path/'runtime';one=pre(root);two=pre(root,token='retry',start='2026-01-01T00:15:00Z',end='2026-01-01T00:25:00Z')
    for path in [one,two]:
        data=json.loads(path.read_text());data['input_before']={'/synthetic/sub-999_T1w.nii.gz':'a'*64};save(path,data)
    pair=root/'results/999_S_9999/EPI_20200101_MT1_20200101'
    save(pair/'pair_metadata.json',dict(subject='ADNI999S9999',pair_id=pair.name,execution_identity=dict(mriqc=dict(started_at='2026-01-01T00:15:00Z',runner_sha256='synthetic'))))
    t.collect(root);rows=json.loads((root/'timing/cases.json').read_text())['cases'];assert len(rows)==1
    data=json.loads(one.read_text());data['input_before']={'/synthetic/sub-999_T1w.nii.gz':'b'*64};save(one,data)
    t.collect(root);rows=json.loads((root/'timing/cases.json').read_text())['cases'];assert len(rows)==2
    assert t.hms(90061)=='25:01:01' and t.hms(None) is None

def test_finished_container_time_survives_pending_output_validation(tmp_path):
    root=tmp_path/'runtime';post(root,status='running',finished_at=None,container_started_at='2026-01-01T00:20:00Z',container_finished_at='2026-01-01T00:30:00Z')
    out=t.collect(root)
    assert out['known_stage_seconds_sum']==600 and out['timed_attempts']==1
    assert out['running_attempts']==1 and out['stage_seconds_sum'] is None
    assert out['wall_time_complete_for_observed_attempts'] is False
    rows=json.loads((root/'timing/ledger.json').read_text())['attempts']
    assert next(iter(rows.values()))['timing_issue']=='runner_completion_pending'
