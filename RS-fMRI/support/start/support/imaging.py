"""Run the seeded, verified ADNI imaging route and publish a shared QC table."""
import csv
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import time

import yaml

from .study import LAB, PIPELINE, existing, fixed_text, settings, template
from _shared import read, sha
from s5d_bids_identity import binding
from s7b_sessionwise_preprocessing.publish_pairs import publish_verified_pair

sys.path.insert(0, str(PIPELINE / 's5d_bids_identity'))
import guarded_runner_seeded as gate
import continuation
from s10_xcpd_integrated_qc import pipeline_seeded as xcpd


def cohort_plans(receipt, pairs):
    proof = binding.proof_files(receipt)
    plans = binding.read_json(proof['outputs']['plans']['path'])
    if pairs:
        wanted = set(existing(pairs).read_text().splitlines())
        plans = [p for p in plans if p['epi_key'] in wanted]
        if {p['epi_key'] for p in plans} != wanted:
            raise ValueError('Unverified EPI key in --pairs. Check the execution plans.')
    if not plans:
        raise ValueError('No verified pairs for imaging.')
    if any(p['subject'] != 'ADNI' + p['ptid'].replace('_', '') for p in plans):
        raise ValueError('The local publisher requires ADNI subject labels of the form sub-ADNI... .')
    for fields in [('ptid', 'date'), ('subject', 'session')]:
        identities = {tuple(p[f] for f in fields) for p in plans}
        if len(identities) != len(plans):
            raise ValueError('Multiple scans share a dated pair or BIDS visit. Review and supply --pairs.')
    return plans


def process_pair(receipt, plan, case, prep):
    config = case / 'pair/verified-config.yaml'
    if not config.exists():
        gate.prepare(receipt, plan['epi_key'], case / 'pair', prep)
    cfg = yaml.safe_load(config.read_text())
    if (cfg['epi_key'] != plan['epi_key'] or Path(cfg['binding_receipt']) != receipt
            or Path(cfg['runtime']) != case / 'pair/processing'
            or any(cfg.get(k) != v for k, v in yaml.safe_load(prep.read_text()).items())):
        raise ValueError(f'Existing case has different inputs or settings: {case}')
    gate.dispatch(config, 'intake')
    runtime = Path(cfg['runtime'])
    decisions = read(runtime / 'results/step5/intake_decisions.tsv', ('sub', 'ses', 'strict_upstream_eligible'))
    if len(decisions) != 1 or (decisions[0]['sub'], decisions[0]['ses']) != (
            'sub-' + plan['subject'], 'ses-' + plan['session']):
        raise ValueError(f'Intake identity mismatch: {runtime}')
    if decisions[0]['strict_upstream_eligible'].lower() != 'true':
        print(f"Held by intake: {plan['epi_key']} (see {runtime / 'results/step5'})", flush=True)
        return None
    paths = gate.backend().paths_for(cfg, cfg['runs'][0])
    for stage in continuation.STAGES:
        _, record = continuation.latest(runtime, plan['subject'], stage)
        if not continuation.completed(record):
            if record and record.get('status') != 'failed':
                raise ValueError(f'Inspect the existing {stage} execution in {runtime}')
            gate.dispatch(config, 'run', stage)
            _, record = continuation.latest(runtime, plan['subject'], stage)
        if not continuation.completed(record):
            raise ValueError(f'{stage} did not complete successfully in {runtime}')
        continuation.check_record(record, paths, plan, runtime / 'bids')
        continuation.output_evidence(runtime, plan['subject'], stage)
    return publish_verified_pair(case)


