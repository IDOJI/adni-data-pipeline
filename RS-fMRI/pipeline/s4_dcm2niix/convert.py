"""Convert exactly the downloaded, selected ADNI series to a new private BIDS dataset."""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import nibabel as nib
import pydicom

from _shared import new_output, read, sha, write
from s3b_image_selection.selection_identity import image_id, scan_date
from s5d_bids_identity import binding


EVIDENCE = Path('sourcedata/conversion')
GENERATOR = 'ADNI Image ID conversion'
TIERS = {'source_qc_pass', 'for_qc_review'}
HASH_FIELDS = ['SOURCE_PTID', 'STUDY_DATE', 'MODALITY', 'SOURCE_IMAGE_ID', 'SERIES_UID',
               'NIFTI_SHA256', 'BIDS_NIFTI', 'CONVERTED_JSON_SHA256', 'DICOM_MANIFEST_SHA256']
AUDIT_FIELDS = ['IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'MODALITY', 'DOWNLOAD_TIER', 'status', 'reason', 'bids_nifti']
HEADER_TAGS = ['SeriesInstanceUID', 'SOPInstanceUID', 'Modality', 'PatientID', 'StudyDate',
               'AcquisitionDate', 'AcquisitionDateTime']


class HeldSeries(ValueError):
    """An individual acquisition needs review before it can be published."""


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def selected_rows(proof):
    registry = read(proof['outputs']['candidates']['path'])
    rows = [r for r in registry if r['DOWNLOAD_TIER'] in TIERS]
    ids = [r['IMAGE_ID'] for r in rows]
    download = Path(proof['outputs']['download']['path']).read_text().splitlines()
    if not ids or len(set(ids)) != len(ids) or sorted('I' + i for i in ids) != sorted(download):
        raise ValueError('Download list and selected Image IDs are empty, duplicated or inconsistent.')
    for r in rows:
        if (not re.fullmatch(r'\d{3}_S_\d{4,}', r['PTID']) or r['MODALITY'] not in ('T1', 'EPI')
                or r['IMAGE_ID'] != image_id(r['IMAGE_ID']) or r['MRI_STUDY_DATE'] != scan_date(r['MRI_STUDY_DATE'])):
            raise ValueError('Invalid identifier in the Stage 1 selection.')
    return sorted(rows, key=lambda r: (r['PTID'], r['MRI_STUDY_DATE'], r['MODALITY'], int(r['IMAGE_ID'])))


def source_index(root, ids):
    if not root.is_dir():
        raise ValueError(f'Missing extracted DICOM directory: {root}')
    locations = defaultdict(list)
    for path in root.glob('*/*/*/*'):
        if path.is_dir() and re.fullmatch(r'[Ii]?\d+', path.name) and image_id(path.name) in ids:
            locations[image_id(path.name)].append(path)
    return locations


def snapshot_series(src, inputs, row):
    """Stage the exact bytes to convert and check every instance against the source registry."""
    inputs.mkdir()
    evidence = []
    instances = set()
    for path in sorted(src.rglob('*')):
        if any(p.startswith('.') for p in path.relative_to(src).parts) or path.name.upper() == 'DICOMDIR':
            continue
        if path.is_symlink():
            raise HeldSeries('Unexpected symbolic link in the source series')
        if not path.is_file() or path.suffix.lower() in ('.txt', '.xml', '.json', '.csv'):
            continue
        staged = inputs / f'{len(evidence):07}.dcm'
        shutil.copyfile(path, staged)
        try:
            header = pydicom.dcmread(staged, stop_before_pixels=True, specific_tags=HEADER_TAGS, force=True)
            uid = str(header.SeriesInstanceUID or '')
            instance = str(header.SOPInstanceUID or '')
            dates = {scan_date(str(header[k].value)[:8]) for k in
                     ('StudyDate', 'AcquisitionDate', 'AcquisitionDateTime') if k in header and header[k].value}
        except (AttributeError, ValueError, EOFError) as exc:
            raise HeldSeries(f'Unreadable DICOM identity in {path.name}') from exc
        if (header.get('Modality') != 'MR' or uid != row['SERIES_UID'] or not uid or not header.SeriesInstanceUID.is_valid
                or not instance or not header.SOPInstanceUID.is_valid or instance in instances):
            raise HeldSeries('DICOM modality, series UID or unique instance identity disagrees')
        if dates and dates != {row['MRI_STUDY_DATE']}:
            raise HeldSeries('DICOM date differs from Stage 1')
        patient = re.fullmatch(r'(?:ADNI[_-]?)?(\d{3})_?S_?(\d{4,})', str(header.get('PatientID', '')), re.I)
        if patient and '_S_'.join(patient.groups()) != row['PTID']:
            raise HeldSeries('DICOM participant differs from Stage 1')
        filename_id = re.search(r'(?:^|_)I(\d+)(?:\.|$)', path.name, re.I)
        if filename_id and image_id(filename_id[1]) != row['IMAGE_ID']:
            raise HeldSeries('DICOM filename Image ID differs from its IDA folder')
        instances.add(instance)
        evidence.append(dict(file=str(path.relative_to(src)), sop_instance_uid=instance, sha256=sha(staged)))
    if not evidence:
        raise HeldSeries('No DICOM instances')
    return evidence


def convert_one(exe, src, row, work, logs, dataset, stem):
    inputs, products = work / 'inputs', work / 'outputs'
    files = snapshot_series(src, inputs, row)
    products.mkdir()
    options = ['-g', 'i', '-b', 'y', '-ba', 'y', '-z', 'y', '-w', '2', '-f', '%j']
    with (logs / ('I' + row['IMAGE_ID'] + '.log')).open('w') as log:
        result = subprocess.run([exe, *options, '-o', products, inputs], stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise HeldSeries(f'dcm2niix exited with code {result.returncode}')
    images = list(products.glob('*.nii*'))
    if len(images) != 1 or not images[0].name.endswith('.nii.gz') or list(products.glob('*.bv*')):
        raise HeldSeries('Expected one compressed MR image; review split, diffusion or missing outputs')
    nii = images[0]
    sidecar = nii.with_suffix('').with_suffix('.json')
    # %j is read independently by dcm2niix from the input DICOMs.
    if (not re.fullmatch(re.escape(row['SERIES_UID']) + r'(?:_[A-Za-z0-9_-]+)?', nii.name[:-7])
            or set(products.glob('*.json')) != {sidecar}):
        raise HeldSeries('Converter output UID or matching sidecar is ambiguous')
    try:
        meta = json.loads(sidecar.read_text())
        shape = nib.load(nii).shape
        if not isinstance(meta, dict) or len(shape) != (3 if row['MODALITY'] == 'T1' else 4) or min(shape) < 1:
            raise HeldSeries('Converted dimensions or sidecar disagree with the selected modality')
        image_type = meta.get('ImageType', [])
        if isinstance(image_type, str):
            image_type = image_type.split('\\')
        if (set(image_type) & {'P', 'PHASE', 'REAL', 'IMAGINARY'}
                or meta.get('ComplexImageComponent') in {'PHASE', 'REAL', 'IMAGINARY'}):
            raise HeldSeries('Phase, real or imaginary component cannot be published as a magnitude image')
        if meta.get('SeriesInstanceUID', row['SERIES_UID']) != row['SERIES_UID']:
            raise HeldSeries('Converter sidecar series UID differs from DICOM')
        if any(image_id(meta[k]) != row['IMAGE_ID'] for k in ('ImageID', 'ImageUID', 'LONIImage') if k in meta):
            raise HeldSeries('Converter sidecar Image ID differs from the source folder')
        if any(scan_date(str(meta[k]).split('T')[0]) != row['MRI_STUDY_DATE']
               for k in ('StudyDate', 'AcquisitionDate', 'AcquisitionDateTime') if meta.get(k)):
            raise HeldSeries('Converter sidecar date differs from Stage 1')
        meta.update(SeriesInstanceUID=row['SERIES_UID'], ImageID=row['IMAGE_ID'])
        if row['MODALITY'] == 'EPI':
            tr = float(meta.get('RepetitionTime', 0))
            if shape[3] < 2 or not math.isfinite(tr) or tr <= 0:
                raise HeldSeries('Resting BOLD needs multiple volumes and a positive repetition time')
            meta['TaskName'] = 'rest'
        save(sidecar, meta)
    except (nib.filebasedimages.ImageFileError, ValueError, TypeError) as exc:
        raise HeldSeries(str(exc)) from exc
    source_record = logs / ('I' + row['IMAGE_ID'] + '.json')
    save(source_record, dict(image_id=row['IMAGE_ID'], source_dir=str(src), series_uid=row['SERIES_UID'],
                             options=options, instances=files))
    output = dataset / (str(stem) + '.nii.gz')
    output.parent.mkdir(parents=True, exist_ok=True)
    nii.rename(output)
    json_output = sidecar.rename(dataset / (str(stem) + '.json'))
    return dict(SOURCE_PTID=row['PTID'], STUDY_DATE=row['MRI_STUDY_DATE'], MODALITY=row['MODALITY'],
                SOURCE_IMAGE_ID=row['IMAGE_ID'], SERIES_UID=row['SERIES_UID'], BIDS_NIFTI=str(output.relative_to(dataset)),
                NIFTI_SHA256=sha(output), CONVERTED_JSON_SHA256=sha(json_output), DICOM_MANIFEST_SHA256=sha(source_record))


def convert(receipt, dicom, destination):
    selection_hash = sha(receipt)
    proof = binding.proof_files(receipt)
    rows = selected_rows(proof)
    new_output(destination, [dicom, receipt.parent])
    exe = shutil.which('dcm2niix')
    if not exe:
        raise ValueError('Install dcm2niix and put its executable on PATH.')
    version = subprocess.run([exe, '--version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    match = re.search(r'v?1\.0\.\d{8}', version.stdout)
    if not match:
        raise ValueError('Could not identify the installed dcm2niix version.')
    locations = source_index(dicom, {r['IMAGE_ID'] for r in rows})
    uids = Counter(r['SERIES_UID'] for r in rows)
    counts = Counter()
    evidence, audits = [], []
    scans = defaultdict(list)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent, prefix='.adni-convert-') as tmp:
        dataset = Path(tmp) / 'rawdata'
        logs = dataset / EVIDENCE / 'series'
        logs.mkdir(parents=True)
        for row in rows:
            iid, modality = row['IMAGE_ID'], row['MODALITY']
            sub = 'sub-ADNI' + row['PTID'].replace('_', '')
            ses = 'ses-' + row['MRI_STUDY_DATE'].replace('-', '')
            counts[sub, ses, modality] += 1
            run = f'run-{counts[sub, ses, modality]:02d}'
            leaf = f'{sub}_{ses}_task-rest_{run}_bold' if modality == 'EPI' else f'{sub}_{ses}_{run}_T1w'
            stem = Path(sub, ses, 'func' if modality == 'EPI' else 'anat', leaf)
            report = {key: row[key] for key in AUDIT_FIELDS[:5]}
            report.update(status='held', reason='', bids_nifti='')
            audits.append(report)
            try:
                matches = locations[iid]
                if not matches:
                    report['status'] = 'missing_dicom'
                    raise HeldSeries('Selected Image ID was not found in the download')
                if len(matches) != 1:
                    raise HeldSeries('Multiple source folders for the same Image ID')
                src = matches[0]
                ptid, _, day, _ = src.relative_to(dicom).parts
                try:
                    folder_date = scan_date(day.split('_')[0])
                except ValueError as exc:
                    raise HeldSeries('Invalid date in the IDA source folder') from exc
                if src.resolve() != src or ptid != row['PTID'] or folder_date != row['MRI_STUDY_DATE']:
                    raise HeldSeries('Source folder participant or date differs from selection')
                if not row['SERIES_UID'] or uids[row['SERIES_UID']] != 1:
                    raise HeldSeries('Stage 1 series UID missing or ambiguous')
                with TemporaryDirectory(dir=tmp) as work:
                    record = convert_one(exe, src, row, Path(work), logs, dataset, stem)
            except HeldSeries as exc:
                report['reason'] = str(exc)
                continue
            evidence.append(record)
            report.update(status='converted', bids_nifti=record['BIDS_NIFTI'])
            scans[sub, ses].append({'filename': str(Path(record['BIDS_NIFTI']).relative_to(Path(sub, ses)))})
        for (sub, ses), files in scans.items():
            write(dataset / sub / ses / f'{sub}_{ses}_scans.tsv', files)
        save(dataset / 'dataset_description.json', dict(Name='ADNI resting-state study', BIDSVersion='1.10.0',
             DatasetType='raw', GeneratedBy=[{'Name': GENERATOR}, {'Name': 'dcm2niix', 'Version': match.group()}]))
        (dataset / 'README').write_text(
            'Private ADNI structural T1w and resting-state BOLD acquisitions. Sessions use the original scan date. '
            'Repeat acquisitions within a modality and session are ordered by Image ID. The table '
            'sourcedata/conversion/conversion-audit.tsv links each selected ID to its conversion outcome.\n')
        out = dataset / EVIDENCE
        write(out / 'conversion-hashes.csv', evidence, HASH_FIELDS)
        write(out / 'conversion-audit.tsv', audits, AUDIT_FIELDS)
        save(out / 'conversion.json', dict(selection=str(receipt), selection_sha256=selection_hash, executable=exe,
                                            version=match.group(), evidence_sha256=sha(out / 'conversion-hashes.csv'),
                                            audit_sha256=sha(out / 'conversion-audit.tsv')))
        binding.proof_files(receipt)
        if sha(receipt) != selection_hash or destination.exists():
            raise ValueError('Selection changed or output already exists. Use a fresh conversion directory.')
        dataset.rename(destination)
    return len(evidence), len(rows)


def verify_conversion(dataset, receipt):
    directory = dataset / EVIDENCE
    run = binding.read_json(directory / 'conversion.json')
    hashes = directory / 'conversion-hashes.csv'
    if (sha(receipt) != run['selection_sha256'] or sha(hashes) != run['evidence_sha256']
            or sha(directory / 'conversion-audit.tsv') != run['audit_sha256']):
        raise ValueError('Direct conversion evidence or selection receipt changed.')
    for row in read(hashes, HASH_FIELDS):
        iid = image_id(row['SOURCE_IMAGE_ID'])
        output = dataset / row['BIDS_NIFTI']
        if not output.resolve().is_relative_to(dataset.resolve()) or not output.is_file():
            raise ValueError('Recorded BIDS file is missing or moved for I' + iid)
        path = directory / 'series' / ('I' + iid + '.json')
        if sha(path) != row['DICOM_MANIFEST_SHA256']:
            raise ValueError('DICOM source evidence changed for I' + iid)
        source = binding.read_json(path)
        if (source['image_id'], source['series_uid']) != (iid, row['SERIES_UID']) or not source['instances']:
            raise ValueError('DICOM source identity differs for I' + iid)
    return hashes
