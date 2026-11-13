"""Move verified completed ADNI pairs to the designated external volume.

Copy -> SHA-256/link verification -> atomic external publication -> local
directory quarantine/alias -> verified local-copy removal. Active subjects
and original source archives are never moved or deleted.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import time
import unicodedata
import uuid



def now():return dt.datetime.now(dt.timezone.utc).isoformat()

def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.writing');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def nfc(value):return unicodedata.normalize('NFC',str(value))

def inventory(root):
    """Preserve empty directories and link text; never follow symbolic links."""
    root=Path(root);out={}
    for folder,dirs,files in os.walk(root,followlinks=False):
        for name in sorted(dirs+files):
            p=Path(folder)/name;rel=nfc(p.relative_to(root));s=p.lstat()
            if rel in out:raise ValueError('Canonically colliding filenames')
            if stat.S_ISLNK(s.st_mode):out[rel]={'kind':'link','target':nfc(os.readlink(p))}
            elif stat.S_ISDIR(s.st_mode):out[rel]={'kind':'directory'}
            elif stat.S_ISREG(s.st_mode):out[rel]={'kind':'file','bytes':s.st_size,'sha256':sha(p)}
            else:raise ValueError(f'Unsupported special file: {p}')
    return out

def put_tree(payload,prefix,items):
    prefix=nfc(prefix)
    payload[prefix]={'kind':'directory'}
    payload.update({prefix+'/'+k:v for k,v in items.items()})

def subtree(items,prefix):
    prefix=nfc(prefix)+'/'
    return {k[len(prefix):]:v for k,v in items.items() if k.startswith(prefix)}

def copy_tree(source,destination):
    destination.mkdir(exist_ok=True)
    for child in source.iterdir():copy_entry(child,destination/child.name)
    shutil.copystat(source,destination,follow_symlinks=False)

def copy_entry(source,destination):
    if source.is_symlink():
        value=os.readlink(source)
        if destination.is_symlink():
            if nfc(os.readlink(destination))!=nfc(value):raise ValueError('Staging link differs')
        elif destination.exists():raise ValueError('Unexpected staging entry')
        else:destination.symlink_to(value)
    elif source.is_dir():copy_tree(source,destination)
    else:
        if destination.exists() and not destination.is_symlink() and destination.stat().st_size==source.stat().st_size and sha(destination)==sha(source):return
        shutil.copy2(source,destination)

def successful(record):
    return record.get('status')=='execution_completed_QC_required' and record.get('exit_code')==0 and record.get('input_unchanged') is True

def active_subjects():
    names=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True,timeout=25).splitlines()
    return {p for name in names if name.startswith(('statmind-','adni-xcpd-')) for p in name.split('-') if p.startswith('ADNI')}

def latest_stage(root,subject,stage):
    paths=sorted((Path(root)/'runs'/subject/'logs').glob(f'*_{stage}_sub-{subject}_ses-*/run.json'))
    if not paths:raise ValueError('Missing stage execution record')
    return json.loads(paths[-1].read_text())

def verify_completed_pair(root,source,active=()):
    root,source=Path(root),Path(source)
    meta=json.loads((source/'pair_metadata.json').read_text());sub=meta['subject']
    if not re.fullmatch(r'\d{3}_S_\d{4,}',meta['ptid']) or not re.fullmatch(r'EPI_\d{8}_MT1_\d{8}',meta['pair_id']):
        raise ValueError('Invalid pair identity')
    if sub!='ADNI'+meta['ptid'].replace('_','') or source!=root/'results'/meta['ptid']/meta['pair_id']:
        raise ValueError('Source path is not the exact registered pair')
    if sub in active:raise ValueError('Subject still has an active container')
    if meta.get('delivery_status')!='processing_complete_QC_pending':raise ValueError('Pair is not published complete')
    if source.name!=meta['pair_id'] or source.parent.name!=meta['ptid']:raise ValueError('Pair path/identity mismatch')
    for stage in ['mriqc','fmriprep']:
        record=latest_stage(root,sub,stage)
        if not successful(record):raise ValueError('Both stages must be complete with unchanged inputs')
        expected=meta['execution_identity'][stage]
        for key in ['started_at','runner_sha256','image']:
            if record.get(key)!=expected.get(key):raise ValueError('Published execution identity mismatch')
    return meta

class Offloader:
    def __init__(self,root,settings,volume_check=None):
        self.root=Path(root);self.here=self.root/'continuous5';self.settings=settings
        self.mount=Path(settings['mount']);self.dest=Path(settings['destination'])
        self.receipts=self.here/'offload_receipts';self.receipts.mkdir(exist_ok=True)
        self.check_volume=volume_check or self.real_volume_check

    def real_volume_check(self):
        if not self.mount.is_mount() or self.mount.stat().st_dev==self.root.stat().st_dev:
            raise RuntimeError('Designated external volume is not mounted')
        raw=subprocess.check_output(['diskutil','info','-plist',str(self.mount)],timeout=25)
        info=plistlib.loads(raw)
        if info.get('VolumeUUID')!=self.settings['volume_uuid'] or not info.get('Writable'):
            raise RuntimeError('External volume identity or writable state differs')
        if not self.dest.is_relative_to(self.mount):raise ValueError('Destination escapes designated volume')

    def latest(self,subject,stage):
        paths=sorted((self.root/'runs'/subject/'logs').glob(f'*_{stage}_sub-{subject}_ses-*/run.json'))
        if not paths:raise ValueError('Missing stage execution record')
        return json.loads(paths[-1].read_text())

    def postprocessing_ready(self,source):
        if not self.settings.get('require_postprocessing',False):return True
        config_id=self.settings['postprocessing_config_id']
        p=source/'s10'/config_id/'archive_ready.json'
        if not p.is_file():return False
        ready=json.loads(p.read_text());meta=json.loads((source/'pair_metadata.json').read_text())
        if ready.get('config_id')!=config_id or ready.get('subject')!=meta['subject'] or ready.get('status')!='postprocessing_complete_final_QC_pending':
            raise ValueError('Invalid S8/XCP-D archival receipt')
        if not ready.get('runs') or not ready.get('evidence'):raise ValueError('Missing postprocessing evidence')
        for run in ready['runs']:
            if run.get('pre_xcpd_qc_status')=='fail':continue
            if run.get('xcpd_status')=='skipped_insufficient_time':continue
            if run.get('xcpd_status')!='success' or run.get('functional_outputs_valid') is not True:
                raise ValueError('XCP-D did not finish validation')
        for relative,expected in ready['evidence'].items():
            rel=Path(relative)
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid postprocessing evidence path')
            path=source/rel
            if not path.is_file() or sha(path)!=expected:raise ValueError('Postprocessing evidence changed')
            if path.name=='execution.json':
                rec=json.loads(path.read_text())
                valid_exit=(rec.get('status')=='success' and rec.get('exit_code')==0) or (rec.get('status')=='skipped_insufficient_time' and rec.get('exit_code')==42)
                if not valid_exit or rec.get('input_unchanged') is not True:
                    raise ValueError('Unsuccessful XCP-D execution record')
        return True

    def verify_eligible(self,source,active,require_postprocessing=True):
        meta=verify_completed_pair(self.root,source,active)
        if require_postprocessing and not self.postprocessing_ready(source):
            raise ValueError('Waiting for S8/XCP-D output validation')
        return meta

    def batch_identity(self):
        self.check_volume();self.dest.mkdir(parents=True,exist_ok=True)
        p=self.dest/'batch_identity.json'
        identity={'source_root':str(self.root),'thread_id':self.settings['thread_id'],'volume_uuid':self.settings['volume_uuid']}
        if p.exists():
            if json.loads(p.read_text())!=identity:raise ValueError('Archive batch belongs to a different source')
        else:save(p,identity)

    def build_payload(self,source,meta):
        sub=meta['subject'];runtime=self.root/'runs'/sub
        if runtime.is_symlink():raise ValueError('Runtime already relocated without a completed local receipt')
        originals={str(source):inventory(source),str(runtime):inventory(runtime)}
        payload={};copies=[]
        published_tree=originals[str(source)];runtime_tree=originals[str(runtime)]
        # Published outputs replace duplicate runtime derivatives, preserving their paths with links.
        for stage in ['mriqc','fmriprep']:
            image_tree=subtree(published_tree,stage)
            if subtree(runtime_tree,'derivatives/'+stage)!=image_tree:
                raise ValueError('Runtime and published derivatives are not identical')
            put_tree(payload,stage,image_tree);copies.append((source/stage,stage))
        payload['pair_metadata.json']=originals[str(source)]['pair_metadata.json']
        copies.append((source/'pair_metadata.json','pair_metadata.json'))
        for child in sorted(source.iterdir()):
            if child.name in ['mriqc','fmriprep','pair_metadata.json']:continue
            entry=published_tree[nfc(child.name)]
            if entry['kind']=='directory':put_tree(payload,child.name,subtree(published_tree,child.name))
            else:payload[nfc(child.name)]=entry
            copies.append((child,child.name))
        payload['_runtime']={'kind':'directory'}
        for child in sorted(runtime.iterdir()):
            if child.name=='derivatives':continue
            rel='_runtime/'+nfc(child.name)
            if child.is_symlink():payload[rel]={'kind':'link','target':nfc(os.readlink(child))}
            elif child.is_dir():put_tree(payload,rel,subtree(runtime_tree,child.name))
            elif child.is_file():payload[rel]=runtime_tree[nfc(child.name)]
            else:raise ValueError('Unexpected runtime file')
            copies.append((child,rel))
        payload['_runtime/derivatives']={'kind':'directory'}
        for stage in ['mriqc','fmriprep']:
            payload['_runtime/derivatives/'+stage]={'kind':'link','target':'../../'+stage}
        for child in sorted((runtime/'derivatives').iterdir()):
            if child.name in ['mriqc','fmriprep']:continue
            rel='_runtime/derivatives/'+nfc(child.name)
            entry=runtime_tree['derivatives/'+nfc(child.name)]
            if entry['kind']=='directory':put_tree(payload,rel,subtree(runtime_tree,'derivatives/'+child.name))
            else:payload[rel]=entry
            copies.append((child,rel))
        aliases=[(runtime,'_runtime'),(source,'')]
        for path,rel in [(self.here/'cases'/sub,'_source'),(self.root/'bids'/('sub-'+sub),'_original_bids')]:
            if path.exists():
                if path.is_symlink():raise ValueError('Unexpected previously relocated source')
                tree=inventory(path);originals[str(path)]=tree;put_tree(payload,rel,tree)
                copies.append((path,rel));aliases.append((path,rel))
        return payload,copies,aliases,originals

    def cleanup(self,receipt_path,receipt):
        self.check_volume();target=Path(receipt['external_path'])
        if not self.postprocessing_ready(target):raise ValueError('S8/XCP-D not complete; local copy preserved')
        if not (target/'archive_manifest.json').is_file():raise ValueError('Verified external manifest missing')
        manifest=json.loads((target/'archive_manifest.json').read_text())
        if target!=self.dest/receipt['ptid']/receipt['pair_id']:raise ValueError('Unexpected archive target')
        allowed={str(self.root/'runs'/receipt['subject']):'_runtime',
                 str(self.root/'results'/receipt['ptid']/receipt['pair_id']):'',
                 str(self.here/'cases'/receipt['subject']):'_source',
                 str(self.root/'bids'/('sub-'+receipt['subject'])):'_original_bids'}
        actual=inventory(target);actual.pop('archive_manifest.json',None)
        if actual!=manifest['payload']:raise ValueError('External archive changed before local cleanup')
        for item in receipt['aliases']:
            source=Path(item['source']);external=Path(item['external']);quarantine=Path(item['quarantine'])
            if str(source) not in allowed or external!=target/allowed[str(source)]:raise ValueError('Unexpected cleanup path')
            if quarantine.parent!=source.parent or not quarantine.name.startswith(source.name+'.offload-verified-'):
                raise ValueError('Unexpected quarantine path')
            self.check_volume()
            if source.is_symlink():
                if source.resolve()!=external.resolve():raise ValueError('Existing local alias points elsewhere')
            elif source.exists():
                if quarantine.exists():raise ValueError('Both local source and quarantine exist')
                if inventory(source)!=manifest['original_trees'][str(source)]:raise ValueError('Local source changed after copy')
                os.rename(source,quarantine)
                source.symlink_to(external,target_is_directory=True)
            elif quarantine.exists():
                source.symlink_to(external,target_is_directory=True)
            else:raise ValueError('Local source vanished unexpectedly')
            # Each file removed here is already represented in the verified external payload.
            if quarantine.exists():
                if inventory(quarantine)!=manifest['original_trees'][str(source)]:raise ValueError('Quarantine changed; preserved for review')
                self.check_volume()
                shutil.rmtree(quarantine)
            item['removed_local_copy']=True;save(receipt_path,receipt)
        receipt.update(status='archived_and_local_space_reclaimed',completed_at=now())
        save(receipt_path,receipt)
        save(target/'relocation_receipt.json',receipt)
        return receipt

    def archive(self,source,active=None):
        source=Path(source);active=set() if active is None else active
        meta=self.verify_eligible(source,active)
        receipt_path=self.receipts/(meta['subject']+'_'+meta['pair_id']+'.json')
        if receipt_path.exists():
            receipt=json.loads(receipt_path.read_text())
            if receipt['status']=='archived_and_local_space_reclaimed':return receipt
            return self.cleanup(receipt_path,receipt)
        self.batch_identity()
        target=self.dest/meta['ptid']/meta['pair_id']
        if target.exists():
            # Recover the tiny crash window between atomic publication and local receipt creation.
            p=target/'archive_manifest.json'
            if not p.is_file():raise ValueError('Untracked existing external destination; refusing overwrite')
            previous=json.loads(p.read_text())
            if previous.get('subject')!=meta['subject'] or previous.get('pair_id')!=meta['pair_id']:
                raise ValueError('Conflicting archive identity')
            layout={str(self.root/'runs'/meta['subject']):'_runtime',str(source):'',
                    str(self.here/'cases'/meta['subject']):'_source',
                    str(self.root/'bids'/('sub-'+meta['subject'])):'_original_bids'}
            if any(path not in layout for path in previous['original_trees']):raise ValueError('Unexpected archived source path')
            aliases=[(Path(path),layout[path]) for path in previous['original_trees']]
            receipt=self.make_receipt(meta,target,aliases,sum(v.get('bytes',0) for v in previous['payload'].values()))
            save(receipt_path,receipt)
            return self.cleanup(receipt_path,receipt)
        payload,copies,aliases,originals=self.build_payload(source,meta)
        payload_bytes=sum(v.get('bytes',0) for v in payload.values())
        reserve=self.settings.get('external_reserve_gib',10)*1024**3
        if shutil.disk_usage(self.dest).free < payload_bytes+reserve:
            raise RuntimeError('External volume has insufficient reserved space')
        parent=target.parent;parent.mkdir(parents=True,exist_ok=True)
        staging=parent/('.copying-'+meta['pair_id'])
        if staging.exists():
            # Resume only our unpublished scratch copy; every retained file is hash checked.
            self.check_volume()
            if staging.is_symlink():raise ValueError('Unexpected staging symlink')
        staging.mkdir(exist_ok=True)
        for src,rel in copies:
            dst=staging/rel;dst.parent.mkdir(parents=True,exist_ok=True)
            copy_entry(src,dst)
        (staging/'_runtime/derivatives').mkdir(exist_ok=True)
        for stage in ['mriqc','fmriprep']:
            path=staging/'_runtime/derivatives'/stage
            if path.is_symlink():
                if os.readlink(path)!='../../'+stage:raise ValueError('Unexpected derivative link')
            else:path.symlink_to('../../'+stage)
        self.check_volume()
        if inventory(staging)!=payload:raise ValueError('Copied bytes or links failed verification; local originals preserved')
        for path,expected in originals.items():
            if inventory(Path(path))!=expected:raise ValueError('Local source changed during copy; originals preserved')
        manifest={'verified_at':now(),'subject':meta['subject'],'pair_id':meta['pair_id'],
                  'verification':'SHA-256 of every regular file and directory/link inventory; Unicode names/link text compared in NFC because NTFS exposes NFD',
                  'payload':payload,'original_trees':originals}
        save(staging/'archive_manifest.json',manifest)
        # Recheck completion and active-container gate immediately before the commit.
        self.verify_eligible(source,active)
        if target.exists():raise ValueError('Destination appeared while copying; no overwrite')
        os.rename(staging,target)
        receipt=self.make_receipt(meta,target,aliases,payload_bytes)
        save(receipt_path,receipt)
        return self.cleanup(receipt_path,receipt)

    def make_receipt(self,meta,target,aliases,payload_bytes):
        return {'status':'verified_external_copy_local_cleanup_pending','verified_at':now(),
                 'subject':meta['subject'],'ptid':meta['ptid'],'pair_id':meta['pair_id'],
                 'external_path':str(target),'payload_bytes':payload_bytes,
                 'scientific_QC_status':'pending','aliases':[
                     {'source':str(src),'external':str(target/rel),
                      'quarantine':str(src.with_name(src.name+'.offload-verified-'+uuid.uuid4().hex))}
                     for src,rel in aliases]}

    def run_once(self):
        self.check_volume();active=active_subjects();results=[]
        # Resume any verified transaction before accepting another source.
        for p in sorted(self.receipts.glob('*.json')):
            receipt=json.loads(p.read_text())
            if receipt['status']!='archived_and_local_space_reclaimed':
                if receipt['subject'] in active:continue
                results.append(self.cleanup(p,receipt))
        for subject_dir in sorted((self.root/'results').iterdir()):
            if not subject_dir.is_dir():continue
            for source in sorted(subject_dir.iterdir()):
                if source.is_symlink() or not (source/'pair_metadata.json').is_file():continue
                meta=json.loads((source/'pair_metadata.json').read_text())
                if meta['subject'] in active:continue
                if not self.postprocessing_ready(source):continue
                save(self.here/'offload_status.json',{'status':'copying_and_verifying','updated_at':now(),'subject':meta['subject'],'destination':str(self.dest)})
                results.append(self.archive(source,active))
        return results

def main():
    p=argparse.ArgumentParser();p.add_argument('--once',action='store_true')
    p.add_argument('--root',type=Path,required=True);p.add_argument('--settings',type=Path,required=True);args=p.parse_args()
    settings=json.loads(args.settings.read_text())
    if settings.get('require_postprocessing') is not True:
        raise ValueError('S8/XCP-D validation gate is required')
    if not settings.get('remove_local_copy_only_after_sha256_verification'):
        raise ValueError('Verified copy policy is required')
    HERE=args.root.absolute()/'continuous5';HERE.mkdir(parents=True,exist_ok=True)
    archiver=Offloader(args.root.absolute(),settings)
    with (HERE/'offload.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            try:
                results=archiver.run_once()
                receipts=[json.loads(p.read_text()) for p in archiver.receipts.glob('*.json')]
                save(HERE/'offload_status.json',{'status':'watching_for_validated_S8_XCPD_pairs' if settings.get('require_postprocessing') else 'watching_for_completed_pairs','updated_at':now(),
                     'required_postprocessing_config':settings.get('postprocessing_config_id'),
                     'destination':str(archiver.dest),'archived_subjects':[r['subject'] for r in receipts if r['status']=='archived_and_local_space_reclaimed'],
                     'payload_bytes_archived':sum(r['payload_bytes'] for r in receipts if r['status']=='archived_and_local_space_reclaimed'),
                     'latest_completed':[r['subject'] for r in results],'LLM_calls':0})
            except Exception as exc:
                message={'at':now(),'error':f'{type(exc).__name__}: {exc}'}
                with (HERE/'offload_errors.jsonl').open('a') as f:f.write(json.dumps(message)+'\n')
                print(json.dumps(message),flush=True)
                save(HERE/'offload_status.json',{'status':'waiting_retry_local_data_preserved','updated_at':now(),'error':f'{type(exc).__name__}: {exc}'})
                if args.once:raise
            if args.once:break
            time.sleep(30)

if __name__=='__main__':main()
