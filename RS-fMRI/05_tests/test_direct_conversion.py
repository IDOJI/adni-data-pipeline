"""Source identity and acquisition preservation for direct ADNI DICOM conversion."""
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from _shared import read, sha, write
from s4_dcm2niix import convert as direct


def source(root, iid='200', participant='999_S_9999', label=None, **overrides):
    """Write classic, uncompressed MR DICOM with known pixel values in each volume."""
    epi = iid != '100'
    path = root / participant / (label or 'series') / '2020-01-01_12_00' / ('I' + iid)
    path.mkdir(parents=True)
    for volume in range(3 if epi else 1):
        for z in range(4):
            n = 4 * volume + z + 1
            uid = f'1.2.{iid}.{n}'
            meta = FileMetaDataset()
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            meta.MediaStorageSOPClassUID = MRImageStorage
            meta.MediaStorageSOPInstanceUID = uid
            f = path / f'{n:04d}_I{iid}.dcm'
            ds = FileDataset(str(f), Dataset(), file_meta=meta, preamble=bytes(128))
            attrs = dict(SOPInstanceUID=uid, SOPClassUID=MRImageStorage, SeriesInstanceUID='1.2.' + iid,
                         StudyInstanceUID='1.2.777', FrameOfReferenceUID='1.2.777.1',
                         Modality='MR', Manufacturer='SIEMENS', MagneticFieldStrength=3.0,
                         SeriesDescription='Resting State fMRI' if epi else 'MPRAGE', SeriesNumber=int(iid),
                         PatientID=participant, PatientName='Synthetic', StudyDate='20200101',
                         AcquisitionDate='20200101', AcquisitionTime=f'1200{volume * 2:02d}',
                         InstanceNumber=n, AcquisitionNumber=volume + 1, SequenceName='epfid2d' if epi else 'mprage',
                         RepetitionTime=2000.0, EchoTime=30.0, FlipAngle=70.0, MRAcquisitionType='2D' if epi else '3D',
                         ImageType=['ORIGINAL','PRIMARY','M'], SamplesPerPixel=1, PhotometricInterpretation='MONOCHROME2',
                         BitsAllocated=16, BitsStored=16, HighBit=15, PixelRepresentation=0,
                         Rows=16, Columns=16, PixelSpacing=[2.,2.], SliceThickness=3., SpacingBetweenSlices=3.,
                         ImageOrientationPatient=[1.,0.,0.,0.,1.,0.], ImagePositionPatient=[0.,0.,z*3.],
                         InPlanePhaseEncodingDirection='COL')
            for key, value in {**attrs, **overrides}.items():
                setattr(ds, key, value)
            ds.PixelData = np.full((16,16), n, dtype='<u2').tobytes()
            ds.save_as(f)
    return path


def setup_selection(base, ids=('100','200','201')):
    folder = base / 'selection'
    folder.mkdir()
    rows = [dict(PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01', IMAGE_ID=iid, SERIES_UID='1.2.' + iid,
                 MODALITY='T1' if iid == '100' else 'EPI', DOWNLOAD_TIER='source_qc_pass') for iid in ids]
    registry = folder / 'registry.csv'
    write(registry, rows)
    download = folder / 'ids.txt'
    download.write_text(''.join('I' + i + '\n' for i in ids))
    receipt = folder / 'selection.json'
    receipt.write_text(json.dumps(dict(inputs={}, outputs={k: dict(path=str(p),sha256=sha(p))
                            for k,p in [('download',download),('candidates',registry)]})))
    return receipt


