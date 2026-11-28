"""Activate prospective logging only after existing preprocessing workers finish."""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import time

LAB = Path(__file__).resolve().parents[2]
LAUNCHER = LAB / 'pipeline/s7c_ants_iteration_logging/run.py'


def save(path, data):
    tmp = path.with_suffix('.writing'); tmp.write_text(json.dumps(data, indent=2)+'\n'); tmp.replace(path)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def arm(root):
    here = Path(root)/'continuous5'; path = here/'ants_logging_activation.json'
    if path.exists():
        return json.loads(path.read_text())
    settings = json.loads((here/'settings.json').read_text())
    original = dict(settings['admission'])
    # Explicit one-time admission hold, not an actual disk-capacity estimate.
    hold = {**original, 'floor_gib': int(shutil.disk_usage(root).total/2**30)+1}
    record = {'status':'waiting_for_idle','armed_at':now(),'original_admission':original,
              'held_admission':hold,'launcher':str(LAUNCHER),'LLM_calls':0}
    save(path,record)
    settings['admission'] = hold
    save(here/'settings.json',settings)
    return record


def check(root, label, runner=subprocess.run):
    here = Path(root)/'continuous5'; path = here/'ants_logging_activation.json'
    record = json.loads(path.read_text())
    if record['status']=='active':
        return record
    settings = json.loads((here/'settings.json').read_text())
    state = json.loads((here/'status.json').read_text())
    if settings['admission'] != record['held_admission']:
        raise ValueError('Admission policy changed during logging activation; preserving the new policy')
    if state.get('ants_iteration_logging_launcher') == str(LAUNCHER):
        settings['admission'] = record['original_admission']
        save(here/'settings.json',settings)
        record.update(status='active',activated_at=now(),admission_restored=True,
                      controller_pid=state.get('controller_pid'))
    else:
        names = runner(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True,check=True,timeout=30).stdout.splitlines()
        active = [n for n in names if n.startswith(('statmind-','adni-xcpd-'))]
        queue_state = json.loads((here/'state.json').read_text())
        busy = [s for s,v in queue_state.items() if v.get('status') in
                ('preparing','reserved','publishing','running_mriqc','running_fmriprep',
                 'observing_existing_mriqc','observing_existing_fmriprep')]
        if active or busy or state.get('global_active_count',0):
            record.update(status='waiting_for_idle',active_containers=active,active_workers=busy,checked_at=now())
        elif record.get('restart_requested_at'):
            record.update(status='waiting_for_new_controller',checked_at=now())
        else:
            # No active containers/workers. Graceful controller termination only;
            # never SIGSTOP/SIGKILL, and never target a Docker process/container.
            result = runner(['launchctl','kill','SIGTERM',f'gui/{__import__("os").getuid()}/{label}'],capture_output=True,text=True,timeout=30)
            if result.returncode:
                raise RuntimeError('Idle controller termination failed: '+result.stderr)
            time.sleep(1)
            runner(['launchctl','kickstart',f'gui/{__import__("os").getuid()}/{label}'],capture_output=True,text=True,timeout=30,check=True)
            record.update(status='waiting_for_new_controller',restart_requested_at=now(),
                          no_active_containers_at_restart=True,no_active_workers_at_restart=True)
    save(path,record)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--service-label',required=True)
    parser.add_argument('--arm',action='store_true')
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args();root=args.root.resolve()
    if not args.service_label.startswith('com.codex.adni-'):
        raise ValueError('Expected an explicitly managed ADNI service')
    if LAB.parent==root or LAB.parent in root.parents or root in LAB.parent.parents:
        raise ValueError('Runtime must be outside the repository')
    if args.arm:
        print(json.dumps(arm(root)),flush=True)
    if args.watch:
        with (root/'continuous5/ants_logging_activation.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            previous=None
            while True:
                try:
                    result=check(root,args.service_label)
                    if result['status']!=previous:
                        print(json.dumps(result),flush=True);previous=result['status']
                    if result['status']=='active':
                        break
                except Exception as exc:
                    print(json.dumps({'at':now(),'error':repr(exc)}),flush=True)
                time.sleep(30)


if __name__=='__main__':main()
