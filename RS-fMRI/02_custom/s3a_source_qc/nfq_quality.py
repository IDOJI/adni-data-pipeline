"""Research NFQ matching rules, independent of slice-timing availability."""
import math
from collections import defaultdict
from qc_registry import date_key, integer_id, text

def seconds(value):
    raw = text(value)
    if not raw:
        return None
    parts = raw.split(':')
    if len(parts) != 3:
        return None
    try:
        h, m, s = map(float, parts)
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in (h, m, s)) or not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        return None
    return 3600 * h + 60 * m + s


def map_raw_nfq(spine_rows, raw_sources):
    """Return per-image evidence, ambiguous/identity holds, and raw-row audit.

    Composite match is exact RID/date/series number and absolute time <= 1s.
    Explicit image IDs are never silently replaced by a composite-key match.
    """
    spine, uids, composite = {}, defaultdict(set), defaultdict(list)
    for row in spine_rows:
        iid = integer_id(row['image_id'], 'I')
        item = dict(image_id=iid, ptid=row['ParticipantID'],
                    rid=integer_id(row['ParticipantID'].split('_')[-1]),
                    date=date_key(row['StudyDate']), number=integer_id(row['SeriesNumber']),
                    time=seconds(row['SeriesTime']), uid=text(row['SeriesInstanceUID']),
                    is_epi=row['SeriesType'].upper() == 'BOLD')
        if iid in spine:
            raise ValueError('Duplicate MRIQC image ID: ' + iid)
        spine[iid] = item
        if item['uid']:
            uids[item['uid']].add(iid)
        if item['is_epi']:
            composite[(item['rid'], item['date'], item['number'])].append(item)
    evidence, holds, audit = defaultdict(list), defaultdict(list), []
    for source, rows in raw_sources.items():
        for row_number, row in rows:
            iid = integer_id(row.get('LONIImage', ''), 'I')
            uid = text(row.get('SeriesInstanceUID', ''))
            ptid = text(row.get('ParticipantID', ''))
            rid = integer_id(row.get('RID', '')) or (integer_id(ptid.split('_')[-1]) if ptid else '')
            dt = date_key(row.get('StudyDate') or row.get('SERIESDATE') or row.get('SCANDATE'))
            series_number = integer_id(row.get('SeriesNumber') or row.get('SERIESNUMBER'))
            tm = seconds(row.get('SeriesTime') or row.get('SERIESTIME'))
            quality = text(row.get('OVERALLQC', ''))
            ref = f'{source}:{row_number}'
            targets, method, reason = [], '', ''
            if iid:
                method = 'image-id'
                targets = [iid] if iid in spine else []
                if not targets and uid and uids.get(uid):
                    for other in uids[uid]:
                        holds[other].append((ref, 'explicit_image_id_not_found_uid_points_elsewhere'))
                    reason = 'explicit_image_id_not_found_uid_points_elsewhere'
                elif not targets:
                    reason = 'image_id_not_in_mriqc'
            elif uid:
                method = 'series-uid'
                targets = sorted(uids.get(uid, set()))
                if not targets:
                    reason = 'series_uid_not_in_mriqc'
            else:
                method = 'rid-date-series-number-time'
                if not rid or not dt or not series_number or tm is None:
                    reason = 'incomplete_composite_key'
                else:
                    targets = [x['image_id'] for x in composite[(rid, dt, series_number)]
                               if x['time'] is not None and abs(tm - x['time']) <= 1.0]
                    if not targets:
                        reason = 'no_composite_candidate_within_one_second'
            targets = sorted(set(targets), key=int)
            if len(targets) > 1:
                reason = 'ambiguous_multiple_image_targets'
                for target in targets:
                    holds[target].append((ref, reason))
            elif len(targets) == 1:
                target = targets[0]
                item = spine[target]
                identity_errors = []
                if not item['is_epi']:
                    identity_errors.append('target_not_bold')
                if not rid or not dt:
                    identity_errors.append('missing_rid_or_date')
                if rid and rid != item['rid']:
                    identity_errors.append('rid_mismatch')
                if dt and dt != item['date']:
                    identity_errors.append('date_mismatch')
                if ptid and ptid != item['ptid']:
                    identity_errors.append('ptid_mismatch')
                if uid and item['uid'] and uid != item['uid']:
                    identity_errors.append('series_uid_mismatch')
                    for other in uids.get(uid, set()):
                        holds[other].append((ref, 'uid_points_to_different_explicit_image_id'))
                if identity_errors:
                    reason = 'identity_conflict:' + ','.join(identity_errors)
                    holds[target].append((ref, reason))
                else:
                    reason = 'matched'
                    evidence[target].append(dict(source=source, row=row_number, ref=ref,
                                                 quality=quality, method=method,
                                                 quality_field_present='OVERALLQC' in row))
            audit.append(dict(NFQ_SOURCE=source, NFQ_SOURCE_ROW=row_number,
                              NFQ_IMAGE_ID=iid, NFQ_RID=rid, NFQ_DATE=dt,
                              NFQ_OVERALLQC=quality, NFQ_MATCH_METHOD=method,
                              CANDIDATE_IMAGE_IDS=';'.join(targets), NFQ_MATCH_STATUS=reason))
    return spine, evidence, holds, audit


