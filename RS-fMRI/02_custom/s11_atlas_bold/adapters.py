#!/usr/bin/env python3
"""Explicit XCP-D acquisition frames and UID-backed raw BIDS to 9.B links."""
import argparse
import json
from pathlib import Path
import re
import sys

import nibabel as nb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from atlas_contracts import tr_seconds
from _shared import finish, new_output, read, sha, snapshot, write, verify_bundle

ENTITIES = ('sub', 'ses', 'task', 'acq', 'run', 'echo', 'dir', 'rec')


def identity(path):
    return dict(re.findall(r'(?:^|_)(sub|ses|task|acq|run|echo|dir|rec)-([^_\.]+)', Path(path).name))


def subject(value):
    value = value.removeprefix('sub-').removeprefix('ADNI')
    if not re.fullmatch(r'\d{3}_?S_?\d{4,}', value):
        raise ValueError('Invalid ADNI subject identity')
    return value.replace('_', '')


def same_run(raw, bold):
    a, b = identity(raw), identity(bold)
    if not all(a.get(k) and b.get(k) for k in ('sub', 'ses', 'task')):
        raise ValueError('Explicit BIDS subject/session/task are required')
    if any((subject(a[k]) != subject(b[k]) if k == 'sub' else a.get(k, '') != b.get(k, '')) for k in ENTITIES):
        raise ValueError('Raw and derivative BIDS run entities differ')
    return b


def sidecar(image, path):
    if Path(image).name.removesuffix('.nii.gz').removesuffix('.nii') != Path(path).stem:
        raise ValueError('Sidecar must match its image filename')
    return json.loads(Path(path).read_text())


def source_ref(metadata, target):
    relative = '/'.join(Path(target).parts[-4:])
    sources = metadata.get('Sources', [])
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        raise ValueError('Sources must be a list of BIDS references')
    references = [s for s in sources if s.endswith('_bold.nii.gz') or s.endswith('_bold.nii') or s.endswith('_outliers.tsv')]
    relevant = [s for s in references if s.endswith('_outliers.tsv')] if relative.endswith('_outliers.tsv') else [s for s in references if not s.endswith('_outliers.tsv')]
    if sum(s.startswith('bids:') and s.rsplit(':', 1)[-1] == relative for s in sources) != 1 or len(relevant) != 1:
        raise ValueError('Missing or ambiguous exact BIDS Sources reference')


def timing(raw_bold, raw_json, bold, bold_json, outliers, dummy_volumes, output_dir):
    if type(dummy_volumes) is not int or dummy_volumes < 0:
        raise ValueError('Dummy count must be an explicit nonnegative integer')
    entities = same_run(raw_bold, bold)
    paths = [Path(__file__).with_name('atlas_contracts.py'), raw_bold, raw_json, bold, bold_json, outliers]
    output = new_output(output_dir, paths); hashes = snapshot(paths)
    raw, derivative = nb.load(raw_bold), nb.load(bold)
    rm, dm = sidecar(raw_bold, raw_json), sidecar(bold, bold_json)
    same_run(raw_bold, outliers)
    source_ref(dm, outliers)
    if len(raw.shape) != 4 or len(derivative.shape) != 4:
        raise ValueError('Frame adapter requires 4-D images')
    tr = tr_seconds(raw, rm)
    if not np.isclose(tr, tr_seconds(derivative, dm), rtol=1e-4, atol=1e-5):
        raise ValueError('Raw and derivative TR differ')
    rows = read(outliers, ['denoising'])
    if len(rows) != raw.shape[3] - dummy_volumes or not rows:
        raise ValueError('Raw frames minus dummy count must equal outlier rows')
    if any(r['denoising'] not in {'0', '1'} for r in rows):
        raise ValueError('Denoising outlier flags must be 0 or 1')
    keep = [i for i, r in enumerate(rows) if r['denoising'] == '0']
    if len(keep) != derivative.shape[3]:
        raise ValueError('Compressed derivative length differs from retained outlier rows')
    records = [{'input_frame_index_zero_based': i, 'post_dummy_frame_index_zero_based': k,
                'raw_frame_index_zero_based': k + dummy_volumes,
                'raw_nominal_time_seconds': (k + dummy_volumes) * tr} for i, k in enumerate(keep)]
    output.mkdir(parents=True)
    write(output / 'acquisition_frames.tsv', records,
          ['input_frame_index_zero_based', 'post_dummy_frame_index_zero_based', 'raw_frame_index_zero_based', 'raw_nominal_time_seconds'])
    return finish(output, 'acquisition_frame_mapping_v1', hashes, {
        'raw_frames': raw.shape[3], 'dummy_volumes': dummy_volumes, 'outlier_rows': len(rows),
        'censored_volumes': len(rows) - len(keep), 'input_frames': derivative.shape[3],
        'tr_seconds': tr, 'bold_sha256': hashes[str(Path(bold).resolve())], 'bids_entities': entities,
        'implementation_sha256': sha(__file__),
        'scope': 'XCP-D compressed denoising output; nominal raw frame times only, not slice timing or a new censor decision.'})


