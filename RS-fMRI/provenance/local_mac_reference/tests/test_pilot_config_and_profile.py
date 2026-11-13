import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
source = Path(__file__).parents[1] / 'pilot.py'
if not source.exists():
    source = Path(__file__).with_name('pilot.future.py')
spec = importlib.util.spec_from_file_location('pilot_future', source)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def make_intake(tmp_path, phase, eligible, failures):
    folder = tmp_path / 'results/step5'
    folder.mkdir(parents=True)
    (folder / 'intake_decisions.tsv').write_text(
        'sub\tses\tstrict_upstream_eligible\tfailed_checks\n'
        f'sub-999S99999\tses-20000102\t{eligible}\t{failures}\n')
    return {'runtime': str(tmp_path)}, {'subject': '999S99999', 'session': '20000102', 'phase': phase}


def test_adni3_strict_profile(tmp_path):
    cfg, case = make_intake(tmp_path, 'ADNI3', 'True', '')
    assert pilot.profile_for(cfg, case) == 'strict'


@pytest.mark.parametrize('failures', ['', 'filter_invalid_repetition_time'])
def test_adni4_retains_technical_extension_with_or_without_tr_failure(tmp_path, failures):
    cfg, case = make_intake(tmp_path, 'ADNI4', 'False', failures)
    assert pilot.profile_for(cfg, case) == 'technical-extension'


def test_adni4_with_additional_failure_is_not_automatically_overridden(tmp_path):
    cfg, case = make_intake(tmp_path, 'ADNI4', 'False', 'filter_invalid_repetition_time;filter_short_duration')
    with pytest.raises(ValueError, match='additional intake rules'):
        pilot.profile_for(cfg, case)


def test_unsupported_adni3_does_not_auto_override(tmp_path):
    cfg, case = make_intake(tmp_path, 'ADNI3', 'False', 'filter_short_duration')
    with pytest.raises(ValueError, match='additional intake rules'):
        pilot.profile_for(cfg, case)


def test_snapshot_saves_requested_config_not_unrelated_default(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    output = tmp_path / 'output'
    output.mkdir()
    for name in ('pilot.py', 'run.py', 'qc.py', 'spatial_qc.py', 'image_tools.py'):
        (source / name).write_text(name)
    (source / 'config.local.yaml').write_text('default: unrelated\n')
    custom = tmp_path / 'custom.yaml'
    custom.write_text('runtime: user_selected\n')
    pilot.snapshot_sources(output, custom, source_dir=source)
    assert (output / 'config_source.yaml').read_text() == custom.read_text()
    assert not (output / 'config.local.yaml').exists()
