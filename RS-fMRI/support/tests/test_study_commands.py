"""Exercise the beginner terminal entry points using private temporary synthetic studies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_bids_binding import fixture as make_bids
from test_clinical_validation import fixture as clinical_fixture
from test_image_selection import collection
from test_source_qc import spine, quality, write
from test_fc_harmonization import archive, config, profile
from _shared import read, sha

LAB = Path(__file__).resolve().parents[2]
START = LAB / 'start'


@pytest.fixture
def imaging(monkeypatch):
    monkeypatch.syspath_prepend(str(START))
    from support import imaging
    return imaging


@pytest.mark.parametrize('already_running', [True, False])
def test_docker_readiness_only_launches_when_needed(imaging, monkeypatch, already_running):
    calls = []
    results = [0] if already_running else [1, 0, 1, 0]

    def command(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, results.pop(0), '', '')

    monkeypatch.setattr(imaging.subprocess, 'run', command)
    monkeypatch.setattr(imaging, 'time', SimpleNamespace(monotonic=lambda: 0, sleep=lambda delay: None))
    imaging.ensure_docker_ready()
    probe = ['docker', 'info', '--format', '{{.ServerVersion}}']
    launch = ['/usr/bin/open', '-g', '-j', '-b', 'com.docker.docker']
    assert calls == ([probe] if already_running else [probe, launch, probe, probe])


def test_docker_start_times_out_and_reports_last_engine_error(imaging, monkeypatch):
    clock = 0

    def sleep(seconds):
        nonlocal clock
        clock += seconds

    def command(argv, **kwargs):
        if argv[0] == 'docker':
            return subprocess.CompletedProcess(argv, 1, '', 'Docker engine is unavailable')
        return subprocess.CompletedProcess(argv, 0, '', '')

    monkeypatch.setattr(imaging.subprocess, 'run', command)
    monkeypatch.setattr(imaging, 'time', SimpleNamespace(monotonic=lambda: clock, sleep=sleep))
    with pytest.raises(ValueError, match='180 seconds.*Docker engine is unavailable'):
        imaging.ensure_docker_ready()
    assert clock == 180


def test_imaging_checks_docker_before_creating_processing_settings(imaging, monkeypatch, tmp_path):
    monkeypatch.setattr(imaging, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(imaging, 'cohort_plans', lambda receipt, pairs: [])
    monkeypatch.setattr(imaging, 'template', lambda name: {})
    (tmp_path / 'receipt.json').touch()
    (tmp_path / 'license.txt').touch()
    cache = tmp_path / 'templateflow'
    cache.mkdir()
    (cache / 'tpl-example').touch()
    args = SimpleNamespace(binding=tmp_path / 'receipt.json', study=tmp_path, pairs=None, templateflow=None, license=None)

    def command(argv, **kwargs):
        if argv[0] == 'docker':
            return subprocess.CompletedProcess(argv, 1, '', 'Engine is stopped')
        assert argv[0] == '/usr/bin/open'
        return subprocess.CompletedProcess(argv, 1, '', 'Docker Desktop is missing')

    monkeypatch.setattr(imaging.subprocess, 'run', command)
    with pytest.raises(ValueError, match='Could not start Docker Desktop: Docker Desktop is missing'):
        imaging.run_images(args, tmp_path)
    assert not (tmp_path / 'preprocessing.yaml').exists()


def cli(script, study, *args, success=True, env=None):
    result = subprocess.run([sys.executable, START / script, study, *args], cwd=study.parent,
                            env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    return result


def study_inputs(study):
    tables = study / 'LONI_download/clindata'
    tables.mkdir(parents=True)
    collections = study / 'collections'
    collections.mkdir()
    scans, grades = [], []
    for iid, kind, label, desc in [('100', 'T1', 'T1w', 'MPRAGE'), ('200', 'EPI', 'BOLD', 'Resting State fMRI')]:
        uid = '1.2.' + iid
        scans.append(dict(spine(iid), SeriesInstanceUID=uid, SeriesType=label, SeriesDescription=desc))
        grades.append(quality(iid, SERIES_TYPE=label, SERIESINSTANCEUID=uid))
        write(collections / (kind + '.csv'), [collection(iid, Phase='ADNI3', Description=desc, Age='70')])
    write(tables / 'MRIQC.csv', scans)
    write(tables / 'MAYO_ADNI3.csv', grades)
    (tables / 'MAYO_GO2.csv').write_text('LONI_IMAGE,PTID\n')
    (tables / 'DELMRSCANS.csv').write_text('IMAGEID,SUBJECTID,SCANDATE,DELETEDATE\n')
    write(tables / 'NFQ.csv', [dict(LONIImage='I200', RID='9999', StudyDate='2020-01-01',
                                    SeriesInstanceUID='1.2.200', OVERALLQC='2', SLICETIMING='')])
    return tables


def test_default_study_select_convert_bind_clinical(tmp_path):
    study = tmp_path / 'private study'
    tables = study_inputs(study)
    for _ in range(2):
        cli('01_select.py', study)
    assert set((study / '01-selection/images/09.download-candidates.txt').read_text().split()) == {'I100', 'I200'}
    _, _, _, _, bids = make_bids(tmp_path)
    from test_direct_conversion import source
    review = study / 'review'
    review.mkdir()
    raw = study / 'LONI_download/sourcedata'
    source(raw, '100')
    source(raw, '200')
    # Isolate the third-party executable; the source checks, receipts and binding are real.
    exe = tmp_path / 'dcm2niix'
    exe.write_text(f"""#!{sys.executable}
from pathlib import Path
import os, shutil, sys, pydicom
if sys.argv[1] == '--version':
    print('v1.0.20240202')
    sys.exit(3)
