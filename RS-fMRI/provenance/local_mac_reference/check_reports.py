#!/usr/bin/env python3
"""Verify fMRIPrep's reported SDC and slice-timing execution for pilot visits."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re

import yaml


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_summary(text):
    fields = {}
    for item in re.findall(r'<li\b[^>]*>(.*?)</li>', text, re.I | re.S):
        plain = html.unescape(re.sub(r'<[^>]+>', '', item)).strip()
        key, separator, value = plain.partition(':')
        key = key.strip().lower()
        if separator and key in ('slice timing correction', 'susceptibility distortion correction',
                                  'registration', 'repetition time (tr)', 'non-steady-state volumes'):
            if key in fields:
                raise ValueError(f'Duplicate reported field: {key}')
            fields[key] = value.strip()
    stc = fields.get('slice timing correction', '')
    sdc = fields.get('susceptibility distortion correction', '')
    if stc.lower() != 'applied':
        raise ValueError(f'Slice timing correction not reported as applied: {stc!r}')
    if not re.search(r'\bsyn\b', sdc, re.I) or re.search(
            r'\b(?:none|not|no|failed|unavailable|disabled|skipped|requested)\b', sdc, re.I):
        raise ValueError(f'SyN distortion correction not reported as applied: {sdc!r}')
    return fields


def check(derivatives, cases, output):
    derivatives, output = Path(derivatives).resolve(), Path(output).resolve()
    if not derivatives.is_dir():
        raise ValueError('fMRIPrep derivatives directory does not exist')
    if derivatives in output.parents or output == derivatives:
        raise ValueError('The report audit must be written outside the fMRIPrep derivatives')
    if output.exists():
        raise ValueError('Refusing to overwrite an existing report audit')
    if not cases:
        raise ValueError('No configured cases')
    records = []
    for case in cases:
        sub, ses = str(case['subject']), str(case['session'])
        if not re.fullmatch('[A-Za-z0-9]+', sub) or not re.fullmatch('[A-Za-z0-9]+', ses):
            raise ValueError('Subject and session must be BIDS alphanumeric labels')
        folder = derivatives / f'sub-{sub}' / 'figures'
        matches = sorted(folder.glob(f'sub-{sub}_ses-{ses}_task-rest*_desc-summary_bold.html'))
        if len(matches) != 1:
            raise ValueError(f'Expected one summary report for sub-{sub}/ses-{ses}: {matches}')
        path = matches[0]
        records.append({'subject': sub, 'session': ses, 'report': str(path), 'report_sha256': sha(path),
                        'reported_fields': parse_summary(path.read_text())})
    output.parent.mkdir(parents=True, exist_ok=True)
    value = {'status': 'reported_slice_timing_and_syn_correction_verified', 'cases': records,
             'scope': 'Confirms the generated fMRIPrep report, not quantitative correction accuracy or study inclusion.',
             'tool_sha256': sha(__file__)}
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': value['status'], 'visits': len(records), 'output': str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.local.yaml'))
    parser.add_argument('--derivatives-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text())
    root = args.derivatives_root or Path(config['runtime']) / 'derivatives/fmriprep'
    check(root, config['runs'], args.output)


if __name__ == '__main__':
    main()
