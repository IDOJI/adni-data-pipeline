"""Exercise the README handoff without Docker or private input files."""
import json
import sys
from pathlib import Path

import pytest
import yaml

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "04_workflow"))
import manual_pair as manual


@pytest.fixture
def bundle(tmp_path):
    toy = manual.load_backend(LAB / "07_reproducibility/toy.py", "manual_pair_fixture")
    source = tmp_path / "fixture"
    toy.init(source)
    data = tmp_path / "input with spaces"
    data.mkdir()
    (data / "license.txt").write_text("Synthetic test only")
    (data / "templateflow").mkdir()
    names = {"bids": "bids", "candidate-audit.csv": "images.csv",
             "04.epi-analysis-manifest.csv": "04.epi-analysis-manifest.csv",
             "pairing-run-manifest.json": "pairing.json", "hash-evidence.csv": "hashes.csv"}
    for dest, origin in names.items():
        (data / dest).symlink_to(source / "inputs" / origin)
    return data


def test_adni_setup_and_handoff_require_successful_execution(bundle, tmp_path):
    first = tmp_path / "from source evidence"
    manual.prepare_adni(bundle, first, None)
    (bundle / "binding").symlink_to(first / "binding", target_is_directory=True)
    second = tmp_path / "from receipt"
    manual.prepare_adni(bundle, second, None)
    cfg = yaml.safe_load((second / "pair/verified-config.yaml").read_text())
    assert len(cfg["runs"]) == 1
    assert (second / "runs" / cfg["runs"][0]["subject"]).resolve() == Path(cfg["runtime"])
    assert Path(cfg["binding_receipt"]) == first / "binding/07.binding-receipt.json"
    xcp = json.loads((second / "xcpd.json").read_text())
    assert xcp["root"] == str(second) and cfg["random_seed"] == xcp["random_seed"] == 1123
    with pytest.raises(ValueError, match="Complete mriqc"):
        manual.publish(second)
    assert not (second / "results").exists()


def test_bids_setup_preserves_outputs_and_requires_one_session(bundle, tmp_path):
    results = tmp_path / "volume run"
    manual.prepare_volume(bundle, results)
    snapshot = (results / "volume.json").read_bytes()
    cfg = json.loads(snapshot)
    assert len(cfg["runs"]) == 1
    assert Path(cfg["paths"]["bids"]) == (bundle / "bids").resolve()
    with pytest.raises(ValueError, match="new results directory"):
        manual.prepare_volume(bundle, results)
    assert (results / "volume.json").read_bytes() == snapshot
    subject, = (bundle / "bids").glob("sub-*")
    (subject / "ses-Extra").mkdir()
    with pytest.raises(ValueError, match="one-session"):
        manual.prepare_volume(bundle, tmp_path / "ambiguous")
    assert not (tmp_path / "ambiguous").exists()