uid = pydicom.dcmread(next(Path(sys.argv[-1]).glob('*.dcm')), stop_before_pixels=True).SeriesInstanceUID
out = Path(sys.argv[sys.argv.index('-o') + 1])
src = Path(os.environ['STUDY_FIXTURE'])
for ext in ('.nii.gz', '.json'):
    suffix = '_T1w' if uid == '1.2.100' else '_bold'
    file, = src.glob('sub-*/ses-*/*/*' + suffix + ext)
    shutil.copy(file, out / (uid + ext))
""")
    exe.chmod(0o700)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'], STUDY_FIXTURE=str(bids))
    cli('02_bids.py', study, 'convert', env=env)
    rawdata = study / '02-bids/rawdata'
    recorded = read(rawdata / 'sourcedata/conversion/conversion-hashes.csv')
    assert {r['SOURCE_IMAGE_ID']: r['NIFTI_SHA256'] for r in recorded} == {
        r['SOURCE_IMAGE_ID'].lstrip('I'): r['NIFTI_SHA256'] for r in read(tmp_path / 'hashes.csv')}
    for _ in range(2):
        assert 'Verified pairs: 1' in cli('02_bids.py', study, 'bind').stdout
    assert cli('02_bids.py', study, 'convert', env=env, success=False).returncode == 1
    final = study / '03-imaging/postprocessing/test/finalizations/one'
    final.mkdir(parents=True)
    included, _, dx, pt = clinical_fixture(tmp_path)
    shutil.copy(included, final / 'final_included_runs.tsv')
    shutil.copy(included, final / 'final_qc_master.tsv')
    (final / 'summary.json').write_text(json.dumps(dict(cohort_finalization_deferred=False)))
    write(final / 'clinical_scan_links.tsv', [dict(read(included)[0], Image_ID='200', Scan_Date='2020-01-01')])
    (study / '03-imaging/finalization.json').write_text(json.dumps(dict(final_qc=str(final / 'final_qc_master.tsv'),
                                                                sha256=sha(final / 'final_qc_master.tsv'))))
    shutil.copy(dx, tables / 'DXSUM.csv')
    shutil.copy(pt, tables / 'PTDEMOG.csv')
    (review / 'confirmed-st-absence.csv').write_text('IMAGE_ID,PTID,MRI_STUDY_DATE,ST_STATUS,EVIDENCE_REF\n')
    for _ in range(2):
        cli('03_process.py', study, 'clinical')
    row, = read(study / '03-imaging/inclusion/inclusion_audit.tsv')
    assert row['MRI_AGE_YEARS'] == '70.0' and row['SERIES_UID'] == '1.2.200' and row['CLINICAL_STATUS'] == 'pass'
    next(rawdata.glob('sub-*/ses-*/func/*bold.json')).write_text('{}')
    assert 'changed' in cli('02_bids.py', study, 'bind', success=False).stderr


def test_harmonize_existing_finalization_audit_and_fit(tmp_path):
    pytest.importorskip('neuroCombat')
    records = [archive(tmp_path, profile(), index) for index in range(16)]
    cfg = json.loads(config(tmp_path, records).read_text())
    final = tmp_path / 'finalizations/reviewed'
    final.mkdir(parents=True)
    for name in ['final_qc_master.tsv', 'summary.json']:
        (tmp_path / name).rename(final / name)
    args = ['--inclusion', cfg['inclusion_dir'], '--final-qc', final / 'final_qc_master.tsv', '--scanners', cfg['scanner_map']]
    assert 'audit_passed' in cli('04_harmonize.py', tmp_path, 'audit', *args).stdout
    assert 'fitted' in cli('04_harmonize.py', tmp_path, 'fit', *args).stdout
    assert (tmp_path / '04-harmonization/fit/fc.npz').is_file()
    table = final / 'final_qc_master.tsv'
    rows = read(table)
    rows[0]['config_id'] = 'different'
    write(table, rows)
    assert 'one XCP-D configuration' in cli('04_harmonize.py', tmp_path, 'audit', *args, success=False).stderr


def test_study_routes_visit_to_its_own_execution_records(tmp_path):
    from s10_xcpd_integrated_qc.pipeline import Pipeline
    root = tmp_path
    app = SimpleNamespace(root=root, cfg={'verified_case_archives': True})
    sub, ptid = 'ADNI999S9999', '999_S_9999'
    for iid, date in [('100', '20200101'), ('200', '20210101')]:
        pairid = f'EPI_{date}_MT1_{date}'
        case = root / 'cases' / ('I' + iid)
        pair = case / 'results' / ptid / pairid
        pair.mkdir(parents=True)
        identity = {}
        for stage in ['mriqc', 'fmriprep']:
            log = case / 'runs' / sub / 'logs' / f'x_{stage}_sub-{sub}_ses-{date}'
            log.mkdir(parents=True)
            identity[stage] = dict(started_at=date, runner_sha256=iid, image={'resolved': 'synthetic'})
            (log / 'run.json').write_text(json.dumps(dict(status='execution_completed_QC_required', exit_code=0,
                                                   input_unchanged=True, **identity[stage])))
        meta = dict(ptid=ptid, subject=sub, epi_image_id=iid, pair_id=pairid, execution_identity=identity,
                    delivery_status='processing_complete_QC_pending')
        (pair / 'pair_metadata.json').write_text(json.dumps(meta))
        link = root / 'results' / ptid / pairid
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(pair)
        assert Pipeline.verify_complete_pair(app, link)['epi_image_id'] == iid
    (log / 'run.json').write_text('{}')
    with pytest.raises(ValueError, match='Both stages'):
        Pipeline.verify_complete_pair(app, link)


def test_finalize_requires_explicit_review(tmp_path):
    assert '--cohort-complete' in cli('03_process.py', tmp_path, 'finalize', success=False).stderr
