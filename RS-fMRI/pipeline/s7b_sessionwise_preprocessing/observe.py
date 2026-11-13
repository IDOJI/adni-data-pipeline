"""Observe existing containers after the original host runners disappeared."""
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def save(p, value):
    tmp = p.with_name(p.name + '.recovery.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(p)

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def adopt(p):
    record = json.loads(p.read_text())
    case = record['case']
    name = f"statmind-{record['stage']}-{case['subject']}-{case['session']}"
    receipt = p.parent / 'recovered-container-exit.json'
    handoff=p.parent/'handoff-container-exit.json'
    if handoff.exists():
        proof=json.loads(handoff.read_text())
        if proof['case']!=case or proof['image']!=record['image']['resolved']:
            raise ValueError('Handoff receipt identity mismatch')
        save(receipt,proof)
    if receipt.exists():
        result = json.loads(receipt.read_text())
    else:
        for _ in range(30):
            result=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
            if result.returncode==0:break
            if handoff.exists():return adopt(p)
            time.sleep(1)
        if result.returncode:raise RuntimeError('Container missing and no preserved exit receipt')
        inspect=json.loads(result.stdout)[0]
        assert inspect['Config']['Image'] == record['image']['resolved'], 'Image identity differs'
        assert case['subject'] in inspect['Config']['Cmd'], 'Subject identity differs'
        assert inspect['State']['Running'], 'Container is no longer running'
        cid = inspect['Id']
        save(p.parent / 'observer-recovery.json', {
            'attached_at': now(), 'container_id': cid,
            'original_runner_missing': True, 'container_restarted': False,
            'command_changed': False, 'observer_pid': os.getpid()})
        waiter = subprocess.Popen(['docker', 'wait', cid], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        log = p.parent / 'console.log'
        since = dt.datetime.fromtimestamp(log.stat().st_mtime - 2, dt.timezone.utc).isoformat()
        with log.open('a') as stream:
            stream.write('\n[observer recovery: reattached to existing container]\n')
            stream.flush()
            logger = subprocess.Popen(['docker', 'logs', '--follow', '--since', since, cid], stdout=stream, stderr=subprocess.STDOUT)
            out, err = waiter.communicate()
            if waiter.returncode or not out.strip().isdigit():
                raise RuntimeError(f'Cannot establish container exit: {err}')
            result = {'exit_code': int(out.strip()), 'observed_ended_at': now(), 'container_id': cid}
            save(receipt, result)
            try:
                logger.wait(timeout=20)
            except subprocess.TimeoutExpired:
                logger.terminate()
                logger.wait(timeout=10)
    bids = Path(record['config']['runtime']) / 'bids'
    after = {relative: sha(bids / relative) for relative in record['input_before']}
    record.update(container_ended_at=result['observed_ended_at'], exit_code=result['exit_code'],
                  input_after=after, input_unchanged=after == record['input_before'],
                  ended_at=now(), completion_recorded_by='recovered_observer')
    record['status'] = 'execution_completed_QC_required' if record['exit_code'] == 0 and record['input_unchanged'] else 'failed'
    for citation in (Path(record['config']['runtime']) / 'derivatives' / record['stage'] / 'logs').glob('CITATION.*'):
        dest = p.parent / 'citations' / citation.name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(citation, dest)
    save(p, record)
    lock = Path(record['config']['runtime']) / 'pipeline.lock'
    if lock.exists():
        owner = json.loads(lock.read_text())
        if owner.get('stage') == record['stage'] and owner.get('case') == case:
            try:
                os.kill(int(owner['pid']), 0)
            except ProcessLookupError:
                lock.unlink()
    print(case['subject'], record['status'], flush=True)
