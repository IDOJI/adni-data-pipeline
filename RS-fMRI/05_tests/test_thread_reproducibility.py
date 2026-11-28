"""Meaningful numerical, identity, scheduling and reporting failures for S13."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

import nibabel as nib
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "pipeline/s13_reproducibility"


def load(name):
    sys.path.insert(0, str(STAGE))
    spec = importlib.util.spec_from_file_location("test_threads_" + name, STAGE / (name + ".py"))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


cmp = load("compare")
runner = load("run")
execution = load("execute")
priority = load("priority")


def test_priority_capacity_preserves_five_and_checks_memory():
    active = {f"ADNI999S{i:04d}": 4000 for i in range(5)}
    assert priority.capacity_reasons("ADNI999S9999", active, 4000, 24 * 2**30)
    active.pop("ADNI999S0004")
    assert priority.capacity_reasons("ADNI999S9999", active, 4000, 24 * 2**30) == []
    assert priority.capacity_reasons("ADNI999S9999", active, 16000, 24 * 2**30)
    assert priority.capacity_reasons("ADNI999S0000", active, 4000, 24 * 2**30)
    with pytest.raises(ValueError, match="five"):
        priority.capacity_reasons("ADNI999S9999", {}, 4000, 24 * 2**30, limit=6)


def test_priority_memory_uses_workflow_declaration_and_never_underestimates_default():
    assert priority.observed_memory_mb({"Config": {"Cmd": ["--mem-mb", "8000"]}}) == 8000
    assert priority.observed_memory_mb({"Config": {"Cmd": ["--mem-gb", "8"]}}) == 8000
    assert priority.observed_memory_mb({"Config": {"Cmd": ["--mem-mb", "1"]}}) == 4000
    assert priority.observed_memory_mb({"Config": {"Cmd": ["--mem-mb", "NaN"]}}) == 4000


def test_priority_gate_blocks_new_admissions_and_releases_on_failure(tmp_path):
    import fcntl
    from types import SimpleNamespace
    directory = tmp_path / "compute_slots"
    directory.mkdir()
    holder = {"gate_held": False}
    slots = SimpleNamespace(HERE=tmp_path)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with priority.admission_priority(slots, holder):
            assert holder["gate_held"]
            with (directory / "admission.lock").open("a") as another_controller:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(another_controller, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raise RuntimeError("synthetic failure")
    assert not holder["gate_held"]
    with (directory / "admission.lock").open("a") as another_controller:
        fcntl.flock(another_controller, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_priority_holds_for_unaccounted_docker_container(monkeypatch, tmp_path):
    from types import SimpleNamespace
    slots = SimpleNamespace(HERE=tmp_path, running_subjects=lambda: set(), live_reservations=lambda path: set())
    def docker(argv, **kwargs):
        return "unmanaged\n" if argv[1] == "ps" else json.dumps([{"Name": "/other-work"}])
    monkeypatch.setattr(priority.subprocess, "check_output", docker)
    with pytest.raises(ValueError, match="Unaccounted"):
        priority.active_subjects(slots)


def test_priority_admission_does_not_wait_for_pending_queue_and_releases_subject(tmp_path, monkeypatch):
    import fcntl
    from types import SimpleNamespace
    shared = tmp_path / "continuous5"
    directory = shared / "compute_slots"
    directory.mkdir(parents=True)
    cmp.save(shared / "settings.json", {"global_compute_limit": 5})
    pending = tmp_path / "production-status.json"
    cmp.save(pending, {"subjects": {"synthetic": {"status": "pending"}}})
    before = pending.read_bytes()
    plan = {"shared_compute_root": str(tmp_path), "production_status_files": [str(pending)],
            "workflow_memory_mb": 4000, "min_free_gib": 1}
    slots = SimpleNamespace(HERE=shared, configure=lambda root: None)
    base = SimpleNamespace(module=lambda rel: slots, report=lambda *a: None, verified_plan=lambda root: plan,
                           read=cmp.read, save=cmp.save, now=lambda: "synthetic", shutil=shutil)
    _, _, holder = priority.install(base, tmp_path)
    assert base.idle_reasons(plan) == []
    adapter = base.module("04_workflow/compute_slots.py")
    with pytest.raises(ValueError, match="gate"):
        with adapter.lease("ADNI999S9999", "reproducibility"):
            pass
    snapshots = [None, {f"ADNI999S{i:04d}": 4000 for i in range(5)},
                 {f"ADNI999S{i:04d}": 4000 for i in range(4)}]
    def observed(slots):
        item = snapshots.pop(0)
        if item is None:
            raise priority.subprocess.TimeoutExpired(["docker", "ps"], 25)
        return item
    monkeypatch.setattr(priority, "active_subjects", observed)
    monkeypatch.setattr(priority.subprocess, "check_output", lambda *a, **k: json.dumps({"MemTotal": 24 * 2**30}))
    monkeypatch.setattr(priority.time, "sleep", lambda seconds: None)
    holder["gate_held"] = True
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with adapter.lease("ADNI999S9999", "reproducibility"):
            with (directory / "ADNI999S9999.lock").open() as probe:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raise RuntimeError("synthetic failure")
    with (directory / "ADNI999S9999.lock").open() as probe:
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not snapshots and pending.read_bytes() == before
    assert cmp.read(tmp_path / "status.json")["pending_production_queue_is_not_a_blocker"] is True


def test_priority_separates_numerical_pass_from_contended_timing(tmp_path):
    from types import SimpleNamespace
    refs = [fixture(tmp_path / "trials" / f"synthetic-t01-r{i:02d}", i) for i in range(1, 4)]
    trials = [fixture(tmp_path / "trials" / f"synthetic-t04-r{i:02d}", i + 3, threads=4, seconds=50) for i in range(1, 3)]
    record = cmp.read(trials[0] / "trial.json")
    record["isolated"] = False
    cmp.save(trials[0] / "trial.json", record)
    cmp.save(tmp_path / "policies/synthetic.json", cmp.calibrate(refs))
    shared = tmp_path / "continuous5"
    shared.mkdir()
    plan = {"cases": [{"id": "synthetic"}], "threads": [1, 4], "reference_repeats": 3,
            "candidate_repeats": 2, "shared_compute_root": str(tmp_path)}
    base = SimpleNamespace(module=lambda rel: SimpleNamespace(configure=lambda root: None, HERE=shared),
                           report=runner.report, verified_plan=lambda root: plan, trial_paths=runner.trial_paths,
                           read=cmp.read, save=cmp.save, itertools=runner.itertools)
    priority.install(base, tmp_path)
    result = base.report(tmp_path, plan)
    row = next(r for r in result["cases"] if r["threads"] == 4)
    assert row["technical_status"] == "PASS"
    assert row["speedup"] is None and row["observed_speedup_uncontrolled"] == 2
    assert result["highest_tested_passing_threads"] == 4
    assert result["fastest_tested_passing_threads"] is None


def nifti(path, data, affine=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = nib.Nifti1Image(np.asarray(data, dtype=np.float32), np.eye(4) if affine is None else affine)
    image.header.set_xyzt_units("mm", "sec")
    nib.save(image, path)


def fixture(root, index=0, delta=0, threads=1, seconds=100):
    """Synthetic completion evidence; never presented as an imaging run."""
    a = "preprocess/derivatives/fmriprep/sub-synthetic/ses-01/func/sub-synthetic_ses-01_task-rest_desc-preproc_bold.nii.gz"
    b = "postprocess/derivatives/sub-synthetic/ses-01/func/"
    nifti(root / a, np.ones((2, 2, 2, 4)) * (1 + delta))
    nifti(root / b / "sub-synthetic_desc-denoised_bold.nii.gz", np.ones((2, 2, 2, 4)) * (2 + delta))
    for suffix, text in {
        "_timeseries.tsv": "roi1\troi2\n1\t2\n2\t4\n3\t6\n4\t8\n",
        "_relmat.tsv": "\troi1\troi2\nroi1\t1\t0.5\nroi2\t0.5\t1\n",
        "_outliers.tsv": "framewise_displacement\tdenoising\n0\t0\n0\t0\n0\t0\n0\t0\n",
        "_desc-linc_qc.tsv": "num_retained_volumes\tmean_fd\n4\t0.1\n",
    }.items():
        (root / b / ("sub-synthetic" + suffix)).write_text(text)
    identity = {"case": "synthetic", "images": "synthetic-only", "seed": 1123, "cpu_budget": 8}
    record = {"trial_id": "independent-synthetic-" + str(index), "threads": threads, "status": "success", "input_unchanged": True,
              "analysis_identity": identity, "isolated": True,
              "executions": {s: {"exit_code": 0, "actual_started_at": "synthetic-fixture", "wall_seconds": seconds} for s in ("fmriprep", "xcpd")}}
    record["products_sha256"] = {rel: cmp.sha(root / rel) for rel in cmp.inventory(root)}
    cmp.save(root / "trial.json", record)
    return root


def reseal(root):
    record = cmp.read(root / "trial.json")
    record["products_sha256"] = {rel: cmp.sha(root / rel) for rel in cmp.inventory(root)}
    cmp.save(root / "trial.json", record)


def test_empirical_policy_accepts_small_and_rejects_large_candidate(tmp_path):
    refs = [fixture(tmp_path / str(i), i, i * 1e-7) for i in range(3)]
    policy = cmp.calibrate(refs)
    close = fixture(tmp_path / "close", 3, 2e-7, threads=4)
    far = fixture(tmp_path / "far", 4, .02, threads=4)
    assert cmp.evaluate(cmp.compare(refs[0], close), policy)["technical_status"] == "PASS"
    assert cmp.evaluate(cmp.compare(refs[0], far), policy)["technical_status"] == "FAIL"
    assert cmp.evaluate(cmp.compare(refs[0], close), policy)["scientific_equivalence"] == "not_established"


def test_frozen_policy_and_independent_reference_receipts(tmp_path):
    refs = [fixture(tmp_path / str(i), i) for i in range(3)]
    with pytest.raises(ValueError, match="three"):
        cmp.calibrate(refs[:2])
    with pytest.raises(ValueError, match="distinct"):
        cmp.calibrate([refs[0]] * 3)
    policy = cmp.calibrate(refs)
    result = cmp.compare(refs[0], refs[1])
    policy["multiplier"] = 100
    with pytest.raises(ValueError, match="policy changed"):
        cmp.evaluate(result, policy)
    policy = cmp.calibrate(refs)
    record = cmp.read(refs[0] / "trial.json")
    record["trial_id"] = "modified"
    cmp.save(refs[0] / "trial.json", record)
    with pytest.raises(ValueError, match="reference receipt changed"):
        cmp.evaluate(result, policy)
    shutil.copyfile(refs[1] / "trial.json", refs[0] / "trial.json")
    with pytest.raises(ValueError, match="independent"):
        cmp.calibrate(refs)


def test_censor_changes_and_same_count_different_frames_are_hard_failures(tmp_path):
    a = tmp_path / "a_outliers.tsv"
    b = tmp_path / "b_outliers.tsv"
    a.write_text("framewise_displacement\tdenoising\n1\t1\n0\t0\n")
    b.write_text("framewise_displacement\tdenoising\n0\t0\n1\t1\n")
    with pytest.raises(ValueError, match="Discrete"):
        cmp.compare_table(a, b)


def test_geometry_missingness_and_surface_topology(tmp_path):
    a, b = tmp_path / "a.nii.gz", tmp_path / "b.nii.gz"
    nifti(a, np.ones((2, 2, 2)))
    grid = np.eye(4)
    grid[0, 3] = .1
    nifti(b, np.ones((2, 2, 2)), grid)
    with pytest.raises(ValueError, match="grid"):
        cmp.compare_product(a, b)
    with pytest.raises(ValueError, match="NaN"):
        cmp.measure([np.nan, 1], [1, np.nan])
    a, b = tmp_path / "a.surf.gii", tmp_path / "b.surf.gii"
    def surface(path, triangles):
        arrays = [nib.gifti.GiftiDataArray(np.zeros((3, 3), dtype=np.float32), intent="NIFTI_INTENT_POINTSET"),
                  nib.gifti.GiftiDataArray(np.asarray(triangles, dtype=np.int32), intent="NIFTI_INTENT_TRIANGLE")]
        nib.save(nib.gifti.GiftiImage(darrays=arrays), path)
    surface(a, [[0, 1, 2]])
    surface(b, [[0, 1, 2]])
    assert cmp.compare_product(a, b)["1"]["disagreement"] == 0
    surface(b, [[0, 2, 1]])
    with pytest.raises(ValueError, match="topology"):
        cmp.compare_product(a, b)


def test_cifti_axis_changes_rejected_even_with_identical_values(tmp_path):
    a, b = tmp_path / "a.dtseries.nii", tmp_path / "b.dtseries.nii"
    from nibabel.cifti2.cifti2_axes import BrainModelAxis, SeriesAxis
    brain = BrainModelAxis.from_mask(np.ones((2, 2, 2), dtype=bool), affine=np.eye(4))
    for path, step in ((a, 2), (b, 3)):
        header = nib.Cifti2Header.from_axes((SeriesAxis(0, step, 4), brain))
        nib.save(nib.Cifti2Image(np.ones((4, 8), dtype=np.float32), header), path)
    with pytest.raises(ValueError, match="CIFTI"):
        cmp.compare_product(a, b)


def test_connectivity_compares_off_diagonal_values_and_preserves_labels(tmp_path):
    a, b = tmp_path / "a_relmat.tsv", tmp_path / "b_relmat.tsv"
    a.write_text("\tr1\tr2\nr1\t1\t0.2\nr2\t0.2\t1\n")
    b.write_text("\tr1\tr2\nr1\t1\t0.3\nr2\t0.3\t1\n")
    assert cmp.compare_table(a, b)["upper_triangle"]["max_abs"] == pytest.approx(.1)
    b.write_text("\tr2\tr1\nr2\t1\t0.2\nr1\t0.2\t1\n")
    with pytest.raises(ValueError, match="labels"):
        cmp.compare_table(a, b)


def test_missing_modified_incomplete_or_wrong_analysis_never_passes(tmp_path):
    a, b = fixture(tmp_path / "a", 0), fixture(tmp_path / "b", 1)
    record = cmp.read(b / "trial.json")
    record["analysis_identity"]["seed"] = 99
    cmp.save(b / "trial.json", record)
    with pytest.raises(ValueError, match="settings"):
        cmp.compare(a, b)
    record["status"] = "running"
    cmp.save(b / "trial.json", record)
    with pytest.raises(ValueError, match="successful"):
        cmp.completed(b)
    record["status"] = "success"
    cmp.save(b / "trial.json", record)
    next((b / "postprocess").rglob("*_timeseries.tsv")).write_text("changed\n1\n")
    with pytest.raises(ValueError, match="changed after"):
        cmp.completed(b)


def test_unstable_reference_frame_selection_does_not_widen_tolerance(tmp_path):
    refs = [fixture(tmp_path / str(i), i) for i in range(3)]
    censor = next(refs[1].rglob("*_outliers.tsv"))
    censor.write_text(censor.read_text().replace("0\t0", "1\t1", 1))
    reseal(refs[1])
    with pytest.raises(ValueError, match="unstable"):
        cmp.calibrate(refs)


def test_thread_adapter_keeps_science_and_seed_and_does_not_change_production():
    argv = ["docker", "run", "--rm", "--name", "old", "--env", "OMP_NUM_THREADS=1", "--env", "OPENBLAS_NUM_THREADS=99",
            "image@sha256:synthetic", "/data", "/out", "participant", "--random-seed", "1123", "--omp-nthreads", "1", "--nprocs", "8", "--force", "syn-sdc"]
    original = list(argv)
    result = execution.numerical_command(argv, 4, "new", "experiment")
    assert argv == original
    assert result[result.index("--omp-nthreads") + 1] == "4"
    assert result[result.index("--nprocs") + 1] == "8"
    assert "OMP_NUM_THREADS=4" in result and "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=4" in result
    assert "OPENBLAS_NUM_THREADS=1" in result and "OPENBLAS_NUM_THREADS=99" not in result
    assert result[-2:] == ["--force", "syn-sdc"]
    assert result[result.index("--random-seed") + 1] == "1123"
    production = execution.module("04_workflow/seed_policy.py")
    with pytest.raises(ValueError, match="requires omp_nthreads: 1"):
        production.require({"seed_policy": "fixed-seed-v1", "random_seed": 1123, "resources": {"omp_nthreads": 4}})


def test_actual_application_threads_and_production_quota_namespace(tmp_path):
    toml = tmp_path / "log/fmriprep.toml"
    toml.parent.mkdir()
    toml.write_text("[nipype]\nnprocs = 8\nomp_nthreads = 4\n")
    result = execution.verify_application_threads(tmp_path, "fmriprep.toml", 4, 8)
    assert result["omp_nthreads"] == 4
    with pytest.raises(ValueError, match="Actual application"):
        execution.verify_application_threads(tmp_path, "fmriprep.toml", 1, 8)
    budget = execution.module("04_workflow/cpu_budget.py")
    assert not budget.NAMES.match("adni-repro-fmriprep-ADNI999S9999-case-t04-r01")
    assert not budget.NAMES.match("adni-repro-xcpd-ADNI999S9999-case-t04-r01")


def test_idle_gate_respects_pending_queue_and_unknown_status(tmp_path, monkeypatch):
    status = tmp_path / "production.json"
    cmp.save(status, {"subjects": {"synthetic": {"status": "pending"}}, "active_subjects": []})
    monkeypatch.setattr(runner, "docker_names", lambda: [])
    plan = {"production_status_files": [str(status)], "shared_compute_root": str(tmp_path)}
    assert any("pending" in r for r in runner.idle_reasons(plan))
    cmp.save(status, {"subjects": {"synthetic": {"status": "completed_QC_pending"}}, "active_subjects": []})
    assert runner.idle_reasons(plan) == []
    monkeypatch.setattr(runner, "docker_names", lambda: ["existing-fmriprep"])
    assert any("existing-fmriprep" in r for r in runner.idle_reasons(plan))
    status.unlink()
    assert any("unavailable" in r for r in runner.idle_reasons(plan))


def test_configuration_rejects_oversubscription_and_unreviewed_margins():
    cfg = cmp.read(ROOT / "03_config/thread_reproducibility.example.json")
    assert runner.validate_config(cfg)
    cfg["threads"] = [1, 16]
    with pytest.raises(ValueError, match="CPU budget"):
        runner.validate_config(cfg)
    cfg["threads"] = [1, 4]
    cfg["scientific_margins"] = {"fake_universal_limit": .01}
    with pytest.raises(ValueError, match="separately reviewed"):
        runner.validate_config(cfg)


def test_report_selects_only_measured_passing_and_unconfounded_candidates(tmp_path):
    case = {"id": "synthetic"}
    plan = {"cases": [case], "threads": [1, 2, 4, 8], "reference_repeats": 3, "candidate_repeats": 2}
    refs = [fixture(p, i, seconds=100) for i, p in enumerate(runner.trial_paths(tmp_path, plan, case, 1))]
    cmp.save(tmp_path / "policies/synthetic.json", cmp.calibrate(refs))
    for t, seconds, delta in ((2, 60, 0), (4, 40, .1)):
        for i, p in enumerate(runner.trial_paths(tmp_path, plan, case, t)):
            fixture(p, 10 * t + i, delta=delta, threads=t, seconds=seconds)
    result = runner.report(tmp_path, plan)
    assert result["highest_tested_passing_threads"] == 2
    assert result["fastest_tested_passing_threads"] == 2
    assert next(r for r in result["cases"] if r["threads"] == 8)["status"] == "PENDING"
    assert result["scientific_equivalence"] == "not_established"
    for p in runner.trial_paths(tmp_path, plan, case, 2):
        r = cmp.read(p / "trial.json")
        r["isolated"] = False
        cmp.save(p / "trial.json", r)
    result = runner.report(tmp_path, plan)
    assert result["highest_tested_passing_threads"] is None


def test_dry_run_cannot_start_imaging(tmp_path, monkeypatch):
    cfg = cmp.read(ROOT / "03_config/thread_reproducibility.example.json")
    monkeypatch.setattr(runner, "verified_plan", lambda root: cfg)
    monkeypatch.setattr(runner, "idle_reasons", lambda plan: ["existing production"])
    monkeypatch.setattr(runner, "run_trial", lambda *a: pytest.fail("Dry run started imaging"))
    result = runner.run(tmp_path)
    assert result["imaging_started"] is False and result["status"] == "plan_only"


def test_missing_or_changed_volume_never_creates_shadow_output(tmp_path):
    root = tmp_path / "volume"
    root.mkdir()
    cmp.protect(root, root.stat().st_dev + 1)
    with pytest.raises(RuntimeError, match="shadow"):
        cmp.save(root / "unexpected/results.json", {})
    assert not (root / "unexpected").exists()
    cmp.protect(root, root.stat().st_dev)
    root.rmdir()
    with pytest.raises(RuntimeError, match="shadow"):
        cmp.save(root / "unexpected/results.json", {})
    assert not root.exists()
