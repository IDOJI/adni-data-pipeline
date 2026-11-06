#!/usr/bin/env python3
"""Compare selected numerical products and identity evidence; never infer scientific equivalence."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import re

import nibabel as nib
import numpy as np
from toy import PAIR, sha, write_json

PUBLIC = ['derivatives/fmriprep/sub-*/**/*.nii.gz', 'derivatives/fmriprep/sub-*/**/*.tsv', 'xcpd/derivatives/sub-*/**/*.nii.gz', 'xcpd/derivatives/sub-*/**/*.tsv']
SYNTHETIC = ['outputs/5c/valid_sessions.tsv', 'outputs/9a/clinical_validation.tsv', 'outputs/9b/inclusion_audit.tsv', 'outputs/8/motion_summary.tsv', 'outputs/8a/paper_motion_summary.tsv', 'outputs/11/timeseries.tsv', 'outputs/11/frames.tsv', 'outputs/11/roi_coverage.tsv', str(PAIR/'results/metrics.csv')]


def numeric(a, b, atol, rtol, exact=False):
    if a.shape != b.shape: return {'status':'fail','reason':'shape differs'}
    if not np.array_equal(np.isnan(a),np.isnan(b)) or not np.array_equal(np.isposinf(a),np.isposinf(b)) or not np.array_equal(np.isneginf(a),np.isneginf(b)):
        return {'status':'fail','reason':'missing/nonfinite value positions differ'}
    finite=np.isfinite(a); left=a[finite].astype(float); right=b[finite].astype(float)
    diff=np.abs(left-right); same=np.array_equal(left,right)
    close=same if exact else bool(np.allclose(left,right,atol=atol,rtol=rtol))
    return dict(status='exact_values' if same else 'within_tolerance' if close else 'fail', max_abs_difference=float(diff.max()) if diff.size else 0., rmse=float(np.sqrt(np.mean(diff**2))) if diff.size else 0., compared_finite_values=int(diff.size), exact_required=exact)


def compare_image(left, right, atol, rtol):
    a=nib.load(left); b=nib.load(right)
    if not isinstance(a,nib.Nifti1Image) or not isinstance(b,nib.Nifti1Image):
        return dict(status='fail',reason='Only volumetric NIfTI supported; compare CIFTI separately')
    if a.shape != b.shape or not np.allclose(a.affine,b.affine,atol=1e-5,rtol=0) or not np.allclose(a.header.get_zooms(),b.header.get_zooms(),atol=1e-5,rtol=0) or a.header.get_xyzt_units() != b.header.get_xyzt_units():
        return dict(status='fail',reason='Image grid, affine, TR or units differ')
    exact=any(part in left.name for part in ('_dseg.', '_mask.', '_mask_'))
    # Load each compressed volume once rather than repeatedly seeking within gzip.
    return numeric(np.asanyarray(a.dataobj),np.asanyarray(b.dataobj),atol,rtol,exact)


def compare_table(left,right,atol,rtol):
    delimiter='\t' if left.suffix == '.tsv' else ','
    def read(path):
        with path.open(newline='') as f: return list(csv.reader(f,delimiter=delimiter))
    a=read(left); b=read(right)
    if not a or not b or a[0] != b[0] or len(a) != len(b): return dict(status='fail',reason='Columns/order or row count differ')
    if any(len(row)!=len(a[0]) for row in a+b): return dict(status='fail',reason='Malformed table')
    columns={}
    missing={'','n/a','NA','NaN','nan'}
    for i,name in enumerate(a[0]):
        x=[row[i] for row in a[1:]]; y=[row[i] for row in b[1:]]
        # Identities, labels, row names and frame order are never sorted/coerced away.
        identity=bool(re.search(r'(?:^|_)(?:id|ptid|rid|sub|ses|subject|participant|label)(?:$|_)',name,re.I)) or not name
        try:
            if identity: raise ValueError('identity column')
            ax=np.array([np.nan if v in missing else float(v) for v in x]); by=np.array([np.nan if v in missing else float(v) for v in y])
            int_tokens=all(re.fullmatch(r'-?(0|[1-9][0-9]*)',v) or v in missing for v in x+y)
            columns[name]=numeric(ax,by,atol,rtol,exact=int_tokens)
        except ValueError:
            columns[name]=dict(status='exact_values' if x==y else 'fail',reason='Text/identity values compared in original row order')
    status='fail' if any(c['status']=='fail' for c in columns.values()) else 'within_tolerance' if any(c['status']=='within_tolerance' for c in columns.values()) else 'exact_values'
    return dict(status=status,rows=len(a)-1,columns=columns)


def compare(left,right,mode='public',atol=1e-6,rtol=1e-5,patterns=None):
    identity='comparison_identity.json' if mode=='public' else 'verification.json'
    result=dict(scope='Technical comparison only; tolerances are engineering defaults, not validated research equivalence limits.',atol=atol,rtol=rtol,identity_file=identity,files={})
    if not (left/identity).is_file() or not (right/identity).is_file():
        result.update(status='FAIL',identity_match=False,reason='Missing identity/reference evidence'); return result
    a=json.loads((left/identity).read_text()); b=json.loads((right/identity).read_text())
    result['identity_match']=a==b
    if mode=='synthetic' and (a.get('status')!='PASS' or b.get('status')!='PASS'): result['identity_match']=False
    if mode=='public':
        result['completed_runs_verified']=True
        for root in (left,right):
            try:
                manifest=json.loads((root/'input_manifest.json').read_text())
                if any(sha(root/rel)!=digest for rel,digest in manifest['sha256'].items()): raise ValueError('Input changed')
                input_folders={rel.split('/')[0] for rel in manifest['sha256']}
                actual_inputs={str(p.relative_to(root)) for folder in input_folders for p in (root/folder).rglob('*') if p.is_file()}
                if actual_inputs and actual_inputs!=set(manifest['sha256']): raise ValueError('Input file inventory changed')
                for stage in ('mriqc','fmriprep','xcpd'):
                    execution=json.loads((root/'logs'/(stage+'_execution.json')).read_text())
                    if execution.get('status')!='success' or execution.get('returncode')!=0: raise ValueError('Stage incomplete: '+stage)
                    expected_image=json.loads((root/identity).read_text())['images'][stage]
                    if expected_image not in execution.get('repo_digests',[]): raise ValueError('Realized image differs: '+stage)
                validation=json.loads((root/'xcpd/output_validation.json').read_text())
                if validation.get('functional_outputs_valid') is not True: raise ValueError('XCP-D outputs unvalidated')
            except (OSError,KeyError,ValueError) as exc:
                result['completed_runs_verified']=False
                result['completion_error']=str(exc)
        # Compare actual application argv too, beyond the planned profile.
        if result['completed_runs_verified']:
            for stage in ('mriqc','fmriprep','xcpd'):
                signatures=[]
                for root in (left,right):
                    execution=json.loads((root/'logs'/(stage+'_execution.json')).read_text())
                    image=json.loads((root/identity).read_text())['images'][stage]
                    argv=execution.get('command',[])
                    if image not in argv:
                        result['completed_runs_verified']=False; break
                    signatures.append(argv[argv.index(image):])
                if len(signatures)!=2 or signatures[0]!=signatures[1]:
                    result['completed_runs_verified']=False
                    result['completion_error']='Actual application command differs: '+stage
    patterns=patterns or (PUBLIC if mode=='public' else SYNTHETIC)
    def inventory(root):
        return {str(p.relative_to(root)) for pattern in patterns for p in root.glob(pattern) if p.is_file() and not p.is_symlink() and not any(part in ('logs','figures') for part in p.relative_to(root).parts)}
    la=inventory(left); rb=inventory(right)
    result['left_only']=sorted(la-rb); result['right_only']=sorted(rb-la)
    if not la or not rb: result['reason']='No matching numerical products'
    for rel in sorted(la & rb):
        p=left/rel; q=right/rel
        if sha(p)==sha(q): record=dict(status='byte_identical')
        else:
            try:
                record=compare_image(p,q,atol,rtol) if rel.endswith(('.nii.gz','.nii')) else compare_table(p,q,atol,rtol)
            except (ValueError,OSError,csv.Error) as exc: record=dict(status='fail',reason=str(exc))
        result['files'][rel]=record
    result['status']='PASS' if result['identity_match'] and result.get('completed_runs_verified',True) and la==rb and la and all(v['status']!='fail' for v in result['files'].values()) else 'FAIL'
    result['excluded']='Logs, timestamps, HTML, provenance JSON, FreeSurfer binary surfaces, CIFTI and work directories are not numerical comparison targets. Compare FreeSurfer scalar exports through S12.'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('left',type=Path);p.add_argument('right',type=Path)
    p.add_argument('--mode',choices=['synthetic','public'],default='public');p.add_argument('--atol',type=float,default=1e-6);p.add_argument('--rtol',type=float,default=1e-5)
    p.add_argument('--include',action='append');p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    if a.atol<0 or a.rtol<0 or not np.isfinite([a.atol,a.rtol]).all():p.error('Tolerances must be finite and nonnegative')
    result=compare(a.left.resolve(),a.right.resolve(),a.mode,a.atol,a.rtol,a.include)
    write_json(a.report,result);print(json.dumps({'status':result['status'],'compared_files':len(result['files']),'report':str(a.report)}))
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':main()
