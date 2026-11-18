#!/usr/bin/env python3
"""Bind IDA collection rows to source QC and propose date-based EPI/T1 pairs.

This stage inventories metadata only. It neither downloads images nor approves
preprocessing or scientific inclusion. Visit labels are retained as provenance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import new_output, read, sha, snapshot, unchanged, verify_bundle, write
import pairing
from series_evidence import equipment, series_class

VERSION = 'date_based_selection_v2'
NAMES = {'candidates': '00.candidate-images.csv', 'policy': '01.pairing-policy.json',
         'pool': '02.t1-reference-pool.csv', 'links': '03.epi-t1-candidates.csv',
         'epi': '04.epi-analysis-manifest.csv', 'review': '05.pairing-review.csv',
         'summary': '06.summary.json', 'receipt': '07.run-manifest.json',
         'rows': '08.collection-row-audit.csv', 'download': '09.download-candidates.txt'}
ALIASES = {
    'IMAGE_ID': ('IMAGE_ID', 'Image Data ID', 'Image ID', 'Image_ID', 'image_id'),
    'PTID': ('PTID', 'Subject', 'Subject ID', 'Subject_ID', 'ParticipantID'),
    'MRI_STUDY_DATE': ('MRI_STUDY_DATE', 'Acq Date', 'Acquisition Date', 'Scan_Date', 'StudyDate', 'Study Date'),
    'SEARCH_PHASE': ('Phase', 'SEARCH_PHASE'),
    'DESCRIPTION': ('Description', 'Series Description', 'SeriesDescription'),
    'IMAGING_PROTOCOL': ('Imaging Protocol', 'Imaging.Protocol'),
    'SERIES_UID': ('SERIES_UID', 'SeriesInstanceUID', 'dicom_SeriesInstanceUID'),
    'VISCODE': ('VISCODE', 'VISCODE2', 'Visit'),
    'MANUFACTURER': ('MANUFACTURER', 'Manufacturer', 'ImagingProtocol___Manufacturer'),
    'SCANNER_MODEL': ('SCANNER_MODEL', 'ManufacturersModelName', 'Mfg Model', 'ImagingProtocol___MfgModel'),
    'FIELD_STRENGTH': ('FIELD_STRENGTH', 'MagneticFieldStrength', 'Field Strength', 'ImagingProtocol___FieldStrength'),
    'ACCELERATION': ('ACCELERATION',),
}
QC_FIELDS = ('QC_STATUS', 'QUALITY', 'SERIES_SELECTED', 'QC_REASON', 'QC_WARNINGS',
             'QC_SOURCE_ROWS', 'QC_MATCH_METHODS', 'SOURCE_QC_STATUS',
             'NFQ_RAW_QC_STATUS', 'NFQ_RAW_REASON', 'NFQ_RAW_SOURCE_ROWS')


def truth(value):
    return str(value).strip().lower() in {'true', '1', 'yes'}


def image_id(value):
    token = str(value).strip()
    if not re.fullmatch(r'[Ii]?[0-9]+', token):
        raise ValueError('Image ID must be a numeric LONI image identifier')
    token = token.removeprefix('I').removeprefix('i')
    return str(int(token))


def scan_date(value):
    token = str(value).strip()
    for fmt in ('%Y-%m-%d', '%Y%m%d', '%m/%d/%Y', '%m/%d/%Y %H:%M:%S'):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(token).date().isoformat()
    except ValueError as exc:
        raise ValueError('Missing or invalid actual acquisition date; VISCODE is not a date substitute') from exc


def phase(value):
    token = str(value).replace(' ', '').upper()
    if token not in {'ADNI1', 'ADNIGO', 'ADNI2', 'ADNI3', 'ADNI4'}:
        raise ValueError('Declare each collection phase explicitly: ADNI1/ADNIGO/ADNI2/ADNI3/ADNI4')
    return token


def cell(row, name, columns):
    """Accept explicit mappings or unambiguous known export headings."""
    if name in columns:
        if name == 'MRI_STUDY_DATE' and re.sub('[^a-z0-9]', '', columns[name].lower()) in {'archivedate','visit','viscode','viscode2','examdate'}:
            raise ValueError('Date mapping must identify an imaging acquisition date')
        if columns[name] not in row:
            raise ValueError('Mapped collection column is missing: ' + columns[name])
        return str(row[columns[name]]).strip()
    found = [str(row[k]).strip() for k in ALIASES[name] if str(row.get(k, '')).strip()]
    # VISCODE and Visit are distinct source labels, not competing identity keys.
    if name == 'VISCODE':
        return json.dumps({k: row[k] for k in ALIASES[name] if row.get(k)}, sort_keys=True)
    if len(set(found)) > 1:
        raise ValueError('Conflicting collection columns for ' + name + '; provide an explicit mapping')
    return found[0] if found else ''


def load_quality(directory):
    receipt = verify_bundle(directory, 'source_qc_v1')
    if 'image_qc.tsv' not in receipt['outputs_sha256']:
        raise ValueError('Source QC receipt must bind image_qc.tsv')
    result = {}
    for row in read(Path(directory) / 'image_qc.tsv', ('IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'MODALITY', 'SOURCE_QC_STATUS', 'SPINE_SERIES_TYPE', 'SPINE_DESCRIPTION')):
        iid = image_id(row['IMAGE_ID'])
        if iid in result:
            raise ValueError('Duplicate Image ID in source QC')
        if row['SOURCE_QC_STATUS'] not in {'pass', 'pending', 'blocked'}:
            raise ValueError('Unsupported source QC state')
        result[iid] = row
    return result


def normalize_collections(collections, quality):
    images, audit = {}, []
    for collection in collections:
        columns = collection.get('columns', {})
        if set(columns) - set(ALIASES):
            raise ValueError('Unsupported collection column mapping')
        declared_phase = phase(collection['phase']) if 'phase' in collection else None
        declared_modality = collection.get('modality')
        if declared_modality not in {None, 'T1', 'EPI'}:
            raise ValueError('Collection modality must be T1 or EPI; omit only for a source-QC classified mixed export')
        path = Path(collection['path']).resolve()
        rows = read(path)
        if not rows:
            raise ValueError('Empty collection export')
        for number, raw in enumerate(rows, 1):
            iid = image_id(cell(raw, 'IMAGE_ID', columns))
            q = quality.get(iid, {})
            ptid = cell(raw, 'PTID', columns)
            if not re.fullmatch(r'\d{3}_S_\d{4,}', ptid):
                raise ValueError('Invalid or missing collection participant identity')
            day = scan_date(cell(raw, 'MRI_STUDY_DATE', columns))
            source_phase = cell(raw, 'SEARCH_PHASE', columns)
            has_phase = any(k in raw for k in (columns.get('SEARCH_PHASE'), *ALIASES['SEARCH_PHASE']))
            row_phase = phase(source_phase) if source_phase else ''
            if declared_phase and has_phase and row_phase != declared_phase:
                raise ValueError('Declared collection phase contradicts or masks row Phase')
            if not has_phase and not declared_phase:
                raise ValueError('Missing row Phase; a reviewed uniform export requires a phase declaration')
            search_phase = row_phase or declared_phase or ''
            modality = declared_modality or q.get('MODALITY')
            if modality not in {'T1', 'EPI'}:
                raise ValueError('Collection image cannot be classified as T1/EPI; provide separate reviewed collections')
            supplied_uid = cell(raw, 'SERIES_UID', columns)
            reasons, warnings = [], []
            for key, value in [('PTID', ptid), ('MRI_STUDY_DATE', day), ('MODALITY', modality)]:
                if q and q.get(key) != value:
                    reasons.append('collection_source_conflict:' + key)
            if supplied_uid and q.get('SERIES_UID') and supplied_uid != q['SERIES_UID']:
                reasons.append('collection_source_conflict:SERIES_UID')
            if q.get('SOURCE_QC_STATUS') == 'blocked' or truth(q.get('QC_BLOCKED')):
                reasons.append('source_qc_blocked')
            if q.get('QC_STATUS', 'unknown') not in {'pass', 'unknown'}:
                reasons.append('source_quality_not_eligible')
            if not q:
                warnings.append('source_qc_missing')
            if q.get('SOURCE_QC_STATUS') != 'pass':
                warnings.append('source_qc_not_confirmed')
            desc = cell(raw, 'DESCRIPTION', columns)
            category, evidence = series_class(modality, desc, q)
            scanner, scanner_warnings = equipment(raw, columns, cell, q)
            warnings.extend(scanner_warnings)
            if not search_phase:
                warnings.append('row_phase_missing')
            if category != 'target':
                warnings.append(evidence)
            if category == 'non_target':
                reasons.append(evidence)
            protocol_phase = str(q.get('MRI_PROTOCOL_PHASE', '')).replace(' ', '').upper()
            if protocol_phase and protocol_phase != search_phase and {protocol_phase, search_phase} - {'ADNIGO', 'ADNI2', 'ADNIGO/ADNI2'}:
                warnings.append('protocol_search_phase_mismatch')
            row = {'PTID': ptid, 'MRI_STUDY_DATE': day, 'MODALITY': modality,
                   'IMAGE_ID': iid, 'SERIES_UID': supplied_uid or q.get('SERIES_UID', ''),
                   'SEARCH_PHASE': search_phase, 'PHASE_SOURCE': 'row' if has_phase else 'uniform_declaration',
                   'MRI_PROTOCOL_PHASE': protocol_phase, 'SEARCH_DESCRIPTION': desc,
                   'SPINE_SERIES_TYPE': q.get('SPINE_SERIES_TYPE',''), 'SPINE_DESCRIPTION': q.get('SPINE_DESCRIPTION',''),
                   'SERIES_CLASS': category, 'CLASS_REASON': evidence,
                   **{k: q.get(k, '') for k in QC_FIELDS},
                   **scanner, 'ACCELERATION': cell(raw, 'ACCELERATION', columns),
                   'ELIGIBLE': not reasons, 'EXCLUSION_REASONS': ';'.join(reasons),
                   'REVIEW_FLAGS': ';'.join(warnings)}
            row['QC_STATUS'] = q.get('QC_STATUS') or 'unknown'
            if not row['SOURCE_QC_STATUS']:
                row['SOURCE_QC_STATUS'] = 'pending'
            if iid in images and row != images[iid]:
                raise ValueError('Conflicting collection records for the same Image ID; no first-row selection')
            images[iid] = row
            audit.append({'SOURCE_FILE': str(path), 'SOURCE_ROW': number, 'IMAGE_ID': iid,
                          'PTID': ptid, 'MRI_STUDY_DATE': day, 'MODALITY': modality,
                          'VISIT_LABELS': cell(raw, 'VISCODE', columns),
                          'SEARCH_PHASE': search_phase, 'PHASE_SOURCE': row['PHASE_SOURCE'],
                          'SERIES_CLASS': category, 'CLASS_REASON': evidence,
                          'SOURCE_QC_STATUS': row['SOURCE_QC_STATUS'], 'EXCLUSION_REASONS': row['EXCLUSION_REASONS']})
    return sorted(images.values(), key=lambda r: (r['PTID'], r['MRI_STUDY_DATE'], r['MODALITY'], int(r['IMAGE_ID']))), audit


def apply_exclusions(images, path):
    """Known conversion/ST failures require exact image, participant, date and modality."""
    by_id = {r['IMAGE_ID']: r for r in images}
    for item in read(path, ('IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'MODALITY', 'REASON', 'CONFIRMED')):
        iid = image_id(item['IMAGE_ID'])
        if not truth(item['CONFIRMED']) or not item['REASON'].strip():
            raise ValueError('Exclusion ledger requires confirmed evidence and a reason')
        if iid not in by_id:
            raise ValueError('Exclusion ledger Image ID is absent from the collection inventory')
        row = by_id[iid]
        if any(row[k] != item[k] for k in ('PTID', 'MRI_STUDY_DATE', 'MODALITY')):
            raise ValueError('Exclusion ledger identity conflict')
        row['ELIGIBLE'] = False
        row['EXCLUSION_REASONS'] = ';'.join(filter(None, [row['EXCLUSION_REASONS'], item['REASON']]))


def run(config):
    config = Path(config).resolve()
    cfg = json.loads(config.read_text())
    if set(cfg) - {'collections', 'source_qc', 'output_dir', 'policy', 'confirmed_exclusions'}:
        raise ValueError('Unsupported selection configuration key')
    collections = cfg['collections']
    if not isinstance(collections, list) or not collections:
        raise ValueError('Provide at least one explicit collection export')
    for entry in collections:
        if set(entry) - {'path', 'phase', 'modality', 'columns'}:
            raise ValueError('Unsupported collection configuration key')
        if not Path(entry['path']).is_absolute():
            raise ValueError('Collection paths must be absolute')
    qdir = Path(cfg['source_qc']).resolve()
    inputs = {'config': config, 'source_qc_receipt': qdir / 'artifact.json', 'source_qc': qdir / 'image_qc.tsv'}
    inputs.update({f'collection_{i}': Path(c['path']).resolve() for i, c in enumerate(collections)})
    if cfg.get('confirmed_exclusions'):
        inputs['confirmed_exclusions'] = Path(cfg['confirmed_exclusions']).resolve()
    out = new_output(cfg['output_dir'], inputs.values())
    hashes = snapshot(inputs.values())
    quality = load_quality(qdir)
    images, row_audit = normalize_collections(collections, quality)
    if 'confirmed_exclusions' in inputs:
        apply_exclusions(images, inputs['confirmed_exclusions'])
    for row in images:
        # Keep the inventory and the strict download contract separate. Preserve specific reasons.
        blockers = list(filter(None, row['EXCLUSION_REASONS'].split(';')))
        if row['SERIES_CLASS'] != 'target':
            blockers.append(row['CLASS_REASON'])
        if row['SOURCE_QC_STATUS'] != 'pass':
            blockers.append('source_qc_' + row['SOURCE_QC_STATUS'])
            if row['QC_STATUS'] != 'pass' and row['QC_REASON']:
                blockers.append(row['QC_REASON'])
            if row['MODALITY'] == 'EPI' and row['NFQ_RAW_QC_STATUS'] != 'pass' and row['NFQ_RAW_REASON']:
                blockers.append(row['NFQ_RAW_REASON'])
        blockers.extend(flag for flag in row['REVIEW_FLAGS'].split(';')
                        if flag.startswith(('scanner_evidence_conflict:', 'invalid_scanner_value:', 'protocol_search_phase_mismatch', 'row_phase_missing')))
        row['DOWNLOAD_REASONS'] = ';'.join(dict.fromkeys(blockers)) or 'target_exact_identity_and_source_qc_pass'
        row['DOWNLOAD_ELIGIBLE'] = not blockers
    policy = pairing.load_policy(cfg.get('policy'))
    pool, links, epis = pairing.build_pairs([r for r in images if r['SERIES_CLASS'] != 'non_target'], policy)
    summary = {'images': len(images), 'collection_rows': len(row_audit), 'epi_images': len(epis),
               'download_by_modality': dict(Counter(r['MODALITY'] for r in images if r['DOWNLOAD_ELIGIBLE'])),
               'series_class': dict(Counter(r['SERIES_CLASS'] for r in images)),
               'participants': len({r['PTID'] for r in epis}),
               'pairing_status': dict(Counter(r['T1_PAIRING_STATUS'] for r in epis)),
               'preprocessing_ready': 0, 'analysis_ready': 0,
               'scope': 'Source metadata and T1 reference proposals; clinical, physical and final imaging QC remain separate'}
    unchanged(hashes)
    out.mkdir(parents=True)
    write(out / NAMES['candidates'], images)
    write(out / NAMES['rows'], row_audit)
    write(out / NAMES['pool'], pool, list(pool[0]) if pool else ['IMAGE_ID', 'REFERENCE_ELIGIBLE'])
    write(out / NAMES['links'], links, list(links[0]) if links else ['EPI_KEY', 'T1_IMAGE_ID'])
    write(out / NAMES['epi'], epis, pairing.EPI_FIELDS)
    write(out / NAMES['review'], [r for r in epis if truth(r['PAIRING_REVIEW_REQUIRED'])], pairing.EPI_FIELDS)
    for key, data in [('policy', policy), ('summary', summary)]:
        (out / NAMES[key]).write_text(json.dumps(data, indent=2) + '\n')
    # Only confirmed target acquisitions belong in the manual download list.
    (out / NAMES['download']).write_text(''.join('I' + r['IMAGE_ID'] + '\n' for r in images if r['DOWNLOAD_ELIGIBLE']))
    unchanged(hashes)
    receipt = {'kind': VERSION, 'created_utc': datetime.now(timezone.utc).isoformat(),
               'inputs': {k: {'path': str(p), 'sha256': hashes[str(p)]} for k, p in inputs.items()},
               'outputs': {k: {'path': str(out / name), 'sha256': sha(out / name)} for k, name in NAMES.items() if k != 'receipt'},
               'implementation_sha256': {name: sha(Path(__file__).parent / name) for name in ('run.py', 'pairing.py', 'series_evidence.py', '../scanner_evidence.py')},
               'analysis_ready': False, 'summary': summary}
    (out / NAMES['receipt']).write_text(json.dumps(receipt, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.config), indent=2))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
