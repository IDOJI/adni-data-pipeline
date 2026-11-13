import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'04_workflow'))
import live_services as live
spec=importlib.util.spec_from_file_location('recovery_pipeline',ROOT/'pipeline/s10_xcpd_integrated_qc/pipeline.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def test_override_changes_only_execution_resources_and_records_provenance(tmp_path):
    cfg=p.load(ROOT/'03_config/xcpd_linc.example.json');cfg.update(root=str(tmp_path),_config_id='unchanged')
    before=json.loads(json.dumps(cfg));attempt=tmp_path/'attempt';attempt.mkdir()
    row={'sub':'sub-ADNI999S9999','ses':'ses-M000','task':'task-rest','run':'','acq':'','dir':'','echo':'','rec':'','source_pair':str(tmp_path/'pair')}
    override={'resources':{'cpus':2,'omp_nthreads':1,'mem_mb':12000,'docker_memory':'16g'}}
    original=p.command(cfg,row,attempt,'synthetic');wrapped=live.execution_command_builder(p.command,override,'unchanged');new=wrapped(cfg,row,attempt,'synthetic')
    assert new[new.index('--memory')+1]=='16g' and new[new.index('--nprocs')+1]=='2'
    assert new[new.index('--mem-mb')+1]=='12000' and new[new.index('--omp-nthreads')+1]=='1'
    # Replacing only the resource tokens restores the exact original command.
    for flag in ['--memory','--nprocs','--mem-mb','--omp-nthreads','--cpus']:
        new[new.index(flag)+1]=original[original.index(flag)+1]
    for prefix in ['OMP_NUM_THREADS=','ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=']:
        i=next(i for i,x in enumerate(new) if x.startswith(prefix));new[i]=next(x for x in original if x.startswith(prefix))
    assert new==original and cfg==before
    evidence=json.loads((attempt/'execution_environment.json').read_text())
    assert evidence['effective_resources']==override['resources'] and evidence['config_id']=='unchanged'


def test_scientific_override_is_rejected():
    with pytest.raises(ValueError,match='Only execution'):
        live.execution_command_builder(None,{'fd_threshold':.5},'id')


@pytest.mark.parametrize('oom,tail,expected',[(True,'','container_oom'),(False,'concurrent.futures.process.BrokenProcessPool: failed','broken_process_pool'),(False,'normal registration output',None)])
def test_terminal_worker_monitor_stops_only_confirmed_failures(tmp_path,monkeypatch,oom,tail,expected):
    app=p.Pipeline.__new__(p.Pipeline);app.config_id='synthetic';row={'sub':'sub-ADNI999S9999','ses':'ses-M000','task':'task-rest','run':'','acq':'','dir':'','echo':'','rec':''}
    app.latest=lambda row:(tmp_path,{});app.event=lambda *a,**k:None
    info={'Config':{'Labels':{'adni.config_id':'synthetic','adni.run_key':p.run_key(row)}},'State':{'Running':True,'OOMKilled':oom}}
    monkeypatch.setattr(p,'load_json_command',lambda argv:[info]);calls=[]
    def run(argv,**kw):calls.append(argv);return SimpleNamespace(stdout=tail,stderr='',returncode=0)
    monkeypatch.setattr(p.subprocess,'run',run)
    assert app.detect_terminal_worker_failure('synthetic',row)==expected
    assert bool([x for x in calls if x[:2]==['docker','stop']])==bool(expected)
    assert (tmp_path/'runtime_failure.json').exists()==bool(expected)


def test_monitor_refuses_another_configuration(tmp_path,monkeypatch):
    app=p.Pipeline.__new__(p.Pipeline);app.config_id='expected'
    monkeypatch.setattr(p,'load_json_command',lambda argv:[{'Config':{'Labels':{'adni.config_id':'other'}},'State':{'Running':True,'OOMKilled':True}}])
    monkeypatch.setattr(p.subprocess,'run',lambda *a,**k:pytest.fail('Wrong container must not be stopped'))
    with pytest.raises(ValueError,match='identity differs'):app.detect_terminal_worker_failure('synthetic',{})

@pytest.mark.parametrize('memory,count,expected',[('8g',1,[False,True]),('8g',2,[False]),('16g',1,[False])])
def test_resource_revision_retry_is_bounded(tmp_path,monkeypatch,memory,count,expected):
    from test_live_service_handoff import compatibility_fixture
    app,cp,dp=compatibility_fixture(tmp_path)
    app.deployment['xcpd_execution_override']={'resources':{'docker_memory':'16g'}}
    row={'sub':'sub-ADNI999S9999','ses':'ses-M000','task':'task-rest','run':'','acq':'','dir':'','echo':'','rec':'','source_pair':str(tmp_path/'pair')}
    for number in range(1,count+1):
        directory=app.attempt_root(row)/f'attempt-{number:03}';directory.mkdir(parents=True)
        (directory/'execution.json').write_text(json.dumps({'status':'failed','command':['docker','--memory',memory]}))
    calls=[]
    monkeypatch.setattr(type(app).__mro__[1],'run_one',lambda self,row,force_retry=False:calls.append(force_retry))
    app.run_one(row)
    assert calls==expected
