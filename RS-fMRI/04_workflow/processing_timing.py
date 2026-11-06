"""Persist execution durations automatically from read-only Docker lifecycle events.

No imaging container is controlled by this observer. Timing files are separate
from frozen configs, work signatures, run records and archive inventories.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import uuid

WORKFLOW = Path(__file__).resolve().parent
if str(WORKFLOW) not in sys.path:
    sys.path.insert(0, str(WORKFLOW))
from duration_display import format_duration

VERSION = '1.1.1'
NAMES = re.compile(r'^(?:statmind-(mriqc|fmriprep)-(ADNI\d+S\d+)-.+|(?:adni|statmind)-xcpd-(ADNI\d+S\d+)-.+)$')
SELFTEST = 'adni.processing_timing.selftest'


def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def epoch(value):return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def iso(value):return dt.datetime.fromtimestamp(value,dt.timezone.utc).isoformat()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def human_summary(row,states=None):
    states=states or {}
    subject=row.get('ptid') or re.sub(r'^ADNI(\d{3})S(\d+)$',r'\1_S_\2',row['subject'])
    return {'대상자':subject,'MRIQC':format_duration(row.get('mriqc_seconds')),
        '전처리(fMRIPrep)':format_duration(row.get('fmriprep_seconds')),
        '후처리(XCP-D)':('QC 스킵' if states.get('xcpd')=='skipped_pre_qc_fail' else format_duration(row.get('xcpd_seconds'))),
        '성공한 실행':format_duration(row.get('successful_attempt_seconds')),
        '실패한 실행':format_duration(row.get('failed_attempt_seconds')),
        '전처리+후처리 실행':format_duration(row.get('preprocessing_postprocessing_seconds')),
        '처리 상태':'처리 종료' if row['processing_status']=='completed_or_qc_skipped' else '진행 중 또는 실패',
        '과거 로그 복원':f"{row['historically_reconstructed_attempts']}회",'표시 단위':'시간·분·초'}


def csv_text(row_list):
    text=io.StringIO(newline='');writer=csv.DictWriter(text,fieldnames=list(row_list[0]));writer.writeheader();writer.writerows(row_list)
    return text.getvalue()


def write_text(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and path.read_text()==text:return
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.writing')
    temp.write_text(text);temp.replace(path)


def save(path,value):write_text(path,json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def overlap_seconds(start,end,intervals):
    """Count the union of pauses/sleep, without double subtracting overlaps."""
    clipped=sorted((max(start,a),min(end,b)) for a,b in intervals if b>a and b>start and a<end)
    total=0.0;left=right=None
    for a,b in clipped:
        if left is None:left,right=a,b
        elif a<=right:right=max(right,b)
        else:total+=right-left;left,right=a,b
    return total+(right-left if left is not None else 0)


def classify(name,labels=None):
    labels=labels or {};name=name.lstrip('/')
    if labels.get(SELFTEST)=='true' and name.startswith('adni-timing-selftest-'):
        return {'subject':'SELFTEST','stage':'selftest'}
    match=NAMES.fullmatch(name)
    if not match:return None
    return {'stage':match[1] or 'xcpd','subject':match[2] or match[3]}


class Docker:
    def json(self,argv):
        result=subprocess.run(['docker',*argv],capture_output=True,text=True,timeout=30)
        if result.returncode:return None
        return json.loads(result.stdout)

    def inspect(self,cid):
        values=self.json(['inspect',cid]);return values[0] if values else None

    def containers(self):
        result=subprocess.run(['docker','ps','-a','--no-trunc','--format','{{json .}}'],capture_output=True,text=True,timeout=30,check=True)
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def history(self,since):
        result=subprocess.run(['docker','events','--since',str(int(since)-1),'--until',iso(time.time()),
            '--format','{{json .}}','--filter','type=container'],capture_output=True,text=True,timeout=30,check=True)
        return [json.loads(x) for x in result.stdout.splitlines() if x.strip()]


class Observer:
    def __init__(self,root,docker=None):
        self.root=Path(root).absolute();self.hub=self.root/'continuous5/timing'
        repository=Path(__file__).resolve().parents[2]
        resolved=self.root.resolve()
        if resolved==Path('/') or resolved==repository or repository in resolved.parents or resolved in repository.parents:
            raise ValueError('Observer runtime must be outside the source repository')
        if not (self.root/'continuous5/settings.json').is_file():raise ValueError('An existing managed runtime is required')
        self.hub.mkdir(parents=True,exist_ok=True);self.docker=docker or Docker()
        self.state=read(self.hub/'observer_state.json') if (self.hub/'observer_state.json').exists() else {
            'schema':1,'first_observed_at':stamp(),'cursor':None,'containers':{},'host_sleep_intervals':[]}
        self.state['containers']={k:v for k,v in self.state['containers'].items() if v.get('started_at')}
        self.records={};self.errors=[]
        self.cache={}
        self.code_sha=sha(__file__)

    def cached_read(self,path):
        path=Path(path);s=path.stat();key=(s.st_ino,s.st_size,s.st_mtime_ns)
        old=self.cache.get(str(path))
        if old and old[0]==key:return old[1]
        value=read(path);self.cache[str(path)]=(key,value);return value

    def scan_records(self):
        records={}
        for path in (self.root/'runs').glob('ADNI*/logs/*/run.json'):
            try:
                d=self.cached_read(path);subject=d['case']['subject'];stage=d['stage']
                if stage not in ('mriqc','fmriprep'):continue
                records[str(path)]={'path':str(path),'subject':subject,'stage':stage,'record':d}
            except (OSError,KeyError,ValueError) as exc:self.errors.append(str(exc))
        for path in (self.root/'results').glob('*/*/s10/*/runs/*/attempt-*/execution.json'):
            try:
                d=self.cached_read(path);subject=d['row']['sub'].removeprefix('sub-')
                records[str(path)]={'path':str(path),'subject':subject,'stage':'xcpd','record':d}
            except (OSError,KeyError,ValueError) as exc:self.errors.append(str(exc))
        self.records=records

    def match_record(self,container):
        if container['subject']=='SELFTEST':return None
        cid=container['id'];start=epoch(container['started_at']) if container.get('started_at') else None
        choices=[]
        for item in self.records.values():
            d=item['record']
            if (item['subject'],item['stage'])!=(container['subject'],container['stage']):continue
            if d.get('container_id')==cid:return item
            if container.get('record_path')==item['path']:return item
            if d.get('started_at') and start is not None and -2<=start-epoch(d['started_at'])<=600:
                expected=d.get('image',{}).get('resolved') if isinstance(d.get('image'),dict) else None
                if expected and container.get('image') and expected!=container['image']:continue
                choices.append((epoch(d['started_at']),item))
        return max(choices,key=lambda v:v[0])[1] if choices else None

    def remember(self,info):
        desc=classify(info['Name'],info.get('Config',{}).get('Labels') or {})
        if not desc:return None
        # Only attach subject names with an actual record in this runtime.
        if desc['subject']!='SELFTEST' and not any(x['subject']==desc['subject'] and x['stage']==desc['stage'] for x in self.records.values()):return None
        cid=info['Id'];state=info['State'];old=self.state['containers'].get(cid,{})
        start=state.get('StartedAt')
        if not start or start.startswith('0001'):return None
        value={**old,**desc,'id':cid,'name':info['Name'].lstrip('/'),'started_at':start,
               'image':info.get('Config',{}).get('Image'),'source':'docker_state',
               'pauses':old.get('pauses',[]),'start_event_observed':old.get('start_event_observed',False)}
        if state.get('Status') in ('exited','dead') and state.get('FinishedAt') and not state['FinishedAt'].startswith('0001'):
            value.update(finished_at=state['FinishedAt'],exit_code=state.get('ExitCode'))
        if state.get('Paused') and not value.get('pause_open'):value['pause_open']=stamp()
        if desc['subject']!='SELFTEST' and self.match_record(value) is None:return None
        self.state['containers'][cid]=value;return value

    def observe_event(self,event):
        if event.get('Type','container')!='container':return
        action=event.get('Action',event.get('status'));actor=event.get('Actor',{})
        cid=actor.get('ID',event.get('id'));attrs=actor.get('Attributes',{})
        desc=classify(attrs.get('name',''),attrs)
        if not desc or action not in ('start','pause','unpause','die'):return
        if action=='start':self.scan_records()
        when=(event['timeNano']/1e9) if event.get('timeNano') else float(event['time'])
        old=self.state['containers'].get(cid,{})
        if not old:
            info=self.docker.inspect(cid)
            if info and self.remember(info) is None:return
            old=self.state['containers'].get(cid,{})
        if not old:
            if desc['subject']!='SELFTEST' and not any(x['subject']==desc['subject'] and x['stage']==desc['stage'] for x in self.records.values()):return
            old={**desc,'id':cid,'name':attrs.get('name'),'pauses':[],'source':'docker_events'}
        value=dict(old)
        if action=='start':
            value.setdefault('started_at',iso(when));value['start_event_observed']=True
        elif action=='pause':
            value['pause_open']=min(value.get('pause_open',iso(when)),iso(when))
        elif action=='unpause':
            if value.get('pause_open'):
                interval=[value.pop('pause_open'),iso(when)]
                if interval not in value['pauses']:value['pauses'].append(interval)
        elif action=='die':
            if not value.get('started_at'):return
            value.setdefault('finished_at',iso(when));value['exit_code']=int(attrs['exitCode']) if 'exitCode' in attrs else value.get('exit_code')
            value.setdefault('terminal_event_observed_at',stamp());value['terminal_event_at']=iso(when)
        self.state['containers'][cid]=value
        self.state['cursor']=max(float(self.state.get('cursor') or 0),when)
        self.persist_container(value)

    def capture_sleep(self):
        if sys.platform!='darwin':return
        result=subprocess.run(['sysctl','-n','kern.sleeptime','kern.waketime'],capture_output=True,text=True,timeout=5)
        matches=re.findall(r'sec\s*=\s*(\d+)\s*,\s*usec\s*=\s*(\d+)',result.stdout)
        self.state['host_sleep_tracking_supported']=not result.returncode and len(matches)==2
        if not self.state['host_sleep_tracking_supported']:return
        start,end=[int(a)+int(b)/1e6 for a,b in matches]
        if end>start>0:
            self.state.setdefault('host_sleep_coverage_start',iso(end))
            interval=[start,end]
            if interval not in self.state['host_sleep_intervals']:self.state['host_sleep_intervals'].append(interval)

    def attempt_path(self,item):
        token=hashlib.sha256(item['path'].encode()).hexdigest()[:20]
        return self.hub/'attempts'/item['subject']/item['stage']/(token+'.json')

    def timing(self,value,item=None):
        start=value.get('started_at');end=value.get('finished_at')
        if not start or not end:return None
        a,b=epoch(start),epoch(end)
        if b<a:raise ValueError('Reversed execution timestamps: '+value['id'])
        pauses=[(epoch(x),epoch(y)) for x,y in value.get('pauses',[])]
        if value.get('pause_open'):pauses.append((epoch(value['pause_open']),b))
        sleeping=[tuple(x) for x in self.state['host_sleep_intervals']]
        excluded=overlap_seconds(a,b,pauses+sleeping)
        covered=(value.get('start_event_observed',False) and self.state.get('host_sleep_tracking_supported',False)
                 and a>=epoch(self.state.get('host_sleep_coverage_start',self.state['first_observed_at']))-2)
        automatic=(value.get('terminal_event_at') and epoch(value['terminal_event_at'])>=epoch(self.state['first_observed_at']))
        return {'schema':1,'subject':value['subject'],'stage':value['stage'],'container_id':value['id'],
            'started_at':start,'finished_at':end,'container_elapsed_seconds':round(b-a,6),
            'observed_pause_sleep_seconds':round(excluded,6),'execution_seconds':round(b-a-excluded,6),
            'execution_duration':format_duration(b-a-excluded),
            'container_elapsed_duration':format_duration(b-a),'excluded_pause_sleep_duration':format_duration(excluded),
            'exit_code':value.get('exit_code'),'measurement_source':value['source'],
            'recording_mode':'automatic_terminal_event' if automatic else 'existing_docker_state',
            'recorded_at':value.get('terminal_event_observed_at',self.state['first_observed_at']),
            'pause_sleep_history_complete':covered,'timing_quality':'observed_container_window' if covered else 'container_window_with_partial_pause_sleep_history',
            'record_path':item['path'] if item else None,'recorder_version':VERSION,'recorder_sha256':self.code_sha,
            'failure_hold_and_queue_wait_included':False,'cpu_time':False,'LLM_calls':0}

    def persist_container(self,value):
        item=self.match_record(value)
        if item:value['record_path']=item['path']
        record=self.timing(value,item)
        if record is None:return
        if value['subject']=='SELFTEST':save(self.hub/'selftests'/(value['id']+'.json'),record)
        elif item:save(self.attempt_path(item),record)

    def reconcile(self,inspect_existing=False):
        self.scan_records();self.capture_sleep()
        if inspect_existing:
            for entry in self.docker.containers():
                if classify(entry.get('Names','')):
                    info=self.docker.inspect(entry['ID'])
                    if info:self.remember(info)
            active=[v for v in self.state['containers'].values() if not v.get('finished_at')]
            if active and hasattr(self.docker,'history'):
                for event in self.docker.history(min(epoch(v['started_at']) for v in active)):
                    self.observe_event(event)
        for value in self.state['containers'].values():self.persist_container(value)
        # Historical driver windows are explicitly reconstructed, never labeled measured.
        for item in self.records.values():
            path=self.attempt_path(item)
            if path.exists():continue
            d=item['record'];start=d.get('started_at')
            end=(d.get('finished_at') if item['stage']=='xcpd' else d.get('container_ended_at') or d.get('ended_at'))
            if start and end:
                seconds=epoch(end)-epoch(start)
                if seconds<0:raise ValueError('Reversed historical attempt')
                save(path,{'schema':1,'subject':item['subject'],'stage':item['stage'],'record_path':item['path'],
                    'started_at':start,'finished_at':end,'execution_seconds':round(seconds,6),
                    'exit_code':d.get('exit_code'),'measurement_source':'historical_driver_log',
                    'recording_mode':'historical_reconstruction','timing_quality':'estimate_includes_driver_observation_overhead',
                    'pause_sleep_history_complete':False,'failure_hold_and_queue_wait_included':'not_fully_verifiable',
                    'cpu_time':False,'recorder_version':VERSION,'recorder_sha256':self.code_sha,'LLM_calls':0})
        self.summaries()
        save(self.hub/'observer_state.json',self.state)
        save(self.hub/'status.json',{'updated_at':stamp(),'pid':os.getpid(),'version':VERSION,
            'status':'watching_terminal_events','observed_containers':len(self.state['containers']),
            'running_subjects':sorted({v['subject'] for v in self.state['containers'].values() if v.get('started_at') and not v.get('finished_at') and v['subject']!='SELFTEST'}),
            'terminal_timings':len(list((self.hub/'attempts').glob('*/*/*.json'))),'errors':self.errors[-5:],'LLM_calls':0})

    def summaries(self):
        groups={}
        published={}
        for meta in (self.root/'results').glob('*/EPI*_MT1*/pair_metadata.json'):
            try:
                subject=self.cached_read(meta)['subject']
                # A subject-level aggregate cannot identify one visit when more
                # than one published pair exists. Keep its totals unassigned.
                published[subject]=None if subject in published else meta
            except (OSError,ValueError,KeyError) as exc:self.errors.append(str(exc))
        for path in (self.hub/'attempts').glob('*/*/*.json'):
            d=read(path)
            if 'execution_duration' not in d:
                d['execution_duration']=format_duration(d['execution_seconds']);d['display_format_version']=VERSION;save(path,d)
            groups.setdefault(d['subject'],[]).append(d)
        rows=[];display_rows=[]
        for subject,attempts in sorted(groups.items()):
            row={'subject':subject}
            states={}
            for stage in ['mriqc','fmriprep','xcpd']:
                parts=[x for x in attempts if x['stage']==stage]
                row[stage+'_seconds']=round(sum(x['execution_seconds'] for x in parts),6) if parts else None
                raw=[v['record'] for v in self.records.values() if (v['subject'],v['stage'])==(subject,stage)]
                latest=max(raw,key=lambda x:x.get('started_at') or x.get('created_at') or '') if raw else {}
                states[stage]=latest.get('status','not_started')
            meta=published.get(subject)
            if meta:
                for ready in (meta.parent/'s10').glob('*/archive_ready.json'):
                    status=self.cached_read(ready)['runs'][0]['xcpd_status']
                    if status=='skipped_pre_qc_fail':states['xcpd']=status;row['xcpd_seconds']=0.0
                data=self.cached_read(meta)
                row.update({k:data.get(k) for k in ['ptid','pair_id','epi_image_id','mt1_image_id']})
            else:row.update({k:None for k in ['ptid','pair_id','epi_image_id','mt1_image_id']})
            complete=(states['fmriprep']=='execution_completed_QC_required' and states['xcpd'] in ('success','skipped_pre_qc_fail','skipped_insufficient_time'))
            row['processing_status']='completed_or_qc_skipped' if complete else 'in_progress_or_failed'
            row['preprocessing_postprocessing_seconds']=(round((row['fmriprep_seconds'] or 0)+(row['xcpd_seconds'] or 0),6) if complete else None)
            row['successful_attempt_seconds']=round(sum(x['execution_seconds'] for x in attempts if x.get('exit_code')==0 and x['stage']!='mriqc'),6)
            row['failed_attempt_seconds']=round(sum(x['execution_seconds'] for x in attempts if x.get('exit_code') not in (0,42,None) and x['stage']!='mriqc'),6)
            row['skipped_execution_seconds']=round(sum(x['execution_seconds'] for x in attempts if x.get('exit_code')==42 and x['stage']!='mriqc'),6)
            row['historically_reconstructed_attempts']=sum(x['recording_mode']=='historical_reconstruction' for x in attempts)
            row['partial_pause_sleep_history_attempts']=sum(not x['pause_sleep_history_complete'] for x in attempts)
            row['attempts']=len(attempts);row['units']='seconds'
            display=human_summary(row,states);display_rows.append(display)
            rows.append(row);save(self.hub/'subjects'/(subject+'.json'),{'display':display,'summary':row,'attempts':attempts,
                'stage_states':states,
                'scope':'fMRIPrep + XCP-D; MRIQC separate; successful and failed execution separate; estimates explicitly identified',
                'successful_retries_can_reuse_prior_failed_attempt_cache':True})
            if meta:
                try:
                    out=meta.parent/'results'
                    # Preserve S12 ownership and its unchanged export fingerprint.
                    if not (out/'export_manifest.json').is_file():continue
                    save(out/'processing_time.json',read(self.hub/'subjects'/(subject+'.json')))
                    write_text(out/'processing_time.csv',csv_text([display]))
                    write_text(out/'processing_time.raw.csv',csv_text([row]))
                except OSError as exc:self.errors.append(str(exc))
        if rows:
            write_text(self.hub/'processing_times.csv',csv_text(display_rows))
            write_text(self.hub/'processing_times.raw.csv',csv_text(rows))

    def watch(self):
        with (self.hub/'observer.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            events=queue.Queue();process=None
            while True:
                if process is None or process.poll() is not None:
                    argv=['docker','events','--format','{{json .}}','--filter','type=container']
                    if self.state.get('cursor'):argv+=['--since',str(int(self.state['cursor'])-1)]
                    process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
                    def pump(stream):
                        for line in stream:
                            try:events.put(json.loads(line))
                            except ValueError:pass
                    threading.Thread(target=pump,args=(process.stdout,),daemon=True).start()
                    self.reconcile(inspect_existing=True)
                    scanned=time.monotonic()
                try:
                    event=events.get(timeout=2);self.observe_event(event)
                    while not events.empty():self.observe_event(events.get_nowait())
                except queue.Empty:pass
                if time.monotonic()-scanned>=5:
                    self.reconcile();scanned=time.monotonic()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('action',choices=['once','watch'])
    args=parser.parse_args();app=Observer(args.root)
    if args.action=='watch':app.watch()
    else:
        with (app.hub/'observer.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);app.reconcile(inspect_existing=True)


if __name__=='__main__':main()
