"""Collection-to-exact-pair regression tests; all images and identities are synthetic."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / 'pipeline/s3b_image_selection'
sys.path.insert(0, str(STEP))
spec = importlib.util.spec_from_file_location('date_image_selection', STEP / 'run.py')
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)
from _shared import finish, read, write


def quality(iid, modality, day='2020-01-01', **updates):
    row = dict(IMAGE_ID=iid, PTID='999_S_9999', MRI_STUDY_DATE=day, MODALITY=modality,
               SERIES_UID='1.2.' + iid, QC_STATUS='pass', QUALITY='2', SERIES_SELECTED='TRUE',
               SOURCE_QC_STATUS='pass', QC_BLOCKED=False, NFQ_RAW_QC_STATUS='pass' if modality == 'EPI' else '',
               MRI_PROTOCOL_PHASE='ADNI3', SPINE_SERIES_TYPE='BOLD' if modality == 'EPI' else 'T1w',
               SPINE_DESCRIPTION='Resting State fMRI' if modality == 'EPI' else 'MPRAGE')
    return {**row, **updates}


def collection(iid, day='01/01/2020', **updates):
    return {'Image Data ID': 'I' + iid, 'Subject': '999_S_9999', 'Acq Date': day, 'Visit': 'bl', **updates}


def setup(tmp, rows=None, qualities=None):
    qdir = tmp / 'qc'; qdir.mkdir()
    qualities = qualities or [quality('100', 'T1'), quality('200', 'EPI')]
    write(qdir / 'image_qc.tsv', qualities)
    finish(qdir, 'source_qc_v1', {}, {'synthetic': True})
    source = tmp / 'collection.csv'
    write(source, rows or [collection('100'), collection('200')])
    cfg = {'collections': [{'path': str(source), 'phase': 'ADNI3'}],
           'source_qc': str(qdir), 'output_dir': str(tmp / 'selection')}
    path = tmp / 'selection.json'; path.write_text(json.dumps(cfg))
    return cfg, path, source


def test_collection_to_binding_and_guarded_runner(tmp_path):
    # The actual binding fixture contains synthetic NIfTI/JSON and independent hashes.
    from test_bids_binding import fixture
    import binding
    binding_cfg, binding_path, _, _, _ = fixture(tmp_path)
    cfg, path, _ = setup(tmp_path)
    summary = selection.run(path)
    assert summary['preprocessing_ready'] == summary['analysis_ready'] == 0
    out = Path(cfg['output_dir'])
    epi = read(out / selection.NAMES['epi'])[0]
    assert epi['PROPOSED_T1_IMAGE_ID'] == '100'
    assert epi['PAIRING_REVIEW_REQUIRED'] == 'False'
    binding_cfg.update(images=str(out / selection.NAMES['candidates']),
                       epi_manifest=str(out / selection.NAMES['epi']),
                       pairing_receipt=str(out / selection.NAMES['receipt']))
    binding_path.write_text(json.dumps(binding_cfg))
    assert binding.run(binding_path)['preprocessing_ready'] == 1
    plan = binding.verify_plan(Path(binding_cfg['output_dir']) / binding.NAMES['receipt'], epi['EPI_KEY'])
    assert plan['t1_image_id'] == '100' and plan['epi_image_id'] == '200'


def test_same_visit_label_does_not_hide_large_acquisition_gap(tmp_path):
    cfg, path, _ = setup(tmp_path, [collection('100', '01/01/2018'), collection('200')],
                         [quality('100', 'T1', '2018-01-01'), quality('200', 'EPI')])
    selection.run(path)
    out = Path(cfg['output_dir'])
    epi = read(out / selection.NAMES['epi'])[0]
    assert epi['T1_PAIRING_STATUS'] == 'cross_date_review'
    assert epi['SIGNED_T1_MINUS_EPI_DAYS'] == '-730'
    assert epi['PAIRING_REVIEW_REQUIRED'] == 'True'
    assert epi['PREPROCESSING_READY'] == 'False'
    assert len(read(out / selection.NAMES['rows'])) == 2


def test_multiple_dates_and_duplicate_exports_preserve_image_population(tmp_path):
    rows = [collection('100'), collection('200'), collection('201', '01/01/2021'), collection('200')]
    cfg, path, _ = setup(tmp_path, rows, [quality('100', 'T1'), quality('200', 'EPI'), quality('201', 'EPI', '2021-01-01')])
    summary = selection.run(path)
    assert summary['images'] == 3 and summary['collection_rows'] == 4 and summary['epi_images'] == 2
    assert len(read(Path(cfg['output_dir']) / selection.NAMES['epi'])) == 2


@pytest.mark.parametrize('field,value', [('PTID', '998_S_9999'), ('MRI_STUDY_DATE', '2019-01-01'), ('SERIES_UID', 'conflict')])
def test_conflicting_source_evidence_is_held(tmp_path, field, value):
    raw = collection('200', SeriesInstanceUID='1.2.200')
    cfg, path, _ = setup(tmp_path, [collection('100'), raw], [quality('100', 'T1'), quality('200', 'EPI', **{field: value})])
    selection.run(path)
    epi = read(Path(cfg['output_dir']) / selection.NAMES['epi'])[0]
    assert epi['EPI_METADATA_QC_STATE'] == 'blocked'
    assert epi['PAIRING_REVIEW_REQUIRED'] == 'True'
    assert 'I200' not in (Path(cfg['output_dir']) / selection.NAMES['download']).read_text()


def test_missing_quality_is_preserved_pending_not_declared_pass(tmp_path):
    cfg, path, _ = setup(tmp_path, [collection('200')], [quality('100', 'T1')])
    cfg['collections'][0]['modality'] = 'EPI'; path.write_text(json.dumps(cfg))
    selection.run(path)
    epi = read(Path(cfg['output_dir']) / selection.NAMES['epi'])[0]
    assert epi['EPI_METADATA_QC_STATE'] == 'pending'
    assert epi['PAIRING_REVIEW_REQUIRED'] == 'True'


@pytest.mark.parametrize('problem', ['no_date', 'conflicting_id', 'bad_phase', 'bad_policy', 'tampered_qc', 'unbound_qc', 'malformed_id'])
def test_untrusted_collection_or_policy_stops_before_publication(tmp_path, problem):
    cfg, path, source = setup(tmp_path)
    if problem == 'no_date':
        write(source, [collection('200', '')])
    elif problem == 'conflicting_id':
        write(source, [collection('200'), collection('200', '01/01/2018')])
    elif problem == 'bad_phase':
        cfg['collections'][0]['phase'] = 'inferred'
    elif problem == 'bad_policy':
        cfg['policy'] = {'cross_date_automatic_assignment': True}
    elif problem == 'unbound_qc':
        receipt = Path(cfg['source_qc']) / 'artifact.json'
        value = json.loads(receipt.read_text())
        value['outputs_sha256'] = {}
        receipt.write_text(json.dumps(value))
    elif problem == 'malformed_id':
        write(source, [collection('II200')])
    else:
        (Path(cfg['source_qc']) / 'image_qc.tsv').write_text('changed')
    path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        selection.run(path)
    assert not Path(cfg['output_dir']).exists()


def test_confirmed_conversion_exclusion_cannot_reenter_reference_pool(tmp_path):
    cfg, path, _ = setup(tmp_path)
    ledger = tmp_path / 'failures.csv'
    write(ledger, [dict(IMAGE_ID='100', PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01',
                       MODALITY='T1', REASON='persistent_conversion_failure', CONFIRMED=True)])
    cfg['confirmed_exclusions'] = str(ledger); path.write_text(json.dumps(cfg))
    selection.run(path)
    epi = read(Path(cfg['output_dir']) / selection.NAMES['epi'])[0]
    assert epi['PROPOSED_T1_IMAGE_ID'] == ''
    assert epi['T1_PAIRING_STATUS'] == 'no_reference_candidate'


def test_selection_source_changes_invalidate_binding_receipt(tmp_path):
    import binding
    cfg, path, source = setup(tmp_path)
    selection.run(path)
    source.write_text('changed')
    with pytest.raises(ValueError, match='fingerprint'):
        binding.proof_files(Path(cfg['output_dir']) / selection.NAMES['receipt'])


def test_existing_outputs_and_input_mutation_are_rejected(tmp_path, monkeypatch):
    cfg, path, source = setup(tmp_path)
    original = selection.pairing.build_pairs
    def mutate(images, policy):
        result = original(images, policy)
        source.write_text('changed')
        return result
    monkeypatch.setattr(selection.pairing, 'build_pairs', mutate)
    with pytest.raises(ValueError, match='source changed'):
        selection.run(path)
    assert not Path(cfg['output_dir']).exists()
    monkeypatch.setattr(selection.pairing, 'build_pairs', original)
    write(source, [collection('100'), collection('200')])
    selection.run(path)
    before = {p.name: selection.sha(p) for p in Path(cfg['output_dir']).iterdir()}
    with pytest.raises(ValueError, match='new output'):
        selection.run(path)
    assert before == {p.name: selection.sha(p) for p in Path(cfg['output_dir']).iterdir()}


def test_mixed_ida_search_is_not_a_download_list(tmp_path):
    from reconcile import reconcile
    cfg, path, source = setup(tmp_path)
    descriptions = ['MPRAGE','Axial rsfMRI (Eyes Open)','relCBF','Perfusion_Weighted',
                    'MoCoSeries','Axial pCASL (Eyes Open)','Axial MB DTI','Advanced fMRI',
                    'Axial rsfMRI (Eyes Open)','task-nback','Axial rsfMRI (Eyes Open)']
    ids = ['100'] + [str(i) for i in range(200,210)]
    rows = [{'Subject ID':'999_S_9999','Image ID':'I'+key,'Study Date':'1/1/2020',
             'Phase': 'ADNI 3' if i != 1 else 'ADNI 4','Archive Date':'2/2/2022','Description':desc,
             'Modality':'fMRI' if i else 'MRI','Imaging Protocol':'Manufacturer=GE MEDICAL SYSTEMS; Field Strength=3.0'}
            for i,(key,desc) in enumerate(zip(ids,descriptions))]
    qc = [quality(k,'EPI' if i else 'T1', SPINE_DESCRIPTION='Advanced fMRI' if i==7 else descriptions[i],
                  MRI_PROTOCOL_PHASE='ADNI4' if i==1 else 'ADNI3', SPINE_MANUFACTURER='GE',
                  SPINE_SCANNER_MODEL='Model X',SPINE_FIELD_STRENGTH='3 T') for i,k in enumerate(ids)]
    qc.pop(8)  # A convincing name without source identity is insufficient.
    qc[-1]['SPINE_MANUFACTURER']='Siemens'
    qdir = tmp_path/'mixed-qc'; qdir.mkdir(); cfg['source_qc'] = str(qdir)
    write(qdir/'image_qc.tsv',qc); finish(qdir,'source_qc_v1',{}, {})
    write(source,rows[1:]); t1=tmp_path/'t1.csv'; write(t1,rows[:1])
    cfg['collections']=[{'path':str(source),'modality':'EPI'},{'path':str(t1),'modality':'T1'}]
    path.write_text(json.dumps(cfg)); selection.run(path); out=Path(cfg['output_dir'])
    reg={r['IMAGE_ID']:r for r in read(out/selection.NAMES['candidates'])}
    assert set((out/selection.NAMES['download']).read_text().splitlines()) == {'I100','I200'}
    assert reg['200']['SEARCH_PHASE']=='ADNI4' and reg['200']['MRI_STUDY_DATE']=='2020-01-01'
    assert reg['200']['MANUFACTURER']=='ge' and reg['200']['FIELD_STRENGTH']=='3'
    assert reg['200']['SCANNER_MODEL']=='modelx' and not reg['200']['SEARCH_SCANNER_MODEL']
    assert 'scanner_evidence_conflict' in reg['209']['DOWNLOAD_REASONS']
    assert 'moco_excluded_by_spine' in reg['203']['DOWNLOAD_REASONS']
    assert 'exact_MRIQC_BOLD_not_confirmed' in reg['207']['DOWNLOAD_REASONS']
    assert 'rest_not_documented' in reg['206']['DOWNLOAD_REASONS']
    assert {r['EPI_IMAGE_ID'] for r in read(out/selection.NAMES['epi'])}.isdisjoint({'201','202','203','204','205'})
    assert next(r for r in read(out/selection.NAMES['epi']) if r['EPI_IMAGE_ID']=='200')['PROTOCOL_SCOPE']=='extension_review'
    legacy={}
    for mod, keys in [('T1',['100']),('EPI',['201','207','999'])]:
        legacy[mod]=tmp_path/(mod+'-legacy.csv')
        write(legacy[mod],[dict(image_id=i,PTID='999_S_9999',STUDY_DATE='2020-01-01') for i in keys])
    compare=tmp_path/'compare'
    stats=reconcile(out/selection.NAMES['receipt'],legacy,compare)['summary']
    assert stats['changed']==4 and stats['unexplained']==0
    changed={r['IMAGE_ID']:r for r in read(compare/'changed-images.csv')}
    assert changed['200']['CHANGE']=='added' and changed['999']['REASON']=='absent_from_supplied_search_exports'
    assert 'perfusion' in changed['201']['REASON']
    cfg['collections'][0]['phase']='ADNI3';path.write_text(json.dumps({**cfg,'output_dir':str(tmp_path/'bad')}))
    with pytest.raises(ValueError,match='row Phase'):
        selection.run(path)


def test_date_mapping_may_not_promote_archive_or_visit_date(tmp_path):
    cfg,path,source=setup(tmp_path)
    cfg['collections'][0]['columns']={'MRI_STUDY_DATE':'Archive Date'}
    write(source,[collection('100',**{'Archive Date':'01/01/2020'})])
    path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='acquisition date'):
        selection.run(path)


def test_missing_grades_allow_download_for_inspection_but_never_dispatch(tmp_path):
    from test_bids_binding import fixture
    import binding
    binding_cfg, binding_path, *_ = fixture(tmp_path)
    cfg, path, _ = setup(tmp_path, qualities=[
        quality('100','T1', SOURCE_QC_STATUS='pending', QC_STATUS='unknown', QUALITY='', QC_REASON='no_matched_quality_record'),
        quality('200','EPI', SOURCE_QC_STATUS='pending', NFQ_RAW_QC_STATUS='unknown', NFQ_RAW_REASON='raw_overallqc_column_absent')])
    selection.run(path)
    out=Path(cfg['output_dir'])
    assert (out/selection.NAMES['download']).read_text().splitlines()==['I200','I100']
    pending=read(out/selection.NAMES['pending_download'])
    assert {r['DOWNLOAD_REASONS'] for r in pending}=={'no_matched_quality_record','raw_overallqc_column_absent'}
    assert all(r['SOURCE_QC_STATUS']=='pending' for r in pending)
    epi=read(out/selection.NAMES['epi'])[0]
    assert epi['EPI_METADATA_QC_STATE']=='pending' and epi['PAIRING_REVIEW_REQUIRED']=='True'
    binding_cfg.update(images=str(out/selection.NAMES['candidates']), epi_manifest=str(out/selection.NAMES['epi']),
                       pairing_receipt=str(out/selection.NAMES['receipt']))
    binding_path.write_text(json.dumps(binding_cfg))
    assert binding.run(binding_path)['preprocessing_ready']==0


@pytest.mark.parametrize('overrides', [
    {'MRI_PROTOCOL_PHASE':'ADNI4'}, {'NFQ_RAW_REASON':'raw_overallqc_undefined_value'},
    {'NFQ_RAW_QC_STATUS':'hold'}, {'NFQ_RAW_REASON':'raw_overallqc_absent_or_undefined'},
    {'QC_STATUS':'unknown','QC_REASON':'quality_missing_or_undefined','QUALITY':'9'}])
def test_real_conflicts_and_undefined_values_are_not_download_review_cases(tmp_path,overrides):
    values=dict(SOURCE_QC_STATUS='pending', NFQ_RAW_QC_STATUS='unknown', NFQ_RAW_REASON='no_unique_raw_nfq_match')
    cfg,path,_=setup(tmp_path,qualities=[quality('100','T1'),quality('200','EPI',**{**values,**overrides})])
    selection.run(path); out=Path(cfg['output_dir'])
    assert (out/selection.NAMES['download']).read_text().splitlines()==['I100']
    assert read(out/selection.NAMES['pending_download'])==[]
