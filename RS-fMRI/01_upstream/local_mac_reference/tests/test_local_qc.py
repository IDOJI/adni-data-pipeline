import importlib.util
import json
from pathlib import Path
import sys

import nibabel as nib
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
spec = importlib.util.spec_from_file_location("statmind_local_qc", Path(__file__).parents[1] / "qc.py")
qc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qc)


@pytest.mark.parametrize("name,expected", [("sub-998S9999", "998"), ("sub-ADNI999S99999", "999"), ("999S99999", "999")])
def test_site_mapping_preserves_synthetic_site(name, expected):
    assert qc.site_code(name) == expected


def test_site_mapping_rejects_unknown_id():
    with pytest.raises(ValueError, match="Cannot derive"):
        qc.site_code("sub-unknown")


def test_euler_parser_uses_final_characteristic_not_vertices_or_holes():
    line = "euler # = v-e+f = 2g-2: 163842 - 491658 + 327680 = -136 --> 69 holes\ntotal defect index = 70"
    assert qc.parse_euler_output(line) == -136
    assert qc.parse_euler_output("Euler number = -10") == -10
    with pytest.raises(ValueError, match="not found"):
        qc.parse_euler_output("license file not found")


def cifti_file(tmp_path, nonfinite=False):
    axis = nib.cifti2.BrainModelAxis
    left = axis.from_surface(np.arange(32000), 32492, name="CortexLeft")
    right = axis.from_surface(np.arange(32000), 32492, name="CortexRight")
    mask = np.zeros(33 ** 3, dtype=bool)
    mask[:27282] = True
    volume = axis.from_mask(mask.reshape((33, 33, 33)), affine=np.diag([2., 2., 2., 1.]), name="CerebellumLeft")
    brain = left + right + volume
    time = nib.cifti2.SeriesAxis(start=0, step=0.607, size=3)
    data = np.ones((3, 91282), dtype=np.float32)
    if nonfinite:
        data[1, 2] = np.nan
    image = nib.Cifti2Image(data, nib.Cifti2Header.from_axes((time, brain)))
    path = tmp_path / "SYNTHETIC.dtseries.nii"
    nib.save(image, path)
    return path


def test_cifti_checks_actual_axes_tr_values_and_constant_signal(tmp_path):
    report = qc.check_cifti(cifti_file(tmp_path), 3, 0.607)
    assert report["shape"] == [3, 91282]
    assert report["nonfinite_values"] == 0
    assert report["constant_grayordinates"] == 91282
    assert report["time_axis_unit"] == "SECOND"


def test_cifti_tr_mismatch_fails(tmp_path):
    with pytest.raises(ValueError, match="shape/TR mismatch"):
        qc.check_cifti(cifti_file(tmp_path), 3, 1.5)


def test_cifti_nonfinite_signal_fails(tmp_path):
    with pytest.raises(ValueError, match="Nonfinite CIFTI"):
        qc.check_cifti(cifti_file(tmp_path, True), 3, 0.607)


def test_latest_failed_attempt_is_not_replaced_by_old_pass(tmp_path):
    cfg = {"runtime": str(tmp_path)}
    case = {"subject": "998S9999", "session": "20000101"}
    for prefix, status in [("20260101", "execution_completed_QC_required"), ("20260102", "failed")]:
        path = tmp_path / "logs" / f"{prefix}_fmriprep_sub-998S9999_ses-20000101/run.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"status": status, "exit_code": 0 if status != "failed" else 1}))
    with pytest.raises(ValueError, match="Latest selected execution"):
        qc.latest_run(cfg, case, "fmriprep")


def test_collect_real_format_iqms_does_not_fit_pilot_outliers(tmp_path, monkeypatch):
    case = {"subject": "999S99999", "session": "20000102", "phase": "ADNI4"}
    cfg = {"runtime": str(tmp_path), "runs": [case]}
    record_path = tmp_path / "logs/fixture/run.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text("{}")
    monkeypatch.setattr(qc, "latest_run", lambda *a: (record_path, {"image": {"resolved": "fixture"}, "profile": "technical-extension"}))
    output = tmp_path / "derivatives/mriqc"
    prefix = "sub-999S99999_ses-20000102"
    for suffix, directory, metrics in [("T1w", "anat", qc.T1_METRICS), ("bold", "func", qc.BOLD_METRICS)]:
        path = output / "sub-999S99999/ses-20000102" / directory / f"{prefix}_{suffix}.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({m: 1.0 for m in metrics}))
        (output / f"{prefix}_{suffix}.html").write_text("<html>" + "fixture " * 200 + "</html>")
    qc.collect_mriqc(cfg)
    result = json.loads((tmp_path / "results/mriqc/IQM_validation.json").read_text())
    assert len(result["checks"]) == 2
    assert result["cohort_outlier_fit"] == "not_estimated_from_two_pilot_visits"
    table = pd.read_csv(tmp_path / "results/mriqc/group_T1w_full.tsv", sep="\t")
    assert "cnr_T1w" in table
    assert table.iloc[0]["participant_id"] == "sub-999S99999"
