#!/usr/bin/env python3
"""Combine source QC, nearest/28-day clinical validation and confirmed exclusions."""
import argparse
from collections import Counter
import csv
from datetime import date
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import finish, new_output, read, sha, snapshot, unchanged, verify_bundle, write

ENTITIES = ('sub', 'ses', 'task', 'acq', 'run', 'echo', 'dir', 'rec')


def identifier(value):
    match = re.fullmatch(r'[Ii]?(\d+)', str(value or '').strip())
    if not match:
        raise ValueError('Missing or invalid image identifier')
    return str(int(match[1]))


def participant(value):
    match = re.fullmatch(r'(?:sub-)?(?:ADNI)?(\d{3})_?S_?(\d{4,})', str(value or ''), re.IGNORECASE)
    if not match:
        raise ValueError('Missing or invalid participant identifier')
    return match[1] + '_S_' + match[2]


def scan_date(value):
    return date.fromisoformat(str(value).strip()[:10]).isoformat()


def bundle(directory, kind, required):
    directory = Path(directory).resolve()
    record = verify_bundle(directory, kind)
    if not set(required) <= set(record['outputs_sha256']):
        raise ValueError('Required artifact outputs are not hash-covered')
    return record, [directory / 'artifact.json', *[directory / f for f in record['outputs_sha256']]]


