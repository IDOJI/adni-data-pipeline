"""Read-only BIDS identity checks and lossless, policy-bound EPI handoffs."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

VERSION = '2026-11-01-bids-identity-v1'
NAMES = {'images': '02.image-validation.csv', 'files': '03.file-audit.csv',
         'epi': '04.epi-execution-manifest.csv', 'plans': '05.execution-plans.json',
         'summary': '06.summary.json', 'receipt': '07.binding-receipt.json'}


def resident(path):
    try:
        s = Path(path).stat()
        return Path(path).is_file() and not (getattr(s, 'st_flags', 0) & 0x40000000)
    except OSError:
        return False


def sha(path):
    if not resident(path):
        raise ValueError(f'File unavailable or cloud-only: {path}')
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        if getattr(os.fstat(stream.fileno()), 'st_flags', 0) & 0x40000000:
            raise ValueError('File became cloud-only')
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read_csv(path):
    if not resident(path):
        raise ValueError(f'Unavailable CSV: {path}')
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Missing/duplicate CSV columns')
        rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('Malformed CSV')
    return rows


def read_json(path):
    if not resident(path):
        raise ValueError(f'Unavailable JSON: {path}')
    return json.loads(Path(path).read_text())


def true(v):
    return str(v).lower() in ('true', '1', 'yes')


def iid(v):
    s = str(v).strip().lstrip('Ii')
    if not s.isdecimal():
        raise ValueError('Invalid Image ID')
    return s


def proof_files(receipt):
    x = read_json(receipt)
    for kind in ('inputs', 'outputs'):
        for meta in x[kind].values():
            if sha(meta['path']) != meta['sha256']:
                raise ValueError(f'{kind} evidence fingerprint changed: {meta["path"]}')
    return x


def path_within(root, path):
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def identity_fields(row):
    return row['PTID'], row['MRI_STUDY_DATE'], row['MODALITY'], iid(row['IMAGE_ID'])


def load_expected(paths):
    expected = defaultdict(list)
    for p in paths:
        rows = read_csv(p) if Path(p).suffix == '.csv' else read_json(p)
        if not isinstance(rows, list):
            raise ValueError('Expected a conversion CSV or a source-mapping JSON list')
        for n, r in enumerate(rows, 1):
            image_id = iid(r.get('SOURCE_IMAGE_ID', r.get('image_id', '')))
            expected[image_id].append({
                'PTID': r.get('SOURCE_PTID', r.get('ptid', '')),
                'MRI_STUDY_DATE': r.get('STUDY_DATE', r.get('scan_date', '')),
                'MODALITY': r.get('MODALITY', r.get('modality', '')),
                'sha256': r.get('NIFTI_SHA256', r.get('sha256', '')),
                'evidence_file': str(Path(p).resolve()), 'evidence_row': n})
    return expected


def inspect_header(path, meta, modality):
    img = nib.load(path)
    shape = img.shape
    if len(shape) != (4 if modality == 'EPI' else 3) or any(n < 1 for n in shape):
        raise ValueError('Invalid NIfTI dimensionality')
    if not np.isfinite(img.affine).all() or not np.isfinite(img.header.get_zooms()).all():
        raise ValueError('Nonfinite NIfTI geometry')
    if modality == 'EPI':
        tr = meta.get('RepetitionTime')
        if isinstance(tr, bool) or not isinstance(tr, (int, float)) or not math.isfinite(tr) or tr <= 0:
            raise ValueError('Invalid JSON RepetitionTime')
        if img.header.get_xyzt_units()[1] != 'sec' or not np.isclose(tr, img.header.get_zooms()[3], atol=1e-5, rtol=0):
            raise ValueError('NIfTI/JSON TR or units mismatch')
        ped = meta.get('PhaseEncodingDirection')
        if ped not in ('i', 'j', 'k', 'i-', 'j-', 'k-'):
            raise ValueError('Phase encoding direction unverified')
        declared = meta.get('SliceEncodingDirection')
        axis_h = img.header.get_dim_info()[2]
        if declared is not None:
            if declared not in ('i', 'j', 'k', 'i-', 'j-', 'k-'):
                raise ValueError('Invalid SliceEncodingDirection')
            axis = 'ijk'.index(declared[0])
            if axis_h is not None and axis_h != axis:
                raise ValueError('NIfTI/JSON slice axis mismatch')
        elif axis_h is not None:
            axis = axis_h
        else:
            raise ValueError('Slice axis unverified; no assumed k axis')
        times = meta.get('SliceTiming')
        if not isinstance(times, list) or len(times) != shape[axis] or any(isinstance(v, bool) for v in times):
            raise ValueError('SliceTiming count/type mismatch')
        t = np.asarray(times, dtype=float)
        if not np.isfinite(t).all() or t.min() < 0 or t.max() >= tr:
            raise ValueError('SliceTiming outside TR')
    return 'x'.join(map(str, shape))


def inspect_file(root, sidecar, by_uid, expected):
    record = {'BIDS_ROOT': str(root), 'JSON_PATH': str(sidecar), 'NIFTI_PATH': '',
              'IMAGE_ID': '', 'PTID': '', 'MRI_STUDY_DATE': '', 'MODALITY': '',
              'SERIES_UID': '', 'SUBJECT': '', 'SESSION': '', 'NIFTI_SHA256': '',
              'JSON_SHA256': '', 'NIFTI_SHAPE': '', 'STATUS': 'pending',
              'REASON': '', 'HASH_EVIDENCE_FILE': '', 'HASH_EVIDENCE_ROW': ''}
    try:
        if not path_within(root, sidecar) or not resident(sidecar):
            raise ValueError('Sidecar unavailable or symlink outside root')
        rel = sidecar.relative_to(root)
        sub = next((s[4:] for s in rel.parts if s.startswith('sub-')), '')
        ses = next((s[4:] for s in rel.parts if s.startswith('ses-')), '')
        if not re.fullmatch('[A-Za-z0-9]+', sub) or not re.fullmatch('[A-Za-z0-9]+', ses):
            raise ValueError('Invalid/missing BIDS subject or session entity')
        record.update(SUBJECT=sub, SESSION=ses)
        modality = 'T1' if sidecar.name.endswith('_T1w.json') else 'EPI'
        record['MODALITY'] = modality
        if modality == 'EPI' and not re.search(r'(?:^|_)task-rest(?:_|\.)', sidecar.name):
            raise ValueError('BOLD outside rest task')
        paths = [p for p in [sidecar.with_suffix('.nii.gz'), sidecar.with_suffix('.nii')] if p.exists()]
        if len(paths) != 1 or not resident(paths[0]) or not path_within(root, paths[0]):
            raise ValueError('Missing/ambiguous/nonresident NIfTI or symlink escape')
        nii = paths[0]; record['NIFTI_PATH'] = str(nii)
        meta = read_json(sidecar)
        uid = str(meta.get('SeriesInstanceUID', '')).strip()
        record['SERIES_UID'] = uid
        matches = by_uid.get(uid, []) if uid else []
        if len(matches) != 1:
            raise ValueError('Series UID missing, unmatched or ambiguous in source registry')
        source = matches[0]
        image_id = iid(source['IMAGE_ID'])
        record.update(IMAGE_ID=image_id, PTID=source['PTID'], MRI_STUDY_DATE=source['MRI_STUDY_DATE'])
        if source['MODALITY'] != modality:
            raise ValueError('Source/BIDS modality conflict')
        if sub not in (source['PTID'].replace('_', ''), 'ADNI' + source['PTID'].replace('_', '')):
            raise ValueError('Source/BIDS participant conflict')
        for k in ('ImageID', 'ImageUID', 'LONIImage'):
            if meta.get(k) is not None and iid(meta[k]) != image_id:
                raise ValueError('Image ID field contradicts source UID match')
        dt = str(meta.get('AcquisitionDateTime', '')).split('T')[0]
        if dt and dt != source['MRI_STUDY_DATE']:
            raise ValueError('Source/JSON acquisition date conflict')
        record['NIFTI_SHA256'] = sha(nii)
        record['JSON_SHA256'] = sha(sidecar)
        evidence = [e for e in expected.get(image_id, [])
                    if e['sha256'] == record['NIFTI_SHA256']
                    and (e['PTID'], e['MRI_STUDY_DATE'], e['MODALITY']) == identity_fields(source)[:3]]
        if not evidence:
            raise ValueError('No independent Image ID/date/modality and NIfTI hash evidence')
        e = evidence[0]
        record.update(HASH_EVIDENCE_FILE=e['evidence_file'], HASH_EVIDENCE_ROW=e['evidence_row'])
        record['NIFTI_SHAPE'] = inspect_header(nii, meta, modality)
        record['STATUS'] = 'verified'
        record['REASON'] = 'source_unique_UID_and_Image_ID_hash_evidence_and_header'
    except (ValueError, OSError, KeyError, TypeError, nib.filebasedimages.ImageFileError) as exc:
        record['REASON'] = str(exc)
        record['STATUS'] = 'pending'
    return record


def bind(images, epis, roots, expected):
    image_ids = [iid(r['IMAGE_ID']) for r in images]
    if len(set(image_ids)) != len(image_ids):
        raise ValueError('Duplicate source Image ID')
    by_id = dict(zip(image_ids, images))
    by_uid = defaultdict(list)
    for row in images:
        if row.get('SERIES_UID'):
            by_uid[row['SERIES_UID']].append(row)
    audit = []
    for root in roots:
        root = Path(root).resolve()
        if not resident(root / 'dataset_description.json'):
            continue
        for sidecar in sorted(root.glob('sub-*/ses-*/*/*.json')):
            if sidecar.name.endswith(('_T1w.json', '_bold.json')):
                audit.append(inspect_file(root, sidecar, by_uid, expected))
    grouped = defaultdict(list)
    for row in audit:
        if row['IMAGE_ID']:
            grouped[row['IMAGE_ID']].append(row)
    image_rows, verified = [], {}
    for image_id, source in by_id.items():
        found = grouped[image_id]
        valid = [r for r in found if r['STATUS'] == 'verified']
        signatures = {(r['NIFTI_SHA256'], r['JSON_SHA256']) for r in valid}
        # A contradictory copy is never hidden by choosing the first good copy.
        status = 'verified' if len(signatures) == 1 and len(valid) == len(found) else 'conflict' if found and (len(signatures) > 1 or valid) else 'pending'
        chosen = valid[0] if status == 'verified' else {}
        record = {**{k: source.get(k, '') for k in ('PTID', 'MRI_STUDY_DATE', 'MODALITY', 'IMAGE_ID', 'SERIES_UID')},
                  'BIDS_STATUS': status, 'OBSERVED_COPY_COUNT': len(found),
                  'BIDS_ROOT': chosen.get('BIDS_ROOT', ''),
                  'BIDS_NIFTI_PATH': chosen.get('NIFTI_PATH', ''), 'BIDS_JSON_PATH': chosen.get('JSON_PATH', ''),
                  'NIFTI_SHA256': chosen.get('NIFTI_SHA256', ''), 'JSON_SHA256': chosen.get('JSON_SHA256', ''),
                  'SUBJECT': chosen.get('SUBJECT', ''), 'SESSION': chosen.get('SESSION', ''),
                  'REASON': 'equivalent_verified_copies' if len(valid) > 1 and status == 'verified' else chosen.get('REASON', '') or 'no_unambiguous_resident_match'}
        image_rows.append(record)
        if status == 'verified':
            verified[image_id] = record
    linked, plans = [], []
    seen = set()
    for epi in epis:
        key, image_id = epi['EPI_KEY'], iid(epi['EPI_IMAGE_ID'])
        if key in seen or image_id not in by_id or identity_fields(by_id[image_id])[:3] != (epi['PTID'], epi['MRI_STUDY_DATE'], 'EPI'):
            raise ValueError('EPI manifest/source identity conflict')
        seen.add(key)
        t1_id = epi.get('PROPOSED_T1_IMAGE_ID', '')
        e, t = verified.get(image_id), verified.get(t1_id)
        reasons = []
        if not e: reasons.append('epi_BIDS_identity_pending')
        if not t: reasons.append('t1_BIDS_identity_pending_or_tied')
        if epi['T1_PAIRING_STATUS'] != 'same_day_proposed': reasons.append(epi['T1_PAIRING_STATUS'])
        if epi['EPI_METADATA_QC_STATE'] != 'documented': reasons.append('source_QC_pending')
        if true(epi['PAIRING_REVIEW_REQUIRED']): reasons.append('pairing_review_pending')
        if epi['PROTOCOL_SCOPE'] != 'GO_2_3': reasons.append('protocol_extension_pending')
        if t1_id:
            ti = by_id.get(t1_id, {})
            if (ti.get('PTID'), ti.get('MRI_STUDY_DATE'), ti.get('MODALITY')) != (epi['PTID'], epi['MRI_STUDY_DATE'], 'T1'):
                reasons.append('T1_subject_date_modality_conflict')
            if not true(ti.get('ELIGIBLE')) or ti.get('QC_STATUS') != 'pass' or ti.get('EXCLUSION_REASONS'):
                reasons.append('T1_source_QC_pending_or_blocked')
        ready = not reasons
        row = {**epi, 'VERIFIED_BIDS_BOLD_PATH': e['BIDS_NIFTI_PATH'] if e else '',
               'VERIFIED_BIDS_T1_PATH': t['BIDS_NIFTI_PATH'] if t else '',
               'BIDS_IDENTITY_STATUS': 'verified' if e and t else 'pending',
               'PREPROCESSING_READY': ready, 'ANALYSIS_READY': False,
               'READINESS_BLOCKERS': ';'.join(reasons) if reasons else 'postprocessing_and_scientific_QC_pending'}
        linked.append(row)
        if ready:
            plans.append({'epi_key': key, 'ptid': epi['PTID'], 'epi_image_id': image_id,
                          't1_image_id': t1_id, 'date': epi['MRI_STUDY_DATE'],
                          'phase': by_id[image_id]['SEARCH_PHASE'].replace(' ', ''),
                          'subject': e['SUBJECT'], 'session': e['SESSION'],
                          'epi': e, 't1': t, 'preprocessing_ready': True, 'analysis_ready': False})
    return image_rows, audit, linked, plans


def write_csv(path, rows, fields):
    with Path(path).open('x', encoding='utf-8', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=fields); w.writeheader(); w.writerows(rows)


def run(config):
    cfg = read_json(config)
    out = Path(cfg['output_dir']); prefix = cfg.get('prefix', '')
    inputs = {k: Path(cfg[k]).resolve() for k in ('images', 'epi_manifest', 'pairing_receipt')}
    inputs['config'] = Path(config).resolve()
    inputs.update({f'hash_evidence_{i}': Path(p).resolve() for i, p in enumerate(cfg['hash_evidence'])})
    before = {k: sha(p) for k, p in inputs.items()}
    prior = proof_files(inputs['pairing_receipt'])
    if sha(inputs['images']) != prior['inputs']['candidates']['sha256']:
        raise ValueError('Image registry does not match pairing evidence')
    epi_hashes = {m['sha256'] for m in prior['outputs'].values() if m['path'].endswith('04.epi-analysis-manifest.csv')}
    if sha(inputs['epi_manifest']) not in epi_hashes:
        raise ValueError('EPI manifest does not match pairing evidence')
    targets = {k: out / (prefix + n) for k, n in NAMES.items()}
    if any(p.exists() for p in targets.values()):
        raise FileExistsError('Use a new binding output directory/prefix')
    result = bind(read_csv(inputs['images']), read_csv(inputs['epi_manifest']), cfg['bids_roots'], load_expected(cfg['hash_evidence']))
    image_rows, files, linked, plans = result
    if not linked:
        raise ValueError('Empty EPI population')
    if before != {k: sha(p) for k, p in inputs.items()}:
        raise ValueError('Input changed during verification')
    # Recheck current file snapshots, not just a saved historical validator result.
    for row in files:
        if row['STATUS'] == 'verified' and (sha(row['NIFTI_PATH']) != row['NIFTI_SHA256'] or sha(row['JSON_PATH']) != row['JSON_SHA256']):
            raise ValueError('BIDS file changed during verification')
    summary = {'version': VERSION, 'source_images': len(image_rows), 'retained_epi': len(linked),
               'file_observations': len(files), 'file_status': dict(Counter(r['STATUS'] for r in files)),
               'image_status': dict(Counter(r['BIDS_STATUS'] for r in image_rows)),
               'preprocessing_ready': len(plans), 'held_epi': len(linked) - len(plans),
               'analysis_ready': 0, 'scope': 'identity/hash/header validation; no imaging quality approval or compute launch'}
    out.mkdir(parents=True, exist_ok=True)
    published = []
    try:
        for k, rows in [('images', image_rows), ('files', files), ('epi', linked)]:
            fields = list(rows[0]) if rows else ['STATUS', 'REASON']
            write_csv(targets[k], rows, fields); published.append(targets[k])
        for k, value in [('plans', plans), ('summary', summary)]:
            with targets[k].open('x') as f: json.dump(value, f, ensure_ascii=False, indent=2)
            published.append(targets[k])
        receipt = {'version': VERSION, 'created_utc': datetime.now(timezone.utc).isoformat(),
                   'inputs': {k: {'path': str(p), 'sha256': before[k]} for k, p in inputs.items()},
                   'outputs': {k: {'path': str(p.resolve()), 'sha256': sha(p)} for k, p in targets.items() if k != 'receipt'},
                   'code': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)}}
        with targets['receipt'].open('x') as f: json.dump(receipt, f, ensure_ascii=False, indent=2)
        published.append(targets['receipt'])
    except Exception:
        for p in published: p.unlink()
        raise
    return summary


def verify_plan(receipt, epi_key):
    proof = proof_files(receipt)
    if proof.get('version') != VERSION:
        raise ValueError('Unsupported binding artifact version')
    if sha(proof['code']['path']) != proof['code']['sha256']:
        raise ValueError('Binding validation code changed after artifact creation')
    # Revalidate upstream policy/registry provenance as well as binding outputs.
    proof_files(proof['inputs']['pairing_receipt']['path'])
    plans = read_json(proof['outputs']['plans']['path'])
    found = [p for p in plans if p['epi_key'] == epi_key]
    if len(found) != 1 or not found[0].get('preprocessing_ready'):
        raise ValueError('EPI is pending or not authorized by the verified pairing artifact')
    plan = found[0]
    for name in ('epi', 't1'):
        r = plan[name]
        if (r['PTID'], r['MRI_STUDY_DATE']) != (plan['ptid'], plan['date']):
            raise ValueError('Execution plan participant/date conflict')
        if r['IMAGE_ID'] != plan[name + '_image_id']:
            raise ValueError('Execution plan Image ID conflict')
        if sha(r['BIDS_NIFTI_PATH']) != r['NIFTI_SHA256'] or sha(r['BIDS_JSON_PATH']) != r['JSON_SHA256']:
            raise ValueError('Verified source BIDS changed after binding')
        if read_json(r['BIDS_JSON_PATH']).get('SeriesInstanceUID') != r['SERIES_UID']:
            raise ValueError('Verified source Series UID changed')
    return plan


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--config', type=Path, required=True)
    print(json.dumps(run(p.parse_args().config), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
