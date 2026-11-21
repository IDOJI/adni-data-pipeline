"""Publish completed outputs under participant/EPI_YYYYMMDD_MT1_YYYYMMDD."""
import argparse,datetime,json,os,subprocess,uuid,fcntl
from pathlib import Path
from zoneinfo import ZoneInfo

def make_plan(root):
 rows=json.loads((root/'source_mapping.json').read_text());groups={}
 for row in rows:groups.setdefault(row['ptid'],[]).append(row)
 plan=[]
 for ptid,items in groups.items():
  epi=[x for x in items if x['modality']=='EPI'];t1=[x for x in items if x['modality']=='T1']
  if len(epi)!=1 or len(t1)!=1:raise ValueError('Explicit image pair required; multiple candidates are not selected automatically')
  e,t=epi[0],t1[0]
  ed=datetime.date.fromisoformat(e['scan_date']).strftime('%Y%m%d');td=datetime.date.fromisoformat(t['scan_date']).strftime('%Y%m%d')
  pair_id=f'EPI_{ed}_MT1_{td}';sub='ADNI'+ptid.replace('_','')
  plan.append({'ptid':ptid,'subject':sub,'pair_id':pair_id,'epi_date':e['scan_date'],'mt1_date':t['scan_date'],'epi_image_id':e['image_id'],'mt1_image_id':t['image_id'],'execution_session_label':e['session'],'pairing_basis':'explicit image IDs and actual scan dates; VISCODE is only an execution label','target':str(root/'results'/ptid/pair_id)})
 return plan

def latest(root,sub,stage):
 ps=sorted((root/'runs'/sub/'logs').glob(f'*_{stage}_sub-{sub}_ses-*/run.json'))
 return json.loads(ps[-1].read_text()) if ps else None

def inventory(p):
 return {str(f.relative_to(p)):f.stat().st_size for f in p.rglob('*') if f.is_file()}

def publish(root,plan):
 with (Path(root)/'scan-date-publish.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  return _publish(root,plan)

def _publish(root,plan):
 report=[]
 for case in plan:
  sub=case['subject'];records={s:latest(root,sub,s) for s in ['mriqc','fmriprep']}
  if not all(r and r.get('status')=='execution_completed_QC_required' and r.get('exit_code')==0 and r.get('input_unchanged') for r in records.values()):
   report.append({**case,'delivery_status':'not_published_execution_incomplete_or_failed'});continue
  identity={k:{'started_at':v.get('started_at'),'runner_sha256':v.get('runner_sha256'),'image':v.get('image',{})} for k,v in records.items()}
  target=Path(case['target'])
  if target.exists():
   meta=json.loads((target/'pair_metadata.json').read_text())
   if any(meta.get(k)!=case[k] for k in ['ptid','pair_id','epi_image_id','mt1_image_id']):raise ValueError('Conflicting pair already occupies target; refusing overwrite')
   if meta.get('execution_identity')!=identity:raise ValueError('Different execution already published; refusing overwrite')
   report.append({**case,'delivery_status':'previously_published'});continue
  parent=target.parent;parent.mkdir(parents=True,exist_ok=True);staging=parent/('.staging-'+uuid.uuid4().hex);staging.mkdir()
  counts={}
  for stage in ['mriqc','fmriprep']:
   src=root/'runs'/sub/'derivatives'/stage
   if not src.is_dir() or not any(src.iterdir()):raise ValueError('Missing completed output directory')
   dst=staging/stage
   subprocess.run(['/bin/cp','-cR',str(src),str(dst)],check=True)
   before,after=inventory(src),inventory(dst)
   if not before or before!=after:raise ValueError('Cloned output inventory does not match source')
   counts[stage]={'files':len(after),'bytes':sum(after.values())}
  metadata={**case,'delivery_status':'processing_complete_QC_pending','execution_identity':identity,'output_inventory':counts,'note':'Outer folder identifies the actual EPI/MT1 pair; internal BIDS derivative names and relative report links are preserved.'}
  (staging/'pair_metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
  os.rename(staging,target)
  report.append(metadata)
 return report


def publish_verified_pair(root):
    """Publish the manual 5.D runtime through the same publisher as the batch."""
    import re
    import sys
    import yaml

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 's5d_bids_identity'))
    import guarded_runner_seeded as gate
    import continuation

    root = Path(root).resolve()
    config = root / 'pair/verified-config.yaml'
    cfg = yaml.safe_load(config.read_text())
    gate.dispatch(config, 'check')
    plan = gate.binding.verify_plan(cfg['binding_receipt'], cfg['epi_key'])
    subject = plan['subject']
    if not re.fullmatch(r'\d{3}_S_\d{4,}', plan['ptid']) or subject != 'ADNI' + plan['ptid'].replace('_', ''):
        raise ValueError('The S10 subject label must match the verified ADNI participant')
    runtime = root / 'pair/processing'
    if Path(cfg['runtime']).resolve() != runtime:
        raise ValueError('Configuration belongs to a different runtime')
    paths = gate.backend().paths_for(cfg, cfg['runs'][0])
    for stage in continuation.STAGES:
        _, record = continuation.latest(runtime, subject, stage)
        if not continuation.completed(record):
            raise ValueError(f'Complete {stage} successfully with unchanged inputs before publishing')
        continuation.check_record(record, paths, plan, runtime / 'bids')
        continuation.output_evidence(runtime, subject, stage)

    link = root / 'runs' / subject
    link.parent.mkdir(exist_ok=True)
    try:
        link.symlink_to(runtime, target_is_directory=True)
    except FileExistsError:
        if link.resolve() != runtime:
            raise ValueError('A different runtime already occupies this subject path')
    date = datetime.date.fromisoformat(plan['date']).strftime('%Y%m%d')
    pair_id = f'EPI_{date}_MT1_{date}'
    target = root / 'results' / plan['ptid'] / pair_id
    case = dict(ptid=plan['ptid'], subject=subject, pair_id=pair_id, target=str(target),
                epi_date=plan['date'], mt1_date=plan['date'], epi_image_id=plan['epi_image_id'],
                mt1_image_id=plan['t1_image_id'], execution_session_label=plan['session'],
                pairing_basis='Verified source images, UIDs, dates and hashes')
    result, = publish(root, [case])
    if result['delivery_status'] not in ('processing_complete_QC_pending', 'previously_published'):
        raise ValueError(result['delivery_status'])
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Directory containing pair/verified-config.yaml')
    args = parser.parse_args()
    print(publish_verified_pair(args.root))
