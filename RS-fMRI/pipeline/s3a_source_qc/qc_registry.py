#!/usr/bin/env python3
"""Read-only ADNI MRI quality registry, independent of selection and ST availability.

Unknown is NOT a pass. Consumers may retain unknown candidates as pending_qc,
but must never select QC_BLOCKED records. No source CSV/RDS is modified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

QUALITY_SOURCES = {'ADNI3_QC', 'GO2_QC'}
BLOCKED_STATUSES = {'fail', 'nonpass', 'conflict', 'hold'}
IDENTITY_FIELDS = ('PTID', 'RID', 'MRI_STUDY_DATE', 'SERIES_UID',
                   'STUDY_UID', 'LONI_STUDY', 'LONI_SERIES', 'SERIES_NUMBER')


def text(value):
    return str(value or '').strip()


def integer_id(value, prefix=''):
    raw = text(value)
    if not raw:
        return ''
    if prefix and raw.upper().startswith(prefix):
        raw = raw[1:]
    if not re.fullmatch(r'\d+', raw):
        raise ValueError(f'Invalid integer identifier {value!r}')
    return str(int(raw))


def date_key(value):
    raw = text(value)
    if not raw:
        return ''
    for fmt, candidate in (('%Y-%m-%d', raw[:10]), ('%Y%m%d', raw),
                           ('%m/%d/%Y', raw)):
        try:
            return datetime.strptime(candidate, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    raise ValueError(f'Invalid scan date {value!r}')


def modality(value):
    value = text(value).upper()
    if value in {'T1W', 'MT1', 'T1'}:
        return 'T1'
    if value in {'BOLD', 'EPB', 'FMRI'}:
        return 'EPI'
    return ''


def selected(value):
    value = text(value).upper()
    if value in {'TRUE', '1'}:
        return 'TRUE'
    if value in {'FALSE', '0'}:
        return 'FALSE'
    if not value:
        return ''
    raise ValueError(f'Unexpected SERIES_SELECTED: {value!r}')


def read_source(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows, seen, duplicates = [], set(), 0
        for row_number, row in enumerate(reader, 1):
            signature = tuple(row[k] for k in fields)
            if signature in seen:
                duplicates += 1
                continue
            seen.add(signature)
            rows.append((row_number, row))
    return rows, duplicates


def normalize(source, row, row_number):
    if source == 'MRIQC':
        ptid = text(row['ParticipantID'])
        return dict(
            IMAGE_ID=integer_id(row['image_id'], 'I'), PTID=ptid,
            RID=integer_id(ptid.split('_')[-1]),
            MRI_STUDY_DATE=date_key(row['StudyDate']),
            MODALITY=modality(row['SeriesType']), SERIES_UID=text(row['SeriesInstanceUID']),
            STUDY_UID=text(row['StudyInstanceUID']),
            LONI_STUDY=integer_id(row['LONIStudy'], 'S'),
            LONI_SERIES=integer_id(row['LONISeries'], 'S'),
            SERIES_NUMBER=integer_id(row['SeriesNumber']),
            MRI_PROTOCOL_PHASE=text(row['MRIProtocolPhase']),
            QUALITY='', SERIES_SELECTED='', STUDY_OVERALLPASS='',
            PROTOCOL_STATUS='', STUDY_PROTOCOL_STATUS='', COMMENTS='',
            SOURCE=source, SOURCE_ROW=row_number)
    if source == 'ADNI3_QC':
        return dict(
            IMAGE_ID=integer_id(row['LONI_IMAGE'], 'I'), PTID=text(row['PTID']),
            RID=integer_id(row['RID']), MRI_STUDY_DATE=date_key(row['SERIES_DATE']),
            MODALITY=modality(row['SERIES_TYPE']), SERIES_UID=text(row['SERIESINSTANCEUID']),
            STUDY_UID=text(row['STUDYINSTANCEUID']),
            LONI_STUDY=integer_id(row['LONI_STUDY'], 'S'),
            LONI_SERIES=integer_id(row['LONI_SERIES'], 'S'), SERIES_NUMBER='',
            MRI_PROTOCOL_PHASE='', QUALITY=text(row['SERIES_QUALITY']),
            SERIES_SELECTED=selected(row['SERIES_SELECTED']),
            STUDY_OVERALLPASS=text(row['STUDY_OVERALLPASS']),
            PROTOCOL_STATUS=text(row['PROTOCOL_STATUS']),
            STUDY_PROTOCOL_STATUS=text(row['STUDY_PROTOCOL_STATUS']),
            COMMENTS='; '.join(text(row[k]) for k in ('SERIES_COMMENTS', 'PROTOCOL_COMMENTS',
                                                     'STUDY_COMMENTS', 'STUDY_PROTOCOL_COMMENT') if text(row[k])),
            SOURCE=source, SOURCE_ROW=row_number)
    if source == 'GO2_QC':
        return dict(
            IMAGE_ID=integer_id(row['loni_image'], 'I'), PTID='', RID=integer_id(row['RID']),
            MRI_STUDY_DATE=date_key(row['series_date']), MODALITY=modality(row['series_type']),
            SERIES_UID='', STUDY_UID='',
            LONI_STUDY=integer_id(row['loni_study'], 'S'),
            LONI_SERIES=integer_id(row['loni_series'], 'S'),
            SERIES_NUMBER=integer_id(row['series_number']), MRI_PROTOCOL_PHASE='',
            QUALITY=text(row['series_quality']), SERIES_SELECTED=selected(row['series_selected']),
            STUDY_OVERALLPASS=text(row['study_overallpass']),
            PROTOCOL_STATUS='', STUDY_PROTOCOL_STATUS='',
            COMMENTS='; '.join(text(row[k]) for k in ('series_comments', 'study_comments') if text(row[k])),
            SOURCE=source, SOURCE_ROW=row_number)
    ptid = text(row['SUBJECTID'])
    return dict(IMAGE_ID=integer_id(row['IMAGEID'], 'I'), PTID=ptid,
                RID=integer_id(ptid.split('_')[-1]), MRI_STUDY_DATE=date_key(row['SCANDATE']),
                SOURCE=source, SOURCE_ROW=row_number, DELETION_DATE=date_key(row['DELETEDATE']))


def build_registry(paths):
    """Return (Image-ID-keyed dictionary, summary, source rows lacking image IDs)."""
    paths = {k: Path(v) for k, v in paths.items()}
    grouped, missing, sources = defaultdict(list), [], {}
    spine_by_series, link_audit = defaultdict(list), []
    source_order = sorted(paths, key=lambda s: (s != 'MRIQC', s))
    for source in source_order:
        path = paths[source]
        rows, duplicates = read_source(path)
        sources[source] = {'path': str(path), 'filename': path.name,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                           'raw_rows': len(rows) + duplicates, 'unique_rows': len(rows),
                           'exact_duplicate_rows_collapsed': duplicates}
        if source == 'GO2_QC':
            sources[source]['assessment_snapshot_note'] = (
                'Check assessment dates and update fields in the supplied GO/2 source; '
                'no assessment snapshot date is inferred from its filename.')
        for row_number, row in rows:
            item = normalize(source, row, row_number)
            item['RAW_IMAGE_ID'] = item['IMAGE_ID']
            item['LINK_METHOD'] = 'image-id' if item['IMAGE_ID'] else ''
            if not item['IMAGE_ID']:
                record = {'SOURCE': source, 'SOURCE_ROW': row_number,
                          'RAW_IMAGE_ID': '', 'RID': item.get('RID', ''),
                          'MRI_STUDY_DATE': item.get('MRI_STUDY_DATE', ''),
                          'LONI_SERIES': item.get('LONI_SERIES', ''),
                          'LONI_STUDY': item.get('LONI_STUDY', ''),
                          'MATCH_METHOD': 'none', 'MATCHED_IMAGE_IDS': '',
                          'QC_REASON': 'missing_image_id_not_joined'}
                # Only a uniquely identified T1/EPI series may supply a missing image ID.
                # A numeric LONI series ID is distinct from a DICOM SeriesInstanceUID.
                keys = ('LONI_SERIES', 'LONI_STUDY', 'RID', 'MRI_STUDY_DATE', 'MODALITY')
                targets = []
                if source == 'GO2_QC' and all(item.get(k) for k in keys):
                    targets = [x for x in spine_by_series[item['LONI_SERIES']]
                               if all(x.get(k) == item[k] for k in keys)]
                target_ids = sorted({x['IMAGE_ID'] for x in targets}, key=int)
                if target_ids:
                    method = 'loni-series-study-rid-date-modality'
                    record.update(MATCH_METHOD=method, MATCHED_IMAGE_IDS=';'.join(target_ids))
                    if len(target_ids) > 1:
                        record['QC_REASON'] = 'ambiguous_loni_series_fallback'
                    else:
                        target = targets[0]
                        number_conflict = (item.get('SERIES_NUMBER') and target.get('SERIES_NUMBER')
                                           and item['SERIES_NUMBER'] != target['SERIES_NUMBER'])
                        record['QC_REASON'] = ('fallback_series_number_conflict' if number_conflict
                                               else 'matched_by_loni_series_not_image_id')
                    for target_id in target_ids:
                        inferred = dict(item, IMAGE_ID=target_id, LINK_METHOD=method)
                        if len(target_ids) > 1:
                            inferred['LINK_CONFLICT'] = 'ambiguous_loni_series_fallback'
                        grouped[target_id].append(inferred)
                else:
                    missing.append(record)
                link_audit.append(record)
                continue
            grouped[item['IMAGE_ID']].append(item)
            if source == 'MRIQC':
                spine_by_series[item['LONI_SERIES']].append(item)

    registry = {}
    for image_id, records in grouped.items():
        canonical = next((x for x in records if x['SOURCE'] == 'MRIQC'), records[0])
        quality_records = [x for x in records if x['SOURCE'] in QUALITY_SOURCES]
        deletion_records = [x for x in records if x['SOURCE'] == 'DELETED']
        conflicts = sorted({x['LINK_CONFLICT'] for x in records if x.get('LINK_CONFLICT')})
        warnings = []
        for field in IDENTITY_FIELDS:
            values = {x.get(field, '') for x in records} - {''}
            if len(values) > 1:
                conflicts.append('identity_mismatch:' + field)
        types = {x.get('MODALITY', '') for x in records} - {''}
        if len(types) > 1:
            conflicts.append('identity_mismatch:MODALITY')
        grades = {x['QUALITY'] for x in quality_records} - {''}
        choices = {x['SERIES_SELECTED'] for x in quality_records} - {''}
        study_pass = {x['STUDY_OVERALLPASS'] for x in quality_records} - {''}
        if len(grades) > 1:
            conflicts.append('quality_conflict')
        if len(choices) > 1:
            conflicts.append('selected_conflict')
        if len(study_pass) > 1:
            conflicts.append('study_overallpass_conflict')
        used_sources = sorted({x['SOURCE'] for x in quality_records})
        if 'GO2_QC' in used_sources:
            warnings.append('go2_assessment_snapshot_requires_review')
            warnings.append('go2_series_uid_not_in_source_checked_image_rid_date_loni_ids')
        if any(x.get('LINK_METHOD', '') != 'image-id' for x in quality_records):
            warnings.append('source_image_id_missing_loni_series_link_used')
        if not any(x['SOURCE'] == 'MRIQC' for x in records):
            warnings.append('absent_from_current_mriqc_spine')
        if not canonical.get('MODALITY'):
            warnings.append('modality_not_t1_or_epi_or_unclassified')
        for field in ('PROTOCOL_STATUS', 'STUDY_PROTOCOL_STATUS'):
            values = sorted({x[field] for x in quality_records} - {'', '1'})
            if values:
                warnings.append(field.lower() + '_review:' + ','.join(values))
        if any(x.get('STUDY_OVERALLPASS') == '-1' for x in quality_records):
            warnings.append('study_overallpass_not_evaluated')
        quality = next(iter(grades)) if len(grades) == 1 else ';'.join(sorted(grades))
        if conflicts:
            status, reason = 'conflict', ';'.join(conflicts)
        elif deletion_records:
            status, reason = 'fail', 'listed_in_deleted_scans'
        elif quality == '4':
            status, reason = 'fail', 'series_quality_4_unusable'
        elif quality == '-1':
            status, reason = 'nonpass', 'series_quality_minus1_outside_pass_1_2_3'
        elif '0' in study_pass:
            status, reason = 'hold', 'study_overallpass_0_requires_review'
        elif quality in {'1', '2', '3'}:
            status, reason = 'pass', 'series_quality_1_2_3'
        else:
            status, reason = 'unknown', ('no_matched_quality_record' if not quality_records
                                         else 'quality_missing_or_undefined')
        if not choices:
            warnings.append('series_selected_unknown')
        if status == 'unknown':
            warnings.append('pending_qc_not_confirmed_pass')
        record = {
            'IMAGE_ID': image_id, 'PTID': canonical.get('PTID', ''),
            'RID': canonical.get('RID', ''),
            'MRI_STUDY_DATE': canonical.get('MRI_STUDY_DATE', ''),
            'MODALITY': canonical.get('MODALITY') or (next(iter(types)) if len(types) == 1 else ''),
            'SERIES_UID': canonical.get('SERIES_UID', ''),
            'MRI_PROTOCOL_PHASE': canonical.get('MRI_PROTOCOL_PHASE', ''),
            'QC_SOURCE': ';'.join(used_sources), 'QC_STATUS': status,
            'QUALITY': quality, 'SERIES_SELECTED': next(iter(choices)) if len(choices) == 1 else '',
            'QC_REASON': reason, 'QC_WARNINGS': ';'.join(sorted(set(warnings))),
            'QC_BLOCKED': status in BLOCKED_STATUSES,
            'QC_CONFIRMED_PASS': status == 'pass',
            'QC_SOURCE_FILES': ';'.join(str(paths[s]) for s in used_sources),
            'QC_SOURCE_ROWS': ';'.join(f'{x["SOURCE"]}:{x["SOURCE_ROW"]}' for x in quality_records),
            'QC_MATCH_METHODS': ';'.join(sorted({x.get('LINK_METHOD', 'image-id') for x in quality_records})),
            'QC_COMMENTS': ' | '.join(sorted({x['COMMENTS'] for x in quality_records if x['COMMENTS']})),
            'STUDY_OVERALLPASS': ';'.join(sorted(study_pass)),
            'PROTOCOL_STATUS': ';'.join(sorted({x['PROTOCOL_STATUS'] for x in quality_records} - {''})),
            'STUDY_PROTOCOL_STATUS': ';'.join(sorted({x['STUDY_PROTOCOL_STATUS'] for x in quality_records} - {''})),
            'DELETED_SCAN': bool(deletion_records),
            'DELETED_SOURCE_ROWS': ';'.join(str(x['SOURCE_ROW']) for x in deletion_records),
        }
        registry[image_id] = record

    uid_ids = defaultdict(set)
    for image_id, records in grouped.items():
        for rec in records:
            if rec.get('SERIES_UID'):
                uid_ids[rec['SERIES_UID']].add(image_id)
    duplicate_uids = {uid: sorted(ids) for uid, ids in uid_ids.items() if len(ids) > 1}
    for ids in duplicate_uids.values():
        for image_id in ids:
            item = registry[image_id]
            item['QC_STATUS'] = 'conflict'
            item['QC_BLOCKED'], item['QC_CONFIRMED_PASS'] = True, False
            item['QC_REASON'] += ';series_uid_maps_multiple_image_ids'
    summary = {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
        'registry_images': len(registry),
        'status_counts': dict(Counter(x['QC_STATUS'] for x in registry.values())),
        't1_epi_status_counts': dict(Counter(x['QC_STATUS'] for x in registry.values()
                                            if x['MODALITY'] in {'T1', 'EPI'})),
        'missing_image_id_rows': dict(Counter(x['SOURCE'] for x in missing)),
        'missing_image_id_source_link_audit': link_audit,
        'fallback_link_status_counts': dict(Counter(x['QC_REASON'] for x in link_audit)),
        'duplicate_series_uid_groups': duplicate_uids,
        'policy': {'pass': 'Consistent known series quality 1/2/3',
                   'fail': 'Series quality 4 or explicit Deleted Scans listing',
                   'nonpass': '-1, outside existing accepted 1/2/3; semantic label not inferred',
                   'unknown': 'Pending QC; lack of a record is neither pass nor fail',
                   'conflict': 'Identity/quality/selected/study status conflict; quarantine',
                   'hold': 'Known study_overallpass 0; review instead of silently selecting',
                   'protocol_status': 'Preserved warnings; code meanings not assumed',
                   'nfq': 'Handled separately by caller, independently of ST availability'},
    }
    return registry, summary, missing


def write_outputs(output_dir, registry, summary, missing):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = [registry[k] for k in sorted(registry, key=int)]
    with (output_dir / 'qc_registry.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ordered[0]))
        writer.writeheader()
        writer.writerows(ordered)
    (output_dir / 'qc_registry.json').write_text(json.dumps(registry, ensure_ascii=False), encoding='utf-8')
    (output_dir / 'qc_registry_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (output_dir / 'qc_unlinked_source_rows.json').write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding='utf-8')
    links = summary.get('missing_image_id_source_link_audit', [])
    if links:
        with (output_dir / 'qc_source_link_audit.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(links[0]))
            writer.writeheader()
            writer.writerows(links)
