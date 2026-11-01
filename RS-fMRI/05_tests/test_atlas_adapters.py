"""Original acquisition gaps and raw UID-backed run evidence must survive extraction."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import nibabel as nb
import numpy as np
import pytest
from test_atlas_bold import a, fixture, save

STEP = Path(__file__).resolve().parents[1] / '02_custom/s11_atlas_bold'
spec = importlib.util.spec_from_file_location('atlas_adapters', STEP / 'adapters.py')
ad = importlib.util.module_from_spec(spec); spec.loader.exec_module(ad)


def evidence(tmp_path, status='pending'):
    old, mask, catalog = fixture(tmp_path)
    func = tmp_path/'derivatives/sub-ADNI999S9999/ses-M000/func';func.mkdir(parents=True)
    bold = func/old.name;shutil.copyfile(old,bold)
    rawdir=tmp_path/'bids/sub-ADNI999S9999/ses-M000/func';rawdir.mkdir(parents=True)
    raw=rawdir/'sub-ADNI999S9999_ses-M000_task-rest_run-1_bold.nii.gz'
    save(raw,np.ones((4,4,4,6),dtype=np.float32))
    rj=raw.with_name(raw.name.replace('.nii.gz','.json'));rj.write_text(json.dumps({'RepetitionTime':2,'SeriesInstanceUID':'1.2.3.999','AcquisitionDateTime':'2020-01-02T10:00:00'}))
    bj=bold.with_name(bold.name.replace('.nii.gz','.json'))
    pre=func/bold.name.replace('desc-denoised','desc-preproc').replace('.nii.gz','.json')
    pre.write_text(json.dumps({'Sources':['bids:raw:'+'/'.join(raw.parts[-4:])]}))
    bj.write_text(json.dumps({'RepetitionTime':2,'Sources':['bids:preprocessed:'+'/'.join(pre.with_suffix('.nii.gz').parts[-4:])]}))
    outliers=func/'sub-ADNI999S9999_ses-M000_task-rest_run-1_outliers.tsv';outliers.write_text('denoising\n0\n0\n1\n0\n0\n')
    meta=json.loads(bj.read_text());meta['Sources'].append('bids::'+'/'.join(outliers.parts[-4:]));bj.write_text(json.dumps(meta))
    inc=tmp_path/'inclusion';inc.mkdir()
    a.write(inc/'inclusion_audit.tsv',[{'IMAGE_ID':'101','INCLUSION_STATUS':status,'SOURCE_MODALITY':'EPI','PTID':'999_S_9999','sub':'sub-ADNI999S9999','ses':'ses-auditI101','INPUT_SCOPE':'metadata_audit_not_step8_or_BIDS','MRI_STUDY_DATE':'2020-01-02','SERIES_UID':'1.2.3.999'}])
    a.finish(inc,'final_inclusion_validation_v1',{}, {})
    return bold,mask,catalog,raw,rj,bj,pre,outliers,inc


def test_compressed_frame_adapter_preserves_raw_gaps_and_pending_run(tmp_path):
    b,m,c,raw,rj,bj,pre,o,inc=evidence(tmp_path)
    ad.timing(raw,rj,b,bj,o,1,tmp_path/'mapping')
    rec=ad.link_run(inc,'101',raw,rj,b,bj,pre,tmp_path/'link')
    assert rec['summary']['inclusion_status']=='pending'
    out=a.process(b,m,'test','MNI152NLin6Asym','denoised',tmp_path/'out',c,bj,
                  inclusion=inc,image_id='101',frame_map=tmp_path/'mapping',run_link=tmp_path/'link')
    frames=a.read(tmp_path/'out/frames.tsv')
    assert [int(r['raw_frame_index_zero_based']) for r in frames]==[1,2,4,5]
    assert [float(r['raw_nominal_time_seconds']) for r in frames]==[2,4,8,10]
    assert frames[2]['raw_interval_from_previous_seconds']=='4.0'
    assert out['summary']['inclusion_status']=='pending' and not out['analysis_ready']
    assert out['summary']['time_axis_status']=='original_acquisition_mapped'


@pytest.mark.parametrize('problem',['dummy','length','flag','tr','subject'])
def test_invalid_frame_contract_rejected(tmp_path,problem):
    b,m,c,raw,rj,bj,pre,o,inc=evidence(tmp_path)
    dummy=1
    if problem=='dummy':dummy=0
    if problem=='length':o.write_text('denoising\n0\n0\n1\n1\n0\n')
    if problem=='flag':o.write_text('denoising\n0\n0\ntrue\n0\n0\n')
    if problem=='tr':rj.write_text(json.dumps({'RepetitionTime':3}))
    if problem=='subject':
        other=raw.with_name(raw.name.replace('999S9999','998S9999'));shutil.copy(raw,other);raw=other
    with pytest.raises(ValueError):ad.timing(raw,rj,b,bj,o,dummy,tmp_path/'map')


@pytest.mark.parametrize('problem',['uid','date','source','excluded','hold','run'])
def test_invalid_link_never_promotes_inclusion(tmp_path,problem):
    b,m,c,raw,rj,bj,pre,o,inc=evidence(tmp_path,status=problem if problem in ['excluded','hold'] else 'pending')
    if problem in ['uid','date']:
        d=json.loads(rj.read_text());d['SeriesInstanceUID' if problem=='uid' else 'AcquisitionDateTime']='1.2.3.998' if problem=='uid' else '2020-01-03T10:00:00';rj.write_text(json.dumps(d))
    if problem=='source':pre.write_text('{"Sources":[]}')
    if problem=='run':
        new=b.with_name(b.name.replace('run-1','run-2'));shutil.copyfile(b,new);b=new
    with pytest.raises(ValueError):ad.link_run(inc,'101',raw,rj,b,bj,pre,tmp_path/'link')


def test_link_and_frame_map_cannot_be_reused_for_other_payload(tmp_path):
    b,m,c,raw,rj,bj,pre,o,inc=evidence(tmp_path)
    ad.timing(raw,rj,b,bj,o,1,tmp_path/'map');ad.link_run(inc,'101',raw,rj,b,bj,pre,tmp_path/'link')
    with pytest.raises(ValueError,match='not bound'):ad.validated_frame_map(tmp_path/'map','0'*64,4,2,b)
    with pytest.raises(ValueError,match='another image'):ad.validated_run_link(tmp_path/'link',inc,'101',b,'0'*64)
    with pytest.raises(ValueError,match='another BIDS'):ad.validated_frame_map(tmp_path/'map',a.sha(b),4,2,b.with_name(b.name.replace('run-1','run-2')))


def test_coverage_diagnostics_describe_signal_loss_without_rescue(tmp_path):
    from diagnose_coverage import diagnose
    b,m,c=fixture(tmp_path)
    brain=np.ones((4,4,4),dtype=np.uint8);brain[2:,:3]=0
    mask=tmp_path/b.name.replace('desc-denoised_bold','desc-brain_mask');save(mask,brain)
    a.process(b,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'extract',c)
    ref=tmp_path/b.name.replace('desc-denoised_bold','boldref');save(ref,np.where(brain,10.,1.).astype(np.float32))
    t1=tmp_path/b.name.replace('desc-denoised_bold','desc-preproc_T1w');save(t1,np.ones((4,4,4),dtype=np.float32))
    gm=tmp_path/b.name.replace('desc-denoised_bold','label-GM_probseg');save(gm,np.full((4,4,4),.8,dtype=np.float32))
    am=tmp_path/b.name.replace('desc-denoised_bold','desc-anatomical_mask');save(am,np.ones((4,4,4),dtype=np.uint8))
    rec=diagnose(tmp_path/'extract',mask,ref,t1,gm,am,tmp_path/'diagnosis')
    rows=a.read(tmp_path/'diagnosis/coverage_diagnostics.tsv')
    assert float(rows[1]['excluded_to_included_reference_ratio'])==.1
    assert rows[1]['qc_status']=='fail'
    assert rec['summary']['qc_policy_changed'] is False and rec['summary']['causality_established'] is False


def test_other_run_outlier_ledger_and_ambiguous_sources_rejected(tmp_path):
    b,m,c,raw,rj,bj,pre,o,inc=evidence(tmp_path)
    other=o.with_name(o.name.replace('run-1','run-2'));shutil.copyfile(o,other)
    with pytest.raises(ValueError,match='entities differ'):ad.timing(raw,rj,b,bj,other,1,tmp_path/'bad-map')
    meta=json.loads(pre.read_text());meta['Sources'].append(meta['Sources'][0].replace('run-1','run-2'));pre.write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='ambiguous'):ad.link_run(inc,'101',raw,rj,b,bj,pre,tmp_path/'bad-link')
