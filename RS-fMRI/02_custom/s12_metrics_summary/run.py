"""Export one row per archived scan/run and link native imaging HTML reports."""
import argparse
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import quote

import pandas as pd

VERSION='1.0.0'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def ident(s):
    return re.sub(r'[^A-Za-z0-9_-]+','_',str(s)).strip('_')

def json_read(p):return json.loads(Path(p).read_text())

def number(v):
    try:
        f=float(v)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError):return None

class Row:
    def __init__(self,pair):self.pair=pair;self.values={};self.dictionary=[];self.sources={}
    def add(self,k,v,source,unit=''):
        if k in self.values:raise ValueError('Duplicate metric: '+k)
        if isinstance(v,float) and not math.isfinite(v):v=None
        self.values[k]=v
        relative=str(Path(source).relative_to(self.pair))
        self.dictionary.append({'column':k,'unit':unit,'source_file':relative})
        if relative not in self.sources:self.sources[relative]=sha(source)


def freesurfer(row,root):
    required=['aseg.stats','lh.aparc.stats','rh.aparc.stats']
    for name in required:
        if not (root/name).is_file():raise ValueError('Required FreeSurfer stats missing: '+name)
    for p in sorted(root.glob('*.stats')):
        prefix='fs__'+ident(p.stem);header=None
        for line in p.read_text().splitlines():
            if line.startswith('# Measure '):
                parts=[x.strip() for x in line[len('# Measure '):].split(',')]
                if len(parts)>=5 and number(parts[-2]) is not None:
                    row.add(prefix+'__measure__'+ident(parts[1]),number(parts[-2]),p,parts[-1])
            elif line.startswith('# ColHeaders '):header=line.split()[2:]
            elif line.strip() and not line.startswith('#') and header and 'StructName' in header:
                fields=line.split()
                if len(fields)!=len(header):raise ValueError('Malformed stats row: '+str(p))
                data=dict(zip(header,fields));region=ident(data['StructName'])
                for col,v in data.items():
                    if col=='StructName':continue
                    try:float(v)
                    except ValueError:raise ValueError('Nonnumeric FreeSurfer value: '+col)
                    unit='mm^3' if col in ('Volume_mm3','GrayVol') else 'mm^2' if col=='SurfArea' else 'mm' if col in ('ThickAvg','ThickStd') else ''
                    row.add(prefix+'__'+region+'__'+col,number(v),p,unit)


def scalar_tsv(row,p,prefix,coverage=False):
    frame=pd.read_csv(p,sep='\t',index_col=0 if coverage else None)
    frame.columns=[re.sub(r'_hash-[A-Za-z0-9]+$','',str(c)) for c in frame.columns]
    if coverage:
        if 'coverage' not in frame:raise ValueError('Coverage column missing')
        values={str(k):v for k,v in frame['coverage'].items()}
    else:
        if len(frame)!=1:raise ValueError('Expected one-row scalar TSV: '+str(p))
        values=frame.iloc[0].to_dict()
    for k,v in values.items():row.add(prefix+'__'+ident(k),number(v),p)


def relative_url(p,base):return quote(os.path.relpath(p,base),safe='/')

