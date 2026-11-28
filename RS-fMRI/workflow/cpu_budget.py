"""Maintain an external CPU quota without changing imaging commands or caches."""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import re
import subprocess
import time

NAMES = re.compile(r'^(?:statmind-(?:fmriprep|mriqc)-ADNI\d+S\d+-|(?:adni|statmind)-xcpd-ADNI\d+S\d+-)')


def now():return dt.datetime.now(dt.timezone.utc).isoformat()


def reconcile(cpus, runner=subprocess.check_output):
    if not 0 < cpus <= 4:raise ValueError('CPU quota must be in (0, 4]')
    ids = runner(['docker', 'ps', '-q'], text=True, timeout=30).split()
    items = json.loads(runner(['docker', 'inspect', *ids], text=True, timeout=30)) if ids else []
    rows = []
    for item in items:
        name = item['Name'].lstrip('/')
        if not NAMES.match(name):continue
        changed = item['HostConfig']['NanoCpus'] != round(cpus * 1_000_000_000)
        if changed:runner(['docker', 'update', '--cpus', str(cpus), item['Id']], text=True, timeout=30)
        rows.append({'name':name, 'id':item['Id'], 'started_at':item['State']['StartedAt'], 'cpus':cpus, 'changed':changed})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--cpus', type=float, default=1.5)
    p.add_argument('--poll-seconds', type=float, default=5)
    p.add_argument('action', choices=['once', 'watch'])
    a = p.parse_args()
    if a.poll_seconds < 1:raise ValueError('Poll interval must be at least one second')
    directory = a.root/'continuous5/cpu-budget';directory.mkdir(parents=True, exist_ok=True)
    with (directory/'observer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            try:state = {'at':now(), 'containers':reconcile(a.cpus), 'error':None, 'cpus_per_container':a.cpus, 'LLM_calls':0}
            except Exception as exc:
                state = {'at':now(), 'error':str(exc), 'LLM_calls':0}
                if a.action == 'once':raise
            temporary = directory/'status.writing';temporary.write_text(json.dumps(state, indent=2)+'\n');temporary.replace(directory/'status.json')
            if a.action == 'once':return
            time.sleep(a.poll_seconds)


if __name__ == '__main__':main()