def link_run(inclusion, image_id, raw_bold, raw_json, bold, bold_json, preprocessed_json, output_dir):
    directory = Path(inclusion).resolve(); inc = verify_bundle(directory, 'final_inclusion_validation_v1')
    if 'inclusion_audit.tsv' not in inc['outputs_sha256']:
        raise ValueError('Inclusion audit must be hash-covered')
    iid = str(image_id).removeprefix('I')
    if not iid.isdigit(): raise ValueError('Explicit image ID is required')
    iid = str(int(iid))
    rows = [r for r in read(directory / 'inclusion_audit.tsv') if r['IMAGE_ID'] == iid]
    if len(rows) != 1 or rows[0]['INCLUSION_STATUS'] not in {'eligible', 'pending'} or rows[0].get('SOURCE_MODALITY') != 'EPI':
        raise ValueError('Image is not a uniquely retained EPI image')
    row = rows[0]; entities = same_run(raw_bold, bold)
    paths = [Path(__file__).with_name('atlas_contracts.py'), directory / 'artifact.json', directory / 'inclusion_audit.tsv', raw_bold, raw_json, bold, bold_json, preprocessed_json]
    output = new_output(output_dir, paths); hashes = snapshot(paths)
    raw_meta, dm = sidecar(raw_bold, raw_json), sidecar(bold, bold_json)
    uid = raw_meta.get('SeriesInstanceUID')
    date = raw_meta.get('AcquisitionDateTime', '')[:10]
    from datetime import date as calendar_date
    calendar_date.fromisoformat(date)
    if not uid or uid != row.get('SERIES_UID') or date != row.get('MRI_STUDY_DATE') or subject(row['PTID']) != subject(entities['sub']) or subject(row['sub']) != subject(entities['sub']):
        raise ValueError('Raw UID/date/participant contradicts 9.B image identity')
    for key in ENTITIES:
        expected = row.get(key, '').removeprefix(key + '-')
        if key == 'sub': continue
        if key == 'ses' and row.get('INPUT_SCOPE') == 'metadata_audit_not_step8_or_BIDS' and expected == 'auditI' + iid:
            continue
        if expected and expected != entities.get(key, ''):
            raise ValueError('9.B run identity conflicts with actual BIDS: ' + key)
    preprocessed = Path(preprocessed_json).with_name(Path(preprocessed_json).stem + '.nii.gz')
    same_run(raw_bold, preprocessed)
    source_ref(dm, preprocessed)
    source_ref(json.loads(Path(preprocessed_json).read_text()), raw_bold)
    tr = tr_seconds(nb.load(raw_bold), raw_meta)
    if not np.isclose(tr, tr_seconds(nb.load(bold), dm), rtol=1e-4, atol=1e-5):
        raise ValueError('Linked raw/derivative TR mismatch')
    linked = dict(row, AUDIT_SESSION=row['ses'])
    for key in ENTITIES: linked[key] = entities.get(key, '')
    linked.update(RUN_LINK_STATUS='uid_date_raw_bids_sources_verified', DERIVATIVE_SHA256=hashes[str(Path(bold).resolve())])
    output.mkdir(parents=True); write(output / 'linked_run.tsv', [linked])
    return finish(output, 'bids_run_inclusion_link_v1', hashes, {
        'image_id': iid, 'inclusion_status': row['INCLUSION_STATUS'], 'bids_entities': entities,
        'bold_sha256': hashes[str(Path(bold).resolve())], 'inclusion_artifact_sha256': hashes[str(directory / 'artifact.json')],
        'inclusion_audit_sha256': hashes[str(directory / 'inclusion_audit.tsv')], 'implementation_sha256': sha(__file__),
        'scope': 'UID/date/subject and declared Sources chain verified; no physical registration or processing-payload proof inferred.'})


