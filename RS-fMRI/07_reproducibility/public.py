#!/usr/bin/env python3
"""Stage bundled public NIfTIs; print imaging commands unless --execute is set."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import urllib.request

import nibabel as nib
from toy import ROOT, external, fingerprint, load_module, sha, write_json

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'04_workflow'))
import seed_policy
IMAGES = {
    'mriqc': 'nipreps/mriqc@sha256:dabe930dd0d1180c565a42f2c6a34f2b23026d9642db5d110f05b427413b829f',
    'fmriprep': 'nipreps/fmriprep@sha256:bd222fba3a9f07d6ecaa680c412907945106b846a76cd4fbfd86e61667c435f8',
    'xcpd': 'pennlinc/xcp_d@sha256:a919b121d1da8e090bfb3594f49ffeb5ddf2ab491327b04a7b8a1f304b64e7ca',
}
SPACES = ['MNI152NLin6Asym:res-2', 'MNI152NLin2009cAsym', 'fsnative', 'fsaverage:den-10k', 'func']


def specification(): return json.loads((HERE / 'public_dataset.json').read_text())


def fetch(root, cache=None, source='bundled'):
    if root.exists(): raise FileExistsError('Use a new public-demo root; inputs are never overwritten')
    if source not in ('bundled', 'remote'): raise ValueError('Unknown public payload source')
    if source == 'remote' and cache is not None: raise ValueError('Use either --source remote or --cache-dir')
    spec = specification()
    payload_root = Path(cache) if cache is not None else HERE / spec['bundled_path']
    if source == 'bundled':
        # Verify availability and exact bytes before creating any output. Never download silently.
        for entry in spec['files']:
            bundled = payload_root / entry['path']
            if not bundled.is_file() or bundled.is_symlink():
                raise FileNotFoundError('Bundled public payload missing/not a regular file: ' + str(bundled))
            if bundled.stat().st_size != entry['bytes'] or sha(bundled) != entry['sha256']:
                raise ValueError('Public payload differs from pinned source: ' + entry['path'])
    root.mkdir(parents=True)
    for entry in spec['files']:
        dest = root / 'download' / entry['path']; dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + '.partial')
        try:
            if source == 'bundled': shutil.copyfile(payload_root / entry['path'], temporary)
            else:
                with urllib.request.urlopen(entry['url'], timeout=120) as response, temporary.open('wb') as out:
                    received = 0
                    while block := response.read(1024 * 1024):
                        received += len(block)
                        if received > entry['bytes']: raise ValueError('Download exceeds pinned size: ' + entry['path'])
                        out.write(block)
            if temporary.stat().st_size != entry['bytes'] or sha(temporary) != entry['sha256']:
                raise ValueError('Public payload differs from pinned source: ' + entry['path'])
            temporary.replace(dest)
        finally:
            temporary.unlink(missing_ok=True)
    bids = root / 'bids'; stem = 'sub-toy001_ses-M000'
    for kind, suffix, source_path in [('anat', 'T1w', 'sub-10159/anat/sub-10159_T1w.nii.gz'), ('func', 'task-rest_bold', 'sub-10159/func/sub-10159_task-rest_bold.nii.gz')]:
        target = bids / 'sub-toy001/ses-M000' / kind / (stem + '_' + suffix + '.nii.gz')
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(root/'download'/source_path, target)
        if sha(target) != sha(root/'download'/source_path): raise ValueError('Image changed while creating execution layout')
    group = json.loads((root/'download/task-rest_bold.json').read_text())
    group.update(json.loads((root/'download/sub-10159/func/sub-10159_task-rest_bold.json').read_text()))
    write_json(bids/'sub-toy001/ses-M000/func'/ (stem+'_task-rest_bold.json'), group)
    write_json(bids/'dataset_description.json', dict(Name='Public reproducibility demo: ds000030 1.0.0 sub-10159', BIDSVersion='1.10.0', DatasetType='raw', License='CC0', SourceDatasets=[{'DOI':spec['doi'], 'URL':spec['source']}]))
    (bids/'participants.tsv').write_text('participant_id\nsub-toy001\n')
    image = nib.load(next(bids.glob('sub-*/ses-*/func/*.nii.gz')))
    if len(group['SliceTiming']) != image.shape[2] or image.header.get_dim_info()[2] != 2 or abs(group['RepetitionTime']-image.header.get_zooms()[3]) > 1e-5:
        raise ValueError('Public BOLD header/metadata slice count, axis or TR mismatch')
    filters = dict(bold=dict(subject='toy001', session='M000', task='rest'), t1w=dict(subject='toy001', session='M000'))
    write_json(root/'config/fmriprep_filter.json', filters)
    write_json(root/'config/mriqc_filter.json', {'bold':filters['bold'], 'T1w':filters['t1w']})
    write_json(root/'input_manifest.json', {'dataset':spec, 'source_subject':'sub-10159', 'execution_subject':'sub-toy001', 'execution_session':'ses-M000',
        'payload_source':'explicit_cache' if cache is not None else 'bundled_git_files' if source == 'bundled' else 'upstream_download',
        'session_note':'Execution wrapper for sessionwise processing; this is not an ADNI VISCODE or acquisition date.',
        'sha256':{str(p.relative_to(root)):sha(p) for folder in (bids,root/'config') for p in sorted(folder.rglob('*')) if p.is_file()}})
    cfg = xcp_config()
    write_json(root/'comparison_identity.json', {'source_files':{e['path']:e['sha256'] for e in spec['files']}, 'adapted_inputs':json.loads((root/'input_manifest.json').read_text())['sha256'],
        'images':IMAGES, 'seed_policy':seed_policy.identity(), 'fmriprep':dict(output_spaces=SPACES, cifti_output='91k', task='rest', anatomical_reference='sessionwise', force=['syn-sdc'], ignore=['fieldmaps'], use_syn_sdc='error', random_seed=357, skull_strip_fixed_seed=True, nprocs=4, omp_nthreads=1, mem_mb=6000),
        'xcpd':{k:v for k,v in cfg.items() if k not in ('root','repo','license','templateflow','slurm','run_id')},
        'code_sha256':fingerprint()['code_sha256'], 'upstream':fingerprint()['upstream']})
    write_json(root/'environment.json', fingerprint())
    print(json.dumps({'status':'verified_public_input', 'root':str(root), 'image_shape':image.shape, 'input_bytes':sum(e['bytes'] for e in spec['files']), 'payload_source':source}))


def xcp_config():
    cfg = json.loads((ROOT/'03_config/xcpd_linc.seeded.example.json').read_text())
    cfg.update(_config_id='public-ds000030-fixed-seed-v1', image=IMAGES['xcpd'])
    cfg['resources'] = dict(cpus=2, omp_nthreads=1, mem_mb=12000, docker_memory='16g')
    return cfg


def check_inputs(root):
    comparison = json.loads((root/'comparison_identity.json').read_text())
    if comparison.get('seed_policy') != seed_policy.identity():
        raise ValueError('Public seed policy differs; keep historical outputs and fetch into a new root')
    expected = json.loads((root/'input_manifest.json').read_text())['sha256']
    observed = {str(p.relative_to(root)) for folder in (root/'bids',root/'config') for p in folder.rglob('*') if p.is_file()}
    if set(expected) != observed: raise ValueError('Public input file inventory changed')
    for rel, digest in expected.items():
        if sha(root/rel) != digest: raise ValueError('Changed public input: ' + rel)


def mount(source, target, readonly=False):
    if ',' in str(source): raise ValueError('Docker bind paths cannot contain commas')
    return ['--mount', f'type=bind,src={source},dst={target}' + (',readonly' if readonly else '')]


def public_row(root, require_derivatives=False):
    row = {key:'' for key in ('sub','ses','task','run','acq','dir','echo','rec')}
    row.update(sub='sub-toy001', ses='ses-M000', task='task-rest')
    if require_derivatives:
        paths = list((root/'derivatives/fmriprep/sub-toy001/ses-M000/func').glob('*_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz'))
        if len(paths) != 1: raise ValueError('Need exactly one completed fMRIPrep MNI6 res-2 BOLD')
        im = nib.load(paths[0]); row.update(source_bold_file=str(paths[0]), n_original_volumes=im.shape[3], tr=float(im.header.get_zooms()[3]))
    return row


def docker_command(root, stage, license_file=None):
    check_inputs(root)
    cpus, omp, memory, workflow_memory = (2,1,'16g',12000) if stage == 'xcpd' else (4,1,'8g',6000)
    args = ['docker','run','--rm','--pull','never','--name','adni-public-toy-'+stage, '--platform','linux/amd64','--cpus',str(cpus),'--memory',memory]
    for folder in ('templateflow', 'work/'+stage, 'derivatives/'+stage, 'logs'): (root/folder).mkdir(parents=True, exist_ok=True)
    if stage in ('fmriprep','xcpd'):
        if not license_file: raise ValueError('Set FS_LICENSE to a valid FreeSurfer license.txt')
        license_file = license_file.expanduser().resolve()
        if not license_file.is_file(): raise ValueError('FreeSurfer license file not found')
        args += mount(license_file, '/license.txt', True)
    args += mount(root/'templateflow', '/templateflow')
    args += ['--env','TEMPLATEFLOW_HOME=/templateflow','--env','OMP_NUM_THREADS='+str(omp)]
    if stage == 'xcpd':
        pipeline = load_module('02_custom/s10_xcpd_integrated_qc/pipeline.py')
        cfg = xcp_config(); row = public_row(root, True)
        job = root/'xcpd'; (job/'derivatives').mkdir(parents=True, exist_ok=True); (job/'work').mkdir(exist_ok=True)
        write_json(job/'bids_filter.json', pipeline.bids_filter(row, cfg))
        write_json(job/'profile.json', cfg)
        args += mount(root/'derivatives/fmriprep','/input',True) + mount(job,'/job')
        args += [IMAGES[stage], *pipeline.xcp_args(cfg,row)]
    else:
        args += mount(root/'bids','/data',True) + mount(root/('derivatives/'+stage),'/out') + mount(root/('work/'+stage),'/work') + mount(root/('config/'+stage+'_filter.json'),'/config/filter.json',True)
        if stage == 'fmriprep':
            fs = root/'derivatives/fmriprep/sourcedata/freesurfer'; fs.mkdir(parents=True, exist_ok=True)
            args += mount(fs,'/fsdir')
        args += [IMAGES[stage],'/data','/out','participant','--participant-label','toy001','--bids-filter-file','/config/filter.json','--nprocs',str(cpus),'--omp-nthreads',str(omp),'--notrack','-w','/work']
        if stage == 'mriqc': args += ['--modalities','T1w','bold','--session-id','M000','--no-sub','--mem-gb','6']
        else: args += ['--task-id','rest','--subject-anatomical-reference','sessionwise','--force','syn-sdc','--ignore','fieldmaps','--use-syn-sdc','error','--output-spaces',*SPACES,'--cifti-output','91k','--fs-license-file','/license.txt','--fs-subjects-dir','/fsdir','--mem-mb','6000','--random-seed','357','--stop-on-first-crash']
    return seed_policy.docker(args, stage, 357, root, [Path(__file__)])


def execute(root, stage, license_file, ants_verbose=False):
    command = docker_command(root, stage, license_file)
    if ants_verbose:
        if stage != 'fmriprep': raise ValueError('--ants-verbose is only valid for fmriprep')
        command = load_module('02_custom/s7c_ants_iteration_logging/run.py').augment(command, root/'logs/fmriprep')
    subprocess.run(['docker','info','--format','{{.OSType}}'], check=True, stdout=subprocess.DEVNULL)
    image = json.loads(subprocess.check_output(['docker','image','inspect',IMAGES[stage]], text=True))[0]
    if IMAGES[stage] not in image.get('RepoDigests',[]): raise ValueError('Pulled image does not match pinned digest')
    if image.get('Architecture') != 'amd64': raise ValueError('Image architecture differs from the pinned profile')
    log = root/'logs'/(stage+'.log')
    receipt = root/'logs'/(stage+'_execution.json')
    if receipt.exists(): raise FileExistsError('Execution already recorded; use a new public root for another run')
    evidence = dict(status='running', stage=stage, case=dict(subject='toy001', session='M000'), started_at=dt.datetime.now(dt.timezone.utc).isoformat(), command=command, image_id=image['Id'], repo_digests=image.get('RepoDigests'), platform=image.get('Architecture'), ants_verbose=ants_verbose, environment=fingerprint())
    write_json(receipt,evidence)
    print('Running; follow the log with: tail -f ' + shlex.quote(str(log)), flush=True)
    with log.open('x') as stream: child = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    evidence.update(status='success' if child.returncode == 0 else 'failed', returncode=child.returncode,
                    container_ended_at=dt.datetime.now(dt.timezone.utc).isoformat())
    workflow = ROOT / '04_workflow'
    import sys
    if str(workflow) not in sys.path: sys.path.insert(0, str(workflow))
    from processing_time import add_timing, refresh_safely
    add_timing(evidence)
    write_json(receipt, evidence)
    refresh_safely(root)
    if child.returncode: raise SystemExit(child.returncode)
    if stage == 'xcpd': validate(root)


def validate(root):
    receipt = json.loads((root/'logs/xcpd_execution.json').read_text())
    if receipt.get('status') != 'success': raise ValueError('XCP-D execution did not succeed')
    pipeline = load_module('02_custom/s10_xcpd_integrated_qc/pipeline.py')
    result = pipeline.validate_outputs(root/'xcpd', public_row(root, True), xcp_config(), 0)
    write_json(root/'xcpd/output_validation.json', result)
    print(json.dumps(result, indent=2))
    if not result['functional_outputs_valid']: raise ValueError('XCP-D technical validation failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['fetch','pull','mriqc','fmriprep','motion','xcpd','validate'])
    parser.add_argument('--root', type=external, required=True)
    parser.add_argument('--cache-dir', type=Path, help='Explicit local payload directory, verified against the same hashes')
    parser.add_argument('--source', choices=['bundled','remote'], default='bundled', help='Use included Git files by default; remote explicitly re-downloads the upstream payloads')
    parser.add_argument('--license', type=Path, default=Path(os.environ['FS_LICENSE']) if os.environ.get('FS_LICENSE') else None)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--ants-verbose', action='store_true')
    args = parser.parse_args(); root=args.root
    if args.stage == 'fetch': fetch(root,args.cache_dir,args.source)
    elif args.stage == 'pull':
        for image in IMAGES.values():
            command=['docker','pull','--platform','linux/amd64',image]; print(shlex.join(command),flush=True)
            if args.execute: subprocess.run(command,check=True)
    elif args.stage == 'validate': check_inputs(root); validate(root)
    elif args.stage == 'motion':
        check_inputs(root)
        commands = [[os.sys.executable,str(ROOT/'01_upstream/ADNI_fMRI_protocol/s8_final_qc/summarize_motion_from_confounds.py'),'--derivatives-dir',str(root/'derivatives/fmriprep'),'--output-dir',str(root/'qc/8')],
            [os.sys.executable,str(ROOT/'02_custom/s8a_motion_duration_qc/run.py'),'--bids-root',str(root/'bids'),'--derivatives-root',str(root/'derivatives/fmriprep'),'--output-dir',str(root/'qc/8a')]]
        for command in commands:
            print(shlex.join(command),flush=True)
            if args.execute: subprocess.run(command,check=True)
    elif args.execute: execute(root,args.stage,args.license,args.ants_verbose)
    else:
        print(shlex.join(docker_command(root,args.stage,args.license)))
        if args.ants_verbose: print('Execution will add the existing 7.C ANTs verbose transport and record the effective command.')


if __name__ == '__main__': main()
