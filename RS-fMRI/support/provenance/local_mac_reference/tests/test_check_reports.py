import importlib.util
import json
import os
from pathlib import Path

import pytest

source = Path(os.environ.get('STATMIND_REPORT_QC_SOURCE', str(Path(__file__).parents[1] / 'check_reports.py')))
spec = importlib.util.spec_from_file_location('report_qc', source)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)

good = '<ul><li>Slice timing correction: Applied</li><li>Susceptibility distortion correction: FLB ("fieldmap-less", SyN-based)</li></ul>'


def test_actual_style_report_is_recognized():
    result = report.parse_summary(good)
    assert result['slice timing correction'] == 'Applied'
    assert 'SyN-based' in result['susceptibility distortion correction']


@pytest.mark.parametrize('sdc', ['None', 'SyN requested but not applied', 'SyN disabled', ''])
def test_only_actual_syn_is_accepted(sdc):
    content = f'<li>Slice timing correction: Applied</li><li>Susceptibility distortion correction: {sdc}</li>'
    with pytest.raises(ValueError, match='not reported as applied'):
        report.parse_summary(content)


def test_skipped_slice_timing_is_not_accepted():
    with pytest.raises(ValueError, match='Slice timing correction'):
        report.parse_summary(good.replace('correction: Applied', 'correction: Not applied', 1))


def test_report_audit_preserves_sources_and_refuses_overwrite(tmp_path):
    d = tmp_path / 'derivatives'
    folder = d / 'sub-998S9999/figures'; folder.mkdir(parents=True)
    f = folder / 'sub-998S9999_ses-20000101_task-rest_desc-summary_bold.html'
    f.write_text(good)
    out = tmp_path / 'qc/report.json'
    report.check(d, [{'subject': '998S9999', 'session': '20000101'}], out)
    value = json.loads(out.read_text())
    assert value['cases'][0]['report_sha256'] == report.sha(f)
    assert f.read_text() == good
    with pytest.raises(ValueError, match='overwrite'):
        report.check(d, [{'subject': '998S9999', 'session': '20000101'}], out)