def export_pair(pair):
    pair=Path(pair).resolve();receipt=pair/'relocation_receipt.json'
    if not receipt.is_file() or json_read(receipt).get('status')!='archived_and_local_space_reclaimed':return 'waiting_for_verified_archive'
    meta_file=pair/'pair_metadata.json';meta=json_read(meta_file);jobs=[]
    for stage in sorted((pair/'s10').glob('*')):
        pre=stage/'pre_qc.json'
        if not pre.exists():continue
        for item in json_read(pre)['rows']:
            if item.get('sub')!='sub-'+meta['subject'] or item.get('config_id')!=stage.name:raise ValueError('Pair/run configuration identity mismatch')
            # Read current local archive paths, never historical host absolute paths.
            run_root=stage/'runs'
            matches=[]
            for f in run_root.glob('*/attempt-*/execution.json'):
                record=json_read(f);r=record.get('row',{})
                if all(str(r.get(k) or '')==str(item.get(k) or '') for k in ('sub','ses','task','run','acq','dir','echo','rec')):matches.append(f)
            last=sorted(matches)[-1] if matches else None
            jobs.append((stage,pre,item,last))
    if not jobs:return 'waiting_for_S8'
    out=pair/'results';manifest_file=out/'export_manifest.json'
    if out.exists() and any(out.iterdir()) and not manifest_file.exists():raise ValueError('Unmanaged results directory: '+str(out))
    if manifest_file.exists():
        old=json_read(manifest_file)
        if any(not (out/p).is_file() or sha(out/p)!=h for p,h in old['outputs'].items()):raise ValueError('Generated results changed; preserving edits')
        # An unchanged successful export requires no repeated parsing.
        if old.get('exporter_sha256')==sha(__file__) and all((pair/p).is_file() and sha(pair/p)==h for p,h in old['sources'].items()):
            if all((out/p).is_file() and sha(out/p)==h for p,h in old['outputs'].items()):return 'already_exported'
            raise ValueError('Generated results changed; preserving edits')
    out.mkdir(exist_ok=True)
    all_sources={};written=[];run_manifests=[];links=[]
    def write(path,text):
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_name(path.name+'.writing');tmp.write_text(text);tmp.replace(path);written.append(path)
    for stage,pre,item,execution in jobs:
        row=Row(pair)
        for key in ('ptid','subject','pair_id','epi_date','mt1_date','epi_image_id','mt1_image_id'):row.add(key,meta.get(key),meta_file)
        for key in ('sub','ses','task','run','acq','dir','echo','rec','config_id','pre_xcpd_qc_status','euler_qc_flag','mriqc_exclude_flag'):
            row.add(key,item.get(key),pre)
        row.add('final_inclusion_status','pending',pre)
        for k,v in item.items():
            if isinstance(v,(float,int)) and not isinstance(v,bool) and k not in row.values:row.add('s8__'+ident(k),v,pre)
        stem=item['sub']+('_'+item['ses'] if item.get('ses') else '')
        fs=pair/'fmriprep/sourcedata/freesurfer'/stem/'stats';freesurfer(row,fs)
        reports=[]
        for p in sorted((pair/'fmriprep').glob(item['sub']+'*.html')):reports.append(('fMRIPrep',p))
        for p in sorted((pair/'mriqc').glob(stem+'*.html')):reports.append(('MRIQC '+p.stem,p))
        if execution:
            record=json_read(execution);validation=execution.with_name('output_validation.json')
            row.add('xcpd_status',record['status'],execution)
            if record['status']=='success':
                qc=json_read(validation)
                if qc.get('functional_outputs_valid') is not True:raise ValueError('Unvalidated XCP-D success')
                for k,v in qc.items():
                    if isinstance(v,(str,int,float,bool)) or v is None:row.add('xcpd_qc__'+ident(k),v,validation)
                row.add('xcpd_qc__warnings',json.dumps(qc.get('xcpd_warnings',[])),validation)
                deriv=execution.parent/'derivatives'
                func=deriv/item['sub']/item['ses']/'func' if item.get('ses') else deriv/item['sub']/'func'
                candidates=list(func.glob('*_stat-reho_bold.tsv'))+list(func.glob('*_stat-alff_bold.tsv'))+list(func.glob('*_stat-coverage_bold.tsv'))
                if not any('_stat-reho_' in p.name for p in candidates):raise ValueError('Required ReHo scalar output missing')
                matched_reho=0
                for p in sorted(candidates):
                    # Exact BIDS run identity prevents unrelated run values entering a row.
                    entities=dict(re.findall(r'(?:^|_)([a-zA-Z0-9]+)-([^_.]+)',p.name))
                    if any((entities.get(k) or '')!=str(item.get(k) or '').removeprefix(k+'-') for k in ('sub','ses','task','run','acq','dir','echo','rec')):continue
                    prefix='xcpd__'+ident(entities.get('space',''))+'__'+ident(entities.get('atlas',''))+'__'+entities['stat']
                    scalar_tsv(row,p,prefix,coverage=entities['stat']=='coverage')
                    if entities['stat']=='reho':matched_reho+=1
                if matched_reho==0:raise ValueError('Selected run ReHo output missing')
                for p in sorted(deriv.glob(item['sub']+'*.html')):reports.append(('XCP-D executive summary' if 'executive_summary' in p.name else 'XCP-D participant report',p))
        else:row.add('xcpd_status','skipped_or_not_started',pre)
        destination=out if len(jobs)==1 else out/stage.name/(execution.parent.parent.name if execution else stem)
        if destination==out and len(jobs)>1:raise ValueError('Ambiguous output row')
        frame=pd.DataFrame([row.values]);assert len(frame)==1
        for filename,sep in [('metrics.csv',','),('metrics.tsv','\t')]:write(destination/filename,frame.to_csv(index=False,sep=sep,na_rep='NA'))
        write(destination/'metrics_dictionary.csv',pd.DataFrame(row.dictionary).to_csv(index=False))
        for label,p in reports:
            if not p.is_file():raise ValueError('Report missing: '+str(p))
            row.sources[str(p.relative_to(pair))]=sha(p)
        buttons=''.join('<li><a href="'+relative_url(p,out)+'">'+html.escape(label)+'</a></li>' for label,p in reports)
        links.append('<section><h2>'+html.escape(stem+' '+str(item.get('run','')) )+'</h2><ul>'+buttons+'<li><a href="'+relative_url(destination/'metrics.csv',out)+'">One-row metrics CSV</a></li><li><a href="'+relative_url(destination/'metrics_dictionary.csv',out)+'">Column dictionary and units</a></li></ul></section>')
        run_manifests.append({'sub':item['sub'],'ses':item['ses'],'run':item.get('run',''),'config_id':stage.name,'rows':1,'columns':len(frame.columns),'csv':str((destination/'metrics.csv').relative_to(out))})
        all_sources.update(row.sources)
    write(out/'index.html','<!doctype html><html lang="en"><meta charset="utf-8"><title>Imaging results</title><style>body{font:17px system-ui;max-width:1000px;margin:3em auto;padding:0 2em;line-height:1.7}a{color:#126249}section{padding:1em;background:#f4f7f6;margin:1em 0}li{margin:.5em}</style><h1>'+html.escape(meta['ptid']+' / '+meta['pair_id'])+'</h1><p>Original MRIQC, fMRIPrep and XCP-D reports. Numerical extraction is not final research inclusion. Coverage warnings and missing values are preserved. Structural values derive from the paired T1; functional values derive from the selected EPI run.</p>'+''.join(links)+'</html>')
    manifest={'version':VERSION,'exporter_sha256':sha(__file__),'created_at':time.time(),'final_inclusion':'pending','sources':all_sources,'runs':run_manifests,'outputs':{str(p.relative_to(out)):sha(p) for p in written},'archive_note':'Additive reproducible derived results; original archive manifest remains unchanged.'}
    write(manifest_file,json.dumps(manifest,indent=2)+'\n')
    return 'exported'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive-root',type=Path,required=True);parser.add_argument('--watch',action='store_true');parser.add_argument('--status',type=Path);args=parser.parse_args()
    while True:
        results={}
        for p in sorted(args.archive_root.glob('*/EPI*_MT1*')):
            if not p.is_dir():continue
            try:results[str(p)]=export_pair(p)
            except Exception as exc:results[str(p)]='error: '+str(exc)
        if args.status:
            args.status.parent.mkdir(parents=True,exist_ok=True);tmp=args.status.with_suffix('.writing');tmp.write_text(json.dumps({'at':time.time(),'pairs':results,'LLM_calls':0},indent=2));tmp.replace(args.status)
        print(json.dumps(results),flush=True)
        if not args.watch:break
        time.sleep(120)

if __name__=='__main__':main()
