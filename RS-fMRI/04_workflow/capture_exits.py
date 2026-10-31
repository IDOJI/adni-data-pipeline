"""Preserve Docker exit receipts across a controller-only service handoff."""
import argparse
import json
from pathlib import Path
import subprocess
import time


def save(path, value):
    path=Path(path);tmp=path.with_suffix('.writing');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
    items=json.loads(a.manifest.read_text());observers=[]
    for item in items:
        info=json.loads(subprocess.check_output(['docker','inspect',item['container_id']],text=True))[0]
        if info['Id']!=item['container_id'] or info['Config']['Image']!=item['image']:
            raise ValueError('Container identity changed before exit capture')
        child=subprocess.Popen(['docker','wait',item['container_id']],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        observers.append((item,child))
    time.sleep(1)
    save(a.manifest.with_name('exit-capture-ready.json'),{'observer_pid':__import__('os').getpid(),'containers':[v['container_id'] for v,_ in observers]})
    # Children all observe concurrently; receipts are written as each one finishes.
    while observers:
        for item,child in list(observers):
            if child.poll() is None:continue
            out,err=child.communicate()
            if child.returncode or not out.strip().isdigit():raise RuntimeError('Docker exit capture failed: '+err)
            save(item['receipt'],{'container_id':item['container_id'],'exit_code':int(out.strip()),
                'observed_ended_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                'case':item['case'],'image':item['image']})
            observers.remove((item,child))
        time.sleep(1)


if __name__=='__main__':main()