def exclusions(path, kind):
    """Only explicit reviewed evidence can declare ST absence or conversion failure."""
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        fields = csv.DictReader(f, delimiter='\t' if Path(path).suffix == '.tsv' else ',').fieldnames or []
    native = kind == 'st' and 'EPI_IMAGE_ID' in fields
    if kind == 'st':
        required = (['EPI_IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'final_analysis_status',
                     'final_slice_timing_class', 'full_dicom_recheck', 'nfq_usable_st', 'st_evidence_class']
                    if native else ['IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'ST_STATUS', 'EVIDENCE_REF'])
    else:
        required = ['IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'MODALITY', 'SELECTION_ACTION', 'ERROR_CLASS', 'ERROR_REASON']
    rows = read(path, required)
    result, audit = {}, []
    for number, row in enumerate(rows, 1):
        iid = identifier(row.get('EPI_IMAGE_ID') if native else row['IMAGE_ID'])
        ptid, dt = participant(row['PTID']), scan_date(row['MRI_STUDY_DATE'])
        modality = 'EPI' if kind == 'st' else row['MODALITY']
        if modality not in {'EPI', 'T1'} or (kind == 'st' and row.get('MODALITY', 'EPI') != 'EPI'):
            raise ValueError('Invalid exclusion modality')
        if kind == 'st':
            confirmed = (row['final_analysis_status'] == 'no_slice_timing_any_source'
                         and row['final_slice_timing_class'] == 'no_slice_timing'
                         and row['full_dicom_recheck'].strip().lower() in {'true', '1'}
                         and row['nfq_usable_st'].strip().lower() in {'false', '0'}
                         and row['st_evidence_class'] == 'not_found_anywhere') if native else (
                             row['ST_STATUS'] == 'confirmed_absent' and bool(row['EVIDENCE_REF'].strip()))
            if not confirmed:
                raise ValueError('ST table must contain only explicitly confirmed absence evidence')
            reason = 'confirmed_st_absence'
        else:
            if row['SELECTION_ACTION'] != 'exclude_before_date_and_image_selection' or not row['ERROR_CLASS'] or not row['ERROR_REASON']:
                raise ValueError('Conversion exclusions require a reviewed exclusion action and reason')
            reason = 'confirmed_conversion_failure'
        identity = (ptid, dt, modality)
        if iid in result and result[iid]['identity'] != identity:
            raise ValueError('Conflicting identities in exclusion ledger')
        entry = result.setdefault(iid, {'identity': identity, 'reason': reason, 'rows': []})
        entry['rows'].append(number)
        audit.append({'KIND': kind, 'SOURCE_ROW': number, 'IMAGE_ID': iid, 'PTID': ptid,
                      'MRI_STUDY_DATE': dt, 'MODALITY': modality, 'REASON': reason,
                      'RAW_JSON': json.dumps(row, ensure_ascii=False)})
    return result, audit


def process(source_qc, clinical, confirmed_st_absence, output_dir, conversion_failures=None):
    source_qc, clinical = Path(source_qc).resolve(), Path(clinical).resolve()
    _, quality_files = bundle(source_qc, 'source_qc_v1', ['image_qc.tsv'])
    clinical_record, clinical_files = bundle(clinical, 'clinical_validation_v2', ['clinical_validation.tsv', 'sex_derivation.tsv'])
    policy = clinical_record['summary']
    if policy.get('max_dx_days') != 28 or policy.get('dx_direction') != 'nearest' or policy.get('demographics_policy') != 'subject_static_sex_team_excluded_v1':
        raise ValueError('Final inclusion requires corrected clinical validation with nearest/28-day policy')
    paths = quality_files + clinical_files + [confirmed_st_absence] + ([conversion_failures] if conversion_failures else [])
    output = new_output(output_dir, paths)
    hashes = snapshot(paths)
    quality = {}
    for row in read(source_qc / 'image_qc.tsv', ['IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'MODALITY', 'SOURCE_QC_STATUS']):
        iid = identifier(row['IMAGE_ID'])
        if iid in quality or row['SOURCE_QC_STATUS'] not in {'pass', 'pending', 'blocked'}:
            raise ValueError('Duplicate QC image or invalid source QC state')
        quality[iid] = row
    st, ledger = exclusions(confirmed_st_absence, 'st')
    conversions = {}
    if conversion_failures:
        conversions, extra = exclusions(conversion_failures, 'conversion')
        ledger.extend(extra)
    rows = read(clinical / 'clinical_validation.tsv', ['sub', 'ses', 'PTID', 'IMAGE_ID', 'MRI_STUDY_DATE', 'CLINICAL_STATUS'])
    if not rows:
        raise ValueError('Empty clinical cohort')
    duplicates = Counter(r['IMAGE_ID'] for r in rows if r['IMAGE_ID'])
    result, seen = [], set()
    for original in rows:
        key = tuple(original.get(k, '') for k in ENTITIES)
        if key in seen:
            raise ValueError('Duplicate clinical run identity')
        seen.add(key)
        if original['CLINICAL_STATUS'] not in {'pass', 'hold'}:
            raise ValueError('Unknown clinical state')
        row = dict(original)
        blocked, holds, warnings = [], [], []
        if not row['ses'].strip():
            holds.append('missing_run_session')
        iid = ''
        try:
            iid = identifier(row['IMAGE_ID'])
            ptid, dt = participant(row['PTID']), scan_date(row['MRI_STUDY_DATE'])
            if participant(row['sub']) != ptid:
                holds.append('clinical_subject_identity_conflict')
            if row.get('SOURCE_IMAGE_ID') and identifier(row['SOURCE_IMAGE_ID']) != iid:
                holds.append('clinical_image_identity_conflict')
        except ValueError:
            ptid, dt = '', ''
            holds.append('clinical_scan_identity_unverified')
        evidence = quality.get(iid, {})
        state = evidence.get('SOURCE_QC_STATUS', 'missing')
        modality = evidence.get('MODALITY', '')
        if not evidence:
            holds.append('source_qc_image_missing')
        else:
            if (evidence['PTID'], evidence['MRI_STUDY_DATE']) != (ptid, dt):
                holds.append('source_qc_identity_conflict')
            if row.get('MODALITY') and row['MODALITY'] != modality:
                holds.append('source_qc_modality_conflict')
            if modality not in {'T1', 'EPI'}:
                holds.append('unsupported_source_modality')
            if row.get('SERIES_UID') and row['SERIES_UID'] != evidence.get('SERIES_UID'):
                holds.append('source_qc_series_uid_conflict')
            if not row.get('SERIES_UID'):
                warnings.append('clinical_uid_not_available')
            if state == 'blocked':
                blocked.append('source_qc_blocked')
        if duplicates[original['IMAGE_ID']] > 1:
            holds.append('image_id_reused_for_multiple_runs')
        if row['CLINICAL_STATUS'] != 'pass':
            blocked.append('clinical_conditions_not_met')
        else:
            gap = float(row.get('DX_DATE_DIFF_DAYS', 'inf') or 'inf')
            if not math.isfinite(gap) or not 0 <= gap <= 28:
                raise ValueError('Clinical pass contradicts the 28-day policy')
        imaging = row.get('final_qc_status', '')
        if imaging:
            if imaging == 'exclude':
                blocked.append('imaging_qc_excluded')
            elif imaging == 'pending_review':
                holds.append('imaging_review_pending')
            elif imaging != 'include':
                raise ValueError('Unknown S10 imaging QC state')
        if str(row.get('final_include', '')).strip():
            flag = str(row['final_include']).strip().lower()
            if flag not in {'true', 'false', '1', '0'}:
                raise ValueError('Invalid imaging include flag')
            flag = flag in {'true', '1'}
            if imaging and flag != (imaging == 'include'):
                holds.append('imaging_include_flag_conflict')
            elif not imaging and not flag:
                holds.append('imaging_review_not_confirmed')
        for registry in (st, conversions):
            if iid in registry:
                entry = registry[iid]
                if entry['identity'] != (ptid, dt, modality):
                    holds.append('exclusion_ledger_identity_conflict')
                else:
                    blocked.append(entry['reason'])
        status = 'excluded' if blocked else 'hold' if holds else 'pending' if state == 'pending' else 'eligible'
        row.update(INCLUSION_STATUS=status, INCLUDED_BY_METADATA_POLICY=status in {'eligible', 'pending'},
                   INCLUSION_REASONS=';'.join(sorted(set(blocked + holds))), INCLUSION_WARNINGS=';'.join(warnings),
                   SOURCE_QC_STATUS=state, SOURCE_MODALITY=modality,
                   ST_CONFIRMED_ABSENT=iid in st and st[iid]['identity'] == (ptid, dt, modality),
                   ST_EVIDENCE_SOURCE_ROWS=';'.join(map(str, st.get(iid, {}).get('rows', []))),
                   CONVERSION_FAILURE_SOURCE_ROWS=';'.join(map(str, conversions.get(iid, {}).get('rows', []))),
                   IMAGING_QC_EVIDENCE='s10_final_qc_status' if imaging else 'reviewed_input_required_not_verified_here',
                   ANALYSIS_READY=False, INCLUSION_SCOPE='source_qc_clinical_confirmed_exclusions_only')
        result.append(row)
    unchanged(hashes)
    output.mkdir(parents=True)
    fields = list(dict.fromkeys(k for r in result for k in r))
    write(output / 'inclusion_audit.tsv', result, fields)
    for name, statuses in [('retained_sessions.tsv', {'eligible', 'pending'}), ('pending_qc.tsv', {'pending'}),
                           ('excluded_sessions.tsv', {'excluded'}), ('held_sessions.tsv', {'hold'})]:
        write(output / name, [r for r in result if r['INCLUSION_STATUS'] in statuses], fields)
    write(output / 'confirmed_exclusion_evidence.tsv', ledger, ['KIND', 'SOURCE_ROW', 'IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'MODALITY', 'REASON', 'RAW_JSON'])
    return finish(output, 'final_inclusion_validation_v1', hashes, {
        'runs': len(result), 'status': dict(Counter(r['INCLUSION_STATUS'] for r in result)),
        'retained': sum(r['INCLUDED_BY_METADATA_POLICY'] for r in result),
        'reason_counts': dict(Counter(reason for r in result for reason in r['INCLUSION_REASONS'].split(';') if reason)),
        'max_dx_days': 28, 'dx_direction': 'nearest', 'pending_policy': 'retain_without_claiming_pass',
        'confirmed_st_images': len(st), 'conversion_exclusions_provided': conversion_failures is not None,
        'implementation_sha256': sha(__file__),
        'scope': 'Input imaging review status is preserved; no physical or visual QC is inferred. ANALYSIS_READY remains false.'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('source-qc', 'clinical', 'confirmed-st-absence', 'output-dir'):
        p.add_argument('--' + flag, required=True)
    p.add_argument('--conversion-failures')
    a = p.parse_args()
    try:
        record = process(a.source_qc, a.clinical, a.confirmed_st_absence, a.output_dir, a.conversion_failures)
        print(json.dumps(record['summary'], ensure_ascii=False))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
