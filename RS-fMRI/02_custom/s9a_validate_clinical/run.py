#!/usr/bin/env python3
"""Date- and identity-aware validation of clinical data for included imaging runs."""
import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import finish, new_output, read, snapshot, unchanged, write, sha

STAGES = {'1': 'CN', '2': 'MCI', '3': 'Dementia'}
ENTITIES = ('sub', 'ses', 'task', 'acq', 'run', 'echo', 'dir', 'rec')


def known(value):
    value = str(value or '').strip()
    return '' if value.lower() in {'', 'na', 'n/a', 'nan', '-1', '-4'} else value


def phase(value):
    value = re.sub(r'[^A-Za-z0-9]', '', str(value)).upper()
    return value if value in {'ADNI1', 'ADNIGO', 'ADNI2', 'ADNI3', 'ADNI4'} else ''


def date_value(value):
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def ptid_from_sub(value):
    match = re.fullmatch(r'(?:sub-)?(?:ADNI)?(\d{3})_?S_?(\d{4,})', value, re.IGNORECASE)
    if not match:
        raise ValueError('Invalid imaging subject identifier')
    return match[1] + '_S_' + match[2]


def rid(row):
    participant = row.get('PTID') or row.get('Subject_ID') or row.get('ParticipantID')
    derived = int(ptid_from_sub(participant).split('_')[-1]) if participant else None
    raw = row.get('RID') or row.get('SUBJID')
    if raw and not re.fullmatch(r'\d+', str(raw).strip()):
        raise ValueError('Invalid clinical RID')
    explicit = int(raw) if raw else None
    if explicit is not None and derived is not None and explicit != derived:
        raise ValueError('Clinical PTID/RID identity conflict')
    if explicit is None and derived is None:
        raise ValueError('Clinical table requires PTID, RID or SUBJID')
    return derived if derived is not None else explicit


def consensus(values, allowed=None):
    values = [known(v) for v in values]
    present = set(values) - {''}
    if not present:
        return '', 'all_missing'
    if allowed is not None and not present <= set(allowed):
        return '', 'invalid_code'
    if len(present) > 1:
        return '', 'conflicting_ties'
    if '' in values:
        return '', 'partial_missing_tie'
    return next(iter(present)), 'complete_consensus'


def indexed(rows, table, date_column=None):
    by_id, audit = defaultdict(list), []
    for number, row in enumerate(rows, 1):
        identifier = rid(row)
        dt = date_value(row.get(date_column, '')) if date_column else None
        reasons = []
        if known(row.get('HAS_QC_ERROR')).lower() in {'1', 'true'}:
            reasons.append('source_qc_error')
        if date_column and dt is None:
            reasons.append('missing_or_invalid_date')
        if table == 'DXSUM' and (row.get('DIAGNOSIS') not in STAGES or not phase(row.get('PHASE', ''))):
            reasons.append('invalid_diagnosis_or_phase')
        audit.append({'TABLE': table, 'SOURCE_ROW': number, 'ELIGIBLE': not reasons, 'REASONS': ';'.join(reasons)})
        if not reasons:
            by_id[identifier].append((number, row, dt))
    return by_id, audit


def nearest(items, scan, direction='nearest'):
    candidates = [r for r in items if direction != 'past' or r[2] <= scan]
    if not candidates:
        return [], None
    gap = min(abs((r[2] - scan).days) for r in candidates)
    return [r for r in candidates if abs((r[2] - scan).days) == gap], gap


def image_id(row):
    values = {str(row[k]).strip().lstrip('Ii') for k in ('IMAGE_ID', 'Image_ID', 'image_id') if row.get(k)}
    if len(values) != 1 or not next(iter(values)).isdigit():
        return ''
    return str(int(next(iter(values))))


def link_uids(row):
    return {known(row.get(k)) for k in ('dicom_SeriesInstanceUID', 'SERIES_UID', 'SeriesInstanceUID')} - {''}


def link_subject(row):
    identities = {ptid_from_sub(row[k]) for k in ('sub', 'PTID', 'Subject_ID') if row.get(k)}
    if len(identities) != 1:
        raise ValueError('Missing or conflicting scan-link subject identity')
    participant = next(iter(identities))
    if row.get('RID') and rid(row) != int(participant.split('_')[-1]):
        raise ValueError('Scan-link RID disagrees with subject')
    return participant


def link_session(row):
    if row.get('ses'):
        return row['ses']
    value = str(row.get('VISCODE', '')).lower()
    if value == 'bl':
        return 'ses-M000'
    if re.fullmatch(r'm\d+', value):
        return f'ses-M{int(value[1:]):03}'
    return ''


