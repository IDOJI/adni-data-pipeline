#!/usr/bin/env python3
"""Inspect the pinned protocol and render external configuration; never submit jobs."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / '01_upstream/ADNI_fMRI_protocol'
LOCK = ROOT / '03_config/upstream.lock.json'


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True).strip()


def doctor():
    lock = json.loads(LOCK.read_text())
    if not (UPSTREAM / '.git').is_file():
        raise ValueError('Initialize the genuine submodule: git submodule update --init --recursive')
    if git('rev-parse', 'HEAD', cwd=UPSTREAM) != lock['commit']:
        raise ValueError('Submodule HEAD differs from 03_config/upstream.lock.json')
    index = git('ls-files', '--stage', '--', lock['path']).split()
    if len(index) < 2 or index[:2] != ['160000', lock['commit']]:
        raise ValueError('Parent gitlink differs from the locked upstream commit')
    if git('status', '--porcelain', '--untracked-files=all', cwd=UPSTREAM):
        raise ValueError('Upstream contains local edits or untracked files')
    url = git('config', '-f', str(ROOT.parent / '.gitmodules'), 'submodule.upstream/ADNI_fMRI_protocol.url')
    if url != lock['repository']:
        raise ValueError('Unexpected upstream URL in .gitmodules')
    module_path = git('config', '-f', str(ROOT.parent / '.gitmodules'), 'submodule.upstream/ADNI_fMRI_protocol.path')
    if module_path != UPSTREAM.relative_to(ROOT.parent).as_posix():
        raise ValueError('Submodule path in .gitmodules differs from the numbered layout')
    for step in ['s1_setup_account', 's2_download', 's3_organize', 's4_clinica',
                 's4b_slice_timing', 's5_post_clinica_qc', 's6_mriqc', 's7_fmriprep',
                 's8_final_qc', 's9_clinical_imaging_merge']:
        if not (UPSTREAM / step / 'README.md').is_file():
            raise ValueError('Missing upstream step: ' + step)
    return {'upstream_commit': lock['commit'], 'upstream_clean': True,
            'scientific_validation': 'not_established_by_source_checks'}


def is_inside(path, parent):
    return path == parent or parent in path.parents


def external(path):
    path = Path(path).expanduser().resolve()
    if is_inside(path, ROOT.parent) or is_inside(ROOT.parent, path):
        raise ValueError('Data, runtime and output paths must be outside the repository and its ancestors')
    return path


def merge(target, values):
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def expand(value, variables):
    if isinstance(value, dict):
        return {k: expand(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [expand(v, variables) for v in value]
    if isinstance(value, str):
        def replace(match):
            name, _, fallback = match.group(1).partition(':-')
            if name in variables:
                return variables[name]
            if fallback:
                return fallback
            raise ValueError('Unresolved upstream variable: ' + name)
        return re.sub(r'\$\{([^}]+)\}', replace, value)
    return value


def render_config(config_path, output_dir, handoff=None):
    doctor()
    raw = yaml.safe_load(Path(config_path).read_text())
    if not isinstance(raw, dict):
        raise ValueError('Lab config must be a YAML mapping')
    values = {}
    for key in ('data_root', 'scratch_root', 'containers_root', 'freesurfer_license'):
        if key not in raw or not isinstance(raw[key], str) or not Path(raw[key]).expanduser().is_absolute():
            raise ValueError('Set an absolute path for ' + key)
        if 'ABSOLUTE/PATH' in raw[key]:
            raise ValueError('Replace example placeholders before rendering configuration')
        values[key] = external(raw[key])
    out = external(output_dir)
    for name in ('data_root', 'scratch_root'):
        if out == values[name] or is_inside(values[name], out):
            raise ValueError('Output must not contain the entire data or scratch tree')
    if out.exists():
        raise ValueError('Use a new output directory')
    template = yaml.safe_load((UPSTREAM / 'config/config_adni.yaml').read_text())
    data = str(values['data_root'])
    merge(template, {
        'slice_timing': {'report_tsv': data + '/qc/step4b/slice_timing_report.tsv'},
        'mriqc': {'participant_label_file': data + '/config/mriqc_participant_labels.txt',
                  'bids_filter_file': data + '/config/mriqc_bids_filter.json'},
        'qc': {'post_clinica_qc_table': data + '/qc/step5/post_clinica_qc.tsv',
               'mriqc_thresholds_file': data + '/qc/step6/mriqc_thresholds.tsv',
               'mriqc_qc_table': data + '/qc/step6/mriqc_qc_decisions.tsv',
               'heuristics_missing_t1w_table': data + '/qc/step5/missing_t1w.tsv',
               'heuristics_missing_data_table': data + '/qc/step5/missing_data.tsv',
               'heuristics_final_table': data + '/qc/step5/final_heuristics.tsv',
               'final_inclusion_table': data + '/qc/step8/included_sessions.tsv',
               'final_exclusion_table': data + '/qc/step8/excluded_sessions.tsv'},
        'sample_size': {'manifest': data + '/qc/step8/sample_size_stages.tsv',
                        'mastersheet_csv': data + '/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv',
                        'mriqc_iqms_table': data + '/results/mriqc/all_IQMs_with_QC_flags_clean.csv',
                        'fmriprep_sessions_table': data + '/qc/step8/motion_summary.tsv',
                        'final_inclusion_table': data + '/qc/step8/included_sessions.tsv'}})
    overrides = raw.get('upstream_overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError('upstream_overrides must be a mapping')
    merge(template, overrides)
    variables = {'ADNI_BASE': str(values['data_root']), 'SCRATCH': str(values['scratch_root']),
                 'CONTAINERS_DIR': str(values['containers_root']), 'REPO_ROOT': str(UPSTREAM),
                 'FREESURFER_LICENSE': str(values['freesurfer_license'])}
    template = expand(template, variables)
    for group, keys in {
        'paths': ['raw_zip_dir', 'raw_metadata_dir', 'raw_dicom_dir', 'raw_subject_list',
                  'slurm_jobs_dir', 'clinica_bids_dir', 'mriqc_output_dir', 'mriqc_work_dir',
                  'mriqc_results_root', 'fmriprep_output_dir', 'fmriprep_work_dir',
                  'fmriprep_results_root', 'fmriprep_heuristics_csv', 'logs_dir', 'qc_dir'],
        'qc': list(template['qc']),
        'sample_size': ['manifest', 'mastersheet_csv', 'mriqc_iqms_table',
                        'fmriprep_sessions_table', 'final_inclusion_table'],
        'slice_timing': ['report_tsv'],
        'mriqc': ['bids_dir', 'output_dir', 'work_dir'],
        'fmriprep': ['bids_dir', 'output_dir', 'work_dir'],
    }.items():
        for key in keys:
            value = template[group][key]
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError('Use an absolute external path for ' + group + '.' + key)
            external(value)
    for name in ('mriqc', 'fmriprep'):
        image = raw.get(name + '_image')
        if not isinstance(image, str) or not image:
            raise ValueError('Set ' + name + '_image')
        path = Path(image)
        template['containers'][name + '_image'] = str(external(path if path.is_absolute() else values['containers_root'] / path))
    # s6 reads a comma CSV; s7 reads the grouped Subject_ID,sessions CSV.
    if handoff:
        directory = external(handoff)
        provenance = json.loads((directory / 'handoff.json').read_text())
        if provenance.get('status') != 'format_validated_no_additional_selection':
            raise ValueError('Invalid Step-5.C handoff')
        for name in ('mriqc_subjects.csv', 'post_clinica.csv', 'valid_sessions.tsv'):
            from hashlib import sha256
            file = directory / name
            if not file.is_file() or sha256(file.read_bytes()).hexdigest() != provenance['outputs_sha256'][name]:
                raise ValueError('Handoff output is missing or changed: ' + name)
        template['qc']['heuristics_final_table'] = str(directory / 'mriqc_subjects.csv')
        template['paths']['fmriprep_heuristics_csv'] = str(directory / 'post_clinica.csv')
    out.mkdir(parents=True)
    (out / 'upstream.yaml').write_text(yaml.safe_dump(template, sort_keys=False))
    record = {'upstream_commit': json.loads(LOCK.read_text())['commit'],
              'handoff': str(Path(handoff).resolve()) if handoff else None,
              'config_source': str(Path(config_path).resolve()), 'jobs_submitted': False}
    (out / 'configuration.json').write_text(json.dumps(record, indent=2) + '\n')
    return {'config': str(out / 'upstream.yaml'), **record}


def commands(config, session_handoff=None):
    """Explicit plans only. Upstream script-specific working directories are retained."""
    cfg = external(config)
    if not cfg.is_file():
        raise ValueError('Render an external config first')
    root = shlex.quote(str(UPSTREAM))
    c = shlex.quote(str(cfg))
    env = f'ADNI_CONFIG={c} PYTHONPATH={root}'
    base = f'cd {root} && {env}'
    configured = yaml.safe_load(cfg.read_text())
    work5 = external(Path(configured['base']['adni_base']) / 'qc/step5a')
    w5 = shlex.quote(str(work5))
    plans = {
        '3': f'{base} bash s3_organize/create_dicom_dir_csv.sh --config {c}',
        '4b': f'{base} python s4b_slice_timing/insert_philips_slicetiming.py --config {c} --dry-run',
        '5a': f'mkdir -p {w5} && cd {w5} && {env} python {root}/s5_post_clinica_qc/create_mastersheet/main.py --config {c}',
        '6': f'{base} bash s6_mriqc/adni_mriqc.slurm --config {c} --dry-run',
        '7': f'{base} bash s7_fmriprep/run_fmriprep_bids_filter_array_all.sh --config {c} --dry-run',
    }
    if session_handoff:
        csv = external(session_handoff) / 'mriqc_sessions.csv'
        if not csv.is_file():
            raise ValueError('Missing mriqc_sessions.csv')
        plans['7'] += ' --sessions-csv ' + shlex.quote(str(csv))
    return {'mode': 'print_only', 'commands': plans,
            'caveats': ['Step 6 is subject-scoped and may process other BIDS sessions; subset group IQMs before outlier fitting.',
                        'Upstream --dry-run can write job files; it is not a read-only command.',
                        'HPC settings are not fully honored by all upstream scripts. Inspect generated Slurm jobs.',
                        'Step 4 templates contain original cluster paths and mail directives; prepare a separate lab template before submitting.',
                        'Step 4b defaults to dry-run; inspect identity and slice axis before applying.',
                        'Step 5b, MRIQC group/outliers, final QC and clinical merge require explicit input arguments; see README.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('doctor')
    r = sub.add_parser('prepare-config')
    r.add_argument('--lab-config', required=True)
    r.add_argument('--output-dir', required=True)
    r.add_argument('--handoff')
    c = sub.add_parser('plan')
    c.add_argument('--config', required=True)
    c.add_argument('--handoff')
    a = p.parse_args()
    try:
        if a.action == 'doctor':
            result = doctor()
        elif a.action == 'prepare-config':
            result = render_config(a.lab_config, a.output_dir, a.handoff)
        else:
            doctor()
            result = commands(a.config, a.handoff)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
