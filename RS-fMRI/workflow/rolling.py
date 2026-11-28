"""Rolling subject window with isolated workers and unchanged verified S6/S7 runners."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import queue_service as q
import source_review


def load(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def archived(here):
    result=set()
    for path in (here/'offload_receipts').glob('*.json'):
        rec=load(path)
        if rec.get('status')=='archived_and_local_space_reclaimed' and (Path(rec['external_path'])/'archive_manifest.json').is_file():
            result.add(rec['subject'])
    return result


def vacancies(subjects, completed, limit=5):
    if limit!=5:raise ValueError('Authorized rolling window is five')
    return max(0,limit-len(set(subjects)-set(completed)))


def select_window(subjects, states, completed, active=(), priority=(), limit=5):
    """Retain owners/deliveries; bounded terminal failures never occupy admission."""
    if limit != 5:raise ValueError('Authorized rolling window is five')
    pending = set(subjects) - set(completed)
    held = {s for s in pending if states.get(s, {}).get('status') == 'skipped_source_review' or
            (states.get(s, {}).get('status') == 'deferred_or_failed'
            and not any(x.get('remaining', 0) > 0 for x in states.get(s, {}).get('retry_plan', {}).values()))}
    # A terminal state may be written just before its owner releases the lock.
    owners = pending & set(active)
    deliveries = {s for s in pending-held if states.get(s, {}).get('status') == 'completed_QC_pending'}
    chosen = owners | deliveries
    order = list(dict.fromkeys([*priority, *subjects]))
    candidates = [s for s in order if s in pending - held - chosen]
    chosen.update(candidates[:max(0, limit-len(chosen))])
    return chosen, held - owners, set(candidates) - chosen


def admission_window(root, registry, completed, legacy=()):
    h = root/'continuous5'
    states = load(h/'state.json', {})
    states.update({p.stem:load(p) for p in (h/'rolling/jobs').glob('*.json')})
    subjects = [s for s in registry['subjects'] if s not in legacy]
    for subject in subjects:
        if source_review.blocked(root, subject):
            states[subject] = {**states.get(subject,{}),'status':'skipped_source_review'}
    active = q.compute_slots.running_subjects() | q.compute_slots.live_reservations(h/'rolling/jobs')
    settings = load(h/'settings.json', {})
    return select_window(subjects, states, completed, active, settings.get('retry_priority', []))


def locked(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
    return False


class SubjectQueue(q.Queue):
    """Keep mutable worker/retry state separate from an older live controller."""
    def __init__(self,subject):
        super().__init__();self.subject=subject;self.job=q.HERE/'rolling/jobs'/(subject+'.json')
        self.state.update({subject:load(self.job,{})})

    def update(self,subject,status,**extra):
        if subject!=self.subject:raise ValueError('Cross-subject worker update')
        value={**load(self.job,{}),'subject':subject,'status':status,'updated_at':q.now(),**extra}
        q.save(self.job,value);self.state[subject]=value

    def retry_request(self,sub,stage,consume=False):
        value=load(self.job,{});entry=value.get('retry_plan',{}).get(stage)
        if not entry or entry.get('remaining',0)<=0:return False
        if consume:
            entry['remaining']-=1;entry['launched_at']=q.now();q.save(self.job,value)
        return True

    def enqueue_failed_stage(self,sub,stage):
        if source_review.blocked(q.ROOT,sub):return False
        record=q.latest(sub,stage)
        if not self.settings.get('retry_new_failures_once') or not record or record.get('status')!='failed' or record.get('input_unchanged') is not True:return False
        value=load(self.job,{});plan=value.setdefault('retry_plan',{})
        if stage in plan:return False
        plan[stage]={'remaining':1,'requested_at':q.now(),'previous_execution':record}
        q.save(self.job,value);self.update(sub,'retry_queued',retry_kind='failed',retry_in_progress=False)
        return True


def run_worker(root,deployment,subject):
    q.ROOT=Path(root).absolute();q.HERE=q.ROOT/'continuous5';q.DEPLOYMENT=Path(deployment).resolve()
    q.ORIGINAL=set(load(q.DEPLOYMENT)['original_subjects']);q.compute_slots.configure(q.ROOT)
    lock=q.HERE/'rolling/jobs'/(subject+'.lock');lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        app=SubjectQueue(subject);row=next(r for r in app.plan if r['subject']==subject)
        # Never consume another subject's retry budget or overwrite legacy state.json.
        while True:
            app.work(row)
            if load(app.job)['status'] not in ('retry_queued','resume_queued'):break


def launch_workers(root,deployment,registry,legacy,completed,admitted=None):
    h=root/'continuous5';directory=h/'rolling/jobs';directory.mkdir(parents=True,exist_ok=True)
    for subject in registry['subjects']:
        if subject in legacy or subject in completed:continue
        if admitted is not None and subject not in admitted:continue
        if source_review.blocked(root,subject):continue
        path=directory/(subject+'.json');value=load(path,{})
        if value.get('status') in ('completed_QC_pending','skipped_source_review'):continue
        if value.get('status')=='deferred_or_failed' and not any(x.get('remaining',0)>0 for x in value.get('retry_plan',{}).values()):continue
        if locked(directory/(subject+'.lock')):continue
        if not value:q.save(path,{'subject':subject,'status':'reserved','updated_at':q.now()})
        log=root/'continuous5/rolling/logs'/(subject+'.log');log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('a') as stream:
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--root',str(root),'--deployment',str(deployment),'--subject',subject],
                             stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)


def reconcile(root,registry):
    """Retire only a legacy controller whose own workers have all finished."""
    h=root/'continuous5';directory=h/'rolling';directory.mkdir(exist_ok=True)
    migration=directory/'legacy-controller.json';state=load(h/'state.json',{})
    if not migration.exists():
        q.save(migration,{'legacy_subjects':list(state),'captured_at':q.now(),'retired':False})
    record=load(migration);legacy=set(record['legacy_subjects'])-set(record.get('transferred_to_rolling', []))
    if not record['retired']:
        busy={s for s in legacy if state.get(s,{}).get('status') in ('reserved','preparing','publishing','running_mriqc','running_fmriprep','observing_existing_mriqc','observing_existing_fmriprep','resume_queued') or (s in registry['subjects'] and state.get(s,{}).get('status')=='retry_queued')}
        if not busy:
            listing=subprocess.check_output(['launchctl','list'],text=True).splitlines()
            pid=next((line.split()[0] for line in listing if line.split()[-1]=='com.codex.adni-sb-queue-five'),'-')
            children=[]
            if pid!='-':
                ps=subprocess.check_output(['ps','-axo','ppid=,command='],text=True)
                children=[line for line in ps.splitlines() if line.split(maxsplit=1)[0]==pid and 'caffeinate' not in line]
            if not children:
                # No owned stage process/container is interrupted; newer workers use separate sessions.
                for label in ['com.codex.adni-sb-queue-watchdog','com.codex.adni-sb-queue-five']:
                    subprocess.run(['launchctl','disable',f'gui/{os.getuid()}/{label}'],check=True)
                    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],capture_output=True)
                record.update(retired=True,retired_at=q.now(),no_legacy_stage_children=True);q.save(migration,record)
    jobs={p.stem:load(p) for p in (directory/'jobs').glob('*.json')}
    if record['retired']:
        state.update(jobs);q.save(h/'state.json',state)
        running=q.compute_slots.running_subjects();prep=q.compute_slots.running_subjects(include_xcpd=False)
        completed=archived(h);occupied=set(registry['subjects'])-completed
        q.save(h/'status.json',{'updated_at':q.now(),'mode':'rolling','controller_pid':os.getpid(),'target_concurrency':5,
            'global_compute_limit':5,'global_active_subjects':sorted(running),'global_active_count':len(running),
            'active_subjects':sorted(prep),'active_count':len(prep),'unarchived_subjects':sorted(occupied),
            'rolling_window_limit':5,'completed_new':sum(v.get('status')=='completed_QC_pending' for v in state.values()),'LLM_calls':0})
    return legacy


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True,type=Path);parser.add_argument('--deployment',required=True,type=Path);parser.add_argument('--subject',required=True);args=parser.parse_args()
    run_worker(args.root,args.deployment,args.subject)


if __name__=='__main__':main()