def classify(dx):
    diagnosis, resolution = consensus([r[1]['DIAGNOSIS'] for r in dx], STAGES)
    if not diagnosis:
        return {'DIAGNOSIS': '', 'CLINICAL_STAGE': '', 'CLINICAL_ETIOLOGY': 'unknown',
                'DIAGNOSIS_NEW': '', 'DIAGNOSIS_RESOLUTION': resolution}, False
    stage = STAGES[diagnosis]
    field = 'DXMDUE' if diagnosis == '2' else 'DXDDUE'
    if diagnosis == '1':
        cause, cause_status = '', 'not_applicable_CN'
        etiology = 'not_applicable_CN'
    elif diagnosis == '3' and any(phase(r[1].get('PHASE', '')) == 'ADNI1' for r in dx):
        cause, cause_status, etiology = '', 'unsupported_ADNI1_dementia_mapping', 'unknown'
    else:
        cause, cause_status = consensus([r[1].get(field, '') for r in dx], {'1', '2'})
        etiology = {'1': 'AD_suspected', '2': 'other_suspected'}.get(cause, 'unknown')
    return {'DIAGNOSIS': diagnosis, 'CLINICAL_STAGE': stage, 'CLINICAL_ETIOLOGY': etiology,
            'DIAGNOSIS_NEW': 'CN' if diagnosis == '1' else stage + '_' + etiology,
            'DIAGNOSIS_RESOLUTION': resolution, 'ETIOLOGY_FIELD': '' if diagnosis == '1' else field,
            'ETIOLOGY_CODE': cause, 'ETIOLOGY_RESOLUTION': cause_status}, True


