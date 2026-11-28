#!/usr/bin/env python3
"""Audit one completed ADNI run without importing or modifying imaging software.

Default checks target the pinned fMRIPrep + XCP-D 26.2 volume protocol.  They
verify technical consistency, never scientific suitability.  JSON goes to stdout;
--output additionally writes that report.  --stage fmriprep permits an interim
audit before postprocessing.  The default --stage all requires both outputs.

XCP-D naming/semantics checked against the 26.2.0 source, particularly
interfaces/censoring.py, utils/confounds.py and workflows/bold/outputs.py:
https://github.com/PennLINC/xcp_d/tree/26.2.0
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import html
import json
import math
from pathlib import Path
import re
import struct
import sys


class AuditError(ValueError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def nifti_header(path):
    """Read single-file NIfTI-1/2, including unit-aware TR. No voxel data loaded."""
    path = Path(path)
    with (gzip.open(path, 'rb') if path.name.endswith('.gz') else path.open('rb')) as f:
        header = f.read(544)
    if len(header) < 348:
        raise AuditError(f'Truncated NIfTI header: {path}')
    endians = [e for e in '<>' if struct.unpack_from(e + 'i', header)[0] in (348, 540)]
    if len(endians) != 1:
        raise AuditError(f'Unknown NIfTI header: {path}')
    endian = endians[0]
    size = struct.unpack_from(endian + 'i', header)[0]
    if len(header) < size:
        raise AuditError(f'Truncated NIfTI-{2 if size == 540 else 1} header: {path}')
    if size == 348:
        dims = struct.unpack_from(endian + '8h', header, 40)
        pix = struct.unpack_from(endian + '8f', header, 76)
        units = header[123]
        magic = header[344:348]
        if magic != b'n+1\x00':
            raise AuditError(f'Expected single-file NIfTI-1: {path}')
    else:
        dims = struct.unpack_from(endian + '8q', header, 16)
        pix = struct.unpack_from(endian + '8d', header, 104)
        units = struct.unpack_from(endian + 'i', header, 500)[0]
        if not header[4:12].startswith(b'n+2\x00'):
            raise AuditError(f'Expected single-file NIfTI-2: {path}')
    if not 1 <= dims[0] <= 7 or any(v < 1 for v in dims[1:dims[0] + 1]):
        raise AuditError(f'Invalid dimensions: {path}')
    scale = {8: 1.0, 16: 0.001, 24: 0.000001}.get(units & 56)
    tr = pix[4] * scale if dims[0] >= 4 and scale is not None else None
    return {'file': str(path), 'nifti_version': 1 if size == 348 else 2,
            'shape': list(dims[1:dims[0] + 1]), 'voxel_sizes': list(pix[1:4]),
            'spatial_unit_code': units & 7, 'temporal_unit_code': units & 56,
            'tr_seconds': tr, 'compressed_bytes': path.stat().st_size}


def read_tsv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter='\t')
        fields = reader.fieldnames or []
        if len(set(fields)) != len(fields):
            raise AuditError(f'Duplicate TSV columns: {path}')
        rows = list(reader)
    if not fields or any(None in r or any(v is None for v in r.values()) for r in rows):
        raise AuditError(f'Malformed TSV: {path}')
    return fields, rows


def column(fields, name):
    # XCP-D 26 adds optional parameter hashes to column names. Ambiguity fails
    # instead of silently mixing two parameter sets.
    matches = [c for c in fields if re.fullmatch(re.escape(name) + r'(_hash-[A-Za-z0-9+]+)?', c)]
    if len(matches) != 1:
        raise AuditError(f'Expected one column {name!r}; found {matches}')
    return matches[0]


def numeric(values, allow_initial_na=False):
    result = []
    for i, value in enumerate(values):
        try:
            n = float(value)
        except (TypeError, ValueError):
            n = math.nan
        if not math.isfinite(n):
            if allow_initial_na and i == 0:
                n = 0.0
            else:
                raise AuditError(f'Nonfinite/missing numeric value at row {i}: {value!r}')
        result.append(n)
    return result


def binary(values):
    numbers = numeric(values)
    if any(x not in (0, 1) for x in numbers):
        raise AuditError('Temporal mask/non-steady-state flags must be binary')
    return [int(x) for x in numbers]


def infer_dummy(fields, rows):
    keys = [k for k in fields if k.startswith('non_steady_state_outlier')]
    series = [binary([row[k] for row in rows]) for k in keys]
    flags = [any(s[i] for s in series) for i in range(len(rows))]
    indices = [i for i, flag in enumerate(flags) if flag]
    # Mirrors XCP-D auto: remove every initial volume through the last NSS flag.
    count = max(indices) + 1 if indices else 0
    return {'columns': keys, 'flagged_indices_zero_based': indices,
            'auto_dummy_volumes': count,
            'flags_are_contiguous_initial_block': indices == list(range(count))}


def entities(path):
    return dict(part.split('-', 1) for part in Path(path).name.split('_') if '-' in part)


def one_file(folder, suffix, **wanted):
    matches = sorted(p for p in Path(folder).glob('*' + suffix)
                     if all(entities(p).get(k) == v for k, v in wanted.items()))
    if len(matches) != 1:
        raise AuditError(f'Expected one {suffix} {wanted} in {folder}; found {len(matches)}: {matches}')
    return matches[0]


def sidecar(path):
    name = Path(path).name
    stem = name[:-7] if name.endswith('.nii.gz') else name[:-4]
    return Path(path).with_name(stem + '.json')


def compare_vectors(a, b, tolerance=1e-5):
    return len(a) == len(b) and all(abs(x - y) <= tolerance for x, y in zip(a, b))


def motion_duration_gate(post_dummy_volumes, censored_volumes, tr_seconds,
                         minimum_seconds=240, maximum_censored_fraction=0.30):
    """Prospective eligibility gate; independent of execution/technical success.

    The censoring denominator excludes automatically removed initial dummy
    volumes. Exactly 30% censoring and exactly 240 seconds satisfy the default
    criteria. These quantitative criteria do not grant visual QC approval.
    """
    if not isinstance(post_dummy_volumes, int) or not isinstance(censored_volumes, int) or \
            post_dummy_volumes < 0 or not 0 <= censored_volumes <= post_dummy_volumes:
        raise AuditError('Invalid post-dummy/censored volume counts')
    if not math.isfinite(tr_seconds) or tr_seconds <= 0 or not math.isfinite(minimum_seconds) or \
            minimum_seconds < 0 or not math.isfinite(maximum_censored_fraction) or \
            not 0 <= maximum_censored_fraction <= 1:
        raise AuditError('Invalid motion/duration gate parameters')
    fraction = censored_volumes / post_dummy_volumes if post_dummy_volumes else None
    retained_seconds = (post_dummy_volumes - censored_volumes) * tr_seconds
    motion_pass = fraction is not None and fraction <= maximum_censored_fraction
    duration_pass = retained_seconds >= minimum_seconds
    return {'censored_fraction': fraction,
            'censored_fraction_denominator': 'volumes after initial dummy removal, before motion censoring',
            'censored_fraction_denominator_volumes': post_dummy_volumes,
            'prospective_maximum_censored_fraction': maximum_censored_fraction,
            'meets_motion_fraction_criterion': motion_pass,
            'retained_seconds': retained_seconds,
            'prospective_minimum_seconds': minimum_seconds,
            'meets_duration_criterion': duration_pass,
            'passes_automated_motion_duration_gate': motion_pass and duration_pass,
            'automated_gate_operator': 'censored_fraction <= maximum AND retained_seconds >= minimum',
            'visual_approval_required': True,
            'analysis_inclusion': 'pending_visual_and_scientific_review' if motion_pass and duration_pass
                                  else 'excluded_by_prospective_motion_duration_gate'}


def xcpd_output_root(data_root, subject, session):
    """Resolve the latest selected run's recorded output, including Docker host mounts.

    XCP-D 26.2 includes session BIDS filters in its configuration hash. Distinct
    visit filters may therefore need separate derivative datasets. Never choose
    an older successful record over a newer failed attempt.
    """
    root = Path(data_root).resolve()
    candidates = []
    for path in (root / 'logs').glob('*/run.json'):
        value = read_json(path)
        if value.get('stage') == 'xcpd' and value.get('run', {}).get('subject') == subject and \
                value.get('run', {}).get('session') == session:
            candidates.append((value.get('started_at', ''), str(path), value))
    if not candidates:
        return root / 'derivatives/xcp_d'
    value = max(candidates, key=lambda item: item[:2])[2]
    paths = value.get('config', {}).get('paths', {})
    if not paths.get('xcpd_output'):
        return root / 'derivatives/xcp_d'  # legacy records and explicit test fixtures
    output = Path(paths['xcpd_output'])
    if not output.is_absolute():
        raise AuditError('Recorded XCP-D output must be absolute')
    if root not in output.parents:
        if not paths.get('bids'):
            raise AuditError('Cannot map the recorded XCP-D host path')
        host_root = Path(paths['bids']).parent
        try:
            output = root / output.relative_to(host_root)
        except ValueError as exc:
            raise AuditError('Recorded XCP-D output is outside the dataset runtime') from exc
    output = output.resolve()
    if root / 'derivatives' not in output.parents:
        raise AuditError('XCP-D output must be within this runtime derivatives tree')
    return output


class Audit:
    def __init__(self, root, subject, session, stage='all', task='rest', fd_threshold=0.5,
                 min_seconds=240, smoothing=6, high_pass=0.01, low_pass=0.08, expected_sdc='syn',
                 max_censored_fraction=0.30):
        self.root = Path(root).resolve()
        self.subject, self.session = subject.removeprefix('sub-'), session.removeprefix('ses-')
        if not all(re.fullmatch('[A-Za-z0-9]+', s) for s in (self.subject, self.session, task)):
            raise AuditError('Subject/session/task must be BIDS alphanumeric labels')
        self.stage, self.task, self.fd_threshold = stage, task, fd_threshold
        self.min_seconds, self.smoothing = min_seconds, smoothing
        self.high_pass, self.low_pass = high_pass, low_pass
        self.expected_sdc = expected_sdc
        self.max_censored_fraction = max_censored_fraction
        # Validate gate parameters before processing or writing any report.
        motion_duration_gate(1, 0, 1.0, min_seconds, max_censored_fraction)
        if expected_sdc not in ('syn', 'none', 'reported'):
            raise AuditError('expected_sdc must be syn, none, or reported')
        self.case = f'sub-{self.subject}/ses-{self.session}'
        self.report = {'audit_version': '1.4.0', 'data_root': str(self.root),
                       'subject': self.subject, 'session': self.session, 'stage': stage,
                       'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                       'checks': [], 'warnings': [], 'scientific_qc': 'not_assessed',
                       'visual_qc': 'required', 'voxel_finiteness': 'not_assessed_header_only'}

    def check(self, name, condition, observed=None, expected=None):
        self.report['checks'].append({'name': name, 'passed': bool(condition),
                                      'observed': observed, 'expected': expected})

    def image(self, path, expected_volumes=None, tr=None):
        h = nifti_header(path)
        self.check(path.name + ':4D', len(h['shape']) == 4, h['shape'])
        if expected_volumes is not None:
            self.check(path.name + ':volumes', len(h['shape']) == 4 and h['shape'][3] == expected_volumes,
                       h['shape'][-1], expected_volumes)
        if tr is not None:
            self.check(path.name + ':TR', h['tr_seconds'] is not None and
                       abs(h['tr_seconds'] - tr) < 1e-5, h['tr_seconds'], tr)
        return h

    def verify_staging(self):
        manifest_path = self.root / 'logs/staging_manifest.json'
        manifest = read_json(manifest_path)
        files = [f for f in manifest['files'] if f['path'].startswith(self.case + '/')]
        expected = {str(p.relative_to(self.root / 'bids')) for p in
                    (self.root / 'bids' / self.case).rglob('*')
                    if p.is_file() and (p.name.endswith(('.nii.gz', '.nii', '.json')))}
        listed = [f['path'] for f in files]
        self.check('staging_manifest_exact_image_and_sidecar_coverage',
                   len(listed) == len(set(listed)) and set(listed) == expected and bool(expected),
                   sorted(listed), sorted(expected))
        result = []
        for item in files:
            path = (self.root / 'bids' / item['path']).resolve()
            if not path.is_relative_to(self.root / 'bids'):
                raise AuditError('Staging manifest path escapes BIDS root')
            digest, size = sha256(path), path.stat().st_size
            self.check('staging_hash:' + item['path'], digest == item['sha256'] and size == item['bytes'],
                       {'sha256': digest, 'bytes': size}, {'sha256': item['sha256'], 'bytes': item['bytes']})
            result.append({'path': item['path'], 'phase': item.get('phase'), 'sha256': digest, 'bytes': size})
        self.report['staged_inputs'] = result

    def execution_record(self, stage):
        records = []
        for path in (self.root / 'logs').glob('*/run.json'):
            record = read_json(path)
            if record.get('stage') == stage and record.get('run', {}).get('subject') == self.subject and \
                    record.get('run', {}).get('session') == self.session:
                records.append((path, record))
        if not records:
            self.check(stage + ':execution_record', False, 'missing')
            return None
        path, record = max(records, key=lambda v: v[1].get('started_at', ''))
        self.check(stage + ':latest_execution_completed',
                   record.get('status') == 'execution_completed_qc_required' and record.get('exit_code') == 0,
                   {'status': record.get('status'), 'exit_code': record.get('exit_code')})
        self.check(stage + ':input_unchanged', record.get('input_unchanged') is True,
                   record.get('input_unchanged'), True)
        before, after = path.parent / 'input_before.json', path.parent / 'input_after.json'
        self.check(stage + ':input_snapshots_match', before.exists() and after.exists() and
                   read_json(before) == read_json(after))
        return {'file': str(path), 'status': record.get('status'), 'image': record.get('image'),
                'started_at': record.get('started_at'), 'ended_at': record.get('ended_at'),
                'command': record.get('command')}

    def reports(self, root, stage):
        candidates = list(root.glob(f'sub-{self.subject}*.html'))
        candidates += list((root / f'sub-{self.subject}').rglob('*.html'))
        # reports/core.py writes these exact names at root, subject, or session
        # level. A citation HTML, reportlet, or another session is not a report.
        report_name = re.compile(rf'sub-{re.escape(self.subject)}'
                                 rf'(?:_ses-{re.escape(self.session)})?'
                                 r'(?:_hash-[A-Za-z0-9+]+)?\.html')
        locations = {root, root / f'sub-{self.subject}', root / self.case}
        assembled = sorted({p for p in candidates if p.parent in locations and
                            report_name.fullmatch(p.name)})
        self.check(stage + ':assembled_html_report', bool(assembled), len(assembled), '>=1')
        return {'assembled_report_count': len(assembled), 'html_snippet_count': len(set(candidates)) - len(assembled),
                'assembled_reports': [str(p) for p in assembled]}

    def sdc(self, root, bold_json):
        evidence = []
        methods = []
        for key, value in bold_json.items():
            if any(word in key.lower() for word in ('distortion', 'fieldmap', 'sdc')):
                evidence.append({'source': 'preproc BOLD JSON', 'field': key, 'value': value})
                if key in ('SusceptibilityDistortionCorrection', 'SusceptibilityDistortionCorrectionMethod',
                           'SDCMethod') and isinstance(value, str):
                    methods.append(value)
        for p in (root / f'sub-{self.subject}').rglob('*desc-summary_bold.html'):
            if f'ses-{self.session}' not in p.name or f'task-{self.task}' not in p.name:
                continue
            for item in re.findall(r'<li[^>]*>(.*?)</li>', p.read_text(), re.S):
                plain = html.unescape(re.sub('<[^>]+>', '', item)).strip()
                if plain.lower().startswith('susceptibility distortion correction:'):
                    method = plain.split(':', 1)[1].strip()
                    evidence.append({'source': str(p), 'value': method})
                    methods.append(method)
        self.check('fmriprep:actual_sdc_reported', bool(methods), methods)
        if self.expected_sdc == 'syn':
            # Exact 25.2.7 SDCFlows report: FLB ("fieldmap-less", SyN-based).
            # ANAT is the corresponding SDCFlows estimator enum. Input fieldmap
            # identifiers, a configured option, and a report saying None are not proof.
            def is_syn(method):
                return bool(re.search(r'\b(?:syn|anat)\b', method, re.I)) and not re.search(
                    r'\b(?:none|not|failed|unavailable|disabled|skipped|requested)\b', method, re.I)
            matched = bool(methods) and all(is_syn(m) for m in methods)
        elif self.expected_sdc == 'none':
            matched = bool(methods) and all(m.strip().lower() in ('none', 'no correction') for m in methods)
        else:
            matched = bool(methods)
        self.check('fmriprep:SDC_matches_expected_method', matched, methods, self.expected_sdc)
        # Presence of a configured --use-syn-sdc flag never proves application.
        return evidence

    def fmriprep(self):
        bids = self.root / 'bids'
        raw = one_file(bids / self.case / 'func', '_bold.nii.gz', task=self.task)
        raw_json = read_json(sidecar(raw))
        tr = float(raw_json['RepetitionTime'])
        self.raw = self.image(raw, tr=tr)
        if len(self.raw['shape']) != 4:
            raise AuditError('Raw BOLD must be 4D')
        n = self.raw['shape'][3]
        self.tr, self.n = tr, n
        root = self.root / 'derivatives/fmriprep'
        func = root / self.case / 'func'
        preproc = one_file(func, '_bold.nii.gz', task=self.task, desc='preproc', space='MNI152NLin2009cAsym')
        h = self.image(preproc, expected_volumes=n, tr=tr)
        self.preproc = h
        self.check('fmriprep:2mm_grid', h['spatial_unit_code'] == 2 and
                   all(abs(x - 2) < 1e-5 for x in h['voxel_sizes']), h['voxel_sizes'], [2, 2, 2])
        meta = read_json(sidecar(preproc))
        self.check('fmriprep:JSON_TR', abs(float(meta['RepetitionTime']) - tr) < 1e-5,
                   meta['RepetitionTime'], tr)
        confounds = one_file(func, '_timeseries.tsv', task=self.task, desc='confounds')
        fields, rows = read_tsv(confounds)
        self.confounds_fields, self.confounds_rows = fields, rows
        self.check('fmriprep:confounds_rows', len(rows) == n, len(rows), n)
        self.dummy = infer_dummy(fields, rows)
        if not self.dummy['flags_are_contiguous_initial_block']:
            self.report['warnings'].append('NSS flags are not a contiguous initial block; XCP-D auto drops through the last flag.')
        fd_key = column(fields, 'framewise_displacement')
        self.fd = numeric([r[fd_key] for r in rows], allow_initial_na=True)
        six = [column(fields, key) for key in ('rot_x', 'rot_y', 'rot_z', 'trans_x', 'trans_y', 'trans_z')]
        motion = [numeric([r[k] for r in rows]) for k in six]
        self.recomputed_fd = [0.0] + [sum(abs(s[i] - s[i-1]) * (50 if j < 3 else 1)
                                           for j, s in enumerate(motion)) for i in range(1, len(rows))]
        self.check('fmriprep:FD_matches_50mm_Power_calculation', compare_vectors(self.fd, self.recomputed_fd))
        self.report['raw'] = {**self.raw, 'metadata': {k: raw_json.get(k) for k in
                               ('RepetitionTime', 'EchoTime', 'PhaseEncodingDirection', 'TotalReadoutTime',
                                'MultibandAccelerationFactor', 'Manufacturer', 'ManufacturersModelName')}}
        self.report['fmriprep'] = {'bold': h, 'confounds': str(confounds), 'confounds_rows': len(rows),
                                  'dummy': self.dummy, 'fd_threshold_mm': self.fd_threshold,
                                  'fd_exceedance_count_all_volumes': sum(x > self.fd_threshold for x in self.fd),
                                  'mean_fd_all_volumes_first_na_as_zero': sum(self.fd) / len(self.fd),
                                  'actual_sdc_evidence': self.sdc(root, meta),
                                  'generated_by': read_json(root / 'dataset_description.json').get('GeneratedBy'),
                                  'execution': self.execution_record('fmriprep'),
                                  **self.reports(root, 'fmriprep')}

    def audit_design(self, fields, rows):
        """Validate the pinned XCP-D acompcor selection against fMRIPrep columns.

        XCP-D 26.2 GenerateConfounds preserves these source names and writes its
        selected design before numerical denoising. It does not drop rank-deficient
        columns from this file: the denoiser later uses numpy.linalg.lstsq.
        Thus a missing regressor here is not explained by a rank-removal step.
        """
        names = [re.sub(r'_hash-[A-Za-z0-9+]+$', '', name) for name in fields]
        motion = [name + derivative for name in ('trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z')
                  for derivative in ('', '_derivative1')]
        wm = [f'w_comp_cor_{i:02d}' for i in range(5)]
        csf = [f'c_comp_cor_{i:02d}' for i in range(5)]
        cosines = [name for name in self.confounds_fields if re.fullmatch(r'cosine\d+', name)]
        required = motion + wm + csf + cosines
        self.check('xcpd:acompcor_source_columns_available',
                   all(name in self.confounds_fields for name in motion + wm + csf) and bool(cosines),
                   [name for name in motion + wm + csf if name not in self.confounds_fields],
                   '12 motion, 5 WM, 5 CSF and all source cosine columns')
        self.check('xcpd:design_unique_base_columns', len(names) == len(set(names)), names)
        self.check('xcpd:design_exact_acompcor_selection', set(names) == set(required),
                   {'missing': sorted(set(required) - set(names)), 'unexpected': sorted(set(names) - set(required))},
                   sorted(required))
        global_names = [name for name in names if name.lower().startswith('global_signal')]
        self.check('xcpd:design_no_global_signal_regression', not global_names, global_names, [])
        dummy = self.dummy['auto_dummy_volumes']
        values_match = []
        for name in required:
            if name not in names or name not in self.confounds_fields or names.count(name) != 1:
                continue
            actual = numeric([row[column(fields, name)] for row in rows])
            # GenerateConfounds replaces missing source values with zero before
            # dropping dummy rows; no motion filtering is requested in this protocol.
            expected = []
            for row in self.confounds_rows[dummy:]:
                try:
                    value = float(row[name])
                except (ValueError, TypeError):
                    value = 0.0
                expected.append(value if math.isfinite(value) else 0.0)
            values_match.append(compare_vectors(actual, expected, tolerance=1e-7))
        self.check('xcpd:design_matches_source_after_dummy_removal',
                   len(values_match) == len(required) and all(values_match))
        return {'motion_columns': [n for n in names if n in motion],
                'white_matter_components': [n for n in names if re.fullmatch(r'w_comp_cor_\d+', n)],
                'CSF_components': [n for n in names if re.fullmatch(r'c_comp_cor_\d+', n)],
                'cosine_columns': [n for n in names if re.fullmatch(r'cosine\d+', n)],
                'has_global_signal': bool(global_names),
                'rank_note': 'Selected design is written before denoising; no column removal for rank is performed here.'}

    def xcpd(self):
        root = xcpd_output_root(self.root, self.subject, self.session)
        self.report['xcpd_output_root'] = str(root)
        func = root / self.case / 'func'
        mask = one_file(func, '_outliers.tsv', task=self.task)
        fields, rows = read_tsv(mask)
        masks = {k: binary([r[column(fields, k)] for r in rows])
                 for k in ('framewise_displacement', 'censor_between', 'denoising')}
        dummy = self.dummy['auto_dummy_volumes']
        expected_n = self.n - dummy
        self.check('xcpd:mask_rows_after_dummy_removal', len(rows) == expected_n, len(rows), expected_n)
        self.check('xcpd:censor_between_disabled', not any(masks['censor_between']))
        union = [int(a or b) for a, b in zip(masks['framewise_displacement'], masks['censor_between'])]
        self.check('xcpd:denoising_mask_is_union', masks['denoising'] == union)
        expected_fd_mask = [int(fd > self.fd_threshold) for fd in self.recomputed_fd[dummy:]]
        self.check('xcpd:FD_mask_matches_unfiltered_50mm_FD', masks['framewise_displacement'] == expected_fd_mask)
        motion = one_file(func, '_motion.tsv', task=self.task)
        mfields, mrows = read_tsv(motion)
        xfd = numeric([r[column(mfields, 'framewise_displacement')] for r in mrows])
        # 26.2.0 prepare_confounds_wf -> postproc_derivatives_wf saves the
        # dummy_scan_buffer motion file, with exactly the same rows as the mask.
        motion_layout = 'after_dummy_removal' if len(xfd) == expected_n else 'invalid_length'
        expected_fd = self.recomputed_fd[dummy:]
        self.check('xcpd:motion_FD_alignment', compare_vectors(xfd, expected_fd) and bool(expected_fd),
                   {'rows': len(xfd), 'layout': motion_layout}, {'rows': expected_n})
        design = one_file(func, '_design.tsv', task=self.task)
        dfields, drows = read_tsv(design)
        self.check('xcpd:design_rows_after_dummy_removal', len(drows) == expected_n, len(drows), expected_n)
        design_summary = self.audit_design(dfields, drows)
        censored = sum(masks['denoising'])
        retained = len(rows) - censored
        denoised = one_file(func, '_bold.nii.gz', task=self.task, desc='denoised')
        smooth = one_file(func, '_bold.nii.gz', task=self.task, desc='denoisedSmoothed')
        den_header = self.image(denoised, expected_volumes=retained, tr=self.tr)
        smooth_header = self.image(smooth, expected_volumes=retained, tr=self.tr)
        self.check('xcpd:denoised_spatial_shape_matches_fmriprep',
                   den_header['shape'][:3] == self.preproc['shape'][:3])
        self.check('xcpd:smoothing_preserves_shape', smooth_header['shape'] == den_header['shape'])
        den_meta, smooth_meta = read_json(sidecar(denoised)), read_json(sidecar(smooth))
        for desc, meta in [('denoised', den_meta), ('denoisedSmoothed', smooth_meta)]:
            filters = meta.get('SoftwareFilters')
            bandpass = filters.get('Bandpass filter') if isinstance(filters, dict) else None
            bandpass = bandpass if isinstance(bandpass, dict) else {}
            for key, value in [('High-pass cutoff (Hz)', self.high_pass), ('Low-pass cutoff (Hz)', self.low_pass),
                               ('Filter order', 2)]:
                self.check(f'xcpd:{desc}_bandpass_' + key, bandpass.get(key) == value, bandpass.get(key), value)
        self.check('xcpd:smoothing_FWHM', smooth_meta.get('FWHM') == self.smoothing,
                   smooth_meta.get('FWHM'), self.smoothing)
        qc = one_file(func, '_qc.tsv', task=self.task, desc='linc')
        qfields, qrows = read_tsv(qc)
        self.check('xcpd:one_QC_row', len(qrows) == 1, len(qrows), 1)
        qnames = [re.sub(r'_hash-[A-Za-z0-9+]+$', '', name) for name in qfields]
        self.check('xcpd:QC_unique_base_columns', len(qnames) == len(set(qnames)), qnames)
        qc_values = {re.sub(r'_hash-[A-Za-z0-9+]+$', '', k): v for k, v in (qrows[0] if qrows else {}).items()}
        for key, expected in [('num_censored_volumes', censored), ('num_retained_volumes', retained),
                              ('num_dummy_volumes', dummy)]:
            value = qc_values.get(key)
            self.check('xcpd:QC_' + key, value is not None and float(value) == expected, value, expected)
        retained_indices = [i + dummy for i, val in enumerate(masks['denoising']) if val == 0]
        gate = motion_duration_gate(len(rows), censored, self.tr,
                                    self.min_seconds, self.max_censored_fraction)
        for key, samples in [('mean_fd', self.recomputed_fd[dummy:]),
                             ('mean_fd_post_censoring', [self.recomputed_fd[i] for i in retained_indices])]:
            expected = sum(samples) / len(samples) if samples else None
            value = qc_values.get(key)
            self.check('xcpd:QC_' + key, value is not None and expected is not None and
                       abs(float(value) - expected) < 1e-5, value, expected)
        self.report['xcpd'] = {'denoised': den_header, 'denoised_smoothed': smooth_header,
                              'denoised_is_bandpass_filtered': True, 'unfiltered_denoised_output': 'not_requested',
                              'mask': str(mask), 'motion': str(motion), 'motion_layout': motion_layout,
                              'design': str(design), 'design_columns': dfields, 'design_rows': len(drows),
                              'design_regressor_summary': design_summary,
                              'dummy_volumes': dummy, 'post_dummy_volumes': len(rows),
                              'motion_censored_volumes': censored, 'retained_volumes': retained,
                              **gate,
                              'retained_original_indices_zero_based': retained_indices,
                              'time_axis_warning': 'Censored volumes have gaps; indices must accompany any temporal analysis.',
                              'QC_file': str(qc), 'QC_metrics': qc_values,
                              'software_filters': den_meta.get('SoftwareFilters'),
                              'generated_by': read_json(root / 'dataset_description.json').get('GeneratedBy'),
                              'execution': self.execution_record('xcpd'), **self.reports(root, 'xcpd')}

    def run(self):
        try:
            self.verify_staging()
            self.fmriprep()
            if self.stage == 'all':
                self.xcpd()
        except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error) as exc:
            self.report['error'] = f'{type(exc).__name__}: {exc}'
        passed = 'error' not in self.report and all(c['passed'] for c in self.report['checks'])
        self.report['technical_checks_passed'] = passed
        self.report['status'] = ('technical_checks_passed_visual_and_scientific_qc_required' if passed
                                 else 'technical_checks_failed_or_outputs_incomplete')
        return self.report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--subject', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--stage', choices=['all', 'fmriprep'], default='all')
    parser.add_argument('--task', default='rest')
    parser.add_argument('--fd-threshold', type=float, default=0.5)
    parser.add_argument('--min-seconds', type=float, default=240)
    parser.add_argument('--max-censored-fraction', type=float, default=0.30,
                        help='Prospective maximum censored/post-dummy fraction; independent of technical checks.')
    parser.add_argument('--smoothing', type=float, default=6)
    parser.add_argument('--high-pass', type=float, default=0.01)
    parser.add_argument('--low-pass', type=float, default=0.08)
    parser.add_argument('--expected-sdc', choices=['syn', 'none', 'reported'], default='syn',
                        help='Default requires an actual SyN/ANAT method in output evidence.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    report = Audit(args.data_root, args.subject, args.session, args.stage, args.task,
                   args.fd_threshold, args.min_seconds, args.smoothing, args.high_pass, args.low_pass,
                   args.expected_sdc, args.max_censored_fraction).run()
    result = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding='utf-8')
    print(result, end='')
    return 0 if report['technical_checks_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
