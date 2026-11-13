"""Run-level ADNI S8/XCP-D orchestration. No model/API calls or data uploads."""
from __future__ import annotations

import argparse
import collections
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
import uuid

import nibabel as nib
import numpy as np
import pandas as pd

KEYS = ('sub', 'ses', 'task', 'run', 'acq', 'dir', 'echo', 'rec')
ENTITY_NAMES = dict(sub='subject', ses='session', task='task', run='run',
                    acq='acquisition', dir='direction', echo='echo', rec='reconstruction')
MANUAL = ('visual_qc_status', 'visual_qc_reason', 'reviewer', 'review_date', 'review_notes')
LAB_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPSTREAM = LAB_ROOT / "pipeline"
if str(LAB_ROOT / "04_workflow") not in sys.path:
    sys.path.insert(0, str(LAB_ROOT / "04_workflow"))
from protocol_source import inspect_protocol
from processing_time import add_timing, refresh_safely


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text())


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.writing')
    tmp.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(b)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(clean(value), sort_keys=True).encode()).hexdigest()


def tsv(path, rows, columns=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=columns) if columns else pd.DataFrame(rows)
    if not len(frame.columns):
        frame = pd.DataFrame(columns=list(KEYS) + ['config_id', 'status'])
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.writing')
    frame.to_csv(tmp, sep='\t', index=False, na_rep='NA')
    tmp.replace(path)


def table(path):
    return pd.read_csv(path, sep='\t', dtype=str, keep_default_na=False).replace('NA', '').to_dict('records')


def entities(path):
    return {k: v for k, v in re.findall(r'(?:^|_)([A-Za-z0-9]+)-([^_.]+)', Path(path).name)}


def identity(path):
    e = entities(path)
    return {k: (k + '-' + e[k] if k in ('sub', 'ses', 'task', 'run') else e[k]) if k in e else '' for k in KEYS}


def key(row):
    return tuple(str(row.get(k) or '') for k in KEYS)


def run_key(row):
    return '_'.join(str(row.get(k)) for k in ('sub', 'ses', 'task', 'run') if row.get(k)) + '-' + digest(key(row))[:10]