@pytest.mark.skipif(not shutil.which('dcm2niix'), reason='dcm2niix executable required')
def test_real_converter_repeat_acquisitions(tmp_path):
    receipt = setup_selection(tmp_path)
    dicom, dataset = tmp_path / 'download', tmp_path / 'rawdata'
    for iid in ['100', '200', '201', '999']:
        source(dicom, iid)
    assert direct.convert(receipt, dicom, dataset) == (3,3)
    evidence = read(direct.verify_conversion(dataset, receipt))
    assert [r['SOURCE_IMAGE_ID'] for r in evidence if r['MODALITY'] == 'EPI'] == ['200','201']
    for row in evidence:
        nii = dataset / row['BIDS_NIFTI']
        meta = json.loads(nii.with_suffix('').with_suffix('.json').read_text())
        assert meta['ImageID'] == row['SOURCE_IMAGE_ID'] and meta['SeriesInstanceUID'] == row['SERIES_UID']
        assert row['NIFTI_SHA256'] == sha(nii)
        assert 'PatientName' not in meta and 'PatientID' not in meta
        arr = np.asarray(nib.load(nii).dataobj)
        if row['MODALITY'] == 'EPI':
            assert meta['TaskName'] == 'rest' and arr.shape == (16,16,4,3)
            assert sorted(set(arr.ravel())) == list(range(1,13))
    assert len(list(dataset.glob('sub-*/ses-*/func/*_run-0?_bold.nii.gz'))) == 2


@pytest.mark.parametrize('failure', ['missing', 'duplicate', 'wrong_uid','mixed','wrong_patient','wrong_date','wrong_file_id'])
def test_bad_source_never_reaches_converter(tmp_path, monkeypatch, failure):
    receipt = setup_selection(tmp_path, ('200',))
    dicom, dataset = tmp_path / 'dicom', tmp_path / 'raw'
    dicom.mkdir()
    if failure != 'missing':
        change = {'wrong_uid':dict(SeriesInstanceUID='1.2.888'), 'wrong_patient':dict(PatientID='998_S_9999'),
                  'wrong_date':dict(AcquisitionDate='20200102')}.get(failure, {})
        original = source(dicom, **change)
        if failure == 'duplicate':
            source(dicom, label='second')
        elif failure == 'mixed':
            f = next(original.glob('*.dcm'))
            ds = pydicom.dcmread(f)
            ds.SeriesInstanceUID = '1.2.888'
            ds.save_as(f)
        elif failure == 'wrong_file_id':
            f = next(original.glob('*.dcm'))
            f.rename(f.with_name('wrong_I888.dcm'))
    monkeypatch.setattr(direct.shutil, 'which', lambda name: 'dcm2niix')
    def version(argv, **kwargs):
        assert argv == ['dcm2niix','--version']
        return SimpleNamespace(stdout='v1.0.20240202')
    monkeypatch.setattr(direct.subprocess, 'run', version)
    assert direct.convert(receipt, dicom, dataset) == (0,1)
    row, = read(dataset / direct.EVIDENCE / 'conversion-audit.tsv')
    assert row['reason'] and row['status'] == ('missing_dicom' if failure == 'missing' else 'held')
    assert not list(dataset.glob('sub-*'))


@pytest.mark.skipif(not shutil.which('dcm2niix'), reason='dcm2niix executable required')
def test_partial_and_split_conversion_keeps_only_verified_outputs(tmp_path, monkeypatch):
    receipt = setup_selection(tmp_path)
    dicom, dataset = tmp_path / 'download', tmp_path / 'rawdata'
    source(dicom, '100')
    source(dicom, '201')
    run = direct.subprocess.run

    def split_one_series(argv, **kwargs):
        result = run(argv, **kwargs)
        if '-o' in argv:
            products = Path(argv[argv.index('-o') + 1])
            first = products / '1.2.201.nii.gz'
            if first.is_file():
                shutil.copyfile(first, products / '1.2.201_e2.nii.gz')
        return result

    monkeypatch.setattr(direct.subprocess, 'run', split_one_series)
    assert direct.convert(receipt, dicom, dataset) == (1, 3)
    audit = read(dataset / direct.EVIDENCE / 'conversion-audit.tsv')
    assert {r['IMAGE_ID']: r['status'] for r in audit} == {
        '100': 'converted', '200': 'missing_dicom', '201': 'held'}
    assert 'split' in next(r['reason'] for r in audit if r['IMAGE_ID'] == '201')
    assert not list(dataset.glob('sub-*/ses-*/func/*.nii.gz'))
    evidence, = read(direct.verify_conversion(dataset, receipt))
    assert evidence['SOURCE_IMAGE_ID'] == '100'
    (dataset / direct.EVIDENCE / 'series/I100.json').write_text('{}')
    with pytest.raises(ValueError, match='DICOM source evidence changed'):
        direct.verify_conversion(dataset, receipt)