def validated_frame_map(directory, bold_hash, n, tr, bold=None):
    p = Path(directory); record = verify_bundle(p, 'acquisition_frame_mapping_v1')
    if 'acquisition_frames.tsv' not in record['outputs_sha256'] or record['summary'].get('bold_sha256') != bold_hash:
        raise ValueError('Frame map is not bound to this BOLD input')
    if not np.isclose(record['summary']['tr_seconds'], tr, rtol=1e-4, atol=1e-5):
        raise ValueError('Frame-map TR mismatch')
    if bold is not None and record['summary'].get('bids_entities') != identity(bold):
        raise ValueError('Frame map belongs to another BIDS run')
    rows = read(p / 'acquisition_frames.tsv', ['input_frame_index_zero_based', 'raw_frame_index_zero_based', 'raw_nominal_time_seconds'])
    raw = [int(r['raw_frame_index_zero_based']) for r in rows]
    if len(rows) != n or [int(r['input_frame_index_zero_based']) for r in rows] != list(range(n)) or any(i < record['summary']['dummy_volumes'] or i >= record['summary']['raw_frames'] for i in raw) or any(b <= a for a, b in zip(raw, raw[1:])):
        raise ValueError('Invalid acquisition frame ordering/count')
    if not all(np.isclose(float(r['raw_nominal_time_seconds']), k * tr, rtol=1e-4, atol=1e-5) for r, k in zip(rows, raw)):
        raise ValueError('Raw frame times disagree with TR')
    return rows


def validated_run_link(directory, inclusion, image_id, bold, bold_hash):
    p = Path(directory); record = verify_bundle(p, 'bids_run_inclusion_link_v1')
    summary = record['summary']; inc = Path(inclusion).resolve()
    if summary.get('inclusion_artifact_sha256') != sha(inc / 'artifact.json') or summary.get('inclusion_audit_sha256') != sha(inc / 'inclusion_audit.tsv'):
        raise ValueError('Run link belongs to different inclusion evidence')
    verify_bundle(inc, 'final_inclusion_validation_v1')
    if summary.get('image_id') != str(image_id).removeprefix('I') or summary.get('bold_sha256') != bold_hash or summary.get('bids_entities') != identity(bold):
        raise ValueError('Run link belongs to another image or BOLD run')
    if 'linked_run.tsv' not in record['outputs_sha256']: raise ValueError('Linked row is not hash-covered')
    rows = read(p / 'linked_run.tsv')
    if len(rows) != 1 or rows[0]['IMAGE_ID'] != summary['image_id'] or rows[0]['INCLUSION_STATUS'] not in {'eligible', 'pending'} or rows[0]['INCLUSION_STATUS'] != summary['inclusion_status']:
        raise ValueError('Invalid retained linked row')
    original = [r for r in read(inc / 'inclusion_audit.tsv') if r['IMAGE_ID'] == summary['image_id']]
    if len(original) != 1 or original[0]['SOURCE_MODALITY'] != 'EPI' or original[0]['INCLUSION_STATUS'] != rows[0]['INCLUSION_STATUS']:
        raise ValueError('Linked status differs from original inclusion evidence')
    return rows[0]


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    for command in ('frames', 'link-run'):
        q = sub.add_parser(command)
        for flag in ('raw-bold', 'raw-json', 'bold', 'bold-json', 'output-dir'): q.add_argument('--' + flag, required=True)
        if command == 'frames':
            q.add_argument('--outliers', required=True); q.add_argument('--dummy-volumes', required=True, type=int)
        else:
            for flag in ('inclusion', 'image-id', 'preprocessed-json'): q.add_argument('--' + flag, required=True)
    a = vars(p.parse_args()); command = a.pop('command'); a = {k.replace('-', '_'): v for k, v in a.items()}
    try: print(json.dumps((timing if command == 'frames' else link_run)(**a)['summary'], indent=2))
    except (ValueError, KeyError, FileNotFoundError) as e: p.exit(1, str(e) + '\n')

if __name__ == '__main__': main()
