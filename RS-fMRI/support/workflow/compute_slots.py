"""Host-wide subject limit shared by S6/S7 and XCP-D. No model calls."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

HERE=None

def configure(root):
    global HERE
    HERE=Path(root).resolve()/"continuous5"
    if not (HERE/"settings.json").is_file():raise ValueError("Missing shared compute settings")

def running_subjects(include_xcpd=True):
    names=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True,timeout=25).splitlines()
    allowed=('statmind-mriqc-','statmind-fmriprep-')+ (('adni-xcpd-','statmind-xcpd-') if include_xcpd else ())
    return {m.group(0) for name in names if name.startswith(allowed) for m in [re.search(r'ADNI[0-9]+S[0-9]+',name)] if m}

def live_reservations(directory):
    subjects=set()
    for path in directory.glob('ADNI*.lock'):
        with path.open('a+') as f:
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:subjects.add(path.stem)
            else:fcntl.flock(f,fcntl.LOCK_UN)
    return subjects

@contextmanager
def lease(subject,stage,poll=2):
    if not re.fullmatch(r'ADNI[0-9]+S[0-9]+',subject):raise ValueError('Invalid compute subject')
    if HERE is None:raise ValueError('Configure the external runtime first')
    settings=json.loads((HERE/'settings.json').read_text());limit=int(settings.get('global_compute_limit',settings['target_concurrency']))
    if limit!=5:raise ValueError('Current authorized total compute limit must remain five')
    directory=HERE/'compute_slots';directory.mkdir(exist_ok=True)
    priority=directory/'xcpd_waiting.json';token=uuid.uuid4().hex
    if stage=='xcpd':priority.write_text(json.dumps({'pid':os.getpid(),'token':token}))
    held=None
    try:
        while held is None:
            with (directory/'admission.lock').open('a') as gate:
                fcntl.flock(gate,fcntl.LOCK_EX)
                active=running_subjects()|live_reservations(directory)
                xcpd_waiting=False
                if priority.exists():
                    try:
                        owner=json.loads(priority.read_text());os.kill(int(owner['pid']),0);xcpd_waiting=True
                    except (OSError,ValueError,json.JSONDecodeError):pass
                allowed=subject in active or (len(active)<limit and (stage=='xcpd' or not xcpd_waiting))
                if allowed:
                    candidate=(directory/(subject+'.lock')).open('a+')
                    try:fcntl.flock(candidate,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:candidate.close()
                    else:
                        held=candidate;held.seek(0);held.truncate();held.write(json.dumps({'pid':os.getpid(),'subject':subject,'stage':stage,'acquired_at':time.time()}));held.flush()
            if held is None:time.sleep(poll)
        if stage=='xcpd' and priority.exists() and json.loads(priority.read_text()).get('token')==token:priority.unlink()
        yield
    finally:
        if held is not None:fcntl.flock(held,fcntl.LOCK_UN);held.close()
        if stage=='xcpd' and priority.exists():
            try:
                if json.loads(priority.read_text()).get('token')==token:priority.unlink()
            except (OSError,json.JSONDecodeError):pass
