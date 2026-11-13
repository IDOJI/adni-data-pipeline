"""Check an external source ZIP and start verified batch feeding after copy validation."""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time
import zipfile


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, value):
    tmp = path.with_suffix('.writing')
    tmp.write_text(json.dumps(value, indent=2)+'\n'); tmp.replace(path)


def fingerprint(path):
    s = path.stat()
    return {k: getattr(s,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')}


def inspect_copy(path, expected_bytes, required_members, stable_seconds=60, progress=lambda **kw:None):
    path = Path(path)
    if not path.is_file():
        return {'status':'waiting_for_copy','reason':'source_missing'}
    if getattr(path.stat(),'st_flags',0) & 0x40000000:
        return {'status':'waiting_for_copy','reason':'online_only_source'}
    before = fingerprint(path)
    if before['st_size'] != expected_bytes:
        return {'status':'waiting_for_copy','reason':'size_incomplete','observed_bytes':before['st_size'],'expected_bytes':expected_bytes}
    progress(status='checking_stability',observed_bytes=before['st_size'])
    time.sleep(stable_seconds)
    if fingerprint(path) != before:
        return {'status':'waiting_for_copy','reason':'source_still_changing'}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if not set(required_members) <= names:
            raise ValueError('Copied archive lacks required registered source members')
        infos = archive.infolist(); checked = 0
        for i,info in enumerate(infos):
            if not info.is_dir():
                # Reaching EOF verifies each member's ZIP CRC; no files are extracted.
                with archive.open(info) as stream:
                    while chunk := stream.read(8*1024*1024):
                        checked += len(chunk)
            progress(status='verifying_zip_crc',members_checked=i+1,members_total=len(infos),uncompressed_bytes_checked=checked)
    if fingerprint(path) != before:
        raise ValueError('Source changed during ZIP verification; no source switch')
    return {'status':'validated','fingerprint':before,'zip_crc_verified':True,'required_members_present':True,
            'members_checked':len(infos),'validated_at':now()}


def activate(cfg, validation, runner=subprocess.run):
    root = Path(cfg['root']); settings_path = root/'continuous5/settings.json'
    settings = json.loads(settings_path.read_text())
    if settings['archive'] != cfg['archive']:
        names = runner(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True,check=True,timeout=30).stdout.splitlines()
        if any(n.startswith(('statmind-','adni-xcpd-')) for n in names):
            return 'validated_waiting_for_idle'
        listing = runner(['launchctl','list'],capture_output=True,text=True,check=True,timeout=30).stdout.splitlines()
        if any(v.split()[-1]=='com.codex.adni-sb-queue-five' and v.split()[0]!='-' for v in listing if v.split()):
            return 'validated_waiting_for_idle'
        backup = root/'continuous5/source-copy-gate/settings.before-source-switch.json'
        if not backup.exists():
            save(backup,settings)
        settings.update(archive=cfg['archive'],archive_bytes=cfg['expected_bytes'],
                        archive_mtime_ns=validation['fingerprint']['st_mtime_ns'])
        settings['source_copy_validation']={'path':str(root/'continuous5/source-copy-gate/status.json'),
                                            'method':'exact source size, stable file and full ZIP member CRC validation'}
        save(settings_path,settings)
    for label in cfg['services']:
        if not label.startswith('com.codex.adni-sb-'):
            raise ValueError('Unexpected service outside the managed ADNI workflow')
        runner(['launchctl','kickstart',f'gui/{os.getuid()}/{label}'],check=True,capture_output=True,text=True,timeout=30)
    return 'ready'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True);args=parser.parse_args()
    cfg=json.loads(args.config.read_text());root=Path(cfg['root']);here=root/'continuous5/source-copy-gate';here.mkdir(exist_ok=True)
    report=here/'status.json';previous=json.loads(report.read_text()) if report.exists() else {}
    with (here/'gate.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def progress(**fields):
            save(report,{'checked_at':now(),'archive':cfg['archive'],'LLM_calls':0,**fields})
        try:
            mount=Path(cfg['mount']);source=Path(cfg['archive'])
            if not mount.is_mount() or not source.resolve().is_relative_to(mount.resolve()):
                progress(status='waiting_for_copy',reason='designated_volume_not_mounted');return
            volume=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(mount)],timeout=30))
            if volume.get('VolumeUUID')!=cfg['volume_uuid']:
                raise ValueError('External source volume identity differs')
            validation=previous.get('validation',{})
            if not source.is_file() or validation.get('fingerprint')!=fingerprint(source) or not validation.get('zip_crc_verified'):
                plan=json.loads((root/'continuous5/queue_plan.json').read_text())
                validation=inspect_copy(source,cfg['expected_bytes'],[r['outer_member'] for r in plan],progress=progress)
            if validation['status']!='validated':
                progress(**validation);return
            # Publish the validated source before starting the feeder.
            progress(status='ready',validation=validation)
            result=activate(cfg,validation)
            progress(status=result,validation=validation)
        except Exception as exc:
            progress(status='waiting_retry',error=repr(exc))
            raise


if __name__=='__main__':main()
