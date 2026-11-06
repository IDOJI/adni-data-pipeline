"""Policy-bound isolated-pair adapter for Step 7.B; existing live runners stay intact."""
from __future__ import annotations
import argparse
import importlib.util
import json
import shutil
from pathlib import Path

import yaml
import binding


def backend():
    path = Path(__file__).resolve().parents[1] / 's7b_sessionwise_preprocessing/run.py'
    spec = importlib.util.spec_from_file_location('binding_step7b', path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def check_runtime(cfg, plan):
    case = cfg['runs']
    if len(case) != 1:
        raise ValueError('One isolated EPI/T1 pair per runtime is required')
    case = case[0]
    if (case.get('subject'), case.get('session'), case.get('ptid'), str(case.get('bold_image_id')), str(case.get('t1_image_id'))) != (
            plan['subject'], plan['session'], plan['ptid'], plan['epi_image_id'], plan['t1_image_id']):
        raise ValueError('Configuration does not match the verified EPI/T1 pairing')
    manifest = binding.read_json(Path(cfg['source_bids']).parent / 'isolated-inputs.json')
    for item in manifest['files']:
        if binding.sha(item['path']) != item['sha256']:
            raise ValueError('Isolated source files changed after pairing')
    mod = backend()
    expected = {k: plan[role][field] for k, role, field in [
        ('bold', 'epi', 'NIFTI_SHA256'), ('bold_json', 'epi', 'JSON_SHA256'),
        ('t1w', 't1', 'NIFTI_SHA256'), ('t1w_json', 't1', 'JSON_SHA256')]}
    for k, p in mod.paths_for(cfg, case).items():
        if binding.sha(p) != expected[k]:
            raise ValueError('Runtime BIDS inputs differ from the verified pair')
    # A session filter alone would allow extra T1 acquisitions into the template.
    for root in (Path(cfg['source_bids']), Path(cfg['runtime']) / 'bids'):
        actual = {p.resolve() for p in root.glob('sub-*/ses-*/*/*')
                  if p.name.endswith(('.nii', '.nii.gz', '.json'))}
        allowed = {p.resolve() for p in (mod.paths_for(cfg, case).values() if root == Path(cfg['runtime']) / 'bids'
                   else [Path(item['path']) for item in manifest['files']])}
        if actual != allowed:
            raise ValueError('Extra or missing BIDS images would bypass the exact T1 pairing')
    return mod, case


def prepare(receipt, epi_key, base, template):
    plan = binding.verify_plan(receipt, epi_key)  # Before mkdir, copy or Docker.
    base = Path(base).resolve()
    # Reusing an existing controller/runtime is deliberately not supported.
    if base.exists():
        raise FileExistsError('Use a new isolated runtime; never repurpose a live runtime')
    repo = Path(__file__).resolve().parents[2]
    if base.is_relative_to(repo):
        raise ValueError('Private runtime must be outside the source repository')
    for role in ('epi', 't1'):
        root = Path(plan[role]['BIDS_ROOT']).resolve()
        if base.is_relative_to(root) or root.is_relative_to(base):
            raise ValueError('Runtime must not overlap the original BIDS tree')
    cfg = yaml.safe_load(Path(template).read_text())
    mod = backend()
    sub, ses = plan['subject'], plan['session']
    source = base / 'isolated_source'
    stem = f'sub-{sub}_ses-{ses}'
    copies = []
    base.mkdir(parents=True)
    # Partial preparation stays outside original data and is never marked ready.
    for role, folder, suffix in [('epi', 'func', 'task-rest_bold'), ('t1', 'anat', 'T1w')]:
        for field, digest, ext in [('BIDS_NIFTI_PATH', 'NIFTI_SHA256', '.nii.gz'), ('BIDS_JSON_PATH', 'JSON_SHA256', '.json')]:
            original = Path(plan[role][field])
            if field == 'BIDS_NIFTI_PATH' and not str(original).endswith('.nii.gz'):
                ext = '.nii'
            # The pinned 7.B adapter currently requires compressed NIfTI inputs.
            if ext == '.nii':
                raise ValueError('Uncompressed NIfTI needs an explicit compatible adapter')
            target = source / f'sub-{sub}' / f'ses-{ses}' / folder / (stem + '_' + suffix + ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            if binding.sha(target) != plan[role][digest]:
                raise ValueError('Verified source changed while preparing isolated view')
            copies.append({'path': str(target), 'source': str(original), 'sha256': plan[role][digest]})
    (source / 'dataset_description.json').write_text(json.dumps({'Name': 'Verified isolated ADNI EPI-T1 pair', 'BIDSVersion': '1.10.0', 'DatasetType': 'raw'}))
    proof = binding.read_json(receipt)
    registry = proof['inputs']['images']
    row = next(r for r in binding.read_csv(registry['path']) if r['IMAGE_ID'] == plan['epi_image_id'])
    evidence = [{'subject': sub, 'session': ses, 'phase': plan['phase'],
                 'evidence_file': registry['path'], 'evidence_file_sha256': registry['sha256'],
                 'matched_row': row, 'phase_match_basis': 'Exact source Image ID, PTID, actual date, UID and independent NIfTI hash',
                 'bids_metadata_sha256': plan['epi']['JSON_SHA256']}]
    evidence_path = base / 'phase-evidence.json'
    evidence_path.write_text(json.dumps(evidence, indent=2))
    cfg.update(runtime=str(base / 'processing'), source_bids=str(source),
               source_manifest=str(base / 'source-manifest.json'), source_phase_evidence=str(evidence_path),
               binding_receipt=str(Path(receipt).resolve()), binding_receipt_sha256=binding.sha(receipt), epi_key=epi_key,
               runs=[{'subject': sub, 'session': ses, 'ptid': plan['ptid'], 'bold_image_id': plan['epi_image_id'],
                      't1_image_id': plan['t1_image_id'], 'phase': plan['phase']}])
    (base / 'isolated-inputs.json').write_text(json.dumps({'epi_key': epi_key, 'files': copies, 'analysis_ready': False}, indent=2))
    config_path = base / 'verified-config.yaml'
    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    pre_path = Path(mod.__file__).with_name('make_source_manifest.py')
    spec = importlib.util.spec_from_file_location('binding_preflight', pre_path)
    pre = importlib.util.module_from_spec(spec); spec.loader.exec_module(pre)
    manifest, _ = pre.inspect(cfg)
    Path(cfg['source_manifest']).write_text(json.dumps(manifest, indent=2))
    mod.prepare(cfg)
    check_runtime(cfg, plan)
    return config_path


def dispatch(config, action, stage=None):
    cfg = yaml.safe_load(Path(config).read_text())
    if binding.sha(cfg['binding_receipt']) != cfg['binding_receipt_sha256']:
        raise ValueError('Binding receipt changed')
    plan = binding.verify_plan(cfg['binding_receipt'], cfg['epi_key'])
    mod, case = check_runtime(cfg, plan)
    if action == 'check':
        return {'verified_pair': plan['epi_key'], 'analysis_ready': False}
    if action == 'intake':
        mod.intake(cfg)
    elif action in ('run', 'dry-run'):
        if stage not in ('mriqc', 'fmriprep'):
            raise ValueError('Specify an MRIQC/fMRIPrep stage')
        if action == 'run':
            mod.run_stage(cfg, stage, case, 'strict')
        else:
            image = mod.image_record(cfg['images'][stage])
            return mod.command(cfg, stage, case, image['resolved'])[0]
    else:
        raise ValueError('Unsupported guarded action')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('verify-pair', 'prepare', 'check', 'intake', 'run', 'dry-run'))
    p.add_argument('--receipt', type=Path); p.add_argument('--epi-key')
    p.add_argument('--runtime', type=Path); p.add_argument('--template', type=Path)
    p.add_argument('--config', type=Path); p.add_argument('--stage', choices=('mriqc', 'fmriprep'))
    a = p.parse_args()
    if a.action == 'verify-pair': result = binding.verify_plan(a.receipt, a.epi_key)
    elif a.action == 'prepare': result = str(prepare(a.receipt, a.epi_key, a.runtime, a.template))
    else: result = dispatch(a.config, a.action, a.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
