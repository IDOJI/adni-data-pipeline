#!/usr/bin/env python3
"""Offline synthetic integration example. No images here are real preprocessed data."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import platform
import shlex
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / '07_reproducibility'
SUB = 'sub-ADNI999S9999'
SES = 'ses-M000'
STEM = SUB + '_' + SES
BOLD = STEM + '_task-rest_run-1'
SPACE = 'MNI152NLin6Asym'
STEPS = ('3a', '5c', '5d', '8', '8a', '9a', '9b', '10', '11', '12')
PAIR = Path('fixture_archive/999_S_9999/EPI_20200101_MT1_20200101')
WARNING = 'SYNTHETIC FIXTURE ONLY. No MRIQC, fMRIPrep, XCP-D or real archival execution occurred.'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def table(path, rows, fields=None):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), delimiter='\t' if path.suffix == '.tsv' else ',')
        writer.writeheader(); writer.writerows(rows)


def image(path, data, tr=3.):
    path.parent.mkdir(parents=True, exist_ok=True)
    im = nib.Nifti1Image(data, np.eye(4))
    im.header.set_xyzt_units('mm', 'sec'); im.header.set_dim_info(slice=2)
    if data.ndim == 4: im.header.set_zooms((1, 1, 1, tr))
    # Fixed gzip mtime and no embedded filename: input hashes do not depend on path/time.
    path.write_bytes(gzip.compress(im.to_bytes(), mtime=0))


def external(path):
    p = Path(path).expanduser().resolve()
    repo = ROOT.parent
    if p == repo or repo in p.parents or p in repo.parents:
        raise ValueError('Use an external data directory, outside the repository and its ancestors')
    return p


def load_module(relative):
    path = ROOT / relative
    sys.path.insert(0, str(path.parent))
    name = 'repro_' + path.parent.name + '_' + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def init(root):
    if root.exists(): raise FileExistsError('Use a new toy root; existing data are never overwritten')
    root.mkdir(parents=True)
    (root / 'SYNTHETIC_ONLY.txt').write_text(WARNING + '\n')
    inp = root / 'inputs'; inp.mkdir()
    bids = inp / 'bids'
    write_json(bids / 'dataset_description.json', {'Name': WARNING, 'BIDSVersion': '1.10.0', 'DatasetType': 'raw', 'License': 'CC0'})
    labels = np.zeros((4, 4, 4), np.int16); labels[:2] = 1; labels[2:] = 3
    t = np.arange(1, 121, dtype=np.float32)
    data = np.where(labels[..., None] == 1, t, 10 * t).astype(np.float32)
    evidence = []; registry = []
    for mod, iid, kind, suffix, values in [('T1', '100', 'anat', 'T1w', np.zeros((4,4,4), np.float32)), ('EPI', '101', 'func', 'task-rest_run-1_bold', data)]:
        stem = bids / SUB / SES / kind / (STEM + '_' + suffix)
        path = Path(str(stem) + '.nii.gz'); image(path, values)
        meta = dict(SeriesInstanceUID='synthetic.' + iid, AcquisitionDateTime='2020-01-01T12:00:00', ImageID=iid)
        if mod == 'EPI': meta.update(TaskName='rest', RepetitionTime=3., SliceTiming=[0., .75, 1.5, 2.25], SliceEncodingDirection='k', PhaseEncodingDirection='j')
        write_json(Path(str(stem) + '.json'), meta)
        registry.append(dict(PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01', MODALITY=mod, IMAGE_ID=iid, SERIES_UID=meta['SeriesInstanceUID'], SEARCH_PHASE='ADNI 3', ELIGIBLE='True', QC_STATUS='pass', EXCLUSION_REASONS=''))
        evidence.append(dict(SOURCE_PTID='999_S_9999', STUDY_DATE='2020-01-01', MODALITY=mod, SOURCE_IMAGE_ID='I' + iid, NIFTI_SHA256=sha(path)))
    table(inp / 'images.csv', registry)
    table(inp / 'hashes.csv', evidence)
    table(inp / '04.epi-analysis-manifest.csv', [dict(EPI_KEY='999_S_9999:2020-01-01:I101', PTID='999_S_9999', MRI_STUDY_DATE='2020-01-01', EPI_IMAGE_ID='101', PROPOSED_T1_IMAGE_ID='100', T1_PAIRING_STATUS='same_day_proposed', EPI_METADATA_QC_STATE='documented', PAIRING_REVIEW_REQUIRED='False', PROTOCOL_SCOPE='GO_2_3', PREPROCESSING_READY='False', ANALYSIS_READY='False')])
    write_json(inp / 'pairing.json', {'simulation_only': True, 'inputs': {'candidates': {'path': str(inp / 'images.csv'), 'sha256': sha(inp / 'images.csv')}}, 'outputs': {'epi': {'path': str(inp / '04.epi-analysis-manifest.csv'), 'sha256': sha(inp / '04.epi-analysis-manifest.csv')}}})
    write_json(inp / 'binding.json', dict(images=str(inp / 'images.csv'), epi_manifest=str(inp / '04.epi-analysis-manifest.csv'), pairing_receipt=str(inp / 'pairing.json'), bids_roots=[str(bids)], hash_evidence=[str(inp / 'hashes.csv')], output_dir=str(root / 'outputs/5d')))
    table(inp / 'MRIQC.csv', [dict(image_id='101', ParticipantID='999_S_9999', StudyDate='2020-01-01', SeriesType='BOLD', SeriesInstanceUID='synthetic.101', StudyInstanceUID='study.synthetic', LONIStudy='S99', LONISeries='S101', SeriesNumber='101', MRIProtocolPhase='ADNI3', SeriesTime='12:00:00')])
    table(inp / 'MAYO.csv', [dict(LONI_IMAGE='I101', PTID='999_S_9999', RID='9999', SERIES_DATE='2020-01-01', SERIES_TYPE='BOLD', SERIESINSTANCEUID='synthetic.101', STUDYINSTANCEUID='study.synthetic', LONI_STUDY='S99', LONI_SERIES='S101', SERIES_QUALITY='2', SERIES_SELECTED='TRUE', STUDY_OVERALLPASS='1', PROTOCOL_STATUS='1', STUDY_PROTOCOL_STATUS='1', SERIES_COMMENTS='', PROTOCOL_COMMENTS='', STUDY_COMMENTS='', STUDY_PROTOCOL_COMMENT='')])
    table(inp / 'NFQ.csv', [dict(LONIImage='I101', RID='9999', StudyDate='2020-01-01', SeriesInstanceUID='synthetic.101', OVERALLQC='2', SLICETIMING='')])
    table(inp / 'final_heuristics.tsv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01', SERIES_UID='synthetic.101')])
    table(inp / 'included.tsv', [dict(sub=SUB, ses=SES, task='rest', run='1')])
    table(inp / 'scan_links.csv', [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='101', Scan_Date='2020-01-01', Phase='ADNI3', Age='70', SERIES_UID='synthetic.101')])
    table(inp / 'DXSUM.csv', [dict(PTID='999_S_9999', RID='9999', PHASE='ADNI3', EXAMDATE='2020-01-02', DIAGNOSIS='3', DXDDUE='2', DXMDUE='1', HAS_QC_ERROR='0')])
    table(inp / 'PTDEMOG.csv', [dict(PTID='999_S_9999', RID='9999', VISDATE='2020-01-01', PTEDUCAT='', PTGENDER='1', PTDOB='01/1950')])
    table(inp / 'confirmed_st_absence.csv', [], ['IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'ST_STATUS', 'EVIDENCE_REF'])
    fd = np.full(120, .1); fd[0] = np.nan; fd[20] = .8; fd[40] = .9
    conf = pd.DataFrame({'framewise_displacement': fd, 'std_dvars': np.ones(120), 'non_steady_state_outlier00': [1,1] + [0]*118})
    func = inp / 'derivative_fixture' / SUB / SES / 'func'; func.mkdir(parents=True)
    conf.to_csv(func / (BOLD + '_desc-confounds_timeseries.tsv'), sep='\t', index=False, na_rep='n/a')
    atlas = inp / 'atlas'; atlas.mkdir()
    image(atlas / 'atlas.nii.gz', labels)
    image(atlas / 'mask.nii.gz', np.ones((4,4,4), np.uint8))
    image(atlas / (BOLD + '_space-' + SPACE + '_desc-denoised_bold.nii.gz'), data)
    write_json(atlas / 'bold.json', {'RepetitionTime': 3., 'Synthetic': True})
    write_json(atlas / 'catalog.json', {'kind': 'discrete_label_catalog', 'atlases': [dict(id='toy', source='external', citation=WARNING, path='atlas.nii.gz', space=SPACE, kind='labels', background=0, sha256=sha(atlas / 'atlas.nii.gz'), expected_labels={'ids':[1,3]}, label_format='numeric', source_warnings=[])]})
    pair = root / PAIR; pair.mkdir(parents=True)
    (pair / 'SYNTHETIC_ONLY.txt').write_text(WARNING + '\n')
    # Deliberately simulated archive and derivative records test only the exporter contract.
    write_json(pair / 'relocation_receipt.json', dict(status='archived_and_local_space_reclaimed', simulation_only=True, warning=WARNING))
    write_json(pair / 'pair_metadata.json', dict(ptid='999_S_9999', subject='ADNI999S9999', pair_id=PAIR.name, epi_date='2020-01-01', mt1_date='2020-01-01', epi_image_id='101', mt1_image_id='100', simulation_only=True))
    stats = pair / 'fmriprep/sourcedata/freesurfer' / STEM / 'stats'; stats.mkdir(parents=True)
    (stats / 'aseg.stats').write_text('# SYNTHETIC\n# Measure EstimatedTotalIntraCranialVol, eTIV, description, 1500000, mm^3\n# ColHeaders Index SegId NVoxels Volume_mm3 StructName\n1 17 100 123.4 Left-Hippocampus\n2 53 110 145.6 Right-Hippocampus\n')
    for hemi in ('lh', 'rh'):
        (stats / (hemi + '.aparc.stats')).write_text('# SYNTHETIC\n# Measure Cortex, MeanThickness, description, 2.4, mm\n# ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd\nsuperiorfrontal 100 200 300 2.1 0.2\n')
    row = dict(sub=SUB, ses=SES, task='task-rest', run='run-1', acq='', dir='', echo='', rec='', config_id='toy-fixture', pre_xcpd_qc_status='review_required', mean_fd=.11166666666666666)
    stage = pair / 's10/toy-fixture'; attempt = stage / 'runs/toy/attempt-001'
    write_json(stage / 'pre_qc.json', dict(simulation_only=True, rows=[row]))
    write_json(attempt / 'execution.json', dict(simulation_only=True, status='success', row=row, warning=WARNING))
    write_json(attempt / 'output_validation.json', dict(simulation_only=True, functional_outputs_valid=True, xcpd_warnings=['synthetic_fixture_not_scientific_output']))
    deriv = attempt / 'derivatives'; outfunc = deriv / SUB / SES / 'func'; outfunc.mkdir(parents=True)
    for metric in ('reho', 'alff'):
        pd.DataFrame([{'ROI_A': .2, 'ROI_B': np.nan}]).to_csv(outfunc / (BOLD + '_space-MNI_atlas-toy_stat-' + metric + '_bold.tsv'), sep='\t', index=False, na_rep='NA')
    pd.DataFrame({'coverage': [1., .1]}, index=['ROI_A', 'ROI_B']).to_csv(outfunc / (BOLD + '_space-MNI_atlas-toy_stat-coverage_bold.tsv'), sep='\t')
    (deriv / (SUB + '.html')).write_text('<!doctype html><h1>' + WARNING + '</h1><p>Simulated report link target for exporter tests.</p>')
    input_files = [p for base in (inp, pair) for p in base.rglob('*') if p.is_file()]
    write_json(root / 'input_manifest.json', {'schema': 1, 'warning': WARNING, 'sha256': {str(p.relative_to(root)): sha(p) for p in sorted(input_files)}})
    write_json(root / 'environment.json', fingerprint())
    print(json.dumps({'root': str(root), 'warning': WARNING}))


def fingerprint():
    packages = {name: version(name) for name in ('numpy', 'pandas', 'nibabel', 'scipy', 'PyYAML')}
    try: commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    except subprocess.CalledProcessError: commit = None
    code = {str(p.relative_to(ROOT)): sha(p) for p in sorted(ROOT.rglob('*.py')) if '.venv' not in p.parts and '01_upstream' not in p.parts and '__pycache__' not in p.parts}
    return dict(python=sys.version, platform=platform.platform(), machine=platform.machine(), packages=packages, git_commit=commit, code_sha256=code, upstream=json.loads((ROOT / '03_config/upstream.lock.json').read_text()), scope='Environment/code evidence, not a claim of numerical equivalence')


def commands(root):
    i = root / 'inputs'; o = root / 'outputs'
    custom = ROOT / '02_custom'
    def cmd(path, *args): return [sys.executable, str(path), *map(str, args)]
    return {
        '3a': cmd(custom / 's3a_source_qc/run.py', '--mriqc-table', i/'MRIQC.csv', '--adni3-qc', i/'MAYO.csv', '--nfq', 'toy='+str(i/'NFQ.csv'), '--output-dir', o/'3a'),
        '5c': cmd(custom / 's5c_validate_handoff/run.py', '--input', i/'final_heuristics.tsv', '--source-qc', o/'3a', '--output-dir', o/'5c'),
        '5d': cmd(custom / 's5d_bids_identity/binding.py', '--config', i/'binding.json'),
        '8': cmd(ROOT / '01_upstream/ADNI_fMRI_protocol/s8_final_qc/summarize_motion_from_confounds.py', '--derivatives-dir', i/'derivative_fixture', '--output-dir', o/'8'),
        '8a': cmd(custom / 's8a_motion_duration_qc/run.py', '--bids-root', i/'bids', '--derivatives-root', i/'derivative_fixture', '--output-dir', o/'8a'),
        '9a': cmd(custom / 's9a_validate_clinical/run.py', '--included', i/'included.tsv', '--scan-links', i/'scan_links.csv', '--dxsum', i/'DXSUM.csv', '--ptdemog', i/'PTDEMOG.csv', '--output-dir', o/'9a'),
        '9b': cmd(custom / 's9b_validate_inclusion/run.py', '--source-qc', o/'3a', '--clinical', o/'9a', '--confirmed-st-absence', i/'confirmed_st_absence.csv', '--output-dir', o/'9b'),
        '11': cmd(custom / 's11_atlas_bold/run.py', 'extract', '--bold', i/'atlas'/(BOLD+'_space-'+SPACE+'_desc-denoised_bold.nii.gz'), '--mask', i/'atlas/mask.nii.gz', '--atlas', 'toy', '--catalog', i/'atlas/catalog.json', '--space', SPACE, '--input-kind', 'denoised', '--bold-json', i/'atlas/bold.json', '--output-dir', o/'11'),
        '12': cmd(custom / 's12_metrics_summary/run.py', '--archive-root', root/'fixture_archive', '--status', o/'12/status.json'),
    }


def check_inputs(root):
    manifest = json.loads((root / 'input_manifest.json').read_text())
    for rel, expected in manifest['sha256'].items():
        if sha(root / rel) != expected: raise ValueError('Changed toy input: ' + rel)


def run(root, step):
    check_inputs(root)
    if step == 'all':
        for name in STEPS: run(root, name)
        return
    receipt = root / 'outputs' / ('done-' + step + '.json')
    if receipt.exists(): raise FileExistsError('Step already run; use a new toy root to repeat: ' + step)
    if step == '10':
        qc = load_module('02_custom/s10_xcpd_integrated_qc/qc_report.py')
        pair = root / PAIR
        row = json.loads((pair / 's10/toy-fixture/pre_qc.json').read_text())['rows'][0]
        row.update(xcpd_status='synthetic_fixture', xcpd_qc_status='review_required', xcpd_warnings=[WARNING])
        cfg = json.loads((ROOT / '03_config/xcpd_linc.example.json').read_text())
        qc.write(pair, [row], cfg, 'toy-fixture')
        command = ['Python API qc_report.write', WARNING]
    else:
        command = commands(root)[step]
        print(shlex.join(command), flush=True)
        subprocess.run(command, check=True, cwd=ROOT)
    # Native exporter exit code does not encode pair-level failure; verify outputs explicitly.
    if step == '12' and not (root / PAIR / 'results/metrics.csv').is_file():
        raise ValueError('S12 did not export a metrics row; inspect outputs/12/status.json')
    write_json(receipt, {'step': step, 'command': command, 'synthetic_only': True})


def verify(root):
    check_inputs(root)
    for step in STEPS:
        if not (root / 'outputs' / ('done-'+step+'.json')).is_file(): raise ValueError('Missing step: '+step)
    o = root / 'outputs'
    def first(path):
        return pd.read_csv(path, sep='\t', keep_default_na=False).iloc[0].to_dict()
    a = first(o/'8a/paper_motion_summary.tsv')
    motion = first(o/'8/motion_summary.tsv')
    if not np.isclose(float(motion['mean_fd_p']), 13.4/120, atol=1e-14, rtol=0): raise ValueError('S8 mean FD differs from the analytical reference')
    if int(motion['n_fd_p_over_thresh']) != 2: raise ValueError('S8 high-motion frame count differs')
    source = first(o/'3a/image_qc.tsv'); clinical = first(o/'9a/clinical_validation.tsv'); inc = first(o/'9b/inclusion_audit.tsv')
    metrics = pd.read_csv(root / PAIR / 'results/metrics.csv').iloc[0]
    ts = pd.read_csv(o/'11/timeseries.tsv', sep='\t').to_numpy()
    expected_ts = np.column_stack([np.arange(1,121), np.arange(1,121)*10])
    if not np.array_equal(ts, expected_ts): raise ValueError('ROI values/order differ from the analytical reference')
    actual = dict(source_qc_status=source['SOURCE_QC_STATUS'], handoff_sessions=json.loads((o/'5c/handoff.json').read_text())['sessions'],
        binding_ready=json.loads(next((o/'5d').glob('*summary.json')).read_text())['preprocessing_ready'],
        clinical_stage=clinical['CLINICAL_STAGE'], diagnosis=clinical['DIAGNOSIS_NEW'], clinical_status=clinical['CLINICAL_STATUS'],
        inclusion=inc['INCLUSION_STATUS'], analysis_ready=str(inc['ANALYSIS_READY']),
        motion_censored_frames=int(a['motion_censored_frames']), retained_fd_seconds=float(a['retained_after_FD_only_seconds']), retained_fd_nonsteady_seconds=float(a['retained_after_FD_and_nonsteady_seconds']),
        roi_shape=list(ts.shape), roi_first=ts[0].tolist(), roi_last=ts[-1].tolist(),
        hippocampus_left_mm3=float(metrics['fs__aseg__Left-Hippocampus__Volume_mm3']), hippocampus_right_mm3=float(metrics['fs__aseg__Right-Hippocampus__Volume_mm3']),
        lh_superiorfrontal_thickness_mm=float(metrics['fs__lh_aparc__superiorfrontal__ThickAvg']), reho_A=float(metrics['xcpd__MNI__toy__reho__ROI_A']), reho_B_missing=bool(pd.isna(metrics['xcpd__MNI__toy__reho__ROI_B'])), final_inclusion=metrics['final_inclusion_status'])
    expected = json.loads((KIT / 'expected.json').read_text())
    if actual != expected: raise ValueError('Reference mismatch:\n' + json.dumps(dict(actual=actual, expected=expected), indent=2))
    write_json(root / 'verification.json', dict(status='PASS', scope='Synthetic integration/analytical checks only', measurements=actual))
    print(json.dumps({'status': 'PASS', 'reference': str(KIT/'expected.json'), 'results': str(root/PAIR/'results/index.html')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'run', 'verify', 'plan'])
    parser.add_argument('--root', type=external, required=True)
    parser.add_argument('--step', choices=(*STEPS, 'all'), default='all')
    args = parser.parse_args()
    if args.action == 'init': init(args.root)
    elif args.action == 'run': run(args.root, args.step)
    elif args.action == 'verify': verify(args.root)
    else:
        for name, command in commands(args.root).items(): print(name + ': ' + shlex.join(command))


if __name__ == '__main__': main()
