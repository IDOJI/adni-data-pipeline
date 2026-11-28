#!/usr/bin/env python3
"""Plan, run and assess isolated tolerance-based numerical-thread experiments."""
from __future__ import annotations

import argparse
import copy
import fcntl
import html
import itertools
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
import uuid

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import calibrate, compare, completed, digest, evaluate, protect, read, save, sha
from execute import LAB, checked_copy, check_tree, docker_names, images, module, now, run_trial, tree_hashes


def validate_config(cfg):
    if cfg.get("schema") != 1:
        raise ValueError("Unsupported experiment schema")
    cpus = cfg.get("workflow_cpus")
    threads = cfg.get("threads")
    if type(cpus) is not int or cpus < 1 or not isinstance(threads, list) or not threads or threads[0] != 1:
        raise ValueError("Declare fixed workflow_cpus and thread candidates starting at one")
    if len(set(threads)) != len(threads) or any(type(t) is not int or not 1 <= t <= cpus for t in threads):
        raise ValueError("Threads must be unique integers within the fixed CPU budget")
    if sorted(threads) != threads or len(threads) < 2:
        raise ValueError("Declare increasing reference and candidate thread counts")
    if type(cfg.get("reference_repeats")) is not int or cfg["reference_repeats"] < 3 or type(cfg.get("candidate_repeats")) is not int or cfg["candidate_repeats"] < 2:
        raise ValueError("Require at least three reference and two candidate repetitions")
    if type(cfg.get("random_seed")) is not int or not 0 <= cfg["random_seed"] < 2**32:
        raise ValueError("Invalid fixed random seed")
    for key in ("workflow_memory_mb", "min_free_gib"):
        if not isinstance(cfg.get(key), (int, float)) or not math.isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError("Declare a finite positive " + key)
    if not re.fullmatch(r"[1-9][0-9]*g", str(cfg.get("docker_memory"))):
        raise ValueError("docker_memory must be an integer GiB ceiling such as 20g")
    if cfg["workflow_memory_mb"] * 10**6 >= int(cfg["docker_memory"][:-1]) * 2**30:
        raise ValueError("Workflow memory must fit below the Docker hard ceiling")
    cases = cfg.get("cases")
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Declare distinct representative cases")
    for case in cases:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]) or case.get("profile") not in ("strict", "technical-extension"):
            raise ValueError("Invalid case identifier or intake profile")
    if not cfg.get("production_status_files") or not cfg.get("shared_compute_root"):
        raise ValueError("Declare production queues and the existing shared compute root")
    if type(cfg.get("prune_owned_work", False)) is not bool:
        raise ValueError("prune_owned_work must be a boolean")
    if cfg.get("scientific_margins") is not None:
        raise ValueError("This version reports technical repeatability only; scientific margins require a separately reviewed endpoint policy")
    return cfg


def source_files():
    candidates = []
    for folder in (LAB / "04_workflow", LAB / "pipeline"):
        candidates.extend(p for p in folder.rglob("*.py") if "01_sources" not in p.parts and "__pycache__" not in p.parts)
    # The executable ANTs wrapper is intentionally extensionless.
    candidates.append(LAB / "pipeline/s7c_ants_iteration_logging/antsRegistration")
    return {str(p.relative_to(LAB)): sha(p) for p in sorted(candidates)}


def external_root(value):
    root = Path(value).expanduser().resolve()
    if not root.is_absolute() or root == Path("/") or root.is_relative_to(LAB.parent) or LAB.parent.is_relative_to(root):
        raise ValueError("Use a new external experiment root, disjoint from the source checkout")
    return root


