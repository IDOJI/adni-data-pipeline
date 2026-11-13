#!/usr/bin/env python3
"""Validate upstream Step-5 output and write a lossless session handoff."""
import argparse
import csv
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import read as read_table, verify_bundle


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def session(value):
    value = value.strip()
    if value.lower() == 'bl':
        return 'M000'
    match = re.fullmatch(r'(?:ses-)?[Mm](\d{1,3})', value)
    if not match:
        raise ValueError('Expected Clinica bl/mNN/ses-MNNN session; no guessed screening or calendar-date mapping')
    return 'M' + match[1].zfill(3)


def write(path, rows, fields, delimiter=','):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)


def process(source, output, source_qc=None, require_confirmed=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents or output in repo.parents:
        raise ValueError('Handoff results must be outside the repository')
    if output == source or output in source.parents:
        raise ValueError('Output must not contain the source')
    if output.exists():
        raise ValueError('Use a new output directory')
    source_hash = digest(source)
    with source.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter='\t')
        if not {'Subject_ID', 'VISCODE'} <= set(reader.fieldnames or []):
            raise ValueError('Expected upstream final_heuristics.tsv with Subject_ID and VISCODE')
        rows = list(reader)
    if not rows:
        raise ValueError('No surviving sessions; refusing an empty handoff')
    if require_confirmed and not source_qc:
        raise ValueError('require-confirmed-qc requires a source QC artifact')
    quality, quality_hashes, audit = {}, {}, []
    if source_qc:
        directory = Path(source_qc).resolve()
        verify_bundle(directory, 'source_qc_v1')
        for name in ('artifact.json', 'image_qc.tsv'):
            quality_hashes[str(directory / name)] = digest(directory / name)
        for row in read_table(directory / 'image_qc.tsv', ('IMAGE_ID', 'SOURCE_QC_STATUS')):
            if row['IMAGE_ID'] in quality:
                raise ValueError('Duplicate source QC image identity')
            quality[row['IMAGE_ID']] = row
    pairs, grouped, seen = [], defaultdict(list), set()
    for row in rows:
        ptid = row['Subject_ID'].strip()
        if not re.fullmatch(r'\d{3}_S_\d{4,}', ptid):
            raise ValueError('Invalid ADNI Subject_ID')
        ses = session(row['VISCODE'])
        key = (ptid, ses)
        if key in seen:
            raise ValueError('Duplicate normalized subject/session; resolve multiple runs explicitly')
        seen.add(key)
        # Flags, if present, must not contradict upstream survival.
        for name in ('NIfTI_exists', 'JSON_exists', 'T1w_exists'):
            if name in row and row[name].strip().lower() not in ('true', '1'):
                raise ValueError('Surviving row contradicts ' + name)
        if source_qc:
            iid = str(row.get('Image_ID', row.get('IMAGE_ID', ''))).strip().lstrip('Ii')
            iid = str(int(iid)) if iid.isdigit() else ''
            evidence = quality.get(iid, {})
            state = evidence.get('SOURCE_QC_STATUS', 'pending')
            scan_date = row.get('Scan_Date', '')[:10]
            matched = bool(evidence and evidence.get('PTID') == ptid and scan_date and scan_date == evidence.get('MRI_STUDY_DATE') and evidence.get('MODALITY') == 'EPI')
            reason = 'source_identity_unverified' if not matched else 'blocked_source_qc' if state == 'blocked' else 'pending_source_qc' if state == 'pending' and require_confirmed else ''
            uid = row.get('dicom_SeriesInstanceUID') or row.get('SERIES_UID') or row.get('SeriesInstanceUID')
            if uid and uid != evidence.get('SERIES_UID'):
                reason = 'source_series_uid_unverified'
            if state not in ('pass', 'pending', 'blocked'):
                reason = 'unsupported_source_qc_state'
            audit.append({'Subject_ID': ptid, 'VISCODE': row['VISCODE'], 'IMAGE_ID': iid,
                          'SOURCE_QC_STATUS': state, 'PROCEED': not reason, 'REASON': reason})
            if reason:
                continue
        grouped[ptid].append(ses)
        pairs.append({'Subject_ID': ptid, 'VISCODE': 'bl' if ses == 'M000' else 'm' + str(int(ses[1:])).zfill(2),
                      'sub': 'sub-ADNI' + ptid.replace('_', ''), 'ses': 'ses-' + ses})
    pairs.sort(key=lambda r: (r['Subject_ID'], r['ses']))
    if any(digest(path) != value for path, value in quality_hashes.items()):
        raise ValueError('Source QC artifact changed during handoff')
    if digest(source) != source_hash:
        raise ValueError('Step-5 source changed while validating')
    output.mkdir(parents=True)
    write(output / 'mriqc_subjects.csv', [{'Subject_ID': p, 'sessions': ' '.join(sorted(v))} for p, v in sorted(grouped.items())], ['Subject_ID', 'sessions'])
    write(output / 'post_clinica.csv', [{'Subject_ID': p, 'sessions': ' '.join(sorted(v))} for p, v in sorted(grouped.items())], ['Subject_ID', 'sessions'])
    write(output / 'mriqc_sessions.csv', [{'Subject_ID': r['Subject_ID'], 'VISCODE': r['VISCODE']} for r in pairs], ['Subject_ID', 'VISCODE'])
    write(output / 'valid_sessions.tsv', [{'sub': r['sub'], 'ses': r['ses']} for r in pairs], ['sub', 'ses'], '\t')
    if source_qc:
        write(output / 'source_qc_audit.tsv', audit, list(audit[0]), '\t')
    names = ['mriqc_subjects.csv', 'post_clinica.csv', 'mriqc_sessions.csv', 'valid_sessions.tsv']
    if source_qc:
        names.append('source_qc_audit.tsv')
    status = 'format_validated_no_additional_selection' if not source_qc else 'source_qc_validated_handoff' if pairs else 'no_surviving_sessions'
    result = {'status': status, 'input': str(source),
              'input_sha256': source_hash, 'subjects': len(grouped), 'sessions': len(pairs),
              'outputs_sha256': {name: digest(output / name) for name in names},
              'mriqc_scope': 'upstream participant launcher is subject-only; group metrics must be restricted to valid_sessions before fitting outliers',
              'research_inclusion': 'not_determined', 'source_qc_inputs_sha256': quality_hashes,
              'source_qc_excluded_sessions': sum(not r['PROCEED'] for r in audit),
              'source_qc_pending_sessions': sum(r['SOURCE_QC_STATUS'] == 'pending' and r['PROCEED'] for r in audit)}
    result['source_qc_application_scope'] = 'Selected BOLD identity only; T1 reference pairing and physical headers require separate validation'
    (output / 'handoff.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--source-qc', help='Step-3.A artifact directory')
    p.add_argument('--require-confirmed-qc', action='store_true')
    a = p.parse_args()
    try:
        result = process(a.input, a.output_dir, a.source_qc, a.require_confirmed_qc)
        print(json.dumps(result, indent=2))
        if result['status'] == 'no_surviving_sessions':
            p.exit(2, 'No surviving sessions; audit written but downstream handoff is blocked\n')
    except (ValueError, FileNotFoundError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
