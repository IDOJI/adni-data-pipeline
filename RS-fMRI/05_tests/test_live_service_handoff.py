"""Live cutover contracts using synthetic state and no imaging containers."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'04_workflow'))
import live_services as live
import queue_service as queue
import compute_slots

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_new_and_existing_subjects_use_distinct_runner_sources():
    q=queue.Queue.__new__(queue.Queue);q.deployment={'legacy_subjects':['ADNI999S9999'],'legacy_preprocessing':'/private/legacy'}
    q.legacy_runner=object();q.runner=object()
    assert q.backend('ADNI999S9999')==(q.legacy_runner,Path('/private/legacy/run.py'))
    assert q.backend('ADNI998S9998')==(q.runner,queue.STEP/'run.py')

def test_sessionwise_command_preserves_surface_cifti_and_scientific_settings(tmp_path):
    runner=load('sessionwise_adapter',ROOT/'02_custom/s7b_sessionwise_preprocessing/run.py')
    cfg={'runtime':str(tmp_path),'resources':{'cpus':4,'docker_memory':'8g','omp_nthreads':2,'workflow_memory_mb':6000},
         'output_spaces':['MNI152NLin6Asym:res-2','MNI152NLin2009cAsym','fsnative','fsaverage:den-10k','func'],
         'random_seed':357,'freesurfer_license':'/private/license.txt','work_revision':'existing-revision'}
    cmd,work=runner.command(cfg,'fmriprep',{'subject':'ADNI999S9999','session':'M000'},'image@sha256:synthetic')
    assert cmd[cmd.index('--cifti-output')+1]=='91k' and '--fs-no-reconall' not in cmd
    assert cmd[cmd.index('--subject-anatomical-reference')+1]=='sessionwise'
    assert cmd[cmd.index('--mem-mb')+1]=='6000' and 'MNI152NLin6Asym:res-2' in cmd
    assert 'existing-revision' in str(work)

def test_common_compute_limit_remains_five(tmp_path):
    d=tmp_path/'continuous5';d.mkdir();(d/'settings.json').write_text(json.dumps({'global_compute_limit':6,'target_concurrency':6}))
    compute_slots.configure(tmp_path)
    with pytest.raises(ValueError,match='five'):
        with compute_slots.lease('ADNI999S9999','xcpd'):pass

def test_preexisting_exit_receipt_completes_without_relaunch(tmp_path,monkeypatch):
    observer=load('handoff_observer',ROOT/'02_custom/s7b_sessionwise_preprocessing/observe.py')
    runtime=tmp_path/'runtime';bids=runtime/'bids';bids.mkdir(parents=True);(bids/'input').write_bytes(b'original')
    folder=runtime/'logs/attempt';folder.mkdir(parents=True);p=folder/'run.json';case={'subject':'ADNI999S9999','session':'M000'}
    rec={'stage':'fmriprep','case':case,'image':{'resolved':'image@digest'},'config':{'runtime':str(runtime)},'status':'running',
         'input_before':{'input':observer.sha(bids/'input')}};p.write_text(json.dumps(rec))
    (folder/'handoff-container-exit.json').write_text(json.dumps({'case':case,'image':'image@digest','container_id':'fixed-container-id','exit_code':0,'observed_ended_at':'2026-11-01T00:00:00Z'}))
    monkeypatch.setattr(observer.subprocess,'run',lambda *a,**k:pytest.fail('Must not launch a container'))
    observer.adopt(p)
    assert json.loads(p.read_text())['status']=='execution_completed_QC_required'
    assert json.loads(p.read_text())['input_unchanged'] is True

def test_receipt_with_wrong_identity_is_rejected(tmp_path):
    observer=load('handoff_observer_conflict',ROOT/'02_custom/s7b_sessionwise_preprocessing/observe.py')
    p=tmp_path/'run.json';p.write_text(json.dumps({'stage':'fmriprep','case':{'subject':'ADNI999S9999','session':'M000'},'image':{'resolved':'original'}}))
    (tmp_path/'handoff-container-exit.json').write_text(json.dumps({'case':{'subject':'ADNI998S9998'},'image':'other'}))
    with pytest.raises(ValueError,match='identity'):observer.adopt(p)

def test_compatibility_deployment_rejects_changed_scientific_config(tmp_path):
    cfg=tmp_path/'config.json';cfg.write_text('{}');dep=tmp_path/'deployment.json';dep.write_text(json.dumps({'xcpd_config_sha256':'different'}))
    with pytest.raises(ValueError,match='configuration changed'):live.verify_deployment(dep,cfg)


def compatibility_fixture(tmp_path):
    p=load('fixture_pipeline',ROOT/'02_custom/s10_xcpd_integrated_qc/pipeline.py')
    cfg=p.load(ROOT/'03_config/xcpd_linc.example.json');cfg.update(root=str(tmp_path),repo=str(p.DEFAULT_UPSTREAM))
    cp=tmp_path/'cfg.json';p.save(cp,cfg);cid=cfg['run_id']+'-'+p.digest(cfg)[:12]
    hub=tmp_path/'postprocessing'/cid;p.save(hub/'configuration.json',{**cfg,'_config_id':cid})
    (tmp_path/'continuous5').mkdir();p.save(tmp_path/'continuous5/settings.json',{'target_concurrency':5,'global_compute_limit':5})
    dep={'root':str(tmp_path),'xcpd_config_sha256':live.sha(cp),'legacy_sources_sha256':{},'xcpd_config_id':cid,'active_xcpd':{}}
    dp=tmp_path/'deployment.json';p.save(dp,dep)
    return live.pipeline(cp,dp),cp,dp


def test_live_deployment_preserves_configuration_and_result_identity(tmp_path):
    app,cp,dp=compatibility_fixture(tmp_path);before=cp.read_bytes()
    assert app.config_id==json.loads((app.hub/'configuration.json').read_text())['_config_id']
    assert cp.read_bytes()==before
    row=dict(sub='sub-ADNI999S9999',ses='ses-M000',task='task-rest',run='',acq='',dir='',echo='',rec='',source_pair=str(tmp_path/'pair'))
    attempt=app.attempt_root(row)/'attempt-001';attempt.mkdir(parents=True)
    (attempt/'execution.json').write_text(json.dumps({'status':'success'}))
    (attempt/'output_manifest.json').write_text('{}')
    (attempt/'output_validation.json').write_text(json.dumps({'xcpd_status':'success','functional_outputs_valid':True}))
    execution=(attempt/'execution.json').read_bytes()
    app.run_one(row)
    assert (attempt/'execution.json').read_bytes()==execution
    assert len(list(app.attempt_root(row).glob('attempt-*')))==1


def test_running_legacy_attempt_delegates_only_to_frozen_completion_source(tmp_path):
    from types import SimpleNamespace
    app,cp,dp=compatibility_fixture(tmp_path)
    row=dict(sub='sub-ADNI999S9999',ses='ses-M000',task='task-rest',run='',acq='',dir='',echo='',rec='',source_pair=str(tmp_path/'pair'))
    attempt=app.attempt_root(row)/'attempt-001';attempt.mkdir(parents=True)
    record={'status':'running','container':'existing-container','pipeline_sha256':'original-code'}
    (attempt/'execution.json').write_text(json.dumps(record));before=(attempt/'execution.json').read_bytes()
    app.deployment.update(active_xcpd={'existing-container':{'pipeline_sha256':'original-code','container_id':'same-id'}},legacy_xcpd=str(tmp_path/'frozen'))
    calls=[];app.legacy=SimpleNamespace(run_one=lambda r,force_retry:calls.append((r,force_retry)))
    app.run_one(row)
    assert calls==[(row,False)] and (attempt/'execution.json').read_bytes()==before
    record['pipeline_sha256']='wrong-code';(attempt/'execution.json').write_text(json.dumps(record))
    with pytest.raises(ValueError,match='identity changed'):app.run_one(row)


def test_controller_transient_error_keeps_admission_loop_alive(tmp_path,monkeypatch):
    from types import SimpleNamespace
    here=tmp_path/'continuous5';here.mkdir()
    settings={'target_concurrency':5,'admission':{'slots':5,'floor_gib':20,'per_slot_gib':12}}
    (here/'settings.json').write_text(json.dumps(settings))
    app=queue.Queue.__new__(queue.Queue);app.settings=settings;app.plan=[];app.state={}
    app.check_sources=lambda:None
    calls=[]
    def publish():
        calls.append('publish')
        if len(calls)==1:raise TimeoutError('transient controller I/O')
    app.publish_originals=publish
    monkeypatch.setattr(queue,'HERE',here);monkeypatch.setattr(queue,'ROOT',tmp_path)
    deployment=tmp_path/'deployment.json';deployment.write_text('{}');monkeypatch.setattr(queue,'DEPLOYMENT',deployment)
    monkeypatch.setattr(queue.subprocess,'Popen',lambda *a,**k:SimpleNamespace())
    monkeypatch.setattr(queue.compute_slots,'running_subjects',lambda **kw:set())
    sleeps=[]
    def pause(seconds):
        sleeps.append(seconds)
        if len(sleeps)>1:raise AssertionError('Controller did not recover after the transient failure')
    monkeypatch.setattr(queue.time,'sleep',pause)
    app.run()
    assert calls==['publish','publish'] and sleeps==[15]
    assert json.loads((here/'status.json').read_text())['mode']=='queue_exhausted'
    assert 'controller_loop_error' in (here/'events.jsonl').read_text()


def test_failed_controller_future_does_not_block_other_workers(monkeypatch):
    from concurrent.futures import Future
    app=queue.Queue.__new__(queue.Queue);updates=[];app.update=lambda *a,**k:updates.append((a,k))
    failed=Future();failed.set_exception(RuntimeError('lost observer connection'))
    running=Future();done=Future();done.set_result(None)
    futures={'ADNI999S9999':failed,'ADNI998S9998':running,'ADNI997S9997':done}
    events=[];monkeypatch.setattr(queue,'event',lambda *a,**k:events.append(a))
    app.finish_futures(futures)
    assert list(futures)==['ADNI998S9998']
    assert updates[0][0]==('ADNI999S9999','resume_queued')
    assert events==[('controller_worker_error',)]
