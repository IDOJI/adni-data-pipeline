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

LAB = Path(__file__).resolve().parents[1]
START = LAB / 'start'


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
    # Use native binding and real synthetic NIfTIs, substituting only the third-party converter.
    review = study / 'review'
    review.mkdir()
    for iid in ('I100', 'I200'):
        dcm = study / 'LONI_download/sourcedata/999_S_9999/series/2020-01-01_12_00' / iid
        dcm.mkdir(parents=True)
        (dcm / 'image.dcm').write_bytes(b'synthetic DICOM placeholder')
    info = bids / 'conversion_info/v0'
    info.mkdir(parents=True)
    scans = []
    for iid, name, suffix in [('100', 't1', 'T1w'), ('200', 'fmri', 'bold')]:
        source = next((study / 'LONI_download/sourcedata').glob('*/*/*/I' + iid))
        write(info / (name + '_paths.tsv'), [dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID=iid,
                                                 Scan_Date='2020-01-01', Path=str(source))])
        nifti = next(bids.glob('sub-*/ses-*/*/*_' + suffix + '.nii.gz'))
        session = nifti.parents[1]
        scans.append(dict(filename=str(nifti.relative_to(session)), scan_id=iid))
    write(session / 'sub-999S9999_ses-20200101_scans.tsv', scans)
    exe = tmp_path / 'clinica'
    exe.write_text("""#!/bin/sh
if [ "$3" = "--help" ]; then
    echo '-m [T1|FMRI] --subjects_list'
    exit 0
fi
test "$3" = "-m" && test "$4" = "T1" && test "$6" = "FMRI" && test "$7" = "--subjects_list" || exit 2
test "$(cat "$8")" = 999_S_9999 || exit 3
test -d "$9" && test -d "${10}" || exit 4
cp -R "$STUDY_FIXTURE" "${11}"
""")
    exe.chmod(0o700)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'], STUDY_FIXTURE=str(bids))
    cli('02_bids.py', study, 'convert', env=env)
    recorded = read(study / '02-bids/conversion-hashes.csv')
    assert {r['SOURCE_IMAGE_ID']: r['NIFTI_SHA256'] for r in recorded} == {
        r['SOURCE_IMAGE_ID'].lstrip('I'): r['NIFTI_SHA256'] for r in read(tmp_path / 'hashes.csv')}
    for _ in range(2):
        assert 'Verified pairs: 1' in cli('02_bids.py', study, 'bind').stdout
    assert 'exists' in cli('02_bids.py', study, 'convert', env=env, success=False).stderr
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
    (study / '02-bids/rawdata'/next(bids.glob('sub-*/ses-*/func/*bold.json')).relative_to(bids)).write_text('{}')
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


def test_conversion_fingerprints_hold_ambiguous_or_conflicting_mappings(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(START))
    from support.conversion import fingerprints
    bids = tmp_path / 'rawdata'
    session = bids / 'sub-ADNI999S9999/ses-M000'
    folder = session / 'func'
    folder.mkdir(parents=True)
    output = folder / 'sub-ADNI999S9999_ses-M000_task-rest_bold.nii.gz'
    output.write_bytes(b'synthetic')
    table = bids / 'conversion_info/v0/fmri_paths.tsv'
    table.parent.mkdir(parents=True)
    dicom = tmp_path / 'dicom'
    source = dicom / '999_S_9999/rest/2020-01-01_12_00/I200'
    source.mkdir(parents=True)
    row = dict(Subject_ID='999_S_9999', VISCODE='bl', Image_ID='200', Scan_Date='2020-01-01', Path=str(source))
    scans = session / 'example_scans.tsv'
    scan = dict(filename='func/' + output.name, scan_id='200')
    registry = [dict(IMAGE_ID='200', PTID='999_S_9999', MODALITY='EPI', MRI_STUDY_DATE='2020-01-01')]
    for inputs, outputs in [([row, row], [scan]), ([row], [scan, scan]),
                            ([dict(row, Scan_Date='2020-02-01')], [scan]), ([row], [dict(scan, scan_id='n/a')])]:
        write(table, inputs)
        write(scans, outputs)
        assert fingerprints(bids, dicom, registry, tmp_path) == 0
        assert not (tmp_path / 'conversion-hashes.csv').exists()
