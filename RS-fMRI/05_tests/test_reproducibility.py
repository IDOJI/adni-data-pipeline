"""Public/offline runnable examples, reference errors and peer-comparison failures."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import nibabel as nib
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
KIT=ROOT/'07_reproducibility'
sys.path.insert(0,str(KIT))


def mod(name):
    spec=importlib.util.spec_from_file_location('repro_test_'+name,KIT/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_complete_example_and_reference_detect_changes(tmp_path):
    toy=mod('toy');compare=mod('compare');root=tmp_path/'one'
    toy.init(root);toy.run(root,'all');toy.verify(root)
    second=tmp_path/'two';shutil.copytree(root,second)
    assert compare.compare(root,second,mode='synthetic')['status']=='PASS'
    table=second/'outputs/11/timeseries.tsv'
    lines=table.read_text().splitlines(); cells=lines[1].split('\t'); cells[1]='11'; lines[1]='\t'.join(cells); table.write_text('\n'.join(lines)+'\n')
    assert compare.compare(root,second,mode='synthetic')['status']=='FAIL'
    with pytest.raises(ValueError,match='ROI values'):toy.verify(second)
    source=root/'inputs/MRIQC.csv';source.write_text(source.read_text()+'\n')
    with pytest.raises(ValueError,match='Changed toy input'):toy.check_inputs(root)


def test_voxel_tolerances_grid_masks_and_missingness(tmp_path):
    compare=mod('compare');a=tmp_path/'a.nii.gz';b=tmp_path/'b.nii.gz'
    nib.save(nib.Nifti1Image(np.ones((2,2,2),np.float32),np.eye(4)),a)
    nib.save(nib.Nifti1Image(np.ones((2,2,2),np.float32)+1e-6,np.eye(4)),b)
    assert compare.compare_image(a,b,1e-5,0)['status']=='within_tolerance'
    assert compare.compare_image(a,b,0,0)['status']=='fail'
    shifted=np.eye(4);shifted[0,3]=1
    nib.save(nib.Nifti1Image(np.ones((2,2,2),np.float32),shifted),b)
    assert compare.compare_image(a,b,1,1)['status']=='fail'
    assert compare.numeric(np.array([np.nan,1]),np.array([1,np.nan]),1,1)['status']=='fail'
    a=tmp_path/'a_mask.nii.gz';b=tmp_path/'b_mask.nii.gz'
    nib.save(nib.Nifti1Image(np.ones((2,2,2),np.float32),np.eye(4)),a)
    nib.save(nib.Nifti1Image(np.zeros((2,2,2),np.float32),np.eye(4)),b)
    assert compare.compare_image(a,b,10,10)['status']=='fail'


def test_text_identity_and_row_order_are_not_normalized(tmp_path):
    compare=mod('compare');a=tmp_path/'a.tsv';b=tmp_path/'b.tsv'
    a.write_text('participant_id\tvalue\n001\t1\n002\t2\n')
    b.write_text('participant_id\tvalue\n1\t1\n2\t2\n')
    assert compare.compare_table(a,b,1,1)['status']=='fail'
    b.write_text('participant_id\tvalue\n002\t2\n001\t1\n')
    assert compare.compare_table(a,b,1,1)['status']=='fail'


def test_public_fetch_with_pinned_cache_and_command_contract(tmp_path,monkeypatch):
    public=mod('public');toy=mod('toy');cache=tmp_path/'cache';cache.mkdir()
    files=[]
    sources={
        'sub-10159/anat/sub-10159_T1w.nii.gz':np.zeros((4,4,4),np.float32),
        'sub-10159/func/sub-10159_task-rest_bold.nii.gz':np.zeros((4,4,4,120),np.float32)}
    for path,values in sources.items():toy.image(cache/path,values,tr=2)
    toy.write_json(cache/'dataset_description.json',{'License':'CC0'})
    toy.write_json(cache/'task-rest_bold.json',{'TaskName':'rest'})
    toy.write_json(cache/'sub-10159/func/sub-10159_task-rest_bold.json',dict(RepetitionTime=2,SliceTiming=[0,.5,1,1.5],PhaseEncodingDirection='j-'))
    for p in sorted(cache.rglob('*')):
        if p.is_file():files.append(dict(path=str(p.relative_to(cache)),url='https://example.invalid/'+p.name,bytes=p.stat().st_size,sha256=toy.sha(p)))
    spec=dict(files=files,doi='synthetic-test',source='synthetic-test')
    monkeypatch.setattr(public,'specification',lambda:spec)
    monkeypatch.setattr(public.urllib.request,'urlopen',lambda *a,**k:pytest.fail('Cache test must not download'))
    root=tmp_path/'public';public.fetch(root,cache)
    assert nib.load(next((root/'bids').rglob('*bold.nii.gz'))).shape[-1]==120
    license_file=tmp_path/'license.txt';license_file.write_text('synthetic planning placeholder, never executed')
    cmd=public.docker_command(root,'fmriprep',license_file)
    assert cmd[cmd.index('--subject-anatomical-reference')+1]=='sessionwise'
    assert cmd[cmd.index('--use-syn-sdc')+1]=='error'
    assert cmd[cmd.index('--omp-nthreads')+1]=='1'
    assert '--skull-strip-fixed-seed' in cmd
    assert cmd[cmd.index('--pull')+1]=='never'
    assert public.IMAGES['fmriprep'] in cmd and '--execute' not in cmd
    filt=root/'config/mriqc_filter.json';original=filt.read_bytes();filt.write_text('{}')
    with pytest.raises(ValueError,match='Changed public input'):public.check_inputs(root)
    filt.write_bytes(original)
    extra=root/'bids/unexpected.txt';extra.write_text('unexpected')
    with pytest.raises(ValueError,match='inventory changed'):public.check_inputs(root)
    extra.unlink()
    source=next((root/'bids').rglob('*bold.nii.gz'));source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='Changed public input'):public.docker_command(root,'mriqc')
    cached=cache/files[0]['path'];cached.write_bytes(b'changed')
    with pytest.raises(ValueError,match='differs from pinned'):public.fetch(tmp_path/'bad',cache)


def test_public_xcpd_uses_existing_analysis_argument_builder(tmp_path):
    public=mod('public');pipeline=public.load_module('02_custom/s10_xcpd_integrated_qc/pipeline.py')
    cfg=public.xcp_config();row=public.public_row(tmp_path)
    args=pipeline.xcp_args(cfg,row)
    assert args[args.index('--nuisance-regressors')+1]=='36P'
    assert args[args.index('--fd-thresh')+1]=='0.3'
    assert args[args.index('--min-time')+1]=='240'
    assert args[args.index('--omp-nthreads')+1]=='1'
    assert args[args.index('--output-type')+1]=='censored'
    assert pipeline.bids_filter(row,cfg)['bold']['space']=='MNI152NLin6Asym'


def test_comparison_cannot_pass_without_products_or_matching_identity(tmp_path):
    compare=mod('compare');a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    assert compare.compare(a,b)['status']=='FAIL'
    for p in [a,b]:(p/'comparison_identity.json').write_text('{}')
    assert compare.compare(a,b)['status']=='FAIL'
    for p in [a,b]:(p/'values.tsv').write_text('v\n1\n')
    assert compare.compare(a,b,patterns=['values.tsv'])['status']=='FAIL'  # Incomplete executions cannot pass
    (b/'comparison_identity.json').write_text('{"image":"different"}')
    assert compare.compare(a,b,patterns=['values.tsv'])['status']=='FAIL'


def test_public_comparison_checks_completion_input_hashes_and_actual_argv(tmp_path):
    # Unit-test evidence only, not an imaging execution record.
    compare=mod('compare');toy=mod('toy');roots=[tmp_path/'a',tmp_path/'b']
    images={name:name+'@sha256:synthetic-test' for name in ('mriqc','fmriprep','xcpd')}
    for root in roots:
        root.mkdir();(root/'input.txt').write_text('synthetic-input')
        toy.write_json(root/'comparison_identity.json',dict(images=images))
        toy.write_json(root/'input_manifest.json',{'sha256':{'input.txt':toy.sha(root/'input.txt')}})
        for stage,image in images.items():
            toy.write_json(root/'logs'/(stage+'_execution.json'),dict(status='success',returncode=0,repo_digests=[image],command=['docker','run',image,'/input','/out','participant']))
        toy.write_json(root/'xcpd/output_validation.json',dict(functional_outputs_valid=True))
        (root/'values.tsv').write_text('v\n1\n')
    a,b=roots
    assert compare.compare(a,b,patterns=['values.tsv'])['status']=='PASS'
    p=b/'logs/xcpd_execution.json';record=json.loads(p.read_text());record['command']+=['--nuisance-regressors','different'];toy.write_json(p,record)
    assert compare.compare(a,b,patterns=['values.tsv'])['status']=='FAIL'
    shutil.copyfile(a/'logs/xcpd_execution.json',p)
    (b/'input.txt').write_text('mutated')
    assert compare.compare(a,b,patterns=['values.tsv'])['status']=='FAIL'


def test_real_sample_is_bundled_and_default_staging_is_offline(tmp_path,monkeypatch):
    public=mod('public');toy=mod('toy');spec=public.specification()
    bundled=KIT/spec['bundled_path']
    assert spec['distribution']=='ordinary_git_blobs'
    assert len(spec['files'])==5 and sum(e['bytes'] for e in spec['files'])==35696832
    expected_sums={e['path']:e['sha256'] for e in spec['files']}
    actual_sums={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (bundled/'SHA256SUMS').read_text().splitlines()}
    assert actual_sums==expected_sums
    for entry in spec['files']:
        p=bundled/entry['path']
        assert p.is_file() and not p.is_symlink()
        assert p.stat().st_size==entry['bytes'] and toy.sha(p)==entry['sha256']
    monkeypatch.setattr(public.urllib.request,'urlopen',lambda *a,**k:pytest.fail('Bundled staging must not access the network'))
    root=tmp_path/'from-git';public.fetch(root)
    assert json.loads((root/'input_manifest.json').read_text())['payload_source']=='bundled_git_files'
    assert nib.load(root/'bids/sub-toy001/ses-M000/anat/sub-toy001_ses-M000_T1w.nii.gz').shape==(176,256,256)
    assert nib.load(root/'bids/sub-toy001/ses-M000/func/sub-toy001_ses-M000_task-rest_bold.nii.gz').shape==(64,64,34,152)
    for entry in spec['files']:assert toy.sha(root/'download'/entry['path'])==entry['sha256']


def test_missing_bundle_never_falls_back_to_network(tmp_path,monkeypatch):
    public=mod('public');spec=public.specification();spec['bundled_path']=str(tmp_path/'missing')
    monkeypatch.setattr(public,'specification',lambda:spec)
    monkeypatch.setattr(public.urllib.request,'urlopen',lambda *a,**k:pytest.fail('Missing bundle must not trigger a download'))
    root=tmp_path/'output'
    with pytest.raises(FileNotFoundError,match='Bundled public payload missing'):public.fetch(root)
    assert not root.exists()


def test_git_ignore_exception_only_allows_two_approved_nii_files():
    public=mod('public');spec=public.specification()
    prefix='RS-fMRI/07_reproducibility/'+spec['bundled_path']+'/'
    for entry in spec['files']:
        if entry['path'].endswith('.nii.gz'):
            r=subprocess.run(['git','-C',str(ROOT.parent),'check-ignore','--no-index','--quiet',prefix+entry['path']])
            assert r.returncode==1
    for path in [prefix+'other_bold.nii.gz','RS-fMRI/private_bold.nii.gz','RS-fMRI/private_clinical.csv']:
        r=subprocess.run(['git','-C',str(ROOT.parent),'check-ignore','--no-index','--quiet',path])
        assert r.returncode==0