def unique(rows, label):
    keys = [key(r) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate run identity in ' + label)
    configs = {r['config_id'] for r in rows if r.get('config_id')}
    if len(configs) > 1:
        raise ValueError('Mixed pipeline configurations in ' + label)


def upstream(repo, name):
    path = Path(repo) / 's8_final_qc' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_one(paths, label):
    paths = list(paths)
    if len(paths) != 1:
        raise ValueError(f'{label}: expected one file; found {len(paths)}')
    return paths[0]


def same_run(path, row):
    return key(identity(path)) == key(row)


def input_runs(pair, cfg):
    """Union of confounds and selected-space BOLD detects missing counterparts."""
    root = Path(pair) / 'fmriprep'
    confounds = list(root.glob('sub-*/**/func/*_desc-confounds_timeseries.tsv'))
    extension = '.nii.gz' if cfg['file_format'] == 'nifti' else '.dtseries.nii'
    bolds = [p for p in root.glob('sub-*/**/func/*bold' + extension)
             if entities(p).get('space') == cfg['space']
             and (cfg['file_format'] != 'nifti' or entities(p).get('res', '') == cfg['resolution'])
             and (cfg['file_format'] != 'cifti' or entities(p).get('den', '') == cfg['density'])
             and entities(p).get('desc', '') in ('preproc', '')]
    groups = {}
    for category, files in [('confounds', confounds), ('bold', bolds)]:
        for p in files:
            if cfg.get('task') and entities(p).get('task') != cfg['task']:
                continue
            row = identity(p)
            group = groups.setdefault(key(row), {**row, 'bold': [], 'confounds': []})
            group[category].append(p)
    if not groups:
        raise ValueError('No matching BOLD/confounds runs; cannot invent a run')
    return list(groups.values())


def strict_flag(value):
    token = str(value).strip().lower()
    if token in ('1', '1.0', 'true', 'yes', 'excluded', 'fail'):
        return 1
    if token in ('0', '0.0', 'false', 'no', 'included', 'pass'):
        return 0
    return None


def get_mriqc_flag(row, cfg):
    path = cfg.get('mriqc_flags_file')
    if not path:
        return None, 'cohort_pending'
    p = Path(path)
    frame = pd.read_csv(p, sep='\t' if p.suffix == '.tsv' else ',', dtype=str, keep_default_na=False)
    cols = ['sub', 'ses'] if cfg['mriqc_flags_grain'] == 'session' else list(KEYS)
    if any(k not in frame for k in cols):
        raise ValueError('MRIQC flags lack configured identity columns')
    if frame.duplicated(cols).any():
        raise ValueError('Duplicate MRIQC flags')
    match = frame.loc[(frame[cols] == pd.Series({k: row[k] for k in cols})).all(axis=1)]
    if len(match) != 1:
        return None, 'missing_metric'
    flagcol = next((c for c in ('exclude_mriqc', 'excluded_any', 'qc_status_any') if c in match), None)
    value = strict_flag(match.iloc[0][flagcol]) if flagcol else None
    return value, 'available' if value is not None else 'missing_metric'


def decide_pre(row, cfg):
    if row.get('validation_errors'):
        return 'missing_or_invalid', False, row['validation_errors']
    fail = []
    if row['mean_fd'] > cfg['pre_mean_fd_threshold']:
        fail.append('mean_fd_above_threshold')
    if row.get('fd_over_threshold_proportion', row['fd_over_0p5_proportion']) > cfg['pre_fd_proportion_threshold']:
        fail.append('fd_proportion_above_threshold')
    if row.get('mriqc_exclude_flag') == 1:
        fail.append('mriqc_excluded')
    if row.get('euler_qc_flag') == 1:
        fail.append('euler_excluded')
    if fail:
        return 'fail', False, ';'.join(fail)
    if row.get('mriqc_flag_status') == 'missing_metric' or row.get('avg_euler') is None:
        return 'missing_metrics', False, 'required_QC_missing'
    if row.get('euler_qc_flag') is None or row.get('mriqc_exclude_flag') is None:
        return 'review_required', cfg['allow_deferred_cohort_candidates'], 'cohort_euler_and_or_mriqc_pending'
    return 'pass', True, ''


def inspect_run(group, pair, cfg, config_id, s8dir):
    row = {k: group[k] for k in KEYS}
    meta = load(Path(pair) / 'pair_metadata.json')
    row.update({k: meta[k] for k in ('ptid', 'pair_id', 'epi_date', 'mt1_date', 'epi_image_id', 'mt1_image_id')})
    row.update(config_id=config_id, pipeline_version=cfg['pipeline_version'], site=meta['ptid'][:3],
               source_pair=str(pair), euler_qc_flag=None, mriqc_exclude_flag=None, avg_euler=None,
               mriqc_flag_status='cohort_pending', validation_errors='', final_qc_status='pending_review', final_include=None)
    inputs = []
    try:
        if row['sub'] != 'sub-' + meta['subject'] or row['ses'] != 'ses-' + meta['execution_session_label']:
            raise ValueError('Pair metadata and run identity disagree')
        bold = exact_one(group['bold'], 'Selected-space BOLD')
        conf = exact_one(group['confounds'], 'Confounds TSV')
        row['source_bold_file'] = str(bold)
        row['source_confounds_file'] = str(conf)
        root = Path(pair) / 'fmriprep'
        desc = root / 'dataset_description.json'
        dd = load(desc)
        row['fmriprep_version'] = next((x.get('Version') for x in dd.get('GeneratedBy', []) if x.get('Name', '').lower() == 'fmriprep'), None)
        if not row['fmriprep_version']:
            raise ValueError('fMRIPrep dataset description/version missing')
        boldjson = bold.with_name(bold.name.replace('.nii.gz', '.json').replace('.dtseries.nii', '.json'))
        cj = conf.with_suffix('.json')
        bm = load(boldjson); load(cj)
        img = nib.load(bold)
        if cfg['file_format'] == 'nifti':
            if len(img.shape) != 4:
                raise ValueError('BOLD must have four dimensions')
            nt = img.shape[3]
            prefix = bold.name.removesuffix('_desc-preproc_bold.nii.gz')
            mask = bold.with_name(prefix + '_desc-brain_mask.nii.gz')
            ref = bold.with_name(prefix + '_boldref.nii.gz')
            for p in (mask, ref):
                ni = nib.load(p)
                if ni.shape != img.shape[:3] or not np.allclose(ni.affine, img.affine):
                    raise ValueError('BOLD reference/mask geometry mismatch')
            inputs += [mask, ref]
        else:
            if not isinstance(img, nib.Cifti2Image) or len(img.shape) != 2:
                raise ValueError('Expected CIFTI dense timeseries')
            nt = img.shape[0]
        tr = float(bm['RepetitionTime'])
        if tr <= 0 or not math.isfinite(tr):
            raise ValueError('Invalid TR')
        df = pd.read_csv(conf, sep='\t')
        if len(df) != nt:
            raise ValueError('Confounds and BOLD length differ')
        fd = pd.to_numeric(df['framewise_displacement'], errors='raise')
        if not np.isfinite(fd.iloc[1:]).all() or fd.iloc[1:].lt(0).any():
            raise ValueError('Missing/nonfinite FD beyond first undefined frame')
        if pd.notna(fd.iloc[0]) and (not math.isfinite(fd.iloc[0]) or fd.iloc[0] < 0):
            raise ValueError('Invalid first FD')
        dvcol = 'std_dvars' if 'std_dvars' in df else 'dvars'
        if dvcol not in df or not np.isfinite(df[dvcol].iloc[1:]).all():
            raise ValueError('Required DVARS missing/nonfinite')
        if cfg['nuisance_regressors'] == '36P':
            base = ['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z', 'global_signal', 'white_matter', 'csf']
            for col in [b + s for b in base for s in ('', '_derivative1', '_power2', '_derivative1_power2')]:
                if col not in df or not np.isfinite(df[col].iloc[1:]).all():
                    raise ValueError('36P confound missing/nonfinite: ' + col)
        motion, series = upstream(cfg['repo'], 'summarize_motion_from_confounds').process_confounds(str(conf), cfg['pre_fd_threshold'])
        for k in KEYS:
            series[k] = row[k]
        row.update(n_original_volumes=int(nt), tr=tr, mean_fd=motion['mean_fd_p'],
                   median_fd=motion['median_fd_p'], max_fd=motion['max_fd_p'],
                   fd_over_0p5_proportion=float((fd.fillna(0)>0.5).mean()), fd_over_threshold_proportion=motion['prop_fd_p_over_thresh'], n_fd_over_threshold=motion['n_fd_p_over_thresh'],
                   pre_fd_threshold=cfg['pre_fd_threshold'], mean_dvars=motion['mean_dvars'])
        series.to_csv(s8dir / (run_key(row) + '_motion_timeseries.tsv'), sep='\t', index=False, na_rep='NA')
        anat = bold.parent.parent / 'anat'
        stem = row['sub'] + ('_' + row['ses'] if row['ses'] else '')
        required_anat = [anat / (stem + s) for s in ['_desc-preproc_T1w.nii.gz', '_desc-brain_mask.nii.gz', '_dseg.nii.gz']]
        volspace = 'MNI152NLin6Asym' if cfg['file_format'] == 'cifti' else cfg['space']
        required_anat += [anat / (stem + '_from-' + a + '_to-' + b + '_mode-image_xfm.h5') for a, b in [('T1w', volspace), (volspace, 'T1w')]]
        required_anat += [exact_one(anat.glob(stem + '_space-' + volspace + '*_desc-brain_mask.nii.gz'), 'Standard anatomical mask')]
        for p in required_anat:
            if not p.is_file() or p.stat().st_size == 0:
                raise ValueError('Required anatomical output missing: ' + p.name)
            if p.name.endswith('.nii.gz'):
                nib.load(p)
        inputs += required_anat
        fs = root / 'sourcedata/freesurfer' / stem
        log = fs / 'scripts/recon-all.log'
        if not log.is_file():
            raise ValueError('Sessionwise FreeSurfer log missing')
        lh, rh = upstream(cfg['repo'], 'extract_euler_from_freesurfer').parse_euler_from_log(str(log))
        if lh is None or rh is None or not np.isfinite([lh, rh]).all():
            raise ValueError('Euler missing; no silent fallback/pass')
        row.update(lh_euler=lh, rh_euler=rh, avg_euler=(lh + rh) / 2, freesurfer_subject=stem)
        fsver = fs / 'scripts/build-stamp.txt'
        row['freesurfer_version'] = fsver.read_text().strip() if fsver.is_file() else 'NA'
        iqmp = exact_one([p for p in (Path(pair) / 'mriqc').glob('sub-*/**/func/*bold.json') if same_run(p, row)], 'MRIQC BOLD IQM')
        iqm = load(iqmp)
        if not all(isinstance(iqm.get(k), (int, float)) and math.isfinite(iqm[k]) for k in ('fd_mean', 'tsnr')):
            raise ValueError('Required MRIQC numerical IQMs missing')
        row['mriqc_version'] = iqm.get('provenance', {}).get('version', 'NA')
        row['scanner_vendor'] = iqm.get('bids_meta', {}).get('Manufacturer', 'unknown')
        row.update({ 'mriqc_' + k: v for k, v in iqm.items() if isinstance(v, (int, float)) })
        row['mriqc_exclude_flag'], row['mriqc_flag_status'] = get_mriqc_flag(row, cfg)
        for flag in ('exclude_mriqc', 'excluded_any', 'qc_status_any'):
            if flag in iqm:
                known = strict_flag(iqm[flag])
                if known is None:
                    raise ValueError('MRIQC embedded QC flag invalid')
                if known == 1 or row['mriqc_exclude_flag'] is None:
                    row['mriqc_exclude_flag'] = known
                    row['mriqc_flag_status'] = 'available'
        report = root / (row['sub'] + '.html')
        if not report.is_file():
            raise ValueError('fMRIPrep HTML report missing')
        row['fmriprep_report'] = str(report)
        inputs += [bold, conf, boldjson, cj, desc, log, iqmp, report]
        row['input_files'] = {str(p): sha(p) for p in inputs}
    except (ValueError, KeyError, OSError, TypeError) as exc:
        row['validation_errors'] = str(exc)
    status, candidate, reason = decide_pre(row, cfg)
    row.update(pre_xcpd_qc_status=status, candidate=candidate, pre_xcpd_reason=reason)
    return row


def bids_filter(row, cfg):
    q = {ENTITY_NAMES[k]: (str(row[k]).removeprefix(k + '-') if k in ('sub', 'ses', 'task', 'run') else row[k]) or None for k in KEYS}
    # XCP-D supplies subject separately to layout.get; repeating it is an error.
    q.pop('subject')
    q.update(space=cfg['space'], desc='preproc' if cfg['file_format'] == 'nifti' else None)
    q['res' if cfg['file_format'] == 'nifti' else 'den'] = cfg['resolution'] if cfg['file_format'] == 'nifti' else cfg['density']
    return {'bold': q, 'atlas': {'template': cfg['space']}}


def xcp_args(cfg, row):
    args = ['/input', '/job/derivatives', 'participant', '--mode', cfg['mode'], '--input-type', cfg['input_type'],
            '--participant-label', row['sub'].removeprefix('sub-'), '--task-id', row['task'].removeprefix('task-'),
            '--bids-filter-file', '/job/bids_filter.json', '--file-format', cfg['file_format'],
            '--combine-runs', 'n', '--output-type', 'censored', '--output-layout', 'bids',
            '--fd-thresh', str(cfg['fd_threshold']), '--min-time', str(cfg['min_time']),
            '--atlases', *cfg['atlases'], '--nuisance-regressors', cfg['nuisance_regressors'],
            '--dummy-scans', str(cfg['dummy_scans']), '--smoothing', str(cfg['smoothing']),
            '--despike', 'y' if cfg['despike'] else 'n', '--motion-filter-type', cfg['motion_filter_type'],
            '--head-radius', str(cfg['head_radius']), '--censor-between', str(cfg['censor_between']),
            '--lower-bpf', str(cfg['lower_bpf']), '--upper-bpf', str(cfg['upper_bpf']), '--bpf-order', str(cfg['bpf_order']),
            '--min-coverage', str(cfg['min_coverage']), '--linc-qc', 'y' if cfg['linc_qc'] else 'n',
            '--abcc-qc', 'y' if cfg['abcc_qc'] else 'n', '--output-run-wise-correlations', 'y',
            '--report-output-level', 'root', '--random-seed', str(cfg['random_seed']),
            '--nprocs', str(cfg['resources']['cpus']), '--omp-nthreads', str(cfg['resources']['omp_nthreads']),
            '--mem-mb', str(cfg['resources']['mem_mb']), '--fs-license-file', '/license.txt',
            '--work-dir', '/job/work', '--stop-on-first-crash', '--notrack']
    if row['ses']:
        args += ['--session-id', row['ses'].removeprefix('ses-')]
    if not cfg['bandpass']:
        args += ['--disable-bandpass-filter']
    return args


def command(cfg, row, attempt, name, create=True):
    cache = Path(cfg['root']) / 'postprocessing/cache'
    cache.mkdir(parents=True, exist_ok=True)
    return ['docker', 'create' if create else 'run', '--platform', 'linux/amd64', '--name', name,
            '--label', 'adni.config_id=' + cfg['_config_id'], '--label', 'adni.run_key=' + run_key(row),
            '--cpus', str(cfg['resources']['cpus']), '--memory', cfg['resources']['docker_memory'],
            '-e', 'MPLCONFIGDIR=/cache/matplotlib', '-e', 'TEMPLATEFLOW_HOME=/templateflow',
            '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'MKL_NUM_THREADS=1',
            '-e', 'OMP_NUM_THREADS=' + str(cfg['resources']['omp_nthreads']),
            '-e', 'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=' + str(cfg['resources']['omp_nthreads']),
            '-v', str((Path(row['source_pair']) / 'fmriprep').resolve()) + ':/input:ro',
            '-v', str(attempt.resolve()) + ':/job', '-v', str(cache) + ':/cache',
            '-v', cfg['templateflow'] + ':/templateflow', '-v', cfg['license'] + ':/license.txt:ro',
            '--entrypoint', 'python', cfg['image'], '/job/container_entry.py', *xcp_args(cfg, row)]


def file_for(root, row, pattern):
    return exact_one([p for p in root.glob('sub-*/**/func/' + pattern) if same_run(p, row)], pattern)


def read_xcp_tsv(path, index_col=None):
    frame = pd.read_csv(path, sep='\t', index_col=index_col)
    frame.columns = [re.sub(r'_hash-[A-Za-z0-9]+$', '', str(c)) for c in frame.columns]
    if frame.columns.duplicated().any():raise ValueError('Conflicting hashed QC columns')
    if index_col is not None:
        frame.index = [re.sub(r'_hash-[A-Za-z0-9]+$', '', str(c)) for c in frame.index]
        if frame.index.duplicated().any():raise ValueError('Duplicate ROI labels')
    return frame


def write_s8_tables(rows, directory):
    mapping = {'n_volumes':'n_original_volumes', 'mean_fd_p':'mean_fd', 'median_fd_p':'median_fd',
               'max_fd_p':'max_fd', 'prop_fd_p_over_thresh':'fd_over_0p5_proportion',
               'n_fd_p_over_thresh':'n_fd_over_threshold', 'mean_dvars':'mean_dvars'}
    motion=[{**{k:r[k] for k in KEYS}, **{k:r.get(v) for k,v in mapping.items()}} for r in rows]
    for output,source in zip(motion,rows):output['prop_fd_p_over_thresh']=source.get('fd_over_threshold_proportion',source.get('fd_over_0p5_proportion'))
    tsv(directory / 'motion_summary.tsv', motion)
    eu = {}
    for r in rows:
        eu[(r['sub'],r['ses'])] = {'sub':r['sub'],'ses':r['ses'],'site':r['site'],'fs_subject':r.get('freesurfer_subject'),
                                  'lh_en':r.get('lh_euler'),'rh_en':r.get('rh_euler'),'avg_en':r.get('avg_euler'),
                                  'euler_qc_flag':r.get('euler_qc_flag')}
    tsv(directory / 'euler_summary.tsv', list(eu.values()))


def validate_outputs(attempt, row, cfg, exit_code):
    root = Path(attempt) / 'derivatives'
    out = {k: row[k] for k in KEYS}
    out.update(config_id=cfg['_config_id'], xcpd_fd_threshold=cfg['fd_threshold'],
               xcpd_status='failed' if exit_code else 'partial', xcpd_qc_status='processing_failed',
               functional_outputs_valid=False, roi_coverage_status='unknown', xcpd_errors=[], xcpd_warnings=[])
    if exit_code == 42 and (Path(attempt) / 'duration_gate.json').is_file():
        gate = load(Path(attempt) / 'duration_gate.json')
        if gate['remaining_duration_sec'] >= cfg['min_time'] or gate['fd_threshold'] != cfg['fd_threshold']:
            raise ValueError('Invalid insufficient-duration gate')
        out.update(gate, xcpd_status='skipped_insufficient_time', xcpd_qc_status='fail',
                   xcpd_warnings=['remaining_duration_below_minimum'], xcpd_errors=[])
        return out
    if exit_code:
        out['xcpd_errors'] = [f'exit_code_{exit_code}']
        return out
    try:
        dd = load(root / 'dataset_description.json')
        if not any(g.get('Version') == cfg['xcpd_version'] and 'xcp' in g.get('Name', '').lower() for g in dd.get('GeneratedBy', [])):
            raise ValueError('XCP-D version missing/mismatched')
        toml_file=exact_one(root.glob('**/xcp_d.toml'),'Actual XCP-D configuration')
        actual=tomllib.loads(toml_file.read_text())
        expected={'mode':cfg['mode'],'file_format':cfg['file_format'],'combine_runs':False,'fd_thresh':cfg['fd_threshold'],
                  'min_time':cfg['min_time'],'bandpass_filter':cfg['bandpass'],'high_pass':cfg['lower_bpf'],'low_pass':cfg['upper_bpf'],
                  'bpf_order':cfg['bpf_order'],'smoothing':cfg['smoothing'],'dummy_scans':cfg['dummy_scans'],'despike':cfg['despike'],
                  'head_radius':cfg['head_radius'],'censor_between':cfg['censor_between'],'min_coverage':cfg['min_coverage'],
                  'linc_qc':cfg['linc_qc'],'abcc_qc':cfg['abcc_qc'],'output_interpolated':False}
        for k,v in expected.items():
            if actual['workflow'].get(k)!=v:raise ValueError('Actual XCP-D option differs: '+k)
        if sorted(actual['execution'].get('atlases',[]))!=sorted(cfg['atlases']):raise ValueError('Actual atlas differs')
        if Path(actual['execution'].get('confounds_config','')).stem!=cfg['nuisance_regressors']:
            raise ValueError('Actual nuisance regression differs')
        out['actual_configuration_file']=str(toml_file)
        ext = '.nii.gz' if cfg['file_format'] == 'nifti' else '.dtseries.nii'
        bold = file_for(root, row, '*_desc-denoised_bold' + ext)
        img = nib.load(bold)
        nout = img.shape[-1] if cfg['file_format'] == 'nifti' else img.shape[0]
        if (cfg['file_format'] == 'nifti' and len(img.shape) != 4) or (cfg['file_format'] == 'cifti' and not isinstance(img, nib.Cifti2Image)):
            raise ValueError('Invalid output image dimensions')
        source=nib.load(row['source_bold_file'])
        if cfg['file_format']=='nifti' and (img.shape[:3]!=source.shape[:3] or not np.allclose(img.affine,source.affine)):
            raise ValueError('Output spatial geometry differs from selected input')
        if cfg['file_format']=='cifti' and img.shape[1]!=source.shape[1]:raise ValueError('Output grayordinate dimension differs')
        # Decompress once; repeated gzip seeks would make validation quadratic in timepoints.
        dense = np.asanyarray(img.dataobj)
        for index in range(nout):
            data = dense[..., index] if cfg['file_format'] == 'nifti' else dense[index, :]
            if not np.isfinite(data).all():
                raise ValueError('Nonfinite denoised BOLD voxel')
        del dense, data
        qcfile = file_for(root, row, '*_desc-linc_qc.tsv')
        qc = read_xcp_tsv(qcfile)
        if len(qc) != 1:
            raise ValueError('LINC QC row count differs from one')
        q = qc.iloc[0].to_dict()
        required = ['mean_fd', 'mean_fd_post_censoring', 'mean_dvars_initial', 'mean_dvars_final',
                    'num_dummy_volumes', 'num_censored_volumes', 'num_retained_volumes', 'coreg_dice', 'norm_dice']
        if any(k not in q or not math.isfinite(float(q[k])) for k in required):
            raise ValueError('Required LINC QC metric missing/nonfinite')
        dummy, censored, retained = [int(q[k]) for k in ('num_dummy_volumes', 'num_censored_volumes', 'num_retained_volumes')]
        if min(dummy, censored, retained) < 0 or dummy + censored + retained != row['n_original_volumes'] or retained != nout:
            raise ValueError('BOLD, dummy/censor/retained counts disagree')
        motion = read_xcp_tsv(file_for(root, row, '*_motion.tsv'))
        censor = read_xcp_tsv(file_for(root, row, '*_outliers.tsv'))
        if len(censor) != retained + censored or len(motion) != len(censor):
            raise ValueError('Motion/censor TSV length mismatch')
        cc = 'framewise_displacement'
        censor_col = 'denoising' if 'denoising' in censor else cc
        if cc not in censor or not censor[cc].isin([0, 1]).all() or not censor[censor_col].isin([0,1]).all() or int(censor[censor_col].sum()) != censored:
            raise ValueError('Censor flags do not match LINC counts')
        if (censor[censor_col] < censor[cc]).any():raise ValueError('Motion outliers missing from denoising mask')
        fdcol = 'framewise_displacement_filtered' if cfg['motion_filter_type'] != 'none' else cc
        if fdcol not in motion or not np.isfinite(motion[fdcol]).all():
            raise ValueError('XCP-D motion FD missing/nonfinite')
        retained_fd = motion.loc[censor[censor_col] == 0, fdcol]
        if (retained_fd > cfg['fd_threshold'] + 1e-7).any():
            raise ValueError('Retained FD exceeds censor threshold')
        duration = retained * row['tr']
        out.update({ 'xcpd_' + k: v for k, v in q.items() })
        out.update(n_original_volumes=row['n_original_volumes'], tr=row['tr'], n_removed_dummy_volumes=dummy,
                   n_censored_volumes=censored, censoring_proportion=censored / (retained + censored),
                   n_remaining_volumes=retained, remaining_duration_sec=duration, denoised_bold=str(bold),
                   xcpd_mean_fd_retained=float(retained_fd.mean()), qc_metric_source=str(qcfile))
        roi_warnings = []
        for atlas in cfg['atlases']:
            ts = read_xcp_tsv(file_for(root, row, '*_atlas-' + atlas + '_stat-mean_timeseries.tsv'))
            fc = read_xcp_tsv(file_for(root, row, '*_atlas-' + atlas + '_stat-pearsoncorrelation_relmat.tsv'), index_col=0)
            coverage = read_xcp_tsv(file_for(root, row, '*_atlas-' + atlas + '_stat-coverage_bold.tsv'), index_col=0)
            n = cfg['expected_rois'][atlas]
            if ts.shape != (retained, n) or fc.shape != (n, n) or len(coverage) != n:
                raise ValueError('ROI timeseries/FC/coverage dimensions mismatch: ' + atlas)
            if list(ts.columns) != list(fc.columns) or list(fc.index) != list(fc.columns) or list(coverage.index) != list(ts.columns):
                raise ValueError('ROI labels/order mismatch: ' + atlas)
            if 'coverage' not in coverage or not np.isfinite(coverage.coverage).all() or not coverage.coverage.between(0, 1).all():
                raise ValueError('Invalid ROI coverage')
            if np.isinf(ts.to_numpy()).any() or np.isinf(fc.to_numpy()).any():
                raise ValueError('Infinite ROI values')
            bad = ts.isna().all(axis=0)
            if int((~bad).sum())<2:raise ValueError('Insufficient usable ROI pairs for connectivity')
            if (ts.isna().any(axis=0) != bad).any():
                raise ValueError('Partially missing ROI timeseries')
            if not np.allclose(fc.to_numpy(), fc.to_numpy().T, equal_nan=True):
                raise ValueError('FC matrix is not symmetric')
            valid_fc = fc.to_numpy()[np.ix_(~bad.to_numpy(), ~bad.to_numpy())]
            if not np.isfinite(valid_fc).all() or (np.abs(valid_fc) > 1.00001).any():
                raise ValueError('Nonfinite/out-of-range FC in valid ROIs')
            frac = float(bad.mean())
            low = float((coverage.coverage < cfg['min_coverage']).mean())
            out[atlas + '_missing_roi_fraction'] = frac
            out[atlas + '_low_coverage_fraction'] = low
            out[atlas + '_min_coverage'] = float(coverage.coverage.min())
            if frac > cfg['review']['missing_roi_fraction_warning'] or low > 0:
                roi_warnings.append(atlas + '_coverage_or_missing_ROI')
        for metric in ('coreg_dice', 'norm_dice'):
            if q[metric] < cfg['review']['registration_dice_warning']:
                out['xcpd_warnings'].append(metric + '_review')
        out['xcpd_warnings'] += roi_warnings
        report = root / (row['sub'] + '.html')
        if not report.is_file() or '<html' not in report.read_text(errors='replace').lower():
            raise ValueError('Participant HTML report missing/invalid')
        out['xcpd_report'] = str(report)
        if cfg['abcc_qc']:
            execs = list(root.glob(row['sub'] + '*executive_summary.html'))
            if not execs:
                raise ValueError('Requested ABCC executive summary missing')
            out['executive_summary'] = str(execs[0])
        if any(root.rglob('crash-*.txt')) or any(root.rglob('crash-*.pklz')):
            raise ValueError('Crash file in derivatives')
        for metric in (['alff','reho'] if cfg['bandpass'] else ['reho']):
            mapfile=file_for(root,row,'*_stat-'+metric+'_boldmap'+('.nii.gz' if cfg['file_format']=='nifti' else '.dscalar.nii'))
            mapimg=nib.load(mapfile)
            if not np.isfinite(np.asanyarray(mapimg.dataobj)).all():raise ValueError('Nonfinite '+metric+' map')
        unexpected = [p for p in root.glob('sub-*/**/func/*_desc-denoised_bold' + ext) if not same_run(p, row)]
        if unexpected:
            raise ValueError('Unselected run appeared in outputs')
        out.update(xcpd_status='success', functional_outputs_valid=True,
                   roi_coverage_status='review' if roi_warnings else 'pass',
                   xcpd_qc_status='fail' if duration < cfg['min_time'] else ('review_required' if out['xcpd_warnings'] else 'pass'))
        if duration < cfg['min_time']:
            out['xcpd_warnings'].append('remaining_duration_below_minimum')
    except (ValueError, KeyError, OSError, TypeError, pd.errors.ParserError) as exc:
        out['xcpd_errors'].append(str(exc))
    return clean(out)


def decide_final(row, cohort_ready=False):
    """Never turn missing flags or an unperformed visual review into a pass."""
    if row.get('xcpd_status') in ('failed', 'partial') or row.get('pre_xcpd_qc_status') in ('missing_metrics', 'missing_or_invalid'):
        return 'processing_failed', False, 'processing_or_required_metrics_failed'
    if not cohort_ready:
        return 'pending_review', None, 'cohort_finalization_deferred'
    reasons = []
    if row.get('pre_xcpd_qc_status') == 'fail': reasons.append(row.get('pre_xcpd_reason', 'pre_qc_failed'))
    if strict_flag(row.get('mriqc_exclude_flag')) == 1: reasons.append('mriqc_excluded')
    if strict_flag(row.get('euler_qc_flag')) == 1: reasons.append('euler_excluded')
    if row.get('xcpd_qc_status') == 'fail': reasons.append('xcpd_quality_failed')
    if row.get('visual_qc_status') == 'fail': reasons.append('visual_qc_failed:' + str(row.get('visual_qc_reason', '')))
    if reasons: return 'exclude', False, ';'.join(reasons)
    if any(strict_flag(row.get(k)) is None for k in ('euler_qc_flag', 'mriqc_exclude_flag')):
        return 'pending_review', None, 'cohort_flags_missing'
    if row.get('xcpd_status') != 'success' or not row.get('functional_outputs_valid'):
        return 'processing_failed', False, 'xcpd_not_validated'
    required = row.get('visual_review_required') in (True, 'True', 'true', '1')
    if (required or row.get('xcpd_qc_status') == 'review_required') and row.get('visual_qc_status') != 'pass':
        return 'pending_review', None, 'human_visual_review_pending'
    if row.get('visual_qc_status') == 'pass' and (not row.get('reviewer') or not row.get('review_date')):
        return 'pending_review', None, 'human_review_identity_missing'
    return 'include', True, ''


class Pipeline:
    def __init__(self, path):
        self.config_path = Path(path).resolve()
        self.cfg = load(path)
        cfg = self.cfg
        cfg['repo'] = str(Path(cfg.get('repo') or DEFAULT_UPSTREAM).resolve())
        if Path(cfg['repo']) != DEFAULT_UPSTREAM.resolve():
            raise ValueError('Use the integrated protocol source; do not substitute an unreviewed checkout')
        runtime = Path(cfg['root']).expanduser()
        repo_root = LAB_ROOT.parent.resolve()
        if not runtime.is_absolute() or 'ABSOLUTE/PATH' in str(runtime) or runtime.resolve() == Path('/'):
            raise ValueError('Set an actual absolute external runtime root')
        if runtime.resolve() == repo_root or repo_root in runtime.resolve().parents or runtime.resolve() in repo_root.parents:
            raise ValueError('Runtime must be outside the source repository')
        self.protocol_source = inspect_protocol(LAB_ROOT)
        if cfg['combine_runs'] or not cfg['defer_final_decision']:
            raise ValueError('This automatic service requires independent runs and deferred finalization')
        if not cfg['linc_qc']:raise ValueError('LINC QC is required for automated output validation')
        if cfg['nuisance_regressors']=='36P' and not cfg['global_signal_regression']:
            raise ValueError('36P includes GSR; configuration must describe it accurately')
        self.config_id = cfg['run_id'] + '-' + digest(cfg)[:12]
        cfg['_config_id'] = self.config_id
        self.root = Path(cfg['root'])
        self.hub = self.root / 'postprocessing' / self.config_id
        self.hub.mkdir(parents=True, exist_ok=True)
        snapshot = self.hub / 'configuration.json'
        if snapshot.exists() and load(snapshot) != cfg:
            raise ValueError('Configuration collision')
        if not snapshot.exists():
            save(snapshot, cfg)
        self.motion = upstream(cfg['repo'], 'summarize_motion_from_confounds')

    def pairs(self):
        return sorted(p.parent for p in (self.root / 'results').glob('*/*/pair_metadata.json'))

    def stage_dir(self, pair):
        return Path(pair) / 's10' / self.config_id

    def verify_complete_pair(self, pair):
        spec = importlib.util.spec_from_file_location('offload_gate', Path(__file__).with_name('offload_completed.py'))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.verify_completed_pair(self.root, Path(pair), set())

    def prepare(self, pair):
        self.verify_complete_pair(pair)
        sd = self.stage_dir(pair); pre = sd / 'pre_qc.json'
        if pre.exists():
            result = load(pre)
            if result['config_id'] != self.config_id:
                raise ValueError('Mixed configuration in pre-QC')
            return result['rows']
        sd.mkdir(parents=True, exist_ok=True)
        s8 = sd / 's8'; s8.mkdir(exist_ok=True)
        rows = [inspect_run(g, pair, self.cfg, self.config_id, s8) for g in input_runs(pair, self.cfg)]
        unique(rows, 'pre-QC')
        save(sd / 'configuration.json', self.cfg)
        save(pre, {'config_id': self.config_id, 'created_at': now(), 'rows': rows})
        write_s8_tables(rows, s8)
        save(sd / 'provenance.json', {'created_at': now(), 'pipeline_sha256': sha(__file__),
             'repo_commit': inspect_protocol(LAB_ROOT)['repository_commit'],
             'protocol_source': inspect_protocol(LAB_ROOT),
             's8_sha256': {n: sha(Path(self.cfg['repo']) / 's8_final_qc' / (n + '.py')) for n in ('summarize_motion_from_confounds', 'extract_euler_from_freesurfer', 'finalize_inclusion')},
             'pair_metadata': load(Path(pair) / 'pair_metadata.json'), 'xcpd_image': self.cfg['image']})
        for name, subset in [('auto_qc', rows), ('candidates', [r for r in rows if r['candidate']]),
                             ('excluded', [r for r in rows if r['pre_xcpd_qc_status'] == 'fail']),
                             ('review_required', [r for r in rows if r['pre_xcpd_qc_status'] not in ('pass', 'fail')])]:
            tsv(sd / ('pre_xcpd_' + name + '.tsv'), [{k: v for k, v in r.items() if k != 'input_files'} for r in subset])
        return rows

    def attempt_root(self, row):
        return self.stage_dir(row['source_pair']) / 'runs' / run_key(row)

    def latest(self, row):
        files = sorted(self.attempt_root(row).glob('attempt-*/execution.json'))
        return (files[-1].parent, load(files[-1])) if files else (None, None)

    def plan_attempt(self, row):
        directory = self.attempt_root(row)
        number = len(list(directory.glob('attempt-*'))) + 1
        return directory / f'attempt-{number:03}', 'adni-xcpd-' + row['sub'].removeprefix('sub-') + '-' + digest([self.config_id, key(row), number])[:12]

    def run_one(self, row, force_retry=False):
        attempt, record = self.latest(row)
        if record and record['status'] == 'skipped_insufficient_time':
            return
        if record and record['status'] == 'success' and (attempt/'output_manifest.json').exists():
            if not (self.hub/'pilot_success.json').exists():
                qc=load(attempt/'output_validation.json')
                if qc['xcpd_status']!='success' or not qc['functional_outputs_valid']:raise ValueError('Success receipt lacks valid outputs')
                save(self.hub/'pilot_success.json',{'at':now(),'config_id':self.config_id,'run':run_key(row),'attempt':str(attempt),'validation':qc})
            return
        if record and record['status'] in ('failed', 'partial'):
            if not force_retry and len(list(self.attempt_root(row).glob('attempt-*'))) >= self.cfg['max_attempts']:
                return
            elapsed = time.time() - dt.datetime.fromisoformat(record['finished_at']).timestamp()
            if not force_retry and elapsed < self.cfg['retry_delay_seconds']:
                return
            record = None
        if not record:
            if shutil.disk_usage(self.root).free < self.cfg['local_reserve_gib'] * 1024**3:
                return
            attempt, name = self.plan_attempt(row)
            attempt.mkdir(parents=True, exist_ok=False)
            for d in ('derivatives', 'work'):
                (attempt / d).mkdir()
            save(attempt / 'bids_filter.json', bids_filter(row, self.cfg))
            save(attempt / 'expected_input.json', {'relative_bold': str(Path(row['source_bold_file']).relative_to(Path(row['source_pair']) / 'fmriprep')),
                 'relative_confounds':str(exact_one([Path(p) for p in row['input_files'] if p.endswith('_desc-confounds_timeseries.tsv')],'Exact selected confounds').relative_to(Path(row['source_pair'])/'fmriprep')),
                 'subject': row['sub'].removeprefix('sub-'), 'session': row['ses'].removeprefix('ses-') or None,
                 'file_format': self.cfg['file_format'], 'atlases': self.cfg['atlases'],
                 'expected_rois': self.cfg['expected_rois'], 'space': self.cfg['space'],
                 'duration_settings':{k:self.cfg[k] for k in ('fd_threshold','min_time','dummy_scans','motion_filter_type','head_radius','censor_between')},
                 'tr':row['tr'],'n_original_volumes':row['n_original_volumes']})
            shutil.copy2(Path(__file__).with_name('container_entry.py'), attempt / 'container_entry.py')
            cmd = command(self.cfg, row, attempt, name)
            record = {'status': 'prepared', 'created_at': now(), 'config_id': self.config_id,
                      'container': name, 'command': cmd, 'pipeline_sha256': sha(__file__), 'row': row}
            save(attempt / 'execution.json', record)
        if record['config_id'] != self.config_id:
            raise ValueError('Attempt from another configuration')
        name = record['container']
        result = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        if result.returncode:
            if record['status'] != 'prepared':
                record.update(status='failed', finished_at=now(), error='Previously started container vanished')
                add_timing(record)
                save(attempt / 'execution.json', record)
                refresh_safely(self.root)
                return
            for p, expected in row.get('input_files', {}).items():
                if sha(p) != expected:
                    raise ValueError('Input changed before XCP-D: ' + p)
            cid = subprocess.check_output(record['command'], text=True).strip()
            record['container_id'] = cid
            save(attempt / 'execution.json', record)
            info = load_json_command(['docker', 'inspect', name])[0]
        else:
            info = json.loads(result.stdout)[0]
        if info['Config'].get('Labels', {}).get('adni.config_id') != self.config_id or info['Config']['Labels'].get('adni.run_key') != run_key(row):
            raise ValueError('Container identity collision')
        if info['State']['Status'] == 'created':
            subprocess.check_call(['docker', 'start', name], stdout=subprocess.DEVNULL)
        record.update(status='running', started_at=record.get('started_at', now()))
        save(attempt / 'execution.json', record)
        save(self.hub / 'status.json', {'at': now(), 'status': 'xcpd_running', 'run': run_key(row), 'container': name, 'LLM_calls': 0})
        exit_code = self.wait_container(name, row)
        record['container_ended_at'] = now()
        try:
            state = load_json_command(['docker', 'inspect', name])[0]['State']
            record['container_started_at'] = state.get('StartedAt')
            record['container_finished_at'] = state.get('FinishedAt')
        except Exception as exc:
            record['timing_observation_error'] = str(exc)
        add_timing(record)
        save(attempt / 'execution.json', record)
        refresh_safely(self.root)
        with (attempt / 'container.log').open('w') as f:
            subprocess.run(['docker', 'logs', name], stdout=f, stderr=subprocess.STDOUT)
        unchanged = all(sha(p) == expected for p, expected in row.get('input_files', {}).items())
        qc = validate_outputs(attempt, row, self.cfg, exit_code)
        if not unchanged:
            qc.update(xcpd_status='partial', functional_outputs_valid=False)
            qc['xcpd_errors'].append('Read-only input hash changed')
        save(attempt / 'output_validation.json', qc)
        if qc['xcpd_status'] == 'success':
            save(attempt / 'output_manifest.json', {str(p.relative_to(attempt / 'derivatives')): sha(p) for p in sorted((attempt / 'derivatives').rglob('*')) if p.is_file()})
        record.update(status=qc['xcpd_status'], exit_code=exit_code, finished_at=now(), input_unchanged=unchanged)
        add_timing(record)
        save(attempt / 'execution.json', record)
        refresh_safely(self.root)
        self.event('run_finished',run=run_key(row),status=qc['xcpd_status'],exit_code=exit_code,errors=qc['xcpd_errors'])
        save(self.hub/'status.json',{'at':now(),'status':'run_'+qc['xcpd_status'],'run':run_key(row),'LLM_calls':0})
        if qc['xcpd_status'] == 'success':
            if not (self.hub / 'pilot_success.json').exists():
                save(self.hub / 'pilot_success.json', {'at': now(), 'config_id': self.config_id, 'run': run_key(row), 'attempt': str(attempt), 'validation': qc})

    def detect_terminal_worker_failure(self, name, row):
        info = load_json_command(['docker', 'inspect', name])[0]
        labels = info['Config'].get('Labels', {})
        if labels.get('adni.config_id') != self.config_id or labels.get('adni.run_key') != run_key(row):
            raise ValueError('Container identity differs during failure monitoring')
        if not info['State'].get('Running'):
            return None
        reason = 'container_oom' if info['State'].get('OOMKilled') else None
        logs = subprocess.run(['docker', 'logs', '--tail', '120', name], capture_output=True, text=True, timeout=25)
        tail = logs.stdout + logs.stderr
        if 'concurrent.futures.process.BrokenProcessPool:' in tail:
            reason = reason or 'broken_process_pool'
        if reason:
            attempt, record = self.latest(row)
            save(attempt / 'runtime_failure.json', {'at': now(), 'reason': reason, 'container': name,
                'container_id': info.get('Id'), 'state': info['State'], 'tail': tail[-16000:],
                'action': 'stop failed container, validate outputs as failure and allow bounded retry'})
            self.event('terminal_worker_failure', container=name, reason=reason)
            subprocess.run(['docker', 'stop', '--time', '10', name], check=True, capture_output=True, text=True, timeout=30)
        return reason

    def wait_container(self,name,row):
        observer=subprocess.Popen(['docker','wait',name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        while observer.poll() is None:
            time.sleep(self.cfg['poll_seconds'])
            self.detect_terminal_worker_failure(name, row)
            changed=False
            for pair in self.pairs():
                if (self.stage_dir(pair)/'pre_qc.json').exists():continue
                try:
                    self.prepare(pair);changed=True
                except Exception as exc:self.event('new_pair_pre_qc_error',pair=str(pair),error=str(exc))
            if changed:
                try:self.aggregate()
                except Exception as exc:self.event('aggregation_error',error=str(exc))
            save(self.hub/'status.json',{'at':now(),'status':'xcpd_running','run':run_key(row),'container':name,
                 'S8_new_completions_scanned':True,'LLM_calls':0})
        output,error=observer.communicate()
        if observer.returncode:raise RuntimeError('Docker wait lost connection; will reattach: '+error[-200:])
        return int(output.strip().splitlines()[-1])

    def revalidate(self):
        for pair in self.pairs():
            pre = self.stage_dir(pair) / 'pre_qc.json'
            if not pre.exists() or (self.stage_dir(pair) / 'archive_ready.json').exists():continue
            for row in load(pre)['rows']:
                attempt, record = self.latest(row)
                if not record or record.get('exit_code') != 0 or record['status'] == 'success':continue
                if not all(sha(path)==h for path,h in row['input_files'].items()):raise ValueError('Input changed before revalidation')
                old=attempt/'output_validation.json'
                if old.exists():shutil.copy2(old,attempt/('validation_previous_'+sha(old)[:12]+'.json'))
                qc=validate_outputs(attempt,row,self.cfg,0)
                save(old,qc);record.update(status=qc['xcpd_status'],revalidated_at=now(),validator_sha256=sha(__file__))
                save(attempt/'execution.json',record)
                if qc['xcpd_status']=='success':
                    save(attempt/'output_manifest.json',{str(f.relative_to(attempt/'derivatives')):sha(f) for f in (attempt/'derivatives').rglob('*') if f.is_file()})
                    if not (self.hub/'pilot_success.json').exists():save(self.hub/'pilot_success.json',{'at':now(),'config_id':self.config_id,'run':run_key(row),'attempt':str(attempt),'validation':qc})
            self.mark_ready(pair,load(pre)['rows'])
        self.aggregate()

    def verify_final_output_files(self, row):
        if row.get('xcpd_status') != 'success':return
        attempt=Path(row['xcpd_attempt']);record=load(attempt/'execution.json')
        if record.get('config_id')!=self.config_id or record.get('exit_code')!=0 or record.get('input_unchanged') is not True:
            raise ValueError('Finalization execution provenance mismatch')
        manifest=load(attempt/'output_manifest.json')
        if not manifest:raise ValueError('Final output manifest missing')
        for relative,expected in manifest.items():
            rel=Path(relative)
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid final output path')
            path=attempt/'derivatives'/rel
            if not path.is_file() or sha(path)!=expected:
                raise ValueError('Final output missing or changed: '+str(path))

    def merge(self, rows):
        merged = []
        for row in rows:
            if row.get('config_id') != self.config_id:raise ValueError('Mixed pipeline run in QC row')
            item = {k: v for k, v in row.items() if k != 'input_files'}
            attempt, execution = self.latest(row)
            if execution:
                validation = attempt / 'output_validation.json'
                item.update(load(validation) if validation.exists() else {'xcpd_status': execution['status']})
                item['xcpd_attempt'] = str(attempt)
            else:
                item['xcpd_status'] = 'skipped_pre_qc_fail' if row['pre_xcpd_qc_status'] == 'fail' else 'not_started'
            merged.append(item)
        unique(merged, 'integrated QC')
        return merged

    def aggregate(self, cohort_ready=False, mriqc_flags=None):
        with (self.hub / 'aggregation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._aggregate(cohort_ready, mriqc_flags)

    def _aggregate(self, cohort_ready=False, mriqc_flags=None):
        rows = []
        for pair in self.pairs():
            p = self.stage_dir(pair) / 'pre_qc.json'
            if p.exists():
                data = load(p)
                if data['config_id'] != self.config_id:
                    raise ValueError('Mixed pipeline runs')
                rows += self.merge(data['rows'])
        unique(rows, 'master')
        if not rows:
            return []
        if cohort_ready:
            if not mriqc_flags:
                raise ValueError('Finalization requires explicit current-cohort MRIQC flags')
            cf = dict(self.cfg, mriqc_flags_file=mriqc_flags)
            eu = pd.DataFrame([{'sub': r['sub'], 'ses': r['ses'], 'site': r['site'], 'avg_en': r.get('avg_euler')} for r in rows]).drop_duplicates(['sub', 'ses'])
            if eu.avg_en.isna().any():
                raise ValueError('Cannot finalize with missing Euler')
            flags, _ = upstream(self.cfg['repo'], 'finalize_inclusion').compute_sitewise_euler_exclusion(eu)
            for r in rows:
                self.verify_final_output_files(r)
                r['euler_qc_flag'] = int(flags.loc[r['sub']])
                r['mriqc_exclude_flag'], r['mriqc_flag_status'] = get_mriqc_flag(r, cf)
        visual = self.hub / 'visual_review.tsv'
        old_visual_hash = sha(visual) if visual.exists() else None
        previous = table(visual) if visual.exists() else []
        unique(previous, 'manual review')
        if any(r.get('config_id') != self.config_id for r in previous):
            raise ValueError('Manual QC from a different pipeline configuration')
        old = {key(r): r for r in previous}
        current_keys = {key(r) for r in rows}
        if any(k not in current_keys for k in old):
            raise ValueError('Manual QC has unknown run identities')
        audit = set()
        strata = collections.defaultdict(list)
        for r in rows:
            if r.get('xcpd_status') == 'success' and r.get('pre_xcpd_qc_status') != 'fail':
                strata[(r['site'], r.get('scanner_vendor', 'unknown'))].append(r)
        for group in strata.values():
            ranked = sorted(group, key=lambda r: digest([self.cfg['random_seed'], key(r)]))
            audit.update(key(r) for r in ranked[:math.ceil(len(group) * self.cfg['review']['random_fraction'])])
        visualrows = []
        for r in rows:
            reasons = []
            high = r.get('xcpd_status') in ('failed', 'partial') or r.get('xcpd_qc_status') in ('review_required', 'fail') or r.get('validation_errors') or r.get('mriqc_exclude_flag') == 1 or r.get('euler_qc_flag') == 1
            if high: reasons.append('processing_or_quantitative_QC_warning')
            near = r.get('mean_fd', 0) >= self.cfg['pre_mean_fd_threshold'] * self.cfg['review']['near_threshold_fraction'] or r.get('fd_over_threshold_proportion',r.get('fd_over_0p5_proportion', 0)) >= self.cfg['pre_fd_proportion_threshold'] * self.cfg['review']['near_threshold_fraction']
            if near: reasons.append('near_motion_threshold')
            if key(r) in audit: reasons.append('seeded_site_vendor_random_audit')
            required = bool(reasons) or old.get(key(r), {}).get('visual_review_required') == 'True'
            if required and not reasons:reasons.append('previously_selected_for_review')
            r.update(review_priority='high' if high else ('medium' if near else ('random_audit' if key(r) in audit else ('medium' if required else 'none'))),
                     review_reason=';'.join(reasons), visual_review_required=required)
            r.update({k: old.get(key(r), {}).get(k, '') for k in MANUAL})
            if not r['visual_qc_status']:
                r['visual_qc_status'] = 'pending' if required else 'not_reviewed'
            if r['visual_qc_status'] not in ('pass', 'fail', 'pending', 'not_reviewed'):
                raise ValueError('Invalid manual review status')
            status, inc, why = decide_final(r, cohort_ready)
            r.update(final_qc_status=status, final_include=inc, final_exclusion_reason=why,
                     ANALYSIS_READY=False, inclusion_scope='imaging_QC_only_source_and_clinical_checks_separate')
            visualrows.append({k: r.get(k, '') for k in list(KEYS) + ['config_id', 'review_priority', 'review_reason', 'fmriprep_report', 'xcpd_report', 'executive_summary', 'visual_review_required'] + list(MANUAL)})
        # Human-entered fields are never filled with AI judgments; preserve every edit revision.
        if visual.exists():
            if sha(visual) != old_visual_hash:
                raise RuntimeError('Human review edited during aggregation; preserving changes for next loop')
            h = sha(visual); history = self.hub / 'manual_review_history' / (h + '.tsv')
            if not history.exists():
                history.parent.mkdir(exist_ok=True); shutil.copy2(visual, history)
        tsv(visual, visualrows)
        outdir = self.hub if not cohort_ready else self.hub / 'finalizations' / dt.datetime.now().strftime('%Y%m%dT%H%M%S')
        tsv(outdir / 'final_qc_master.tsv', rows)
        links = []
        for row in rows:
            value = str(row.get('epi_date') or '')
            if re.fullmatch(r'\d{8}', value):
                value = value[:4] + '-' + value[4:6] + '-' + value[6:]
            links.append({**{k: row[k] for k in KEYS}, 'Image_ID': row.get('epi_image_id', ''),
                          'Scan_Date': value, 'pair_id': row.get('pair_id', '')})
        tsv(outdir / 'clinical_scan_links.tsv', links)
        for filename, condition in [('final_included_runs.tsv', lambda r: r['final_qc_status'] == 'include'),
                                    ('final_excluded_runs.tsv', lambda r: r['final_qc_status'] == 'exclude'),
                                    ('pending_review.tsv', lambda r: r['final_qc_status'] == 'pending_review')]:
            tsv(outdir / filename, [r for r in rows if condition(r)], list(rows[0]))
        included = sorted({(r['sub'], r['ses']) for r in rows if r['final_qc_status'] == 'include'})
        tsv(outdir / 'final_included_sessions.tsv', [{'sub': s, 'ses': v, 'rule': 'at_least_one_included_run'} for s, v in included], ['sub', 'ses', 'rule'])
        counts = {field: dict(collections.Counter(str(r.get(field, 'NA')) for r in rows)) for field in ('pre_xcpd_qc_status', 'xcpd_status', 'xcpd_qc_status', 'final_qc_status', 'review_priority', 'visual_qc_status')}
        summary = {'subjects': len({r['sub'] for r in rows}), 'sessions': len({(r['sub'], r['ses']) for r in rows}), 'runs': len(rows), 'cohort_finalization_deferred': not cohort_ready, 'counts': counts}
        summary.update(xcpd_attempts_total=sum(len(list(self.attempt_root(r).glob('attempt-*/execution.json'))) for r in rows),
                       visual_review_required=sum(bool(r['visual_review_required']) for r in rows),
                       visual_review_completed=sum(r['visual_qc_status'] in ('pass','fail') and bool(r['reviewer']) and bool(r['review_date']) for r in rows))
        summary['input_versions']={k:sorted({str(r.get(k,'NA')) for r in rows}) for k in ('fmriprep_version','freesurfer_version','mriqc_version')}
        save(outdir / 'summary.json', summary)
        frame = pd.DataFrame(rows)
        site_counts=[]
        for site,group in frame.groupby('site',dropna=False):
            for stage in ('pre_xcpd_qc_status','xcpd_status','xcpd_qc_status','final_qc_status'):
                if stage not in group:continue
                for status,n in group[stage].fillna('NA').value_counts().items():
                    site_counts.append({'site':site,'stage':stage,'status':status,'runs':int(n),'site_runs':len(group),'proportion':float(n/len(group))})
        tsv(outdir/'site_qc_counts.tsv',site_counts)
        reasons=collections.Counter()
        for r in rows:
            for field in ('xcpd_errors','xcpd_warnings','final_exclusion_reason'):
                values=r.get(field,[])
                if isinstance(values,str):values=values.split(';')
                for reason in values or []:
                    if reason:reasons[(field,str(reason))]+=1
        tsv(outdir/'qc_reason_counts.tsv',[{'category':k[0],'reason':k[1],'runs':n} for k,n in sorted(reasons.items())],['category','reason','runs'])
        distributions = {}
        for metric in ('mean_fd', 'censoring_proportion', 'remaining_duration_sec'):
            values = pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors='coerce').dropna()
            distributions[metric] = {'n': len(values), 'min': values.min() if len(values) else None,
                                     'median': values.median() if len(values) else None, 'max': values.max() if len(values) else None}
        save(outdir / 'metric_distributions.json', distributions)
        lines = ['# ADNI S8 · XCP-D QC', '', f'설정 ID: `{self.config_id}`', '', '전체 자료 기반 최종 판정: ' + ('실행됨' if cohort_ready else '보류 중'), '', '```json', json.dumps(summary, ensure_ascii=False, indent=2), '```', '', '육안 QC는 연구자만 기록. 자동 판정 대기는 정상 통과를 의미하지 않음.', '', '## Methods 초안', '',
                 f'XCP-D {self.cfg["xcpd_version"]}, {self.cfg["mode"]}, {self.cfg["file_format"]}, atlas {self.cfg["atlases"]}. '
                 f'Nuisance regressors: {self.cfg["nuisance_regressors"]}; GSR: {self.cfg["global_signal_regression"]}. '
                 f'Frame censoring FD > {self.cfg["fd_threshold"]} mm, 최소 유효 시간 {self.cfg["min_time"]}초. '
                 f'Bandpass {self.cfg["bandpass"]}: {self.cfg["lower_bpf"]}–{self.cfg["upper_bpf"]} Hz, order {self.cfg["bpf_order"]}; '
                 f'smoothing {self.cfg["smoothing"]} mm; dummy scans {self.cfg["dummy_scans"]}; despike {self.cfg["despike"]}. '
                 f'S8 mean FD > {self.cfg["pre_mean_fd_threshold"]}, FD > {self.cfg["pre_fd_threshold"]} 비율 > {self.cfg["pre_fd_proportion_threshold"]}. '
                 'Run 결합 없음. 실제 설정 정본은 configuration.json. 사이트별 Euler·MRIQC와 인간 검토 후 최종 포함 확정.', '',
                 '## 분포 및 사이트 요약', '', '수치 정본: metric_distributions.json, site_qc_counts.tsv, qc_reason_counts.tsv. 사이트 표는 각 단계의 건수와 비율이며, 최종 판정 보류 상태의 제외율은 확정하지 않음.', '',
                 '### 실제 입력 버전', '', '```json',json.dumps(summary['input_versions'],ensure_ascii=False,indent=2),'```','',
                 '### 정량적 지표 분포', '', '```json',json.dumps(clean(distributions),ensure_ascii=False,indent=2),'```','',
                 '### 처리 실패·경고·최종 사유', '', '```json',json.dumps([{'category':k[0],'reason':k[1],'runs':n} for k,n in sorted(reasons.items())],ensure_ascii=False,indent=2),'```','',
                 '```mermaid', 'flowchart LR', f'A["fMRIPrep 입력 {len(rows)} runs"] --> B["S8 지표"]',
                 f'B --> C["XCP-D 성공 {sum(r.get("xcpd_status")=="success" for r in rows)} runs"]',
                 'C --> D["정량적 QC 및 육안 검토 목록"]', 'D --> E["전체 자료 기반 최종 판정: 별도 실행"]', '```']
        (outdir / 'qc_summary_report.md').write_text('\n'.join(lines) + '\n')
        return rows

    def mark_ready(self, pair, rows):
        merged = self.merge(rows)
        complete = all(r.get('xcpd_status') in ('success', 'skipped_insufficient_time') or r['pre_xcpd_qc_status'] == 'fail' for r in merged)
        if not complete:
            return False
        sd = self.stage_dir(pair)
        report_spec = importlib.util.spec_from_file_location('individual_qc_report', Path(__file__).with_name('qc_report.py'))
        reports = importlib.util.module_from_spec(report_spec); report_spec.loader.exec_module(reports)
        report_paths = reports.write(Path(pair), clean(merged), self.cfg, self.config_id)
        receipt = {'status': 'postprocessing_complete_final_QC_pending', 'config_id': self.config_id,
                   'completed_at': now(), 'subject': load(Path(pair) / 'pair_metadata.json')['subject'],
                   'runs': [{k: r.get(k) for k in list(KEYS) + ['pre_xcpd_qc_status', 'xcpd_status', 'xcpd_attempt', 'functional_outputs_valid']} for r in merged]}
        receipt['evidence'] = {str(path.relative_to(pair)): sha(path) for path in report_paths}
        for r in merged:
            if r.get('xcpd_status') in ('success', 'skipped_insufficient_time'):
                names = ('execution.json', 'output_validation.json', 'output_manifest.json') if r['xcpd_status']=='success' else ('execution.json','output_validation.json','duration_gate.json')
                for name in names:
                    path = Path(r['xcpd_attempt']) / name
                    receipt['evidence'][str(path.relative_to(pair))] = sha(path)
        receipt['evidence'][str((sd / 'pre_qc.json').relative_to(pair))] = sha(sd / 'pre_qc.json')
        p = sd / 'archive_ready.json'
        if not p.exists():
            save(p, receipt)
        return True

    def once(self, pilot=False, prepare_only=False, retry_failed=False):
        prepared = []
        for pair in self.pairs():
            try:
                prepared.append((pair, self.prepare(pair)))
            except Exception as exc:
                self.event('prepare_error', pair=str(pair), error=str(exc))
        self.aggregate()
        if prepare_only:
            return
        for pair, rows in prepared:
            for row in rows:
                if not row['candidate']:
                    continue
                if retry_failed:
                    _, rec = self.latest(row)
                    if not rec or rec['status'] not in ('failed', 'partial'):continue
                if pilot and (self.hub / 'pilot_success.json').exists():
                    break
                self.run_one(row, force_retry=retry_failed)
                self.aggregate()
                if not (self.hub / 'pilot_success.json').exists():
                    # A failed pilot blocks batch expansion; a later loop retries it.
                    _, current = self.latest(row)
                    if current and current['status']=='skipped_insufficient_time':continue
                    save(self.hub/'status.json',{'at':now(),'status':'pilot_validation_pending_or_blocked','run':run_key(row),
                         'execution_status':current['status'] if current else 'not_started','LLM_calls':0})
                    return
            self.mark_ready(pair, rows)
        save(self.hub / 'status.json', {'at': now(), 'status': 'watching_for_completed_fmriprep', 'config_id': self.config_id, 'LLM_calls': 0})

    def event(self, kind, **fields):
        item = {'at': now(), 'kind': kind, **fields}
        with (self.hub / 'events.jsonl').open('a') as f:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(json.dumps(item, ensure_ascii=False), flush=True)


def load_json_command(cmd):
    return json.loads(subprocess.check_output(cmd, text=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, help='External private JSON; start from 03_config/xcpd_linc.example.json')
    parser.add_argument('action', choices=['preflight', 'pre-qc', 'dry-run', 'pilot', 'once', 'watch', 'retry-failed', 'revalidate', 'collect', 'finalize', 'slurm'])
    parser.add_argument('--cohort-complete', action='store_true')
    parser.add_argument('--mriqc-flags')
    args = parser.parse_args()
    p = Pipeline(args.config)
    if args.action == 'preflight':
        cfg = p.cfg
        for path in (cfg['root'], cfg['repo'], cfg['license'], cfg['templateflow']):
            if not Path(path).exists(): raise ValueError('Required path missing: ' + path)
        cache=p.root/'postprocessing/cache';cache.mkdir(exist_ok=True)
        prefix=['docker','run','--rm','--platform','linux/amd64','--network','none',
                '-e','OPENBLAS_NUM_THREADS=1','-e','MPLCONFIGDIR=/cache/matplotlib','-v',str(cache)+':/cache',cfg['image']]
        versions = subprocess.check_output(prefix + ['--version'], text=True)
        if cfg['xcpd_version'] not in versions: raise ValueError('XCP-D version differs')
        helptext = subprocess.check_output(prefix + ['--help'], text=True)
        (p.hub / 'xcpd-help.txt').write_text(helptext)
        (p.hub / 'xcpd-version.txt').write_text(versions)
        save(p.hub / 'environment.json', {'at': now(), 'os': platform.platform(), 'architecture': platform.machine(), 'cpu_count':os.cpu_count(),
             'slurm': shutil.which('sbatch'), 'apptainer': shutil.which('apptainer'), 'docker_image': cfg['image'], 'version': versions.strip(),
             'local_free_bytes': shutil.disk_usage(p.root).free,'repo_commit':inspect_protocol(LAB_ROOT)['repository_commit']})
        print(versions.strip(), p.hub); return
    if args.action == 'finalize':
        if not args.cohort_complete: raise ValueError('Explicit --cohort-complete required; automatic loop never finalizes')
        p.aggregate(cohort_ready=True, mriqc_flags=args.mriqc_flags); return
    if args.action == 'collect':
        p.aggregate()
        # Plot only on demand, avoiding repeated plotting work in the watch loop.
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            frame = pd.read_csv(p.hub / 'final_qc_master.tsv', sep='\t')
            fig, axes = plt.subplots(1, 3, figsize=(12, 3))
            for ax, metric in zip(axes, ('mean_fd', 'censoring_proportion', 'remaining_duration_sec')):
                data = pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors='coerce').dropna()
                ax.hist(data, bins=min(20, max(1, len(data))))
                ax.set_title(metric + f' (n={len(data)})')
            fig.tight_layout(); fig.savefig(p.hub / 'qc_distributions.png', dpi=160); plt.close(fig)
        except ImportError:
            p.event('plot_skipped', reason='matplotlib unavailable; numerical summaries retained')
        return
    with (p.hub / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if args.action == 'watch' else fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'revalidate':p.revalidate();return
        if args.action in ('pre-qc', 'dry-run', 'slurm'):
            p.once(prepare_only=True)
            commands = []
            for pair in p.pairs():
                fp = p.stage_dir(pair) / 'pre_qc.json'
                if not fp.exists(): continue
                for row in load(fp)['rows']:
                    if row['candidate']:
                        attempt, name = p.plan_attempt(row)
                        commands.append({'run': run_key(row), 'bids_filter': bids_filter(row, p.cfg), 'command': command(p.cfg, row, attempt, name)})
            save(p.hub / 'dry_run.json', commands)
            if args.action == 'slurm':
                # Export only; never submit jobs automatically.
                s = p.cfg['slurm']
                script = ['#!/bin/bash', f'#SBATCH --partition={s["partition"]}', f'#SBATCH --cpus-per-task={s["cpus"]}', f'#SBATCH --mem={s["mem_gb"]}G', f'#SBATCH --time={s["time"]}', f'#SBATCH --array=0-{max(0, len(commands)-1)}', 'set -euo pipefail', '# Review paths and the Apptainer image on the target cluster before submission.', 'python3 ' + shlex.quote(str(Path(__file__).with_name('slurm_task.py'))) + ' ' + shlex.quote(str(p.config_path)) + ' "$SLURM_ARRAY_TASK_ID"']
                (p.hub / 'xcpd_array.slurm').write_text('\n'.join(script) + '\n')
            print(json.dumps({'candidates': len(commands), 'mapping': str(p.hub / 'dry_run.json')})); return
        while True:
            try:
                p.once(pilot=args.action == 'pilot', retry_failed=args.action == 'retry-failed')
            except Exception as exc:
                p.event('worker_error', error=f'{type(exc).__name__}: {exc}')
                if args.action != 'watch': raise
            if args.action != 'watch': break
            time.sleep(p.cfg['poll_seconds'])


if __name__ == '__main__':
    main()
