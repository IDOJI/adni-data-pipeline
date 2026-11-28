import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lab_workflow', ROOT / '04_workflow/lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def configuration(tmp_path):
    cfg = tmp_path / 'lab.yaml'
    cfg.write_text(yaml.safe_dump({'data_root': str(tmp_path / 'data'), 'scratch_root': str(tmp_path / 'scratch'),
                                  'containers_root': str(tmp_path / 'containers'),
                                  'freesurfer_license': str(tmp_path / 'license.txt'),
                                  'mriqc_image': 'mriqc.sif', 'fmriprep_image': 'fmriprep.sif'}))
    return cfg


def test_integrated_protocol_identity_and_origin():
    result = lab.doctor()
    assert result['protocol_clean']
    assert result['distribution'] == 'integrated-source'
    assert result['scientific_validation'] != 'passed'


def test_config_does_not_mutate_source_and_uses_external_outputs(tmp_path):
    source = ROOT / 'pipeline/config/config_adni.yaml'
    before = source.read_bytes()
    result = lab.render_config(configuration(tmp_path), tmp_path / 'new-config')
    cfg = yaml.safe_load(Path(result['config']).read_text())
    assert '${' not in Path(result['config']).read_text()
    assert cfg['paths']['clinica_bids_dir'] == str(tmp_path / 'data/rawdata')
    assert cfg['sample_size']['mastersheet_csv'] == str(tmp_path / 'data/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv')
    assert cfg['slice_timing']['report_tsv'].startswith(str(tmp_path))
    assert cfg['qc']['final_inclusion_table'].startswith(str(tmp_path))
    assert source.read_bytes() == before
    with pytest.raises(ValueError, match='new output'):
        lab.render_config(configuration(tmp_path), tmp_path / 'new-config')


def test_placeholder_and_repo_output_rejected(tmp_path):
    with pytest.raises(ValueError, match='placeholders'):
        lab.render_config(ROOT / '03_config/lab_config.example.yaml', tmp_path / 'out')
    with pytest.raises(ValueError, match='outside'):
        lab.render_config(configuration(tmp_path), ROOT.parent / 'runtime')


def test_overrides_cannot_send_outputs_back_into_source(tmp_path):
    path = configuration(tmp_path)
    config = yaml.safe_load(path.read_text())
    config['upstream_overrides'] = {'qc': {'final_inclusion_table': str(ROOT / 'leak.tsv')}}
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match='outside'):
        lab.render_config(path, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_handoff_config_and_actual_upstream_mriqc_dry_run(tmp_path):
    custom_spec = importlib.util.spec_from_file_location('handoff_integration', ROOT / 'pipeline/s5c_validate_handoff/run.py')
    custom = importlib.util.module_from_spec(custom_spec); custom_spec.loader.exec_module(custom)
    source = tmp_path / 'final.tsv'
    source.write_text('Subject_ID\tVISCODE\n999_S_9999\tbl\n999_S_9999\tm12\n')
    handoff_dir = tmp_path / 'handoff'
    custom.process(source, handoff_dir)
    result = lab.render_config(configuration(tmp_path), tmp_path / 'generated', handoff_dir)
    config = yaml.safe_load(Path(result['config']).read_text())
    assert config['qc']['heuristics_final_table'] == str(handoff_dir / 'mriqc_subjects.csv')
    assert config['paths']['fmriprep_heuristics_csv'] == str(handoff_dir / 'post_clinica.csv')
    Path(config['mriqc']['bids_dir']).mkdir(parents=True)
    env = dict(os.environ, PYTHONPATH=str(lab.PIPELINE), PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'])
    child = subprocess.run(['bash', str(lab.PIPELINE / 's6_mriqc/adni_mriqc.slurm'), '--config', result['config'], '--dry-run'],
                           cwd=tmp_path, env=env, capture_output=True, text=True)
    assert child.returncode == 0, child.stdout + child.stderr
    assert '1 array entries' in child.stderr
    jobs = list((tmp_path / 'data/results/mriqc/scripts').glob('job_array_input_part_*'))
    assert len(jobs) == 1
    assert jobs[0].read_text().splitlines() == ['sub-ADNI999S9999']
    plan = lab.commands(result['config'], handoff_dir)
    assert plan['mode'] == 'print_only'
    assert '--sessions-csv' in plan['commands']['7']
    assert 'qc/step5a' in plan['commands']['5a']
    # Provenance prevents silently reusing a modified consumer input.
    (handoff_dir / 'mriqc_subjects.csv').write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        lab.render_config(configuration(tmp_path), tmp_path / 'bad-config', handoff_dir)


def test_metrics_summary_plan_is_explicit_and_shell_safe(tmp_path):
    import shlex
    archive=tmp_path/'archive with spaces';archive.mkdir()
    state=tmp_path/'runtime'/'metrics status.json'
    argv=lab.metrics_summary_command(archive,state,watch=True)
    assert argv[-1]=='--watch'
    assert argv[argv.index('--archive-root')+1]==str(archive)
    result=lab.render_config(configuration(tmp_path),tmp_path/'configured')
    default=lab.commands(result['config'])
    assert '12' not in default['commands']
    planned=lab.commands(result['config'],archive_root=archive,metrics_status=state)
    command=shlex.split(planned['commands']['12'])
    assert command==lab.metrics_summary_command(archive,state)
    assert planned['mode']=='print_only' and not state.exists()


def test_metrics_summary_rejects_repository_and_missing_paths(tmp_path):
    with pytest.raises(ValueError,match='outside'):
        lab.metrics_summary_command(ROOT)
    with pytest.raises(ValueError,match='existing external archive'):
        lab.metrics_summary_command(tmp_path/'missing')
    archive=tmp_path/'archive';archive.mkdir()
    with pytest.raises(ValueError,match='file path'):
        lab.metrics_summary_command(archive,archive)
