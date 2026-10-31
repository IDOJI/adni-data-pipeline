"""Fixed-concurrency S6/S7 queue. No model/API calls or new pairing inference."""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import datetime as dt
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import zipfile

import nibabel as nib
import numpy as np
import yaml
import compute_slots

LAB=Path(__file__).resolve().parents[1]
STEP=LAB/'02_custom/s7b_sessionwise_preprocessing'
HERE=ROOT=DEPLOYMENT=None
PY=Path(sys.executable)
ORIGINAL=set()
MUTEX = threading.RLock()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def save(p, value):
    with MUTEX:
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + '.writing')
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        tmp.replace(p)

def event(kind, **values):
    with MUTEX, (HERE / 'events.jsonl').open('a') as f:
        f.write(json.dumps({'at': now(), 'event': kind, **values}, ensure_ascii=False) + '\n')

def load_module(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def latest(subject, stage):
    paths = sorted((ROOT / 'runs' / subject / 'logs').glob(f'*_{stage}_sub-{subject}_ses-*/run.json'))
    return json.loads(paths[-1].read_text()) if paths else None

def successful(record):
    return bool(record and record.get('status') == 'execution_completed_QC_required'
                and record.get('exit_code') == 0 and record.get('input_unchanged'))

def admission(free_bytes, active, slots=5, floor_gib=20, per_slot_gib=12):
    # Reserve remaining temporary/output growth for every active subject as well.
    required = (floor_gib + per_slot_gib * (active + 1)) * 1024**3
    return active < slots and free_bytes >= required

def verify_meta(row, t1, epi, anat, func):
    if anat.ndim != 3 or func.ndim != 4:
        raise ValueError('Expected 3D T1 and 4D EPI')
    if not np.isfinite(anat.affine).all() or not np.isfinite(func.affine).all():
        raise ValueError('Invalid image geometry')
    for m, key in [(t1, 't1_series_uid'), (epi, 'epi_series_uid')]:
        if m.get('SeriesInstanceUID') and m['SeriesInstanceUID'] != row[key]:
            raise ValueError('Image/RDS SeriesInstanceUID mismatch')
    if not np.isclose(float(epi.get('RepetitionTime', 0)), 3.0):
        raise ValueError('Not the selected SB protocol')
    if float(epi.get('MultibandAccelerationFactor', 1)) != 1:
        raise ValueError('Multiband data outside this SB queue')
    if not np.isclose(func.header.get_zooms()[3], 3.0) or func.shape[3] < 190:
        raise ValueError('Image timing/length differs from selected SB protocol')
    if epi.get('PhaseEncodingDirection') not in {'i','i-','j','j-','k','k-'}:
        raise ValueError('PhaseEncodingDirection unavailable')
    direction = epi.get('SliceEncodingDirection', 'k')
    if direction not in {'i','i-','j','j-','k','k-'}:
        raise ValueError('Invalid slice direction')
    axis = {'i':0,'j':1,'k':2}[direction[0]]
    timings = np.asarray(epi.get('SliceTiming', []), dtype=float)
    if func.shape[axis] != 48 or timings.shape != (48,) or not np.isfinite(timings).all():
        raise ValueError('Slice count/timing inconsistency')
    if np.unique(np.round(timings, 5)).size != 48 or timings.min() < 0 or timings.max() >= 3:
        raise ValueError('Not valid single-band slice timing')
    raw = np.array([float(v) for v in row['nfq_raw_timing'].split('_')])
    raw -= raw.min()
    # Compare in the declared NIfTI slice order; do not flip or replace timing.
    if raw.shape != timings.shape or not np.allclose(raw, timings, atol=.0011, rtol=0):
        raise ValueError('RDS NFQ and image JSON SliceTiming disagree')
    return {'slice_axis': direction, 'nfq_json_max_error_seconds': float(np.max(np.abs(raw-timings))),
            'direct_DICOM_pixel_mapping_checked': False,
            'note': 'Image header/sidecar and preserved RDS NFQ concordance; not a new direct DICOM audit.'}

class Queue:
    def __init__(self):
        if ROOT.resolve()==LAB.parent.resolve() or LAB.parent.resolve() in ROOT.resolve().parents or ROOT.resolve() in LAB.parent.resolve().parents:
            raise ValueError('Runtime must be outside the repository')
        self.settings = json.loads((HERE / 'settings.json').read_text())
        self.plan = json.loads((HERE / 'queue_plan.json').read_text())
        self.state = json.loads((HERE / 'state.json').read_text()) if (HERE / 'state.json').exists() else {}
        self.deployment=json.loads(Path(DEPLOYMENT).read_text())
        for path,digest in {**self.deployment['legacy_sources_sha256'],**self.deployment['integrated_sources_sha256']}.items():
            if sha(path)!=digest:raise ValueError('Deployment source changed: '+path)
        self.runner = load_module('adni_local_runner', STEP/'run.py')
        self.legacy_runner = load_module('legacy_adni_local_runner', Path(self.deployment['legacy_preprocessing'])/'run.py')
        self.final = load_module('adni_date_publisher', STEP/'publish_pairs.py')
        self.extraction_lock = threading.Lock()

    def backend(self, subject):
        if subject in self.deployment['legacy_subjects']:
            return self.legacy_runner, Path(self.deployment['legacy_preprocessing'])/'run.py'
        return self.runner, STEP/'run.py'

    def check_sources(self):
        for p, digest in self.settings['source_hashes'].items():
            if sha(p) != digest:
                raise ValueError(f'Frozen selection source changed: {p}')
        p = Path(self.settings['archive'])
        if p.stat().st_size != self.settings['archive_bytes'] or p.stat().st_mtime_ns != self.settings['archive_mtime_ns']:
            raise ValueError('Source archive identity changed')

    def update(self, subject, status, **extra):
        with MUTEX:
            self.state[subject] = {**self.state.get(subject, {}), 'status': status, 'updated_at': now(), **extra}
            save(HERE / 'state.json', self.state)
        event(status, subject=subject, **extra)

    def prepare(self, row):
        self.check_sources()
        sub, ses = row['subject'], row['session']
        runner, script = self.backend(sub)
        case_dir = HERE / 'cases' / sub
        ready = case_dir / 'prepared.json'
        if ready.exists():
            return Path(json.loads(ready.read_text())['config'])
        if (ROOT / 'runs' / sub).exists():
            raise ValueError('Unrecognized existing runtime; refusing overwrite')
        case_dir.mkdir(parents=True, exist_ok=True)
        stem = f'sub-{sub}_ses-{ses}'
        source = case_dir / 'bids'
        paths = {}
        mapping = []
        # One archive reader at a time; never unpack a whole subject or cohort.
        with self.extraction_lock:
            with zipfile.ZipFile(self.settings['archive']) as outer:
                with outer.open(row['outer_member']) as stream, zipfile.ZipFile(stream) as inner:
                    for mod, date, image_id, folder, suffix in [
                        ('EPI',row['epi_date'],row['epi_image_id'],'func','task-rest_bold'),
                        ('T1',row['t1_date'],row['t1_image_id'],'anat','T1w')]:
                        prefix = f"{row['ptid']}/{mod}/{row['ptid']}_{mod}_{date}_I{image_id}"
                        for ext in ['.nii.gz','.json']:
                            member = prefix + ext
                            info = inner.getinfo(member)
                            if info.file_size > 2 * 1024**3:
                                raise ValueError('Unexpected selected file size')
                            target = source / f'sub-{sub}' / f'ses-{ses}' / folder / (stem + '_' + suffix + ext)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with inner.open(member) as src, target.open('xb') as dst:
                                shutil.copyfileobj(src, dst, length=8*1024*1024)
                            paths[(mod,ext)] = target
                        mapping.append({'ptid':row['ptid'],'session':ses,'modality':mod,'image_id':image_id,
                                        'scan_date':date,'source_member':row['outer_member']+'::'+prefix+'.nii.gz',
                                        'bids_file':str(paths[(mod,'.nii.gz')].relative_to(source)),
                                        'sha256':sha(paths[(mod,'.nii.gz')])})
        tmeta = json.loads(paths[('T1','.json')].read_text())
        emeta = json.loads(paths[('EPI','.json')].read_text())
        quality = verify_meta(row,tmeta,emeta,nib.load(paths[('T1','.nii.gz')]),nib.load(paths[('EPI','.nii.gz')]))
        for mod in ['T1','EPI']:
            with gzip.open(paths[(mod,'.nii.gz')],'rb') as stream:
                while stream.read(8*1024*1024):
                    pass
        emeta['TaskName'] = 'rest'
        save(paths[('EPI','.json')],emeta)
        save(source/'dataset_description.json',{'Name':'ADNI selected SB explicit-pair queue','BIDSVersion':'1.10.0','DatasetType':'raw'})
        save(case_dir/'source_mapping.json',mapping)
        evidence = [{'subject':sub,'session':ses,'phase':row['phase'],
                     'evidence_file':self.settings['selected_images'],'evidence_file_sha256':self.settings['source_hashes'][self.settings['selected_images']],
                     'matched_row':row['selected_epi_row'],
                     'phase_match_basis':'Exact PTID, Image ID, actual scan date and SeriesInstanceUID; image IDs/NFQ verified directly in canonical RDS',
                     'canonical_rds':self.settings['canonical_rds'],
                     'canonical_rds_sha256':self.settings['source_hashes'][self.settings['canonical_rds']],
                     'bids_metadata_sha256':sha(paths[('EPI','.json')])}]
        save(case_dir/'phase_evidence.json',evidence)
        cfg = yaml.safe_load(Path(self.deployment['template_config']).read_text())
        cfg.update(runtime=str(ROOT/'runs'/sub),source_bids=str(source),source_manifest=str(case_dir/'manifest.json'),
                   source_phase_evidence=str(case_dir/'phase_evidence.json'))
        cfg['resources']={'cpus':4,'omp_nthreads':2,'workflow_memory_mb':6000,'docker_memory':'8g'}
        cfg['runs']=[{'subject':sub,'session':ses,'ptid':row['ptid'],'bold_image_id':row['epi_image_id'],'phase':row['phase']}]
        config = case_dir/'config.yaml'
        config.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
        manifest_module = load_module('adni_source_manifest',script.with_name('make_source_manifest.py'))
        manifest, details = manifest_module.inspect(cfg)
        save(case_dir/'manifest.json',manifest)
        runner.prepare(cfg)
        runner.intake(cfg)
        decisions = list(csv.DictReader((Path(cfg['runtime'])/'results/step5/intake_decisions.tsv').open(),delimiter='\t'))
        if len(decisions)!=1 or decisions[0]['strict_upstream_eligible'].lower()!='true':
            raise ValueError('Original S5 intake did not pass')
        save(ready,{'config':str(config),'prepared_at':now(),'input_checks':quality,'preflight':details})
        return config

    def retry_request(self, sub, stage, consume=False):
        with MUTEX:
            path=HERE/'retry_plan.json'
            if not path.exists():return False
            plan=json.loads(path.read_text());entry=plan.get('subjects',{}).get(sub,{}).get('stages',{}).get(stage)
            if not entry or entry.get('remaining',0)<=0:return False
            if consume:
                entry['remaining']-=1;entry['launched_at']=now()
                entry['previous_execution']=latest(sub,stage)
                save(path,plan)
            return True

    def enqueue_failed_stage(self, sub, stage):
        if not self.settings.get('retry_new_failures_once',False):return False
        record=latest(sub,stage)
        if not record or record.get('status')!='failed' or record.get('input_unchanged') is not True:return False
        with MUTEX:
            path=HERE/'retry_plan.json'
            plan=json.loads(path.read_text()) if path.exists() else {'subjects':{}}
            stages=plan.setdefault('subjects',{}).setdefault(sub,{}).setdefault('stages',{})
            if stage in stages:return False
            stages[stage]={'remaining':1,'requested_at':now(),'basis':'Master authorized sequential retries under fixed total-five policy','previous_execution':record}
            save(path,plan)
        self.update(sub,'retry_queued',retry_kind='failed',retry_in_progress=False,error='Execution failed; one sequential retry queued')
        return True

    def pending_rows(self, futures):
        retry_busy=any(self.state.get(s,{}).get('retry_in_progress') for s in futures)
        retries=[r for r in self.plan if self.state.get(r['subject'],{}).get('status')=='retry_queued']
        resumed=[r for r in self.plan if self.state.get(r['subject'],{}).get('status')=='resume_queued']
        fresh=[r for r in self.plan if r['subject'] not in self.state]
        return ([] if retry_busy else retries)+resumed+fresh

    def publish_originals(self):
        for case in self.final.make_plan(ROOT):
            if not all(successful(latest(case['subject'],stage)) for stage in ('mriqc','fmriprep')):continue
            if (Path(case['target'])/'pair_metadata.json').exists():continue
            result=self.final.publish(ROOT,[case])
            save(HERE/('original-delivery-'+case['subject']+'.json'),result)
            event('original_pair_published',subject=case['subject'],target=case['target'])

    def work(self, row):
        with compute_slots.lease(row['subject'],'S6_S7'):
            self._work(row)

    def _work(self, row):
        sub = row['subject']
        runner, script = self.backend(sub)
        try:
            self.update(sub,'preparing',runner_source=str(script),code_deployment_sha256=sha(DEPLOYMENT))
            config = self.prepare(row)
            cfg = yaml.safe_load(config.read_text())
            for stage in ['mriqc','fmriprep']:
                if successful(latest(sub,stage)):
                    continue
                existing = latest(sub,stage)
                if existing:
                    if existing.get('status')=='running':
                        self.update(sub,'observing_existing_'+stage)
                        observer=load_module('adni_orphan_observer',STEP/'observe.py')
                        path=sorted((ROOT/'runs'/sub/'logs').glob(f'*_{stage}_sub-{sub}_ses-*/run.json'))[-1]
                        observer.adopt(path)
                        if successful(latest(sub,stage)):
                            continue
                    if existing.get('status')!='failed' or not self.retry_request(sub,stage):
                        raise ValueError('Existing failed execution retained; no authorized retry')
                    if existing.get('input_unchanged') is not True:
                        raise ValueError('Retry blocked: original input integrity was not established')
                    self.retry_request(sub,stage,consume=True)
                    event('authorized_stage_retry',subject=sub,stage=stage)

                image = runner.image_record(cfg['images'][stage])
                if image['resolved'] != self.settings['pinned_images'][stage]:
                    raise ValueError('Container image differs from frozen pipeline')
                self.update(sub,'running_'+stage,retry_in_progress=(stage=='mriqc' and self.state.get(sub,{}).get('retry_kind')=='failed'))
                with (HERE/'cases'/sub/(stage+'-controller.log')).open('a') as log:
                    result = subprocess.run([str(PY),str(script),'--config',str(config),'run','--stage',stage,'--subject',sub],
                                            cwd=script.parent,stdout=log,stderr=subprocess.STDOUT)
                if result.returncode or not successful(latest(sub,stage)):
                    raise RuntimeError(f'{stage} execution failed; see controller and run logs')
            self.update(sub,'publishing')
            pair_id=f"EPI_{row['epi_date'].replace('-','')}_MT1_{row['t1_date'].replace('-','')}"
            case={'ptid':row['ptid'],'subject':sub,'pair_id':pair_id,'epi_date':row['epi_date'],'mt1_date':row['t1_date'],
                  'epi_image_id':row['epi_image_id'],'mt1_image_id':row['t1_image_id'],'execution_session_label':row['session'],
                  'pairing_basis':'Existing explicit selected pair, verified in canonical RDS; VISCODE used only as execution label',
                  'target':str(ROOT/'results'/row['ptid']/pair_id)}
            published = self.final.publish(ROOT,[case])
            save(HERE/'cases'/sub/'delivery.json',published)
            self.update(sub,'completed_QC_pending',result_path=case['target'])
        except Exception as exc:
            if 'stage' in locals() and self.enqueue_failed_stage(sub,stage):return
            self.update(sub,'deferred_or_failed',retry_in_progress=False,error=f'{type(exc).__name__}: {exc}')

    def external_active(self):
        p = subprocess.run(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True,timeout=25,check=True)
        subjects=ORIGINAL | {row['subject'] for row in self.plan}
        return [s for s in sorted(subjects) if any(name.startswith('statmind-') and f'-{s}-' in name for name in p.stdout.splitlines())]

    def run(self):
        with (HERE/'queue.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.check_sources()
            # Keep this requested compute batch active during idle time; display behavior is unchanged.
            subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
            futures = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
                resumable=[row for row in self.plan if self.state.get(row['subject'],{}).get('status') not in
                           [None,'completed_QC_pending','deferred_or_failed','retry_queued','resume_queued']]
                if len(resumable)>32:
                    raise ValueError('Unexpected number of resumable subjects')
                for row in resumable:
                    futures[row['subject']]=pool.submit(self.work,row)
                while True:
                    updated=json.loads((HERE/'settings.json').read_text())
                    target=int(updated['target_concurrency'])
                    if not 1<=target<=32 or int(updated['admission']['slots'])!=target:
                        raise ValueError('Invalid configured concurrency')
                    self.settings['target_concurrency']=target
                    self.settings['admission']=updated['admission']
                    for sub, future in list(futures.items()):
                        if future.done():
                            future.result()
                            del futures[sub]
                    # A restarted controller may encounter a still-running container.
                    # It never recreates that execution; original run records remain the authority.
                    self.publish_originals()
                    all_running=compute_slots.running_subjects()
                    external=[s for s in all_running if s not in futures]
                    active=len(set(external)|set(futures))
                    pending=self.pending_rows(futures)
                    free = shutil.disk_usage(ROOT).free
                    mode = 'running'
                    if pending and admission(free,active,**self.settings['admission']):
                        row=pending[0]
                        self.update(row['subject'],'reserved',retry_in_progress=(self.state.get(row['subject'],{}).get('status')=='retry_queued'))
                        futures[row['subject']]=pool.submit(self.work,row)
                        continue
                    if pending and active<target:
                        mode='waiting_for_disk_capacity'
                    if not pending and not futures and not external:
                        mode='queue_exhausted'
                    prep_running=compute_slots.running_subjects(include_xcpd=False)
                    snapshot={'controller_source':__file__,'new_subject_runner':str(STEP/'run.py'),'code_deployment_sha256':sha(DEPLOYMENT),'updated_at':now(),'mode':mode,'target_concurrency':target,
                              'active_subjects':sorted(prep_running),'active_count':len(prep_running),
                              'global_compute_limit':5,'global_active_subjects':sorted(all_running),'global_active_count':len(all_running),
                              'original_subjects_active':sorted(prep_running & ORIGINAL),'pending':len(pending),
                              'retry_queued':sum(v['status']=='retry_queued' for v in self.state.values()),
                              'resume_queued':sum(v['status']=='resume_queued' for v in self.state.values()),
                              'completed_new':sum(v['status']=='completed_QC_pending' for v in self.state.values()),
                              'deferred_or_failed':sum(v['status']=='deferred_or_failed' for v in self.state.values()),
                              'disk_free_GiB':round(free/1024**3,2),'disk_policy':self.settings['admission'],
                              'scope':'S6 + S7; scientific inclusion and S8 QC remain pending','LLM_calls':0}
                    save(HERE/'status.json',snapshot)
                    if mode=='queue_exhausted':
                        break
                    time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--prepare-first',type=int,default=0)
    p.add_argument('--check',action='store_true')
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--deployment',type=Path,required=True)
    args=p.parse_args()
    ROOT=args.root.resolve();HERE=ROOT/'continuous5';DEPLOYMENT=args.deployment.resolve()
    dep=json.loads(DEPLOYMENT.read_text());ORIGINAL=set(dep['original_subjects'])
    compute_slots.configure(ROOT)
    q=Queue()
    if args.check:
        q.check_sources();print(json.dumps({'controller_source':__file__,'integrated_runner':str(STEP/'run.py'),'legacy_subjects_preserved':len(q.deployment['legacy_subjects']),'planned_subjects':len(q.plan)}))
    elif args.prepare_first:
        for row in q.plan[:args.prepare_first]:
            try:
                print(row['subject'],q.prepare(row),flush=True)
            except Exception as exc:
                print(row['subject'],type(exc).__name__,str(exc),flush=True)
                raise
    else:
        q.run()