def candidate_qc(candidates, spine, evidence, holds):
    output = []
    for candidate in candidates:
        if candidate['MODALITY'] != 'EPI':
            continue
        iid = integer_id(candidate['IMAGE_ID'], 'I')
        ev, issues = evidence.get(iid, []), list(holds.get(iid, []))
        if iid not in spine:
            issues.append(('', 'candidate_absent_from_mriqc'))
        else:
            item = spine[iid]
            if item['ptid'] != candidate['PTID'] or item['date'] != candidate['MRI_STUDY_DATE']:
                issues.append(('', 'candidate_mriqc_identity_conflict'))
            if candidate.get('SERIES_UID') and item['uid'] != candidate['SERIES_UID']:
                issues.append(('', 'candidate_mriqc_uid_conflict'))
        grades = {x['quality'] for x in ev} - {''}
        if len(grades) > 1:
            issues.append(('', 'conflicting_raw_overallqc_values'))
        grade = next(iter(grades)) if len(grades) == 1 else ';'.join(sorted(grades))
        if issues:
            status, reason = 'hold', ';'.join(sorted({x[1] for x in issues}))
        elif grade == '4':
            status, reason = 'fail', 'raw_overallqc_4'
        elif grade in {'1', '2', '3'}:
            status, reason = 'pass', 'raw_overallqc_1_2_3'
        elif not ev:
            status, reason = 'unknown', 'no_unique_raw_nfq_match'
        else:
            status, reason = 'unknown', 'raw_overallqc_absent_or_undefined'
        output.append(dict(
            IMAGE_ID=iid, PTID=candidate['PTID'], MRI_STUDY_DATE=candidate['MRI_STUDY_DATE'],
            NFQ_RAW_QC_STATUS=status, NFQ_RAW_OVERALLQC=grade, NFQ_RAW_REASON=reason,
            NFQ_RAW_SOURCE_ROWS=';'.join(sorted({x['ref'] for x in ev} | {x[0] for x in issues if x[0]})),
            NFQ_RAW_MATCH_METHODS=';'.join(sorted({x['method'] for x in ev})),
            NFQ_RAW_MATCH_COUNT=len(ev),
            PREVIOUS_NFQ_OVERALLQC=candidate.get('NFQ_OVERALLQC', ''),
            PREVIOUS_NFQ_ST_USABLE=candidate.get('NFQ_ST_USABLE', ''),
            NFQ_RAW_ADDED_QC_EVIDENCE=bool(grade and not candidate.get('NFQ_OVERALLQC', ''))))
    return output
