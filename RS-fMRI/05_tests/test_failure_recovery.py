"""Synthetic failure admission and execution-only recovery checks."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

LAB = Path(__file__).resolve().parents[1]
SOURCE = LAB/'04_workflow'
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(LAB/'02_custom/s5d_bids_identity'))
def module(name):
    spec = importlib.util.spec_from_file_location('recovery_test_'+name, SOURCE/(name+'.py'))
    m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
rolling = module('rolling')
recovery = module('recovery_runner')

def test_terminal_failure_frees_slot_without_losing_history():
    states={'A':{'status':'deferred_or_failed','retry_plan':{'mriqc':{'remaining':0}}}}
    chosen, held, waiting=rolling.select_window(['A','B','C','D','E','F'],states,set(),{'B','C'})
    assert chosen=={'B','C','D','E','F'} and held=={'A'} and not waiting
    assert states['A']['status']=='deferred_or_failed'

def test_owner_never_evicted_and_fourth_retry_waits():
    chosen,held,waiting=rolling.select_window(['A','B','C','D','E','F'],{},set(),{'A','B'},['C','D','E','F'])
    assert chosen=={'A','B','C','D','E'} and waiting=={'F'} and not held
    chosen,_,waiting=rolling.select_window(['A','B','C','D','E','F'],{}, {'C'}, {'A','B','D','E'}, ['F'])
    assert chosen=={'A','B','D','E','F'} and not waiting

def test_finished_output_holds_until_archive_and_renewed_failure_is_eligible():
    states={'A':{'status':'completed_QC_pending'},'B':{'status':'deferred_or_failed','retry_plan':{'mriqc':{'remaining':1}}}}
    chosen,held,_=rolling.select_window(['A','B','C','D','E','F'],states,set(),priority=['B'])
    assert len(chosen)==5 and {'A','B'}<=chosen and not held
    chosen,_,_=rolling.select_window(['A','B','C','D','E','F'],states,{'A'},priority=['B'])
    assert chosen=={'B','C','D','E','F'}

def test_failure_written_before_owner_exits_keeps_slot():
    chosen,held,_=rolling.select_window(['A','B'],{'A':{'status':'deferred_or_failed'}},set(),{'A'})
    assert 'A' in chosen and 'A' not in held

def test_only_admitted_workers_are_launched(tmp_path, monkeypatch):
    calls=[];monkeypatch.setattr(rolling.subprocess,'Popen',lambda argv,**kw:calls.append(argv))
    rolling.launch_workers(tmp_path,tmp_path/'deployment.json',{'subjects':{'A':{},'B':{}}},set(),set(),{'B'})
    assert len(calls)==1 and calls[0][-1]=='B'

def command():
    return ['docker','run','--memory','8g','--cpus','4','x@sha256:abc','/data','/out','participant','--mem-mb','6000','--random-seed','357','--force','syn-sdc']

def test_resource_recovery_preserves_every_other_argument():
    base=command(); result=recovery.effective_command(base)
    assert base[3]=='8g' and result[3]=='16g'
    assert [(i,a,b) for i,(a,b) in enumerate(zip(base,result)) if a!=b]==[(3,'8g','16g')]
    assert recovery.effective_command(result)==result

@pytest.mark.parametrize('fault',['tag','unknown','missing','duplicate'])
def test_recovery_rejects_unknown_execution(fault):
    argv=command()
    if fault=='tag':argv[6]='unpinned:tag'
    elif fault=='unknown':argv[3]='32g'
    elif fault=='missing':del argv[2:4]
    else:argv[2:2]=['--memory','8g']
    with pytest.raises(ValueError):recovery.effective_command(argv)

def test_effective_execution_is_recorded_separately_from_cache_command(tmp_path):
    calls=[]
    original=SimpleNamespace(run=lambda argv,*a,**kw:calls.append(argv))
    logging=SimpleNamespace(augment=lambda argv,*_:argv+['logging-only'])
    with (tmp_path/'console.log').open('w') as stream:
        recovery.Transport(original,logging).run(command(),stdout=stream)
    proof=json.loads((tmp_path/'execution_environment.json').read_text())
    assert proof['base_cache_argv']==command() and proof['effective_docker_argv']==calls[0]
    assert proof['effective_resource_argv'][3]=='16g' and proof['LLM_calls']==0

def test_technical_retry_retains_review_and_rejects_other_blockers():
    import review_continuation as review
    row={'EPI_KEY':'TEST:2000-01-01:I1','PTID':'TEST','EPI_IMAGE_ID':'1',
         'PROPOSED_T1_IMAGE_ID':'2','REVIEW_FLAGS':'epi_source:protocol_status_review:2',
         'READINESS_BLOCKERS':'pairing_review_pending','BIDS_IDENTITY_STATUS':'verified'}
    auth={'schema':1,'scope':'technical_retry_only','authorization_type':'explicit_user_request',
          'request_text':'Retry this exact pair, retain pending research review',
          'request_reference':'synthetic-test','epi_key':row['EPI_KEY'],'ptid':'TEST',
          'epi_image_id':'1','t1_image_id':'2','review_flags':['epi_source:protocol_status_review:2']}
    review.authorize(row,auth)
    for changes in [{'READINESS_BLOCKERS':'pairing_review_pending;source_QC_pending'},
                    {'BIDS_IDENTITY_STATUS':'pending'}, {'REVIEW_FLAGS':'other_pending_review'}]:
        with pytest.raises(ValueError):review.authorize({**row,**changes},auth)
    with pytest.raises(ValueError):review.authorize(row,{**auth,'t1_image_id':'3'})
    with pytest.raises(ValueError):review.authorize(row,{**auth,'scope':'research_inclusion'})
