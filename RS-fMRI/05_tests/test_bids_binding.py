import csv
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / 'pipeline/s5d_bids_identity'
sys.path.insert(0, str(STEP))
import binding as b
import guarded_runner as g


def csvwrite(p, rows):
    with p.open('w', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def fixture(tmp):
    root = tmp / 'source'; folder = root / 'sub-999S9999/ses-20200101'
    (folder / 'anat').mkdir(parents=True); (folder / 'func').mkdir()
    (root / 'dataset_description.json').write_text('{"Name":"Synthetic","BIDSVersion":"1.10.0"}')
    images, evidence = [], []
    for mod, image_id, kind, suffix, shape in [('T1', '100', 'anat', 'T1w', (4,4,4)), ('EPI','200','func','task-rest_bold',(4,4,4,8))]:
        stem = folder / kind / ('sub-999S9999_ses-20200101_' + suffix)
        path = Path(str(stem) + '.nii.gz')
        img = nib.Nifti1Image(np.zeros(shape, dtype=np.float32), np.eye(4))
        img.header.set_xyzt_units('mm', 'sec'); img.header.set_dim_info(slice=2)
        img.header.set_zooms((1,1,1,2) if mod == 'EPI' else (1,1,1)); nib.save(img, path)
        meta = {'SeriesInstanceUID':'1.2.'+image_id,'AcquisitionDateTime':'2020-01-01T12:00:00'}
        if mod == 'EPI': meta.update(RepetitionTime=2.,SliceTiming=[0.,.5,1.,1.5],PhaseEncodingDirection='j')
        Path(str(stem)+'.json').write_text(json.dumps(meta))
        images.append(dict(PTID='999_S_9999',MRI_STUDY_DATE='2020-01-01',MODALITY=mod,IMAGE_ID=image_id,
                           SERIES_UID=meta['SeriesInstanceUID'],SEARCH_PHASE='ADNI 3',ELIGIBLE='True',QC_STATUS='pass',EXCLUSION_REASONS=''))
        evidence.append(dict(SOURCE_PTID='999_S_9999',STUDY_DATE='2020-01-01',MODALITY=mod,SOURCE_IMAGE_ID='I'+image_id,NIFTI_SHA256=b.sha(path)))
    epi = dict(EPI_KEY='999_S_9999:2020-01-01:I200',PTID='999_S_9999',MRI_STUDY_DATE='2020-01-01',EPI_IMAGE_ID='200',
               PROPOSED_T1_IMAGE_ID='100',T1_PAIRING_STATUS='same_day_proposed',EPI_METADATA_QC_STATE='documented',
               PAIRING_REVIEW_REQUIRED='False',PROTOCOL_SCOPE='GO_2_3',PREPROCESSING_READY='False',ANALYSIS_READY='False')
    ip=tmp/'images.csv'; ep=tmp/'04.epi-analysis-manifest.csv'; hp=tmp/'hashes.csv'
    csvwrite(ip,images); csvwrite(ep,[epi]); csvwrite(hp,evidence)
    proof=tmp/'pairing.json';proof.write_text(json.dumps({'inputs':{'candidates':{'path':str(ip),'sha256':b.sha(ip)}},
                                                       'outputs':{'epi':{'path':str(ep),'sha256':b.sha(ep)}}}))
    cfg=dict(images=str(ip),epi_manifest=str(ep),pairing_receipt=str(proof),bids_roots=[str(root)],hash_evidence=[str(hp)],output_dir=str(tmp/'out'))
    cp=tmp/'config.json';cp.write_text(json.dumps(cfg))
    return cfg,cp,images,epi,root


def refreshed(cp, cfg): cp.write_text(json.dumps(cfg))


def test_positive_binding_and_plan(tmp_path):
    cfg,cp,_,epi,_=fixture(tmp_path);s=b.run(cp)
    assert s['preprocessing_ready']==1 and s['analysis_ready']==0
    p=b.verify_plan(Path(cfg['output_dir'])/b.NAMES['receipt'],epi['EPI_KEY'])
    assert p['t1_image_id']=='100' and p['epi_image_id']=='200'


@pytest.mark.parametrize('change',['tie','cross_date','source_pending','review_pending','extension'])
def test_policy_pending_never_dispatches(tmp_path,change):
    cfg,cp,_,epi,_=fixture(tmp_path)
    if change=='tie':epi.update(PROPOSED_T1_IMAGE_ID='',T1_PAIRING_STATUS='same_day_tie_review')
    elif change=='cross_date':epi['T1_PAIRING_STATUS']='cross_date_review'
    elif change=='source_pending':epi['EPI_METADATA_QC_STATE']='pending'
    elif change=='review_pending':epi['PAIRING_REVIEW_REQUIRED']='True'
    else:epi['PROTOCOL_SCOPE']='extension_review'
    csvwrite(Path(cfg['epi_manifest']),[epi]);proof=json.loads(Path(cfg['pairing_receipt']).read_text());proof['outputs']['epi']['sha256']=b.sha(cfg['epi_manifest']);Path(cfg['pairing_receipt']).write_text(json.dumps(proof))
    s=b.run(cp);assert s['preprocessing_ready']==0 and s['retained_epi']==1
    with pytest.raises(ValueError,match='pending'):b.verify_plan(Path(cfg['output_dir'])/b.NAMES['receipt'],epi['EPI_KEY'])


@pytest.mark.parametrize('change',['uid_missing','uid_wrong','participant','date','image_id','tr','st','ped','symlink','hash'])
def test_unverified_files_held(tmp_path,change):
    cfg,cp,_,_,root=fixture(tmp_path)
    f=next(root.glob('sub-*/ses-*/func/*.json'));m=json.loads(f.read_text())
    if change=='uid_missing':m.pop('SeriesInstanceUID')
    elif change=='uid_wrong':m['SeriesInstanceUID']='1.2.999'
    elif change=='date':m['AcquisitionDateTime']='2021-01-01T00:00:00'
    elif change=='image_id':m['ImageID']='999'
    elif change=='tr':m['RepetitionTime']=3.
    elif change=='st':m['SliceTiming']=[0.]
    elif change=='ped':m.pop('PhaseEncodingDirection')
    elif change=='participant':
        subject=root/'sub-999S9999';subject.rename(root/'sub-998S9999')
    elif change=='symlink':
        nii=f.with_suffix('.nii.gz');target=tmp_path/'outside.nii.gz';nii.rename(target);nii.symlink_to(target)
    else:
        with f.with_suffix('.nii.gz').open('ab') as stream:stream.write(b'changed')
    if change!='participant':f.write_text(json.dumps(m))
    s=b.run(cp);assert s['preprocessing_ready']==0 and s['held_epi']==1


def test_uid_ambiguity_never_picks_first(tmp_path):
    cfg,cp,images,_,root=fixture(tmp_path);images.append({**images[1],'IMAGE_ID':'201'})
    rows,files,linked,plans=b.bind(images,b.read_csv(cfg['epi_manifest']),[root],b.load_expected(cfg['hash_evidence']))
    assert not plans and len(linked)==1
    assert any('ambiguous' in f['REASON'] for f in files)


def test_equivalent_copies_are_audited(tmp_path):
    cfg,cp,_,_,root=fixture(tmp_path);copy=tmp_path/'copy';shutil.copytree(root,copy)
    cfg['bids_roots'].append(str(copy));refreshed(cp,cfg);s=b.run(cp)
    assert s['file_observations']==4 and s['preprocessing_ready']==1


def test_conflicting_copy_blocks_other_good_copy(tmp_path):
    cfg,cp,_,_,root=fixture(tmp_path);copy=tmp_path/'copy';shutil.copytree(root,copy)
    f=next(copy.glob('sub-*/ses-*/func/*.json'));m=json.loads(f.read_text());m['SliceTiming']=[1.,1.5,0.,.5];f.write_text(json.dumps(m))
    cfg['bids_roots'].append(str(copy));refreshed(cp,cfg);s=b.run(cp)
    assert s['image_status']['conflict']==1 and s['held_epi']==1


def test_missing_root_retains_all_epi(tmp_path):
    cfg,cp,_,_,_=fixture(tmp_path);cfg['bids_roots']=[str(tmp_path/'offline')];refreshed(cp,cfg)
    s=b.run(cp);assert s['retained_epi']==1 and s['held_epi']==1


def test_source_mutation_after_binding_refused(tmp_path):
    cfg,cp,_,epi,root=fixture(tmp_path);b.run(cp)
    f=next(root.glob('sub-*/ses-*/anat/*.json'));f.write_text('{}')
    with pytest.raises(ValueError,match='changed'):b.verify_plan(Path(cfg['output_dir'])/b.NAMES['receipt'],epi['EPI_KEY'])


def test_output_mutation_refused(tmp_path):
    cfg,cp,_,epi,_=fixture(tmp_path);b.run(cp);p=Path(cfg['output_dir'])/b.NAMES['plans'];p.write_text('[]')
    with pytest.raises(ValueError,match='fingerprint'):b.verify_plan(Path(cfg['output_dir'])/b.NAMES['receipt'],epi['EPI_KEY'])


def test_existing_output_never_overwritten(tmp_path):
    cfg,cp,_,_,_=fixture(tmp_path);b.run(cp);out=Path(cfg['output_dir']);before={p.name:b.sha(p) for p in out.iterdir()}
    with pytest.raises(FileExistsError):b.run(cp)
    assert before=={p.name:b.sha(p) for p in out.iterdir()}


def test_source_registry_change_refused(tmp_path):
    cfg,cp,_,_,_=fixture(tmp_path);Path(cfg['images']).write_text('changed')
    with pytest.raises(ValueError,match='fingerprint'):b.run(cp)


def test_prepare_pending_before_backend_or_mkdir(tmp_path,monkeypatch):
    cfg,cp,_,epi,root=fixture(tmp_path);cfg['bids_roots']=[];refreshed(cp,cfg);b.run(cp)
    monkeypatch.setattr(g,'backend',lambda:pytest.fail('Backend must not be called'))
    target=tmp_path/'isolated'
    with pytest.raises(ValueError,match='pending'):g.prepare(Path(cfg['output_dir'])/b.NAMES['receipt'],epi['EPI_KEY'],target,tmp_path/'none.yaml')
    assert not target.exists()


def prepared(tmp):
    cfg,cp,_,epi,_=fixture(tmp);b.run(cp)
    tf=tmp/'templates';tf.mkdir();template=tmp/'template.yaml'
    template.write_text(yaml.safe_dump({'source_templateflow':str(tf),'resources':{'cpus':1,'omp_nthreads':1,'workflow_memory_mb':1000,'docker_memory':'2g'},
                                      'images':{'mriqc':'example','fmriprep':'example'},'output_spaces':['MNI152NLin6Asym'],'random_seed':1,'freesurfer_license':str(tmp/'license')}))
    path=g.prepare(Path(cfg['output_dir'])/b.NAMES['receipt'],epi['EPI_KEY'],tmp/'isolated',template)
    return path,yaml.safe_load(path.read_text())


def test_prepare_uses_exact_pair_and_real_backend(tmp_path):
    path,cfg=prepared(tmp_path);result=g.dispatch(path,'check')
    assert result['analysis_ready'] is False and cfg['runs'][0]['t1_image_id']=='100'
    paths=g.backend().paths_for(cfg,cfg['runs'][0]);assert len(paths)==4


def test_extra_t1_cannot_enter_anatomical_template(tmp_path):
    path,cfg=prepared(tmp_path);paths=g.backend().paths_for(cfg,cfg['runs'][0])
    shutil.copy2(paths['t1w'],paths['t1w'].with_name('sub-999S9999_ses-20200101_run-2_T1w.nii.gz'))
    with pytest.raises(ValueError,match='Extra'):g.dispatch(path,'check')


def test_runtime_t1_swap_refused_before_dispatch(tmp_path):
    path,cfg=prepared(tmp_path);f=g.backend().paths_for(cfg,cfg['runs'][0])['t1w'];f.write_bytes(b'swapped')
    with pytest.raises(ValueError,match='Runtime BIDS'):g.dispatch(path,'run','fmriprep')


def test_config_t1_change_refused(tmp_path):
    path,cfg=prepared(tmp_path);cfg['runs'][0]['t1_image_id']='999';path.write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError,match='pairing'):g.dispatch(path,'run','fmriprep')
