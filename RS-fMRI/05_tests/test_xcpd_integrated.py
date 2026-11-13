import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('integrated_pipeline', Path(__file__).resolve().parents[1] / '02_custom/s10_xcpd_integrated_qc/pipeline.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

@pytest.fixture
def cfg():
    c = p.load(Path(p.__file__).resolve().parents[2] / '03_config/xcpd_linc.example.json')
    c['_config_id'] = 'test'
    return c

def row():
    return dict(sub='sub-ADNI999S9999', ses='ses-M150', task='task-rest', run='', acq='', dir='', echo='', rec='',
                config_id='test', pipeline_version='1.0.0', mean_fd=0.1, fd_over_0p5_proportion=0.02,
                avg_euler=-20, euler_qc_flag=None, mriqc_exclude_flag=None, mriqc_flag_status='cohort_pending',
                validation_errors='', n_original_volumes=100, tr=3, pre_xcpd_qc_status='review_required')

def test_multi_session_run_and_absent_label():
    names = ['sub-A_ses-1_task-rest_desc-confounds_timeseries.tsv', 'sub-A_ses-2_task-rest_desc-confounds_timeseries.tsv',
             'sub-A_ses-2_task-rest_run-1_desc-confounds_timeseries.tsv', 'sub-A_ses-2_task-rest_run-2_desc-confounds_timeseries.tsv']
    rows = [p.identity(n) for n in names]
    p.unique(rows, 'fixture')
    assert rows[0]['run'] == ''
    assert len({p.run_key(r) for r in rows}) == 4

def test_duplicate_qc_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        p.unique([row(), row()], 'QC')

def test_mixed_pipeline_rows_rejected():
    a=row();b=row();b.update(run='run-2',config_id='other')
    with pytest.raises(ValueError,match='Mixed'):p.unique([a,b],'QC')

def test_hashed_qc_columns(tmp_path):
    f=tmp_path/'qc.tsv';f.write_text('mean_fd_hash-abc123\tmean_dvars_final_hash-abc123\n0.1\t1.2\n')
    assert p.read_xcp_tsv(f).mean_fd.iloc[0]==.1

def test_acquisition_direction_separate():
    a=p.identity('sub-A_ses-1_task-rest_acq-A_dir-AP_desc-preproc_bold.nii.gz')
    b=p.identity('sub-A_ses-1_task-rest_acq-B_dir-AP_desc-preproc_bold.nii.gz')
    assert p.key(a) != p.key(b)

def test_filter_explicit_absent_run(cfg):
    f=p.bids_filter(row(), cfg)['bold']
    assert f['run'] is None and f['acquisition'] is None
    assert f['session'] == 'M150' and f['res'] == '2'
    assert 'subject' not in f

@pytest.mark.parametrize('missing', ['bold', 'confounds'])
def test_discovery_missing_counterpart(tmp_path,cfg,missing):
    folder=tmp_path/'fmriprep/sub-A/ses-1/func';folder.mkdir(parents=True)
    names={'bold':'sub-A_ses-1_task-rest_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz',
           'confounds':'sub-A_ses-1_task-rest_desc-confounds_timeseries.tsv'}
    (folder/names['confounds' if missing=='bold' else 'bold']).touch()
    runs=p.input_runs(tmp_path,cfg)
    assert len(runs)==1 and runs[0][missing]==[]

def test_cohort_missing_is_pending_not_pass(cfg):
    status,candidate,reason=p.decide_pre(row(),cfg)
    assert status=='review_required' and candidate and 'pending' in reason

def test_missing_euler_blocks(cfg):
    r=row();r['avg_euler']=None
    assert p.decide_pre(r,cfg)[:2]==('missing_metrics',False)

def test_missing_flag_in_supplied_cohort_blocks(cfg):
    r=row();r['mriqc_flag_status']='missing_metric'
    assert not p.decide_pre(r,cfg)[1]

@pytest.mark.parametrize('field,value', [('mean_fd',0.501),('fd_over_0p5_proportion',0.301),('mriqc_exclude_flag',1),('euler_qc_flag',1)])
def test_actual_fail_excluded_from_xcpd(cfg,field,value):
    r=row();r[field]=value
    assert p.decide_pre(r,cfg)[:2]==('fail',False)

def test_boundary_not_greater(cfg):
    r=row();r.update(mean_fd=0.5,fd_over_0p5_proportion=0.30)
    assert p.decide_pre(r,cfg)[0]!='fail'

def test_mriqc_unknown_flag_never_zero():
    assert p.strict_flag('NA') is None and p.strict_flag('') is None

def test_mriqc_duplicates(cfg,tmp_path):
    t=tmp_path/'flags.tsv';pd.DataFrame([{'sub':row()['sub'],'ses':row()['ses'],'exclude_mriqc':0}]*2).to_csv(t,sep='\t',index=False)
    cfg['mriqc_flags_file']=str(t)
    with pytest.raises(ValueError,match='Duplicate'):p.get_mriqc_flag(row(),cfg)

def finalrow():
    r=row();r.update(xcpd_status='success',xcpd_qc_status='pass',functional_outputs_valid=True,euler_qc_flag=0,mriqc_exclude_flag=0,
                    visual_review_required=True,visual_qc_status='pending')
    return r

def test_never_finalize_in_watch():
    r=finalrow();r.update(visual_qc_status='pass',reviewer='human',review_date='2026-11-01')
    assert p.decide_final(r)[0]=='pending_review'

def test_pending_manual():
    assert p.decide_final(finalrow(),True)[0]=='pending_review'

def test_manual_fail():
    r=finalrow();r.update(visual_qc_status='fail',visual_qc_reason='registration')
    assert p.decide_final(r,True)==('exclude',False,'visual_qc_failed:registration')

def test_unreviewed_remains_unreviewed():
    r=finalrow();r.update(visual_review_required=False,visual_qc_status='not_reviewed')
    assert p.decide_final(r,True)[0]=='include' and r['visual_qc_status']=='not_reviewed'

def test_missing_final_flag():
    r=finalrow();r.update(mriqc_exclude_flag=None,visual_review_required=False)
    assert p.decide_final(r,True)[0]=='pending_review'

@pytest.mark.parametrize('status',['failed','partial'])
def test_failed_partial_not_success(cfg,tmp_path,status):
    r=finalrow();r['xcpd_status']=status
    assert p.decide_final(r,True)[0]=='processing_failed'
    v=p.validate_outputs(tmp_path,row(),cfg,1 if status=='failed' else 0)
    assert v['xcpd_status']==status and not v['functional_outputs_valid']

def fixture_outputs(tmp_path,cfg,nret=90,low=False):
    r=row();root=tmp_path/'derivatives';folder=root/r['sub']/r['ses']/'func';folder.mkdir(parents=True)
    stem=r['sub']+'_'+r['ses']+'_'+r['task'];sp=stem+'_space-MNI152NLin6Asym'
    p.save(root/'dataset_description.json',{'GeneratedBy':[{'Name':'XCP-D','Version':'26.2.0'}]})
    workflow={'mode':cfg['mode'],'file_format':cfg['file_format'],'combine_runs':False,'fd_thresh':cfg['fd_threshold'],
              'min_time':cfg['min_time'],'bandpass_filter':cfg['bandpass'],'high_pass':cfg['lower_bpf'],'low_pass':cfg['upper_bpf'],
              'bpf_order':cfg['bpf_order'],'smoothing':cfg['smoothing'],'dummy_scans':cfg['dummy_scans'],'despike':cfg['despike'],
              'head_radius':cfg['head_radius'],'censor_between':cfg['censor_between'],'min_coverage':cfg['min_coverage'],
              'linc_qc':cfg['linc_qc'],'abcc_qc':cfg['abcc_qc'],'output_interpolated':False}
    (root/'xcp_d.toml').write_text('[execution]\nconfounds_config="/data/36P.yml"\natlases=["4S256Parcels"]\n[workflow]\n'+'\n'.join(k+' = '+json.dumps(v) for k,v in workflow.items()))
    source=tmp_path/'input.nii.gz';nib.save(nib.Nifti1Image(np.ones((2,2,2,100),dtype='float32'),np.eye(4)),source);r['source_bold_file']=str(source)
    img=nib.Nifti1Image(np.ones((2,2,2,nret),dtype='float32'),np.eye(4))
    nib.save(img,folder/(sp+'_desc-denoised_bold.nii.gz'))
    qc=dict(mean_fd=.1,mean_fd_post_censoring=.08,mean_dvars_initial=2.,mean_dvars_final=1.,num_dummy_volumes=0,
            num_censored_volumes=100-nret,num_retained_volumes=nret,coreg_dice=.9,norm_dice=.9)
    pd.DataFrame([qc]).to_csv(folder/(stem+'_desc-linc_qc.tsv'),sep='\t',index=False)
    pd.DataFrame({'framewise_displacement':[.1]*nret+[.6]*(100-nret)}).to_csv(folder/(stem+'_motion.tsv'),sep='\t',index=False)
    pd.DataFrame({'framewise_displacement':[0]*nret+[1]*(100-nret)}).to_csv(folder/(stem+'_outliers.tsv'),sep='\t',index=False)
    labels=[f'ROI{i}' for i in range(256)]
    data=np.random.default_rng(1).normal(size=(nret,256));coverage=np.ones(256)
    if low:data[:,0:20]=np.nan;coverage[:20]=.1
    ts=pd.DataFrame(data,columns=labels);ats=sp+'_atlas-4S256Parcels'
    ts.to_csv(folder/(ats+'_stat-mean_timeseries.tsv'),sep='\t',index=False)
    ts.corr().to_csv(folder/(ats+'_stat-pearsoncorrelation_relmat.tsv'),sep='\t')
    pd.DataFrame({'coverage':coverage},index=labels).to_csv(folder/(ats+'_stat-coverage_bold.tsv'),sep='\t')
    (root/(r['sub']+'.html')).write_text('<html>report</html>')
    (root/(r['sub']+'_'+r['ses']+'_executive_summary.html')).write_text('<html>executive</html>')
    for metric in ('alff','reho'):nib.save(nib.Nifti1Image(np.ones((2,2,2)),np.eye(4)),folder/(sp+'_stat-'+metric+'_boldmap.nii.gz'))
    return r,folder

def test_valid_output(tmp_path,cfg):
    r,_=fixture_outputs(tmp_path,cfg)
    q=p.validate_outputs(tmp_path,r,cfg,0)
    assert q['xcpd_status']=='success',q
    assert q['remaining_duration_sec']==270 and q['functional_outputs_valid']

def test_duration_short(tmp_path,cfg):
    r,_=fixture_outputs(tmp_path,cfg,nret=70)
    q=p.validate_outputs(tmp_path,r,cfg,0)
    assert q['xcpd_status']=='success' and q['xcpd_qc_status']=='fail'

def test_duration_gate_is_quality_skip_not_fake_success(tmp_path,cfg):
    p.save(tmp_path/'duration_gate.json',{'remaining_duration_sec':210,'fd_threshold':.3,'n_remaining_volumes':70})
    q=p.validate_outputs(tmp_path,row(),cfg,42)
    assert q['xcpd_status']=='skipped_insufficient_time' and q['xcpd_qc_status']=='fail'
    assert not q['functional_outputs_valid']

def test_export_upstream_s8_columns(tmp_path):
    r=row();r.update(site='003',n_original_volumes=100,median_fd=.1,max_fd=.6,n_fd_over_threshold=2,mean_dvars=1.)
    p.write_s8_tables([r],tmp_path)
    assert {'n_volumes','mean_fd_p','prop_fd_p_over_thresh'} <= set(pd.read_csv(tmp_path/'motion_summary.tsv',sep='\t'))
    assert {'fs_subject','lh_en','rh_en','avg_en'} <= set(pd.read_csv(tmp_path/'euler_summary.tsv',sep='\t'))

def test_manual_fields_preserved_and_not_fabricated(tmp_path,cfg):
    cfg.pop('_config_id');cfg['root']=str(tmp_path);cp=tmp_path/'cfg.json';p.save(cp,cfg);app=p.Pipeline(cp)
    pair=tmp_path/'results/999_S_9999/EPI_20190507_MT1_20190507';pair.mkdir(parents=True)
    p.save(pair/'pair_metadata.json',{'subject':'ADNI999S9999'})
    r=row();r.update(config_id=app.config_id,source_pair=str(pair),site='003',scanner_vendor='Siemens',candidate=True)
    sd=app.stage_dir(pair);p.save(sd/'pre_qc.json',{'config_id':app.config_id,'rows':[r]})
    app.aggregate();v=app.hub/'visual_review.tsv';initial=p.table(v)
    assert initial[0]['visual_qc_status']=='not_reviewed'
    summary=p.load(app.hub/'summary.json')
    assert summary['runs']==1 and summary['subjects']==1 and summary['xcpd_attempts_total']==0
    sites=pd.read_csv(app.hub/'site_qc_counts.tsv',sep='\t')
    assert set(sites['stage'])=={'pre_xcpd_qc_status','xcpd_status','final_qc_status'}
    assert (sites.proportion==1).all()
    initial[0].update(visual_qc_status='fail',visual_qc_reason='human observed error',reviewer='reviewer1',review_date='2026-11-01')
    p.tsv(v,initial);app.aggregate();saved=p.table(v)
    assert saved[0]['visual_qc_status']=='fail' and saved[0]['reviewer']=='reviewer1'
    assert p.load(app.hub/'summary.json')['visual_review_completed']==1
    assert list((app.hub/'manual_review_history').glob('*.tsv'))
    saved[0]['visual_review_required']='True';p.tsv(v,saved);app.aggregate()
    assert p.table(v)[0]['review_reason']=='previously_selected_for_review'

def test_finalization_detects_missing_real_outputs(tmp_path,cfg):
    cfg.pop('_config_id');cfg['root']=str(tmp_path);cp=tmp_path/'cfg.json';p.save(cp,cfg);app=p.Pipeline(cp)
    attempt=tmp_path/'attempt';attempt.mkdir()
    p.save(attempt/'execution.json',{'config_id':app.config_id,'exit_code':0,'input_unchanged':True})
    p.save(attempt/'output_manifest.json',{'missing.nii.gz':'abc'})
    with pytest.raises(ValueError,match='missing or changed'):
        app.verify_final_output_files({'xcpd_status':'success','xcpd_attempt':str(attempt)})

def test_roi_coverage_warning_not_invented_exclusion(tmp_path,cfg):
    r,_=fixture_outputs(tmp_path,cfg,low=True)
    q=p.validate_outputs(tmp_path,r,cfg,0)
    assert q['xcpd_status']=='success' and q['xcpd_qc_status']=='review_required',q

def test_corrupt_censor_counts(tmp_path,cfg):
    r,folder=fixture_outputs(tmp_path,cfg)
    f=next(folder.glob('*outliers.tsv'));pd.DataFrame({'framewise_displacement':[0]*100}).to_csv(f,sep='\t',index=False)
    assert p.validate_outputs(tmp_path,r,cfg,0)['xcpd_status']=='partial'

def test_actual_denoising_mask_can_include_nonmotion_censoring(tmp_path,cfg):
    r,folder=fixture_outputs(tmp_path,cfg)
    f=next(folder.glob('*outliers.tsv'))
    pd.DataFrame({'framewise_displacement':[0]*91+[1]*9,'denoising':[0]*90+[1]*10}).to_csv(f,sep='\t',index=False)
    assert p.validate_outputs(tmp_path,r,cfg,0)['xcpd_status']=='success'

def test_denoising_mask_must_include_all_motion_outliers(tmp_path,cfg):
    r,folder=fixture_outputs(tmp_path,cfg)
    f=next(folder.glob('*outliers.tsv'))
    pd.DataFrame({'framewise_displacement':[0]*89+[1]*11,'denoising':[0]*90+[1]*10}).to_csv(f,sep='\t',index=False)
    assert p.validate_outputs(tmp_path,r,cfg,0)['xcpd_status']=='partial'

def test_actual_settings_must_match_requested(tmp_path,cfg):
    r,_=fixture_outputs(tmp_path,cfg)
    t=tmp_path/'derivatives/xcp_d.toml';t.write_text(t.read_text().replace('fd_thresh = 0.3','fd_thresh = 0.5'))
    q=p.validate_outputs(tmp_path,r,cfg,0)
    assert q['xcpd_status']=='partial' and 'option differs' in q['xcpd_errors'][0]

def test_roi_label_mismatch(tmp_path,cfg):
    r,folder=fixture_outputs(tmp_path,cfg)
    f=next(folder.glob('*relmat.tsv'));d=pd.read_csv(f,sep='\t',index_col=0);d=d.iloc[::-1];d.to_csv(f,sep='\t')
    assert p.validate_outputs(tmp_path,r,cfg,0)['xcpd_status']=='partial'

def test_pipeline_run_isolation(tmp_path,cfg):
    cfg.pop('_config_id');cfg['root']=str(tmp_path);path=tmp_path/'cfg.json';p.save(path,cfg)
    a=p.Pipeline(path)
    cfg['fd_threshold']=.2;p.save(path,cfg)
    b=p.Pipeline(path)
    assert a.config_id!=b.config_id

def test_readonly_input_mount(cfg,tmp_path):
    r=row();r['source_pair']=str(tmp_path)
    cfg['root']=str(tmp_path)
    cmd=p.command(cfg,r,tmp_path/'job','fixture')
    assert str(tmp_path/'fmriprep')+':/input:ro' in cmd
    assert '--notrack' in cmd and '--combine-runs' in cmd and cmd[cmd.index('--combine-runs')+1]=='n'

def test_xcpd_does_not_consume_s6_s7_slots(tmp_path,cfg):
    cfg.pop('_config_id');cfg['root']=str(tmp_path);cp=tmp_path/'cfg.json';p.save(cp,cfg);app=p.Pipeline(cp)
    r=row();r['source_pair']=str(tmp_path/'pair')
    _,name=app.plan_attempt(r)
    assert name.startswith('adni-xcpd-') and not name.startswith('statmind-')

def test_reconnect_running_container_without_relaunch(tmp_path,cfg,monkeypatch):
    cfg.pop('_config_id');cfg['root']=str(tmp_path);cp=tmp_path/'cfg.json';p.save(cp,cfg);app=p.Pipeline(cp)
    attempt=tmp_path/'attempt';(attempt/'derivatives').mkdir(parents=True);(attempt/'derivatives/file.txt').write_text('validated')
    r=row();r.update(config_id=app.config_id,input_files={})
    record={'status':'running','config_id':app.config_id,'container':'fixture','row':r}
    monkeypatch.setattr(app,'latest',lambda _: (attempt,record))
    calls=[]
    info={'Config':{'Labels':{'adni.config_id':app.config_id,'adni.run_key':p.run_key(r)}},'State':{'Status':'running'}}
    fail_once=[True]
    def run(cmd,**kwargs):
        calls.append(cmd)
        if cmd[1]=='inspect':return SimpleNamespace(returncode=0,stdout=json.dumps([info]))
        if cmd[1]=='logs':return SimpleNamespace(returncode=0,stdout='')
        raise AssertionError('Unexpected Docker relaunch: '+str(cmd))
    def wait(name,r):
        if fail_once[0]:fail_once[0]=False;raise RuntimeError('reattach')
        return 0
    monkeypatch.setattr(p.subprocess,'run',run)
    monkeypatch.setattr(app,'wait_container',wait)
    monkeypatch.setattr(p,'validate_outputs',lambda *args:{'xcpd_status':'success','functional_outputs_valid':True,'xcpd_errors':[]})
    with pytest.raises(RuntimeError,match='reattach'):app.run_one(r)
    assert p.load(attempt/'execution.json')['status']=='running'
    app.run_one(r)
    assert p.load(attempt/'execution.json')['status']=='success'
    assert (app.hub/'pilot_success.json').exists()
    assert not any(c[1] in ('create','start','run') for c in calls)

def test_s8_harvest_continues_while_xcpd_runs(tmp_path,cfg,monkeypatch):
    cfg.pop('_config_id');cfg['root']=str(tmp_path);cp=tmp_path/'cfg.json';p.save(cp,cfg);app=p.Pipeline(cp)
    pair=tmp_path/'pair';pair.mkdir();seen=[]
    monkeypatch.setattr(app,'pairs',lambda:[pair])
    monkeypatch.setattr(app,'prepare',lambda item:seen.append(item))
    monkeypatch.setattr(app,'aggregate',lambda:seen.append('aggregated'))
    monkeypatch.setattr(p.time,'sleep',lambda _:None)
    polls=iter([None,0])
    fake=SimpleNamespace(poll=lambda:next(polls),communicate=lambda:('0\n',''),returncode=0)
    monkeypatch.setattr(p.subprocess,'Popen',lambda *a,**k:fake)
    monkeypatch.setattr(app,'detect_terminal_worker_failure',lambda name,row:seen.append('monitored'))
    assert app.wait_container('fixture',row())==0
    assert seen==['monitored',pair,'aggregated']
