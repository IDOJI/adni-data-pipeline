"""Refill a rolling five-subject window after verified archival; preserve identity gates."""
import argparse
from pathlib import Path
import json,sys,importlib.util,hashlib,csv,subprocess,time,datetime,fcntl
LAB=Path(__file__).resolve().parents[1]
R=H=D=OUT=GATE=None
PY=sys.executable
sys.path.insert(0,str(LAB/'04_workflow'));sys.path.insert(0,str(LAB/'02_custom/s5d_bids_identity'))
import queue_service as qmod
import binding,continuation,rolling,source_review

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):
 t=p.with_suffix('.writing');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def main():
 global R,H,D,OUT,GATE
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--deployment',type=Path,required=True);parser.add_argument('--gate-status',type=Path,required=True);a=parser.parse_args()
 R=a.root.absolute();H=R/'continuous5';D=a.deployment.resolve();GATE=a.gate_status.resolve();OUT=H/'verified-batch-feed'
 if R.resolve()==LAB.parent or LAB.parent in R.resolve().parents or R.resolve() in LAB.parent.parents:raise ValueError('Runtime must be outside repository')
 OUT.mkdir(exist_ok=True)
 if not GATE.exists() or json.loads(GATE.read_text()).get('status')!='ready':return
 with (OUT/'feed.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while True:
   try:
    if not GATE.exists() or json.loads(GATE.read_text()).get('status')!='ready':time.sleep(30);continue
    settings=json.loads((H/'settings.json').read_text());reg=continuation.load_registry(settings['verified_continuation']['path'],settings['verified_continuation']['sha256'])
    qmod.compute_slots.configure(R)
    legacy=rolling.reconcile(R,reg);completed=rolling.archived(H)
    admitted,failed,waiting=rolling.admission_window(R,reg,completed,legacy)
    rolling.launch_workers(R,D,reg,legacy,completed,admitted)
    available=max(0,5-len(admitted))
    save(H/'rolling/status.json',{'at':qmod.now(),'window_limit':5,'admitted_subjects':sorted(admitted),'held_failures':sorted(failed),'waiting_registered_subjects':sorted(waiting),'unarchived_subjects':sorted(set(reg['subjects'])-completed),'available_slots':available,'LLM_calls':0})
    if not available:time.sleep(30);continue
    receipt=json.loads(Path(next(iter(reg['subjects'].values()))['receipt']).read_text());base=json.loads(Path(receipt['inputs']['config']['path']).read_text())
    epis={x['EPI_KEY']:x for x in binding.read_csv(base['epi_manifest'])}
    qmod.ROOT=R;qmod.HERE=H;qmod.DEPLOYMENT=D;qmod.ORIGINAL=set(json.loads(D.read_text())['original_subjects']);qmod.compute_slots.configure(R);q=qmod.Queue()
    held=json.loads((OUT/'held.json').read_text()) if (OUT/'held.json').exists() else {}
    if Path(settings['archive']).stat().st_flags & 0x40000000:
     raise RuntimeError('Original ZIP is online-only; wait for source availability without holding individual subjects')
    chosen=[]
    q.check_sources()
    for row in q.plan:
     sub=row['subject']
     skip=source_review.blocked(R,sub,row)
     if skip:
      source_review.record_skip(R,row,skip['skip_reasons'],skip.get('evidence'));held[sub]='skipped_source_review: '+';'.join(skip['skip_reasons']);continue
     if sub in q.state or sub in reg['subjects'] or sub in held:continue
     key=f"{row['ptid']}:{row['epi_date']}:I{row['epi_image_id']}";e=epis.get(key,{})
     if e.get('PROPOSED_T1_IMAGE_ID')!=row['t1_image_id'] or e.get('T1_PAIRING_STATUS')!='same_day_proposed' or e.get('EPI_METADATA_QC_STATE')!='documented' or binding.true(e.get('PAIRING_REVIEW_REQUIRED')):
      held[sub]='Existing queue pair does not satisfy current verified same-day proposal';continue
     try:
      config=q.prepare(row);chosen.append((row,config));print('PREPARED',sub,flush=True)
     except ValueError as exc:
      if source_review.policy(R) is not None:source_review.record_skip(R,row,['input_verification_failed:'+str(exc)])
      held[sub]=repr(exc);print('SKIPPED_INPUT_REVIEW',sub,repr(exc),flush=True)
     except Exception as exc:held[sub]=repr(exc);print('HELD',sub,repr(exc),flush=True)
     if len(chosen)==available:break
    save(OUT/'held.json',held)
    if not chosen:
     save(OUT/'status.json',{'status':'no_more_dispatch_eligible_pairs','held':len(held),'at':qmod.now()});time.sleep(30);continue
    batch=OUT/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');batch.mkdir()
    cfg={**base,'bids_roots':list(dict.fromkeys(base['bids_roots']+[str(H/'cases'/row['subject']/'bids') for row,c in chosen])), 'hash_evidence':list(dict.fromkeys(base['hash_evidence']+[str(H/'cases'/row['subject']/'source_mapping.json') for row,c in chosen])),'output_dir':str(batch),'prefix':''}
    save(batch/'binding-config.json',cfg);summary=binding.run(batch/'binding-config.json');plans=json.loads((batch/'05.execution-plans.json').read_text());added=[]
    for row,config in chosen:
     plan=next((x for x in plans if x['subject']==row['subject'] and x['epi_image_id']==row['epi_image_id'] and x['t1_image_id']==row['t1_image_id']),None)
     if not plan:held[row['subject']]='Binding held pair; see batch evidence';continue
     runner,script=q.backend(row['subject']);launcher=settings.get('execution_launcher',{});launcher_path=launcher.get('path',str(LAB/'02_custom/s7c_ants_iteration_logging/run.py'))
     if launcher and sha(launcher_path)!=launcher['sha256']:raise ValueError('Execution launcher fingerprint changed')
     paths={'config':str(config),'backend':str(script),'receipt':str(batch/'07.binding-receipt.json'),'launcher':launcher_path};route={**paths,**{k+'_sha256':sha(p) for k,p in paths.items()},'runtime':str(R/'runs'/row['subject']),'epi_key':plan['epi_key'],'allowed_stages':['mriqc','fmriprep']};reg['subjects'][row['subject']]=route
     continuation.verify_route(reg,row['subject'],config,script,row);added.append(row['subject'])
    save(OUT/'held.json',held)
    if not added:continue
    save(batch/'continuation-registry.json',reg);settings=json.loads((H/'settings.json').read_text());settings['verified_continuation']={'path':str(batch/'continuation-registry.json'),'sha256':sha(batch/'continuation-registry.json')};save(H/'settings.json',settings)
    save(OUT/'status.json',{'status':'rolling_dispatched','subjects':added,'at':qmod.now(),'binding_summary':summary,'LLM_calls':0});admitted,_,_=rolling.admission_window(R,reg,completed,legacy);rolling.launch_workers(R,D,reg,legacy,completed,admitted);print('DISPATCHED',added,flush=True)
   except Exception as exc:
    save(OUT/'status.json',{'status':'waiting_retry','error':repr(exc),'at':qmod.now()});print('ERROR',repr(exc),flush=True)
   time.sleep(30)
if __name__=='__main__':main()
