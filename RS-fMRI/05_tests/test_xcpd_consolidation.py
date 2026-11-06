"""Contracts introduced by consolidation, tested without Docker or private data."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

p = module('consolidated_xcpd', '02_custom/s10_xcpd_integrated_qc/pipeline.py')
clinical = module('consolidated_clinical', '02_custom/s9a_validate_clinical/run.py')


def config(tmp_path):
    value = p.load(ROOT / '03_config/xcpd_linc.example.json')
    value['root'] = str(tmp_path / 'runtime')
    path = tmp_path / 'private.json'; p.save(path, value)
    return path, value


@pytest.mark.parametrize('bad', ['repository', 'relative', 'placeholder'])
def test_integrated_runtime_guard_precedes_output_creation(tmp_path, bad):
    path, cfg = config(tmp_path)
    cfg['root'] = {'repository':str(ROOT.parent), 'relative':'relative-runtime',
                   'placeholder':'/ABSOLUTE/PATH/runtime'}[bad]
    p.save(path, cfg)
    with pytest.raises(ValueError, match='external runtime|outside the source'):
        p.Pipeline(path)
    assert not (tmp_path / 'runtime').exists()


def test_unreviewed_upstream_checkout_cannot_be_substituted(tmp_path):
    path, cfg = config(tmp_path)
    cfg['repo'] = str(tmp_path / 'other-protocol'); p.save(path, cfg)
    with pytest.raises(ValueError, match='integrated protocol'):
        p.Pipeline(path)
    assert not (tmp_path / 'runtime').exists()


def test_config_must_be_explicit_for_both_execution_paths():
    for name in ('s7a_volume_workflow', 's10_xcpd_integrated_qc'):
        command = [sys.executable, str(ROOT / '02_custom' / name / 'pipeline.py')]
        result = subprocess.run(command, text=True, capture_output=True)
        assert result.returncode == 2 and '--config' in result.stderr


def test_two_profiles_keep_distinct_processing_choices(tmp_path):
    legacy = module('volume_profile_for_test', '02_custom/s7a_volume_workflow/pipeline.py')
    old = p.load(ROOT / '02_custom/s7a_volume_workflow/config.example.json')
    new = p.load(ROOT / '03_config/xcpd_linc.example.json')
    cmd = legacy.build_command(old, 'xcpd', old['runs'][0])
    assert cmd[cmd.index('--nuisance-regressors')+1] == 'acompcor'
    assert cmd[cmd.index('--fd-thresh')+1] == '0.5'
    assert new['nuisance_regressors'] == '36P' and new['global_signal_regression'] is True
    assert new['fd_threshold'] == 0.3 and new['min_time'] == 240
    assert '--config' in (ROOT / '02_custom/s10_xcpd_integrated_qc/pipeline.py').read_text()


def write(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t' if path.suffix == '.tsv' else ',')
        writer.writeheader(); writer.writerows(rows)
    return path


def test_aggregate_exports_actual_image_date_link_for_clinical_step(tmp_path):
    path, cfg = config(tmp_path); app = p.Pipeline(path)
    pair = app.root / 'results/999_S_9999/EPI_20200101_MT1_20191231'
    pair.mkdir(parents=True)
    p.save(pair / 'pair_metadata.json', {'subject':'ADNI999S9999'})
    row = dict(sub='sub-ADNI999S9999', ses='ses-M000', task='task-rest', run='', acq='', dir='', echo='', rec='',
               config_id=app.config_id, pipeline_version=cfg['pipeline_version'], site='999',
               source_pair=str(pair), candidate=True, mean_fd=.1, fd_over_0p5_proportion=.01,
               pre_xcpd_qc_status='review_required', epi_image_id='101', epi_date='20200101',
               pair_id=pair.name, avg_euler=-20, euler_qc_flag=None, mriqc_exclude_flag=None)
    p.save(app.stage_dir(pair) / 'pre_qc.json', {'config_id':app.config_id, 'rows':[row]})
    app.aggregate()
    links = app.hub / 'clinical_scan_links.tsv'
    assert p.table(links)[0]['Scan_Date'] == '2020-01-01'
    assert p.table(app.hub / 'final_included_runs.tsv') == []
    assert p.table(app.hub / 'final_qc_master.tsv')[0]['ANALYSIS_READY'] == 'False'
    # The reviewed inclusion fixture is separate; collection does not auto-approve a run.
    included = write(tmp_path / 'reviewed.tsv', [{k:row[k] for k in p.KEYS}])
    dx = write(tmp_path / 'dx.csv', [dict(RID='9999', PHASE='ADNI3', EXAMDATE='2020-01-01', DIAGNOSIS='1')])
    pt = write(tmp_path / 'pt.csv', [dict(RID='9999', VISDATE='2020-01-01')])
    result = clinical.process(included, links, dx, pt, tmp_path / 'clinical')
    assert result['summary']['clinical_status'] == {'pass':1}