def process(included, scan_links, dxsum, ptdemog, output_dir, apoe=None, adsl=None, dm=None,
            max_days=28, direction='nearest'):
    if max_days < 0 or direction not in {'nearest', 'past'}:
        raise ValueError('Invalid diagnosis window or direction')
    paths = [included, scan_links, dxsum, ptdemog] + [p for p in (apoe, adsl, dm) if p]
    output = new_output(output_dir, paths)
    hashes = snapshot(paths)
    scans = read(included, ('sub', 'ses'))
    if not scans:
        raise ValueError('No included runs to validate')
    links = read(scan_links)
    tables = {'DXSUM': (read(dxsum, ('DIAGNOSIS', 'EXAMDATE', 'PHASE')), 'EXAMDATE'),
              'PTDEMOG': (read(ptdemog, ('VISDATE',)), 'VISDATE')}
    for name, path in [('APOERES', apoe), ('ADSL', adsl), ('DM', dm)]:
        if path:
            tables[name] = (read(path), None)
    indexes, eligibility = {}, []
    for name, (rows, date_column) in tables.items():
        indexes[name], audit = indexed(rows, name, date_column)
        eligibility.extend(audit)
    link_index = defaultdict(list)
    for number, row in enumerate(links, 1):
        link_index[(link_subject(row), link_session(row))].append((number, row))
    result, raw_ledger, seen = [], [], set()
    for input_row, scan in enumerate(scans, 1):
        key = tuple(scan.get(k, '') for k in ENTITIES)
        if key in seen:
            raise ValueError('Duplicate included run identity; preserve all BIDS entities explicitly')
        seen.add(key)
        ptid = ptid_from_sub(scan['sub']); identifier = int(ptid.split('_')[-1])
        for field in ('PTID', 'Subject_ID'):
            if scan.get(field) and ptid_from_sub(scan[field]) != ptid:
                raise ValueError('Included row subject identity conflict')
        if scan.get('RID') and rid(scan) != identifier:
            raise ValueError('Included row RID disagrees with subject')
        for index in indexes.values():
            for _, raw, _ in index.get(identifier, []):
                participant = raw.get('PTID') or raw.get('Subject_ID') or raw.get('ParticipantID')
                if participant and ptid_from_sub(participant) != ptid:
                    raise ValueError('Clinical source PTID disagrees with imaging subject for this RID')
        # A mastersheet may have multiple phases/dates for a visit code. Never take its first row.
        matches = [(n, r) for n, r in link_index[(ptid, scan['ses'])]
                   if all(not r.get(k) or r[k] == scan.get(k, '') for k in ENTITIES[2:])]
        identity = {(image_id(r), r.get('Scan_Date', ''), ';'.join(sorted(link_uids(r))),
                     phase(r.get('Phase', r.get('MRI_PROTOCOL_PHASE', '')))) for _, r in matches}
        row = dict(scan)
        if 'DIAGNOSIS' in row:
            row['UPSTREAM_DIAGNOSIS_ORIGINAL'] = row.pop('DIAGNOSIS')
        row.update(INPUT_ROW=input_row, PTID=ptid, IMAGE_ID='', MRI_STUDY_DATE='',
                   ANALYSIS_READY=False, BIOLOGICAL_AD_STATUS='not_inferred')
        reasons = []
        if any(len(link_uids(r)) > 1 for _, r in matches):
            reasons.append('conflicting_scan_link_uid')
        if len(identity) != 1 or not next(iter(identity), ('', '', ''))[0]:
            reasons.append('missing_or_ambiguous_scan_identity')
        scan_date = date_value(next(iter(identity))[1]) if len(identity) == 1 else None
        if scan_date is None:
            reasons.append('scan_date_not_verified')
        if reasons:
            row.update(CLINICAL_STATUS='hold', CLINICAL_REASONS=';'.join(reasons))
            result.append(row)
            continue
        iid, _, uid, scan_phase = next(iter(identity))
        row.update(IMAGE_ID=iid, MRI_STUDY_DATE=scan_date.isoformat(), SERIES_UID=uid,
                   SCAN_LINK_SOURCE_ROWS=';'.join(str(n) for n, _ in matches))
        for number, raw in matches:
            raw_ledger.append({'INPUT_ROW': input_row, 'TABLE': 'SCAN_LINKS', 'SOURCE_ROW': number, 'RAW_JSON': json.dumps(raw, ensure_ascii=False)})
        dx, gap = nearest(indexes['DXSUM'].get(identifier, []), scan_date, direction)
        pt, ptgap = nearest(indexes['PTDEMOG'].get(identifier, []), scan_date)
        classified, valid_dx = classify(dx)
        row.update(classified, DX_DATE_DIFF_DAYS='' if gap is None else gap,
                   DX_EXAMDATES=';'.join(r[2].isoformat() for r in dx), DXSUM_TIE_COUNT=len(dx),
                   DX_SOURCE_ROWS=';'.join(str(r[0]) for r in dx),
                   DX_SIGNED_DAYS=';'.join(str((r[2] - scan_date).days) for r in dx),
                   DX_USES_FUTURE_VISIT=any(r[2] > scan_date for r in dx),
                   SCAN_DXSUM_PHASE_MISMATCH=any(scan_phase not in {'', phase(r[1].get('PHASE', ''))} for r in dx),
                   PTDEMOG_DATE_DIFF_DAYS='' if ptgap is None else ptgap,
                   PTDEMOG_GAP_OVER_365_DAYS=ptgap is not None and ptgap > 365,
                   PTDEMOG_SOURCE_ROWS=';'.join(str(r[0]) for r in pt), PTDEMOG_TIE_COUNT=len(pt))
        if not valid_dx:
            reasons.append('missing_or_conflicting_diagnosis')
        if gap is None or gap > max_days:
            reasons.append('diagnosis_gap_over_window')
        if not pt:
            reasons.append('missing_dated_demographics')
        education, edu_resolution = consensus([r[1].get('PTEDUCAT', '') for r in pt])
        if education and not re.fullmatch(r'\d+', education):
            education, edu_resolution = '', 'invalid_value'
        row.update(EDUCATION_PTEDUCAT=education, EDUCATION_RESOLUTION=edu_resolution,
                   EDUCATION_MISSING=not bool(education),
                   EDUCATION_VARIES_ACROSS_VALID_RECORDS=len({known(r[1].get('PTEDUCAT', '')) for r in indexes['PTDEMOG'].get(identifier, [])} - {''}) > 1)
        births = {known(r[1].get('PTDOB', '')) for r in indexes['PTDEMOG'].get(identifier, [])} - {''}
        approx_age = ''
        if len(births) == 1 and re.fullmatch(r'(0[1-9]|1[0-2])/\d{4}', next(iter(births))):
            month, year = map(int, next(iter(births)).split('/'))
            candidate = ((scan_date.year - year) * 12 + scan_date.month - month) / 12
            if candidate > 0:
                approx_age = round(candidate, 4)
        ages = []
        for _, link in matches:
            value = link.get('Age', link.get('SEARCH_AGE', ''))
            try:
                age = float(value)
                if math.isfinite(age) and age > 0:
                    ages.append(str(age))
                else:
                    ages.append('')
            except (ValueError, TypeError):
                ages.append('')
        search_age, age_resolution = consensus(ages)
        row.update(MRI_AGE_YEARS=search_age, MRI_AGE_SOURCE='scan_link_age' if search_age else 'unknown',
                   AGE_RESOLUTION=age_resolution, MRI_AGE_FROM_PTDOB_APPROX=approx_age,
                   PTDOB_CONFLICT=len(births) > 1,
                   AGE_SEARCH_PTDOB_DIFF_OVER_0_5=bool(search_age and approx_age != '' and abs(float(search_age) - approx_age) > 0.5))
        for field, dest in [('PTHAND', 'HANDEDNESS_CODE'), ('PTETHCAT', 'ETHNICITY_CODE'), ('PTRACCAT', 'RACE_CODE')]:
            value, status = consensus([r[1].get(field, '') for r in pt])
            row.update({dest: value, dest + '_RESOLUTION': status})
        sex_values = []
        for _, raw, _ in pt:
            codes = [known(raw.get(k)) for k in ('LEGACY_PARTICIPANT_GENDER_FILLED', 'ADNI4_SEX_ASSIGNED_AT_BIRTH_FILLED', 'PTGENDER')]
            value, _ = consensus([v for v in codes if v], {'1', '2'})
            sex_values.append({'1': 'Male', '2': 'Female'}.get(value, ''))
        for name, path in [('ADSL', adsl), ('DM', dm)]:
            if path:
                aux = indexes[name].get(identifier, [])
                labels = {'M': 'Male', 'F': 'Female', 'MALE': 'Male', 'FEMALE': 'Female'}
                sex_values.extend([labels.get(known(r[1].get('SEX', '')).upper(), '') for r in aux] or [''])
        sex, sex_resolution = consensus(sex_values, {'Male', 'Female'})
        row.update(BIOLOGICAL_SEX=sex, SEX_RESOLUTION=sex_resolution,
                   SEX_CROSS_SOURCE_VALIDATED=bool(adsl and dm and sex))
        apo = indexes.get('APOERES', {}).get(identifier, [])
        genotype, genotype_status = consensus([r[1].get('GENOTYPE', '') for r in apo], {'2/2', '2/3', '2/4', '3/3', '3/4', '4/4'})
        row.update(APOE_GENOTYPE=genotype, APOE_RESOLUTION=genotype_status,
                   APOE4_ALLELE_COUNT=genotype.split('/').count('4') if genotype else '', APOE_MISSING=not bool(genotype))
        for table, selected in [('DXSUM', dx), ('PTDEMOG', pt), ('APOERES', apo),
                                ('ADSL', indexes.get('ADSL', {}).get(identifier, [])), ('DM', indexes.get('DM', {}).get(identifier, []))]:
            for number, raw, _ in selected:
                raw_ledger.append({'INPUT_ROW': input_row, 'TABLE': table, 'SOURCE_ROW': number, 'RAW_JSON': json.dumps(raw, ensure_ascii=False)})
        # No complete-case filtering for sex, education or APOE, and no latest-date reduction.
        row.update(CLINICAL_STATUS='hold' if reasons else 'pass', CLINICAL_REASONS=';'.join(reasons))
        result.append(row)
    image_runs = defaultdict(list)
    for row in result:
        if row.get('IMAGE_ID'):
            image_runs[row['IMAGE_ID']].append(row)
    for rows in image_runs.values():
        if len(rows) > 1:
            for row in rows:
                row['CLINICAL_STATUS'] = 'hold'
                row['CLINICAL_REASONS'] = ';'.join(filter(None, [row.get('CLINICAL_REASONS'), 'image_id_reused_for_multiple_runs']))
    unchanged(hashes)
    output.mkdir(parents=True)
    fields = list(dict.fromkeys(k for row in result for k in row))
    write(output / 'clinical_validation.tsv', [{k: r.get(k, '') for k in fields} for r in result], fields)
    write(output / 'clinically_validated_sessions.tsv', [{k: r.get(k, '') for k in fields} for r in result if r['CLINICAL_STATUS'] == 'pass'], fields)
    write(output / 'clinical_source_rows.tsv', raw_ledger, ['INPUT_ROW', 'TABLE', 'SOURCE_ROW', 'RAW_JSON'])
    write(output / 'clinical_source_eligibility.tsv', eligibility, ['TABLE', 'SOURCE_ROW', 'ELIGIBLE', 'REASONS'])
    return finish(output, 'clinical_validation_v1', hashes, {
        'runs': len(result), 'clinical_status': dict(Counter(r['CLINICAL_STATUS'] for r in result)),
        'implementation_sha256': sha(__file__), 'max_dx_days': max_days, 'dx_direction': direction, 'diagnosis_mapping': STAGES,
        'policy': 'All runs and nearest ties preserved; no APOE/education complete-case gate. Clinical validity alone is not research inclusion.'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('included', 'scan-links', 'dxsum', 'ptdemog', 'output-dir'):
        p.add_argument('--' + flag, required=True)
    for flag in ('apoe', 'adsl', 'dm'):
        p.add_argument('--' + flag)
    p.add_argument('--max-dx-days', type=int, default=28)
    p.add_argument('--dx-direction', choices=['nearest', 'past'], default='nearest')
    a = p.parse_args()
    try:
        result = process(a.included, a.scan_links, a.dxsum, a.ptdemog, a.output_dir,
                         a.apoe, a.adsl, a.dm, a.max_dx_days, a.dx_direction)
        print(json.dumps(result['summary'], ensure_ascii=False))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
