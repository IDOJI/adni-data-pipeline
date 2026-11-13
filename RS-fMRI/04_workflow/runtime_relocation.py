"""Relocate an idle managed runtime on one filesystem, preserving recorded paths."""
import argparse
import datetime as dt
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.writing')
    temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def managed_containers(runner=subprocess.run):
    result=runner(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True,check=True,timeout=30)
    return [n for n in result.stdout.splitlines() if n.startswith(('statmind-','adni-xcpd-'))]


def ready(cfg, runner=subprocess.run):
    root=Path(cfg['source']);h=root/'continuous5'
    if managed_containers(runner):return False,'waiting_for_active_preprocessing_or_xcpd'
    state=load(h/'state.json')
    if any(state.get(s,{}).get('status')!='completed_QC_pending' for s in cfg['subjects']):
        return False,'waiting_for_current_batch_preprocessing'
    metrics=load(root/'postprocessing/metrics_export_status.json').get('pairs',{})
    spec=importlib.util.spec_from_file_location('relocation_offload',cfg['offloader_source'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    offloader=module.Offloader(root,load(h/'offload_settings.json'))
    offloader.check_volume()
    for subject in cfg['subjects']:
        receipts=[load(p) for p in (h/'offload_receipts').glob(subject+'_*.json')]
        if not receipts or any(r.get('status')!='archived_and_local_space_reclaimed' for r in receipts):
            return False,'waiting_for_validated_postprocessing_and_archival'
        for receipt in receipts:
            target=Path(receipt['external_path'])
            if not offloader.postprocessing_ready(target):return False,'waiting_for_validated_postprocessing'
            if metrics.get(str(target)) not in ('exported','already_exported'):
                return False,'waiting_for_S12_export'
    result=runner(['launchctl','list'],capture_output=True,text=True,check=True,timeout=30)
    for line in result.stdout.splitlines():
        parts=line.split()
        if parts and parts[-1]==cfg['queue_label'] and parts[0]!='-':return False,'waiting_for_queue_normal_exit'
    return True,'ready_to_relocate'


def relocate(source, destination, expected_identity):
    """Only rename; never copy/delete payloads or rewrite provenance/configuration."""
    source=Path(source);destination=Path(destination)
    if source.is_symlink():
        if source.resolve()!=destination.resolve():raise ValueError('Source alias points elsewhere')
    elif source.exists():
        st=source.stat()
        if [st.st_dev,st.st_ino]!=expected_identity:raise ValueError('Runtime identity changed')
        if destination.is_symlink():raise ValueError('Destination is a symlink')
        if destination.exists():
            if not destination.is_dir() or any(destination.iterdir()):raise ValueError('Destination is not empty')
        if source.stat().st_dev!=destination.parent.stat().st_dev:raise ValueError('Cross-filesystem relocation is not supported')
        if destination.exists():destination.rmdir()  # Empty directory only; never remove payloads.
        source.rename(destination)
        source.symlink_to(destination,target_is_directory=True)
    else:
        # Recover the rename-to-alias crash window using the saved directory identity.
        st=destination.stat()
        if [st.st_dev,st.st_ino]!=expected_identity:raise ValueError('Relocated runtime identity differs')
        source.symlink_to(destination,target_is_directory=True)
    st=destination.stat()
    if [st.st_dev,st.st_ino]!=expected_identity or not source.samefile(destination):
        raise ValueError('Relocation identity verification failed')


def service(action,label,runner=subprocess.run,check=True):
    if not label.startswith('com.codex.adni-sb-'):raise ValueError('Unexpected service label')
    domain=f'gui/{os.getuid()}'
    argv=['launchctl',action,domain+'/'+label]
    if action=='bootstrap':argv=['launchctl',action,domain,str(Path.home()/'Library/LaunchAgents'/(label+'.plist'))]
    return runner(argv,capture_output=True,text=True,check=check,timeout=30)


def step(cfg, runner=subprocess.run):
    source=Path(cfg['source']);report=source/'continuous5/runtime-relocation/status.json'
    previous=load(report) if report.exists() else {}
    if previous.get('status')=='completed':return True
    after_rename=source.is_symlink() or not source.exists()
    if not after_rename:
        ok,reason=ready(cfg,runner)
        if not ok:
            save(report,{'status':reason,'at':timestamp(),'destination':cfg['destination'],'subjects':cfg['subjects'],'LLM_calls':0});return False
    if not after_rename:
        for label in cfg['services']:
            service('disable',label,runner)
            service('bootout',label,runner,check=False)
        if managed_containers(runner):raise RuntimeError('Unexpected compute after idle shutdown; relocation held')
    # Closed services have no worker left holding a runtime lock.
    handles=[]
    try:
        if source.exists() and not after_rename:
            paths=[source/'continuous5/queue.lock',source/'continuous5/offload.lock',source/'continuous5/verified-batch-feed/feed.lock',source/'postprocessing'/cfg['xcpd_config_id']/'worker.lock']
            for path in paths:
                handle=path.open('a');handles.append(handle);fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        relocate(source,Path(cfg['destination']),cfg['source_identity'])
        save(report,{'status':'relocated_verifying','at':timestamp(),'destination':cfg['destination'],'compatibility_alias':cfg['source'],'LLM_calls':0})
        for command in cfg['checks']:
            runner(command,capture_output=True,text=True,check=True,timeout=120)
    finally:
        for handle in handles:handle.close()
    for label in cfg['services']:
        service('enable',label,runner)
        state=runner(['launchctl','print',f'gui/{os.getuid()}/{label}'],capture_output=True,text=True,timeout=30)
        if state.returncode!=0:service('bootstrap',label,runner)
    save(report,{'status':'completed','at':timestamp(),'destination':cfg['destination'],'compatibility_alias':cfg['source'],'subjects':cfg['subjects'],'services_resumed':cfg['services'],'scientific_configuration_rewritten':False,'LLM_calls':0})
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True);args=parser.parse_args()
    cfg=load(args.config)
    source=Path(cfg['source']);destination=Path(cfg['destination'])
    if not source.is_absolute() or not destination.is_absolute() or source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Relocation requires separate absolute runtime paths')
    # Config and lock are reached through the persistent source alias after relocation.
    lock_path=Path(cfg['source'])/'continuous5/runtime-relocation/worker.lock'
    if not lock_path.parent.exists() and Path(cfg['destination']).exists():
        relocate(cfg['source'],cfg['destination'],cfg['source_identity'])
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            try:
                if step(cfg):return
            except Exception as exc:
                save(lock_path.parent/'status.json',{'status':'waiting_retry','at':timestamp(),'error':repr(exc),'LLM_calls':0})
                print(repr(exc),flush=True)
            time.sleep(30)


if __name__=='__main__':main()
