import importlib.util,json,sys
from pathlib import Path
import pandas as pd
import pytest
spec=importlib.util.spec_from_file_location('metrics_export',Path(__file__).resolve().parents[1]/'pipeline/s12_metrics_summary/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture(tmp):
 p=tmp/'example';p.mkdir();(p/'relocation_receipt.json').write_text(json.dumps({'status':'archived_and_local_space_reclaimed'}))
 meta={'ptid':'999_S_9999','subject':'ADNI999S9999','pair_id':'EPI_20000101_MT1_20000102','epi_date':'2000-01-01','mt1_date':'2000-01-02','epi_image_id':'100','mt1_image_id':'200'}
 (p/'pair_metadata.json').write_text(json.dumps(meta));stem='sub-ADNI999S9999_ses-M000'
 stats=p/'fmriprep/sourcedata/freesurfer'/stem/'stats';stats.mkdir(parents=True)
 (stats/'aseg.stats').write_text('# Measure EstimatedTotalIntraCranialVol, eTIV, description, 1500000, mm^3\n# ColHeaders Index SegId NVoxels Volume_mm3 StructName\n1 17 100 123.4 Left-Hippocampus\n2 53 110 145.6 Right-Hippocampus\n')
 for h in ['lh','rh']:(stats/(h+'.aparc.stats')).write_text('# Measure Cortex, MeanThickness, description, 2.4, mm\n# ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd\nsuperiorfrontal 100 200 300 2.1 0.2\n')
 stage=p/'s10/cfg';stage.mkdir(parents=True)
 row=dict(sub='sub-ADNI999S9999',ses='ses-M000',task='task-rest',run='',acq='',dir='',echo='',rec='',config_id='cfg',pre_xcpd_qc_status='review_required',mean_fd=.1)
 (stage/'pre_qc.json').write_text(json.dumps({'rows':[row]}));a=stage/'runs/key/attempt-001';a.mkdir(parents=True)
 (a/'execution.json').write_text(json.dumps({'status':'success','row':row}));(a/'output_validation.json').write_text(json.dumps({'functional_outputs_valid':True,'xcpd_warnings':['coverage_review']}))
 deriv=a/'derivatives';func=deriv/'sub-ADNI999S9999/ses-M000/func';func.mkdir(parents=True)
 for metric in ['reho','alff']:pd.DataFrame([{'ROI_A':.2,'ROI_B':float('nan')}]).to_csv(func/(stem+'_task-rest_space-MNI_atlas-test_stat-'+metric+'_bold.tsv'),sep='\t',index=False)
 pd.DataFrame({'coverage':[1.,.1]},index=['ROI_A','ROI_B']).to_csv(func/(stem+'_task-rest_space-MNI_atlas-test_stat-coverage_bold.tsv'),sep='\t')
 (deriv/'sub-ADNI999S9999.html').write_text('<html>report</html>')
 return p,a

def test_one_row_values_and_reports(tmp_path):
 p,a=fixture(tmp_path);assert m.export_pair(p)=='exported'
 f=pd.read_csv(p/'results/metrics.csv');assert len(f)==1
 assert f['fs__aseg__Left-Hippocampus__Volume_mm3'][0]==123.4
 assert f['fs__lh_aparc__superiorfrontal__ThickAvg'][0]==2.1
 assert f['xcpd__MNI__test__reho__ROI_A'][0]==.2
 assert pd.isna(f['xcpd__MNI__test__reho__ROI_B'][0])
 assert 'XCP-D participant report' in (p/'results/index.html').read_text()
 assert m.export_pair(p)=='already_exported'

def test_edited_results_preserved(tmp_path):
 p,a=fixture(tmp_path);m.export_pair(p);(p/'results/metrics.csv').write_text('edited')
 with pytest.raises(ValueError,match='preserving edits'):m.export_pair(p)
 assert (p/'results/metrics.csv').read_text()=='edited'

def test_unverified_archives_wait(tmp_path):
 assert m.export_pair(tmp_path)=='waiting_for_verified_archive'

def test_invalid_success_blocked(tmp_path):
 p,a=fixture(tmp_path);(a/'output_validation.json').write_text('{"functional_outputs_valid":false}')
 with pytest.raises(ValueError,match='Unvalidated'):m.export_pair(p)

def test_foreign_subject_never_joined(tmp_path):
 p,a=fixture(tmp_path);pre=p/'s10/cfg/pre_qc.json';d=json.loads(pre.read_text());d['rows'][0]['sub']='sub-OTHER';pre.write_text(json.dumps(d))
 with pytest.raises(ValueError,match='identity mismatch'):m.export_pair(p)

def test_nonfinite_freesurfer_is_missing(tmp_path):
 p,a=fixture(tmp_path);f=next(p.glob('fmriprep/sourcedata/freesurfer/*/stats/aseg.stats'));f.write_text(f.read_text().replace('123.4','nan'))
 m.export_pair(p);table=pd.read_csv(p/'results/metrics.csv');assert pd.isna(table['fs__aseg__Left-Hippocampus__Volume_mm3'][0])


def test_integrated_export_results_cli(tmp_path):
 import subprocess
 pair,_=fixture(tmp_path)
 archive=tmp_path/'external archive';target=archive/'999_S_9999'/'EPI_20000101_MT1_20000102';target.parent.mkdir(parents=True)
 pair.rename(target);status=tmp_path/'runtime'/'metrics.json'
 lab=Path(__file__).resolve().parents[1]/'04_workflow/lab.py'
 child=subprocess.run([sys.executable,str(lab),'export-results','--archive-root',str(archive),'--status',str(status)],capture_output=True,text=True)
 assert child.returncode==0,child.stdout+child.stderr
 assert json.loads(status.read_text())['pairs'][str(target)]=='exported'
 assert len(pd.read_csv(target/'results/metrics.csv'))==1
 assert (target/'results/index.html').is_file()
 repeated=subprocess.run([sys.executable,str(lab),'export-results','--archive-root',str(archive),'--status',str(status)],capture_output=True,text=True)
 assert repeated.returncode==0,repeated.stderr
 assert json.loads(status.read_text())['pairs'][str(target)]=='already_exported'
