"""Synthetic volumes establish signal values, space restrictions and missing-ROI behavior."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import nibabel as nb
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / 'pipeline/s11_atlas_bold'
spec = importlib.util.spec_from_file_location('atlas_bold_step', STEP / 'run.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)


def save(path, data, affine=None):
    im = nb.Nifti1Image(np.asarray(data), np.eye(4) if affine is None else affine)
    im.header.set_xyzt_units('mm', 'sec')
    if len(im.shape) == 4: im.header.set_zooms((1, 1, 1, 2))
    nb.save(im, path); return path


def fixture(tmp_path):
    atlas = np.zeros((4, 4, 4), dtype=np.int16); atlas[:2] = 1; atlas[2:] = 3
    signal = np.zeros((4, 4, 4, 4), dtype=np.float32)
    for t in range(4): signal[..., t] = np.where(atlas == 1, t + 1, (t + 1) * 10)
    bold = save(tmp_path / 'sub-ADNI999S9999_ses-M000_task-rest_run-1_space-MNI152NLin6Asym_desc-denoised_bold.nii.gz', signal)
    mask = save(tmp_path / 'mask.nii.gz', np.ones((4, 4, 4), dtype=np.uint8))
    labels = save(tmp_path / 'atlas.nii.gz', atlas)
    entry = {'id': 'test', 'source': 'external', 'citation': 'Synthetic test fixture', 'path': labels.name,
             'space': 'MNI152NLin6Asym', 'kind': 'labels', 'background': 0, 'sha256': a.sha(labels),
             'expected_labels': {'ids': [1, 3]}, 'label_format': 'numeric', 'source_warnings': []}
    catalog = tmp_path / 'catalog.json'; catalog.write_text(json.dumps({'kind': 'discrete_label_catalog', 'atlases': [entry]}))
    return bold, mask, catalog


def run(tmp_path, **kwargs):
    bold, mask, catalog = fixture(tmp_path)
    return a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog=catalog, **kwargs)


def refresh_catalog(catalog, image):
    value = json.loads(catalog.read_text()); value['atlases'][0]['sha256'] = a.sha(image); catalog.write_text(json.dumps(value))


def test_exact_roi_means_and_frame_times(tmp_path):
    record = run(tmp_path)
    matrix = np.loadtxt(tmp_path / 'out/timeseries.tsv', skiprows=1)
    np.testing.assert_allclose(matrix, [[1, 10], [2, 20], [3, 30], [4, 40]])
    assert record['summary']['status'] == 'extracted_qc_pass'
    assert record['summary']['maximum_loaded_bold_frames'] == 1
    assert record['analysis_ready'] is False
    assert [r['input_frame_time_seconds'] for r in a.read(tmp_path / 'out/frames.tsv')] == ['0.0', '2.0', '4.0', '6.0']
    assert [r['label_id'] for r in a.read(tmp_path / 'out/labels.tsv')] == ['1', '3']


def test_zscore_is_explicit(tmp_path):
    run(tmp_path, standardize='zscore')
    matrix = np.loadtxt(tmp_path / 'out/timeseries.tsv', skiprows=1)
    np.testing.assert_allclose(matrix.mean(0), 0, atol=1e-10)
    np.testing.assert_allclose(matrix.std(0, ddof=1), 1)


def test_missing_roi_remains_a_nan_column_with_failed_qc(tmp_path):
    bold, mask, catalog = fixture(tmp_path)
    data = np.ones((4, 4, 4), dtype=np.uint8); data[2:] = 0; save(mask, data)
    rec = a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog)
    matrix = np.loadtxt(tmp_path / 'out/timeseries.tsv', skiprows=1)
    assert matrix.shape == (4, 2) and np.isnan(matrix[:, 1]).all()
    assert rec['summary']['status'] == 'failed_qc'
    assert a.read(tmp_path / 'out/roi_coverage.tsv')[1]['mask_coverage'] == '0.0'


def test_partial_roi_coverage_is_audited(tmp_path):
    bold, mask, catalog = fixture(tmp_path)
    data = np.ones((4, 4, 4), dtype=np.uint8); data[2:, :3] = 0; save(mask, data)
    rec = a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog)
    assert rec['summary']['status'] == 'failed_qc'
    assert 'low_mask_coverage' in a.read(tmp_path / 'out/roi_coverage.tsv')[1]['qc_reasons']


def test_different_mni_spaces_are_never_resampled_as_registration(tmp_path):
    bold, mask, catalog = fixture(tmp_path)
    with pytest.raises(ValueError, match='spaces must match'):
        a.process(bold, mask, 'test', 'MNI152NLin2009cAsym', 'denoised', tmp_path / 'out', catalog, resample_labels=True)
    assert not (tmp_path / 'out').exists()


def test_filename_space_conflict_rejected(tmp_path):
    bold, mask, catalog = fixture(tmp_path)
    entry = json.loads(catalog.read_text()); entry['atlases'][0]['space'] = 'MNI152NLin2009cAsym'; catalog.write_text(json.dumps(entry))
    with pytest.raises(ValueError, match='filename space'):
        a.process(bold, mask, 'test', 'MNI152NLin2009cAsym', 'denoised', tmp_path / 'out', catalog)


def test_grid_resampling_is_explicit_and_nearest_neighbor(tmp_path):
    bold, mask, catalog = fixture(tmp_path)
    labels = tmp_path / 'atlas.nii.gz'
    data = np.ones((2, 2, 2), dtype=np.int16); data[1] = 3
    save(labels, data, np.diag([2., 2., 2., 1.])); refresh_catalog(catalog, labels)
    with pytest.raises(ValueError, match='explicitly request'):
        a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'no', catalog)
    rec = a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'yes', catalog, resample_labels=True)
    assert rec['summary']['resampled_atlas']
    assert set(np.unique(nb.load(tmp_path / 'yes/atlas_on_bold_grid.nii.gz').get_fdata())) <= {0, 1, 3}


def test_resampling_loss_is_preserved_and_failed(tmp_path):
    bold, mask, catalog = fixture(tmp_path)
    labels = tmp_path / 'atlas.nii.gz'; data = np.ones((4, 4, 4), dtype=np.int16); data[3] = 3
    affine = np.eye(4); affine[0, 3] = 10; save(labels, data, affine); refresh_catalog(catalog, labels)
    rec = a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog, resample_labels=True)
    assert rec['summary']['status'] == 'failed_qc'
    assert all('lost_on_bold_grid' in r['qc_reasons'] for r in a.read(tmp_path / 'out/roi_coverage.tsv'))


def test_nonfinite_input_is_not_silently_averaged_out(tmp_path):
    bold, mask, catalog = fixture(tmp_path); data = nb.load(bold).get_fdata().astype(np.float32); data[0, 0, 0, 1] = np.nan; save(bold, data)
    rec = a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog)
    ts = np.loadtxt(tmp_path / 'out/timeseries.tsv', skiprows=1)
    assert np.isnan(ts[1, 0]) and np.isfinite(ts[:, 1]).all()
    assert rec['summary']['status'] == 'failed_qc'


def test_sample_mask_preserves_input_frame_indices(tmp_path):
    bold, mask, catalog = fixture(tmp_path); temporal = tmp_path / 'temporal.tsv'
    temporal.write_text('original_frame_index_zero_based\tretain_FD_and_nonsteady\n0\tFalse\n1\tTrue\n2\tFalse\n3\tTrue\n')
    a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog, sample_mask=temporal)
    np.testing.assert_allclose(np.loadtxt(tmp_path / 'out/timeseries.tsv', skiprows=1), [[2, 20], [4, 40]])
    assert [r['input_frame_index_zero_based'] for r in a.read(tmp_path / 'out/frames.tsv')] == ['1', '3']


@pytest.mark.parametrize('rows', ['0\ttrue\n1\ttrue\n', '0\ttrue\n1\ttrue\n3\ttrue\n2\ttrue\n'])
def test_temporal_mask_must_match_entire_input(tmp_path, rows):
    bold, mask, catalog = fixture(tmp_path); temporal = tmp_path / 'temporal.tsv'; temporal.write_text('frame_index\tkeep\n' + rows)
    with pytest.raises(ValueError, match='enumerate every'):
        a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog, sample_mask=temporal)


def test_tr_units_and_sidecar_mismatch(tmp_path):
    bold, mask, catalog = fixture(tmp_path); sidecar = tmp_path / 'bold.json'; sidecar.write_text('{"RepetitionTime":3}')
    with pytest.raises(ValueError, match='TR disagree'):
        a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog, bold_json=sidecar)
    im = nb.load(bold); data = im.get_fdata().astype(np.float32); im = nb.Nifti1Image(data, im.affine); im.header.set_xyzt_units('mm','msec');im.header.set_zooms((1,1,1,2000));nb.save(im,bold)
    rec = a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog)
    assert rec['summary']['tr_seconds'] == 2


@pytest.mark.parametrize('problem', ['changed', 'probability', 'unknown_labels'])
def test_invalid_or_changed_atlas_rejected(tmp_path, problem):
    bold, mask, catalog = fixture(tmp_path); p = tmp_path / 'atlas.nii.gz'
    if problem == 'changed': p.write_bytes(p.read_bytes() + b'changed')
    else:
        data = nb.load(p).get_fdata().astype(np.float32); data[0,0,0] = .5 if problem == 'probability' else 7; save(p,data);refresh_catalog(catalog,p)
    with pytest.raises(ValueError): a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog)


def test_memory_cap_and_overwrite_protection(tmp_path):
    bold, mask, catalog = fixture(tmp_path)
    with pytest.raises(ValueError, match='memory cap'):
        a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'small', catalog, max_workspace_mb=.0001)
    a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog)
    with pytest.raises(ValueError, match='new output'):
        a.process(bold, mask, 'test', 'MNI152NLin6Asym', 'denoised', tmp_path / 'out', catalog)


def test_failed_cli_writes_audit_and_nonzero_status(tmp_path):
    bold, mask, catalog = fixture(tmp_path); save(mask, np.zeros((4,4,4),dtype=np.uint8))
    command=[sys.executable,str(STEP/'run.py'),'extract','--bold',str(bold),'--mask',str(mask),'--atlas','test','--space','MNI152NLin6Asym','--input-kind','denoised','--catalog',str(catalog),'--output-dir',str(tmp_path/'out')]
    rec=subprocess.run(command,capture_output=True,text=True)
    assert rec.returncode==2 and (tmp_path/'out/artifact.json').is_file()


def test_pinned_catalog_and_source_declarations():
    import configparser
    catalog=json.loads((STEP/'catalog.json').read_text()); lock=json.loads((STEP/'sources.lock.json').read_text())['sources']; modules=configparser.ConfigParser();modules.read(ROOT.parent/'.gitmodules')
    assert len(catalog['atlases'])==252
    assert len({e['id'] for e in catalog['atlases']})==252
    assert set(lock)=={'neuroparc','CBIG','nilearn','templateflow'}
    for name,s in lock.items():
        assert modules['submodule "'+s['submodule']+'"']['url']==s['url']
        assert len(s['commit'])==40
    for e in catalog['atlases']:
        assert e['kind']=='labels' and len(e['sha256'])==64
        assert len(a.expected_ids(e))==e['expected_regions']
        assert not Path(e['path']).is_absolute()


@pytest.mark.parametrize('status,allowed', [('eligible', True), ('pending', True), ('excluded', False), ('hold', False)])
def test_final_inclusion_gate_is_honored(tmp_path, status, allowed):
    bold, mask, catalog = fixture(tmp_path)
    inc=tmp_path/'inclusion';inc.mkdir()
    a.write(inc/'inclusion_audit.tsv',[{'IMAGE_ID':'101','INCLUSION_STATUS':status,'SOURCE_MODALITY':'EPI','sub':'sub-ADNI999S9999','ses':'ses-M000','task':'rest','run':'1'}])
    a.finish(inc,'final_inclusion_validation_v1',{}, {})
    if allowed:
        r=a.process(bold,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'out',catalog,inclusion=inc,image_id='101')
        assert r['summary']['inclusion_status']==status
    else:
        with pytest.raises(ValueError,match='not uniquely retained'):
            a.process(bold,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'out',catalog,inclusion=inc,image_id='101')


def test_retained_image_does_not_validate_another_bids_run(tmp_path):
    bold,mask,catalog=fixture(tmp_path);inc=tmp_path/'inclusion';inc.mkdir()
    a.write(inc/'inclusion_audit.tsv',[{'IMAGE_ID':'101','INCLUSION_STATUS':'eligible','SOURCE_MODALITY':'EPI','sub':'sub-ADNI999S9999','ses':'ses-auditI101','task':'rest','run':'1'}])
    a.finish(inc,'final_inclusion_validation_v1',{}, {})
    with pytest.raises(ValueError,match='identity differs'):
        a.process(bold,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'out',catalog,inclusion=inc,image_id='101')


def test_source_count_mismatch_is_never_claimed_as_qc_pass(tmp_path):
    bold,mask,catalog=fixture(tmp_path);m=json.loads(catalog.read_text());m['atlases'][0]['declared_regions']=4;catalog.write_text(json.dumps(m))
    r=a.process(bold,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'out',catalog)
    assert r['summary']['source_declared_count_discrepancy'] and r['summary']['status']=='failed_qc'


def test_constant_roi_signal_is_a_qc_failure(tmp_path):
    bold,mask,catalog=fixture(tmp_path);data=nb.load(bold).get_fdata().astype(np.float32);data[:2]=1;save(bold,data)
    r=a.process(bold,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'out',catalog)
    assert r['summary']['status']=='failed_qc'
    assert 'undefined_or_constant_signal' in a.read(tmp_path/'out/roi_coverage.tsv')[0]['qc_reasons']


def test_means_agree_with_nilearn_reference(tmp_path):
    from nilearn.maskers import NiftiLabelsMasker
    bold,mask,catalog=fixture(tmp_path)
    a.process(bold,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'out',catalog)
    reference=NiftiLabelsMasker(labels_img=tmp_path/'atlas.nii.gz',mask_img=mask,resampling_target=None,standardize=False,reports=False).fit_transform(bold)
    np.testing.assert_allclose(np.loadtxt(tmp_path/'out/timeseries.tsv',skiprows=1),reference)


def test_partial_field_of_view_cannot_hide_behind_full_mask_coverage(tmp_path):
    bold,mask,catalog=fixture(tmp_path);atlas=tmp_path/'atlas.nii.gz'
    data=nb.load(atlas).get_fdata().astype(np.int16);affine=np.eye(4);affine[0,3]=1
    save(atlas,data,affine);refresh_catalog(catalog,atlas)
    r=a.process(bold,mask,'test','MNI152NLin6Asym','denoised',tmp_path/'out',catalog,resample_labels=True,min_coverage=.75)
    coverage=a.read(tmp_path/'out/roi_coverage.tsv')[1]
    assert float(coverage['mask_coverage'])==1
    assert float(coverage['masked_source_volume_fraction'])==.5
    assert 'low_source_volume_coverage' in coverage['qc_reasons']
    assert r['summary']['status']=='failed_qc'
    assert nb.load(tmp_path/'out/atlas_on_bold_grid.nii.gz').header.get_xyzt_units()[0]=='mm'