def docker_engine_error(timeout):
    try:
        result = subprocess.run(
            ['docker', 'info', '--format', '{{.ServerVersion}}'],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ValueError('Docker CLI is unavailable. Install Docker Desktop and put docker on PATH.') from exc
    except subprocess.TimeoutExpired:
        return 'docker info did not respond'
    if result.returncode == 0:
        return ''
    return result.stderr.strip() or result.stdout.strip() or f'docker info exited with {result.returncode}'


def ensure_docker_ready():
    problem = docker_engine_error(timeout=5)
    if not problem:
        return

    print('Starting Docker Desktop in the background. Waiting for the engine...', flush=True)
    try:
        launch = subprocess.run(
            ['/usr/bin/open', '-g', '-j', '-b', 'com.docker.docker'],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError('macOS did not respond to the Docker Desktop launch request.') from exc
    if launch.returncode:
        detail = launch.stderr.strip() or launch.stdout.strip() or f'open exited with {launch.returncode}'
        raise ValueError(f'Could not start Docker Desktop: {detail}')

    deadline = time.monotonic() + 180
    while (remaining := deadline - time.monotonic()) > 0:
        problem = docker_engine_error(timeout=min(5, remaining))
        if not problem:
            print('Docker is ready.', flush=True)
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise ValueError(f'Docker did not become ready within 180 seconds. Check Docker Desktop and the selected context. {problem}')


def run_images(args, folder):
    if sys.platform != 'darwin':
        raise ValueError('The local publisher needs macOS clone-copy support. See 06_docs/platform_execution.md.')
    receipt = existing(args.binding or args.study / '02-bids/binding/07.binding-receipt.json')
    plans = cohort_plans(receipt, args.pairs)
    tf = (args.templateflow or args.study / 'templateflow').expanduser().resolve()
    if not tf.is_dir() or not any(tf.iterdir()):
        raise ValueError(f'Missing populated TemplateFlow cache: {tf}')
    license_file = existing(args.license or args.study / 'license.txt')
    batch = template('local_batch.seeded.example.json')
    ensure_docker_ready()
    prep = batch['preprocessing_template']
    prep.update(source_templateflow=str(tf), freesurfer_license=str(license_file))
    prep_path = fixed_text(folder / 'preprocessing.yaml', yaml.safe_dump(prep))
    for stage, expected in batch['pinned_images'].items():
        actual = gate.backend().image_record(prep['images'][stage])
        if actual['resolved'] != expected:
            raise ValueError(f'Load the pinned {stage} image from the installation guide.')
    settings(folder / 'cohort.json', dict(receipt=receipt, sha256=sha(receipt),
                                          epi_keys=[p['epi_key'] for p in plans]))
    xcfg = template('xcpd_linc.seeded.example.json')
    xcfg.update(root=str(folder), license=str(license_file), templateflow=str(tf),
                resources=batch['xcpd_resources'], verified_case_archives=True)
    config = settings(folder / 'xcpd.json', xcfg)
    app = xcpd.Pipeline(config)
    cli = [sys.executable, PIPELINE / 's10_xcpd_integrated_qc/pipeline_seeded.py', '--config', config]
    subprocess.run([*cli, 'preflight'], check=True)
    expected_pairs = set()
    for plan in plans:
        case = folder / 'cases' / ('I' + plan['epi_image_id'])
        target = process_pair(receipt, plan, case, prep_path)
        if target is None:
            continue
        link = folder / 'results' / target.parent.name / target.name
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink():
            link.symlink_to(target, target_is_directory=True)
        if link.resolve() != target:
            raise ValueError(f'Unexpected existing archive at {link}')
        expected_pairs.add(link)
    if not expected_pairs or expected_pairs != set(app.pairs()):
        raise ValueError('No published pairs, or the study contains unexpected archive entries.')
    subprocess.run([*cli, 'once'], check=True)
    subprocess.run([*cli, 'collect'], check=True)
    for pair in expected_pairs:
        ready = app.stage_dir(pair) / 'archive_ready.json'
        if not ready.exists() or not json.loads(ready.read_text()).get('runs'):
            raise ValueError(f'XCP-D or QC remains incomplete for {pair}. See {app.hub / "events.jsonl"}')
    settings(folder / 'processed-pairs.json', dict(config_id=app.config_id, pairs=sorted(map(str, expected_pairs))))
    print(f'Open the reports listed in {app.hub / "visual_review.tsv"}')



def cohort_iqms(args, folder):
    """Build the two wide metric tables used by the native seeded R fitter."""
    app = xcpd.Pipeline(existing(folder / 'xcpd.json'))
    processed = json.loads(existing(folder / 'processed-pairs.json').read_text())
    if processed != dict(config_id=app.config_id, pairs=list(map(str, app.pairs()))):
        raise ValueError('The MRIQC population differs from the processed cohort.')
    cfg = {}
    for modality, modality_dir, metrics in [
            ('bold', 'func', 'aor aqi efc fd_mean dvars_std fwhm_avg snr tsnr'),
            ('T1w', 'anat', 'cjv efc fwhm_avg cnr snr_total tpm_overlap_csf tpm_overlap_gm tpm_overlap_wm')]:
        suffix = '_T1w' if modality == 'T1w' else ''
        fields = {m: m + suffix for m in metrics.split()}
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=['participant_id', 'ses_id', *fields.values()], delimiter='\t',
                                lineterminator='\n')
        writer.writeheader()
        for pair in app.pairs():
            meta = app.verify_complete_pair(pair)
            sub, ses = 'sub-' + meta['subject'], 'ses-' + meta['execution_session_label']
            base = pair / 'mriqc' / sub / ses / modality_dir
            files = list(base.glob(f'{sub}_{ses}_*{modality}.json'))
            if len(files) != 1:
                raise ValueError(f'Expected one {modality} IQM file in {base}.')
            iqms = json.loads(files[0].read_text())
            writer.writerow(dict(participant_id=sub, ses_id=ses, **{name: iqms.get(m) for m, name in fields.items()}))
        cfg['group_' + modality.lower() + '_tsv'] = str(fixed_text(folder / f'iqms-{modality}.tsv', stream.getvalue()))
    config = settings(folder / 'iqms.json', dict(mriqc=cfg))
    target = folder / 'cohort-iqms'
    subprocess.run([sys.executable, LAB / '04_workflow/iqm_seeded.py', '--config', config,
                    '--out-dir', target, '--execute'], check=True)
    print(f'Review the cohort flags in {existing(target / "all_IQMs_with_QC_flags_clean.tsv")}')

def finalize(args, folder):
    if not args.cohort_complete:
        raise ValueError('Finish cohort and visual review, then add --cohort-complete.')
    flags = existing(args.mriqc_flags or folder / 'cohort-iqms/all_IQMs_with_QC_flags_clean.tsv')
    app = xcpd.Pipeline(existing(folder / 'xcpd.json'))
    processed = json.loads(existing(folder / 'processed-pairs.json').read_text())
    if processed != dict(config_id=app.config_id, pairs=list(map(str, app.pairs()))):
        raise ValueError('Published cohort differs from the completed run.')
    pointer = folder / 'finalization.json'
    if pointer.exists():
        raise ValueError(f'A finalization is already recorded in {pointer}. Use clinical to continue.')
    out = app.hub / 'finalizations'
    before = set(out.glob('*/final_qc_master.tsv'))
    app.aggregate(cohort_ready=True, mriqc_flags=str(flags))
    new = set(out.glob('*/final_qc_master.tsv')) - before
    if len(new) != 1:
        raise ValueError(f'Check the finalization in {out}. No unique new master table.')
    master = new.pop()
    settings(pointer, dict(final_qc=str(master), sha256=sha(master)))
    print(f'Final imaging decisions: {master}')