def initialize(config_file):
    cfg = validate_config(read(config_file))
    root = external_root(cfg["root"])
    if root.exists():
        raise FileExistsError("Existing results are preserved; choose a new experiment root")
    host = json.loads(subprocess.check_output(["docker", "info", "--format", "{{json .}}"], text=True, timeout=30))
    memory = int(cfg["docker_memory"][:-1]) * 2**30
    if cfg["workflow_cpus"] > host["NCPU"] or memory > host["MemTotal"] - 2**30:
        raise ValueError("Requested CPU or memory budget exceeds Docker capacity with a 1 GiB reserve")
    source_configs = []
    for case in cfg["cases"]:
        base = yaml.safe_load(Path(case["config"]).read_text())
        completion = read(case["completion_receipt"])
        if completion.get("exit_code") != 0 or completion.get("input_unchanged") is not True or completion.get("stage") != "fmriprep":
            raise ValueError("Representative source needs an actual successful input-preserving fMRIPrep receipt")
        if len(base.get("runs", [])) != 1 or completion.get("case") != base["runs"][0]:
            raise ValueError("Source configuration and completion receipt select different visits")
        if base.get("random_seed") != cfg["random_seed"]:
            raise ValueError("Keep the original source random seed")
        # Prevent accidental roots inside any original runtime, inputs or cache.
        for key in ("runtime", "source_bids", "source_templateflow"):
            old = Path(base[key]).resolve()
            if root.is_relative_to(old) or old.is_relative_to(root):
                raise ValueError("Experiment overlaps an original source/runtime/cache")
        source_configs.append(base)
    xcfg = read(cfg["xcpd_config"])
    if xcfg.get("random_seed") != cfg["random_seed"] or xcfg.get("combine_runs") or xcfg.get("file_format") not in ("nifti", "cifti"):
        raise ValueError("Keep the source XCP-D seed, independent runs and declared file format")
    if not xcfg.get("linc_qc"):
        raise ValueError("S10 LINC output validation is required")
    pinned = images({"fmriprep": source_configs[0]["images"]["fmriprep"], "xcpd": xcfg["image"]})
    for base in source_configs[1:]:
        if images({"fmriprep": base["images"]["fmriprep"]})["fmriprep"] != pinned["fmriprep"]:
            raise ValueError("Representative cases must use the same fMRIPrep image")
    shared_settings = Path(cfg["shared_compute_root"]) / "continuous5/settings.json"
    settings = read(shared_settings)
    if int(settings.get("global_compute_limit", settings.get("target_concurrency", 0))) != 5:
        raise ValueError("Keep the authorized shared five-subject limit")
    plan = copy.deepcopy(cfg)
    plan.update(experiment_id=uuid.uuid4().hex[:12], created_at=now(), source_hashes=source_files(), images=pinned,
                host={"docker_cpus": host["NCPU"], "docker_memory": host["MemTotal"], "architecture": host["Architecture"],
                      "docker_version": host["ServerVersion"], "system": platform.platform()},
                LLM_calls=0, scope="Technical repeatability of the declared cases and OMP/ITK settings; BLAS remains one")
    plan["xcpd_settings"] = {k: v for k, v in xcfg.items() if k not in ("root", "repo", "run_id", "license", "templateflow", "resources", "_config_id")}
    root.mkdir(parents=True)
    plan["runtime_device"] = root.stat().st_dev
    protect(root, plan["runtime_device"])
    shutil.copytree(source_configs[0]["source_templateflow"], root / "templateflow", symlinks=False)
    plan["templateflow_hashes"] = tree_hashes(root / "templateflow")
    for case, base in zip(plan["cases"], source_configs):
        inputs = root / "inputs" / case["id"]
        original = Path(base["source_bids"])
        source_manifest = read(base["source_manifest"])
        visit = base["runs"][0]
        prefix = f"sub-{visit['subject']}/ses-{visit['session']}/"
        selected = [entry for entry in source_manifest["files"] if entry["path"].startswith(prefix)]
        if len(selected) != 4:
            raise ValueError("Exact-pair manifest must select four original image/sidecar files")
        for entry in selected:
            relative = Path(entry["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe source manifest path")
            if checked_copy(original / relative, inputs / "bids" / relative) != entry["sha256"]:
                raise ValueError("Original manifest hash mismatch")
        for name in ("dataset_description.json", "participants.tsv", "participants.json", ".bidsignore"):
            if (original / name).is_file():
                checked_copy(original / name, inputs / "bids" / name)
        checked_copy(base["source_phase_evidence"], inputs / "phase.json")
        checked_copy(case["completion_receipt"], inputs / "original_completion_receipt.json")
        save(inputs / "source_manifest.json", {"source": source_manifest.get("source"), "files": selected})
        save(inputs / "preprocessing.json", base)
        case["bids_hashes"] = tree_hashes(inputs / "bids")
        case["subject"] = visit["subject"]
        case["scientific_settings"] = {k: v for k, v in base.items() if k not in ("runtime", "source_bids", "source_manifest", "source_phase_evidence", "source_templateflow", "resources", "seed_policy", "work_revision", "freesurfer_license")}
        case["scientific_settings"]["xcpd"] = plan["xcpd_settings"]
        case["snapshot_hashes"] = {str(p.relative_to(inputs)): sha(p) for p in inputs.rglob("*") if p.is_file()}
    save(root / "plan.json", plan, exclusive=True)
    save(root / "plan.lock.json", {"sha256": sha(root / "plan.json")}, exclusive=True)
    save(root / "status.json", {"status": "prepared_not_executed", "at": now(), "LLM_calls": 0})
    return root


def verified_plan(root):
    root = external_root(root)
    if sha(root / "plan.json") != read(root / "plan.lock.json")["sha256"]:
        raise ValueError("Experiment plan changed after initialization")
    plan = validate_config(read(root / "plan.json"))
    if root.stat().st_dev != plan.get("runtime_device"):
        raise ValueError("Experiment volume identity changed")
    protect(root, plan["runtime_device"])
    for rel, expected in plan["source_hashes"].items():
        if sha(LAB / rel) != expected:
            raise ValueError("Frozen execution source changed: " + rel)
    for case in plan["cases"]:
        inputs = root / "inputs" / case["id"]
        for rel, expected in case["snapshot_hashes"].items():
            if sha(inputs / rel) != expected:
                raise ValueError("Frozen case metadata/input changed: " + rel)
    return plan


def idle_reasons(plan):
    reasons = []
    active = docker_names()
    if active:
        reasons.append("Existing Docker containers: " + ", ".join(active))
    for filename in plan["production_status_files"]:
        try:
            status = read(filename)
        except (OSError, ValueError) as exc:
            reasons.append("Production status unavailable: " + str(exc))
            continue
        subjects = status.get("subjects")
        if not isinstance(subjects, dict) or not subjects:
            reasons.append("Production queue schema unknown: " + filename)
            continue
        unfinished = [key for key, value in subjects.items() if not (value.get("status", "").startswith("held_") or value.get("status") in ("completed_QC_pending", "complete", "completed", "deferred_or_failed"))]
        if unfinished or status.get("active_subjects"):
            reasons.append("Production queue has active/pending work: " + filename)
        if status.get("error"):
            reasons.append("Production queue reports an error: " + filename)
    shared = Path(plan["shared_compute_root"]) / "continuous5/compute_slots"
    if shared.exists():
        # Check existing subject locks without rewriting their contents.
        for path in shared.glob("ADNI*.lock"):
            with path.open("r") as stream:
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(stream, fcntl.LOCK_UN)
                except BlockingIOError:
                    reasons.append("Existing shared compute reservation: " + path.stem)
    return reasons


def trial_paths(root, plan, case, threads):
    repeats = plan["reference_repeats"] if threads == 1 else plan["candidate_repeats"]
    return [Path(root) / "trials" / f"{case['id']}-t{threads:02d}-r{i:02d}" for i in range(1, repeats + 1)]


def report(root, plan):
    rows = []
    for threads in plan["threads"]:
        rows_for_threads = []
        for case in plan["cases"]:
            trials = trial_paths(root, plan, case, threads)
            refs = trial_paths(root, plan, case, 1)
            row = {"case": case["id"], "threads": threads, "status": "PENDING", "speedup": None}
            if all((p / "trial.json").exists() for p in trials + refs):
                records = [read(p / "trial.json") for p in trials]
                if any(r.get("status") == "failed" for r in records):
                    row["status"] = "FAILED_EXECUTION"
                elif all(r.get("status") == "success" for r in records):
                    for path in trials:
                        completed(path)
                    policy_file = Path(root) / "policies" / (case["id"] + ".json")
                    if policy_file.exists():
                        policy = read(policy_file)
                        comparisons = []
                        for left, right in (itertools.combinations(refs, 2) if threads == 1 else itertools.product(refs, trials)):
                            result = compare(left, right)
                            verdict = evaluate(result, policy)
                            comparisons.append(verdict)
                            save(Path(root) / "comparisons" / f"{left.name}--{right.name}.json", {**result, **verdict})
                        row["status"] = "PASS" if comparisons and all(v["technical_status"] == "PASS" for v in comparisons) else "FAIL_TOLERANCE"
                        totals = [sum(r["executions"][s]["wall_seconds"] for s in ("fmriprep", "xcpd")) for r in records]
                        reference_records = [read(p / "trial.json") for p in refs]
                        reference_time = statistics.median(sum(r["executions"][s]["wall_seconds"] for s in ("fmriprep", "xcpd")) for r in reference_records)
                        row.update(median_wall_seconds=statistics.median(totals), speedup=reference_time / statistics.median(totals),
                                   stage_median_seconds={s: statistics.median(r["executions"][s]["wall_seconds"] for r in records) for s in ("fmriprep", "xcpd")},
                                   isolated=all(r.get("isolated") is True for r in records + reference_records))
                        if not row["isolated"]:
                            row["status"] = "CONFOUNDED_LOAD"
            rows.append(row)
            rows_for_threads.append(row)
    passing = [t for t in plan["threads"] if t != 1 and all(r["status"] == "PASS" for r in rows if r["threads"] == t)]
    eligible = [t for t in passing if all(r["speedup"] > 1 for r in rows if r["threads"] == t)]
    result = {"at": now(), "cases": rows, "highest_tested_passing_threads": max(passing, default=None),
              "fastest_tested_passing_threads": max(eligible, key=lambda t: statistics.geometric_mean(r["speedup"] for r in rows if r["threads"] == t), default=None),
              "scientific_equivalence": "not_established", "production_settings_changed": False, "LLM_calls": 0,
              "scope": "Only these inputs, fixed CPU/memory budget, image digests, OMP/ITK controls and BLAS=1; untested thread counts are unknown"}
    save(Path(root) / "report.json", result)
    lines = ["<!doctype html><meta charset='utf-8'><title>Thread reproducibility</title>",
             "<h1>Thread reproducibility experiment</h1><p>Technical tolerance and timing results. Scientific equivalence remains unestablished. Production settings are unchanged.</p>",
             "<table><tr><th>Case</th><th>Threads</th><th>Status</th><th>Median seconds</th><th>Speedup</th></tr>"]
    for row in rows:
        lines.append("<tr>" + "".join("<td>" + html.escape(str(row.get(k, ""))) + "</td>" for k in ("case", "threads", "status", "median_wall_seconds", "speedup")) + "</tr>")
    lines.append("</table><p>Highest tested passing threads: " + str(result["highest_tested_passing_threads"]) + "; fastest tested passing threads: " + str(result["fastest_tested_passing_threads"]) + "</p>")
    (Path(root) / "report.html").write_text("\n".join(lines))
    return result


def run(root, execute=False, wait_idle=False, poll=60):
    root = external_root(root)
    plan = verified_plan(root)
    if not execute:
        return {"status": "plan_only", "threads": plan["threads"], "imaging_started": False,
                "trial_count": len(plan["cases"]) * (plan["reference_repeats"] + (len(plan["threads"]) - 1) * plan["candidate_repeats"]),
                "idle_blockers": idle_reasons(plan)}
    with (root / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        slots = module("04_workflow/compute_slots.py")
        slots.configure(plan["shared_compute_root"])
        try:
            for case in plan["cases"]:
                for threads in plan["threads"]:
                    for i, path in enumerate(trial_paths(root, plan, case, threads), 1):
                        if (path / "trial.json").is_file():
                            completed(path)
                            continue
                        while True:
                            reasons = idle_reasons(plan)
                            if shutil.disk_usage(root).free < plan["min_free_gib"] * 2**30:
                                reasons.append("Experiment volume is below the frozen free-space floor")
                            if not reasons:
                                break
                            save(root / "status.json", {"status": "waiting_for_production_idle", "at": now(), "reasons": reasons, "LLM_calls": 0})
                            if not wait_idle:
                                return read(root / "status.json")
                            time.sleep(poll)
                        verified_plan(root)
                        check_tree(root / "templateflow", plan["templateflow_hashes"])
                        with slots.lease(case["subject"], "reproducibility"):
                            # Recheck queue priority after obtaining a shared subject slot.
                            queue_reasons = [s for s in idle_reasons(plan) if not s.startswith("Existing shared compute reservation: " + case["subject"])]
                            if queue_reasons:
                                raise RuntimeError("Production changed during admission; no benchmark container started")
                            save(root / "status.json", {"status": "running", "at": now(), "case": case["id"], "threads": threads, "repeat": i, "LLM_calls": 0})
                            run_trial(root, plan, case, threads, i)
                    if threads == 1:
                        destination = root / "policies" / (case["id"] + ".json")
                        if not destination.exists():
                            policy = calibrate(trial_paths(root, plan, case, 1), **plan.get("calibration", {}))
                            save(destination, policy, exclusive=True)
                    report(root, plan)
            result = report(root, plan)
            save(root / "status.json", {"status": "completed", "at": now(), "report": str(root / "report.json"), "LLM_calls": 0})
            return result
        except Exception as exc:
            save(root / "status.json", {"status": "held_review_required", "at": now(), "error": f"{type(exc).__name__}: {exc}", "LLM_calls": 0})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init")
    init.add_argument("--config", type=Path, required=True)
    for action in ("run", "report", "status"):
        p = sub.add_parser(action)
        p.add_argument("--root", type=Path, required=True)
        if action == "run":
            p.add_argument("--execute", action="store_true")
            p.add_argument("--wait-idle", action="store_true")
            p.add_argument("--poll", type=int, default=60)
    args = parser.parse_args()
    if args.action == "init":
        result = {"root": str(initialize(args.config)), "status": "prepared_not_executed"}
    elif args.action == "run":
        if args.poll < 15:
            parser.error("Poll interval must be at least 15 seconds")
        result = run(args.root, args.execute, args.wait_idle, args.poll)
    elif args.action == "report":
        result = report(args.root, verified_plan(args.root))
    else:
        result = read(args.root / "status.json")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
