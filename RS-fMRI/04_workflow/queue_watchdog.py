"""Recover only a stale queue controller; never start/stop imaging containers."""
import argparse
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time


def load(path,default):
    return json.loads(path.read_text()) if path.exists() else default


def save(path,data):
    temp=path.with_suffix('.writing');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(path)


def check(root,label,stale_seconds=180,now=None,runner=subprocess.run):
    now=time.time() if now is None else now
    directory=Path(root)/'continuous5';directory.mkdir(parents=True,exist_ok=True)
    report=directory/'watchdog_status.json';journal=directory/'watchdog_restarts.json'
    record={'at':datetime.fromtimestamp(now,timezone.utc).isoformat(),'service':label,'LLM_calls':0}
    with (directory/'watchdog.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        maintenance=load(directory/'watchdog_maintenance.json',{})
        if float(maintenance.get('until_epoch',0))>now:
            record['status']='maintenance';save(report,record);return record
        state=load(directory/'status.json',{})
        try:age=now-datetime.fromisoformat(state['updated_at']).timestamp()
        except (ValueError,KeyError):age=float('inf')
        record['heartbeat_age_seconds']=round(age) if age!=float('inf') else None
        if state.get('mode') in ('queue_exhausted', 'verified_scope_finished'):
            record['status']=state['mode']
        elif age<=stale_seconds:record['status']='healthy'
        else:
            restarts=[float(t) for t in load(journal,[]) if now-float(t)<3600]
            if len(restarts)>=3:record['status']='recovery_rate_limited'
            else:
                result=runner(['launchctl','kickstart','-k','gui/'+str(os.getuid())+'/'+label],capture_output=True,text=True,timeout=30)
                record.update(status='controller_restarted' if result.returncode==0 else 'restart_failed',returncode=result.returncode,error=result.stderr[-500:])
                if result.returncode==0:save(journal,restarts+[now])
                with (directory/'watchdog_events.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        save(report,record);return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--service-label',required=True);args=p.parse_args()
    if not args.service_label.startswith('com.codex.adni-') or 'queue' not in args.service_label:raise ValueError('Unexpected queue service label')
    root=args.root.resolve();repository=Path(__file__).resolve().parents[2]
    if root==repository or repository in root.parents or root in repository.parents:raise ValueError('Runtime must be external to the repository')
    if not (root/'continuous5/settings.json').is_file():raise ValueError('Missing managed queue settings')
    print(json.dumps(check(args.root.resolve(),args.service_label)))

if __name__=='__main__':main()
