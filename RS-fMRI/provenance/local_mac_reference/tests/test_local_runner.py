import copy
import importlib.util
import json
from pathlib import Path
import types

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location("statmind_local_runner", Path(__file__).parents[1] / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    config = runner.load(Path(runner.__file__).with_name("config.local.yaml"))
    config["runtime"] = str(tmp_path / "new")
    config["source_bids"] = str(tmp_path / "source")
    config["freesurfer_license"] = str(tmp_path / "license.txt")
    root = runner.runtime(config)
    (root / "bids").mkdir(parents=True)
    (root / "bids/dataset_description.json").write_text('{"Name":"fixture"}')
    rows = []
    for case in config["runs"]:
        for p in runner.paths_for(config, case).values():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"synthetic input")
        rows.append({"sub": "sub-" + case["subject"], "ses": "ses-" + case["session"],
                     "strict_upstream_eligible": case["phase"] == "ADNI3"})
    decision = root / "results/step5/intake_decisions.tsv"
    decision.parent.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(decision, sep="\t", index=False)
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    monkeypatch.setattr(runner, "REPO", fake_repo)
    return config


def test_fmriprep_keeps_surfaces_cifti_and_all_requested_spaces(cfg):
    argv, _ = runner.command(cfg, "fmriprep", cfg["runs"][0], "pinned@sha256:abc")
    assert argv.count("--output-spaces") == 1
    start = argv.index("--output-spaces") + 1
    assert argv[start:start + len(cfg["output_spaces"])] == cfg["output_spaces"]
    assert argv[argv.index("--cifti-output") + 1] == "91k"
    assert "--fs-no-reconall" not in argv
    assert "--skip-bids-validation" not in argv
    assert argv[argv.index("--use-syn-sdc") + 1] == "error"
    assert argv[argv.index("--random-seed") + 1] == "357"


def test_docker_bids_mount_read_only_and_resource_limits(cfg):
    argv, _ = runner.command(cfg, "fmriprep", cfg["runs"][0], "image")
    assert f"type=bind,src={runner.runtime(cfg)}/bids,dst=/data,readonly" in argv
    assert argv[argv.index("--memory") + 1] == "18g"
    assert argv[argv.index("--mem-mb") + 1] == "14000"
    assert argv[argv.index("--cpus") + 1] == "6"


def test_mriqc_disables_submission_and_requests_both_modalities(cfg):
    argv, _ = runner.command(cfg, "mriqc", cfg["runs"][0], "image")
    assert "--no-sub" in argv
    start = argv.index("--modalities") + 1
    assert argv[start:start + 2] == ["T1w", "bold"]
    assert "--fs-license-file" not in argv
    assert argv[argv.index("--mem-gb") + 1] == "14"


def test_inputs_are_bound_to_selected_visit(cfg):
    first, second = cfg["runs"]
    a = runner.selected_inputs(cfg, first)
    runner.paths_for(cfg, second)["bold"].write_bytes(b"other visit changed")
    assert runner.selected_inputs(cfg, first) == a
    assert len(a) == 5


def test_verified_copy_refuses_source_hash_mismatch(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"input")
    with pytest.raises(ValueError, match="Source hash mismatch"):
        runner.copy_verified(source, target, "0" * 64)
    assert not target.exists()


def test_verified_copy_refuses_overwrite_and_accepts_identical(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"input")
    runner.copy_verified(source, target)
    runner.copy_verified(source, target)
    target.write_bytes(b"existing work")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        runner.copy_verified(source, target)
    assert target.read_bytes() == b"existing work"


def test_adni4_strict_rejects_before_any_docker_call(cfg, monkeypatch):
    def must_not_run(_):
        pytest.fail("Docker must not run for strict ADNI4")
    monkeypatch.setattr(runner, "image_record", must_not_run)
    with pytest.raises(ValueError, match="fails official intake"):
        runner.run_stage(cfg, "fmriprep", cfg["runs"][1], "strict")
    assert not (runner.runtime(cfg) / "pipeline.lock").exists()


def fake_image(_):
    return {"resolved": "pinned@sha256:abc", "tag": "fake"}


def test_failed_container_records_failure_and_releases_lock(cfg, monkeypatch):
    monkeypatch.setattr(runner, "image_record", fake_image)
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *a, **k: "fixed-commit")
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=7))
    with pytest.raises(RuntimeError, match="Execution failed"):
        runner.run_stage(cfg, "mriqc", cfg["runs"][1], "technical-extension")
    root = runner.runtime(cfg)
    record_path = next((root / "logs").glob("*/run.json"))
    record = json.loads(record_path.read_text())
    assert record["status"] == "failed"
    assert record["exit_code"] == 7
    assert record["input_unchanged"] is True
    assert record["strict_upstream_eligible"] is False
    assert record["profile"] == "technical-extension"
    assert (record_path.parent / "runner_source.py").is_file()
    assert not (root / "pipeline.lock").exists()


def test_unknown_cache_is_rejected_and_kept(cfg, monkeypatch):
    monkeypatch.setattr(runner, "image_record", fake_image)
    _, work = runner.command(cfg, "mriqc", cfg["runs"][0], fake_image(None)["resolved"])
    (work / "unknown-output").write_bytes(b"preserve")
    with pytest.raises(ValueError, match="unknown existing work cache"):
        runner.run_stage(cfg, "mriqc", cfg["runs"][0], "strict")
    assert (work / "unknown-output").read_bytes() == b"preserve"
    assert not (runner.runtime(cfg) / "pipeline.lock").exists()


@pytest.mark.parametrize("relative", [".", "nested/child"])
def test_config_rejects_runtime_source_overlap(cfg, tmp_path, relative):
    import yaml
    cfg = copy.deepcopy(cfg)
    cfg["runtime"] = str(Path(cfg["source_bids"]) / relative)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError, match="must be disjoint"):
        runner.load(path)


def test_config_rejects_shell_metacharacters_in_identity(cfg, tmp_path):
    import yaml
    cfg["runs"][0]["subject"] = "998S9999;echo"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError, match="alphanumeric"):
        runner.load(path)
