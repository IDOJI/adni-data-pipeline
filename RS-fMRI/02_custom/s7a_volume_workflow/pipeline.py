#!/usr/bin/env python3
"""Auditable, shell-free Docker execution for the ADNI rs-fMRI volume protocol."""
from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import uuid

import repair_xcpd_metadata as xcpd_metadata

PATH_KEYS = ("bids", "fmriprep_output", "xcpd_output", "fmriprep_work", "xcpd_work", "templateflow", "logs")
IDENTIFIER = re.compile(r"^[A-Za-z0-9]+$")
# Read once when this runner starts, before a later deployment can replace it.
RUNNER_SOURCE = Path(__file__).resolve().read_bytes()
CACHE_SIGNATURE_NAME = ".adni-cache-signature.json"
RUNNER_VERSION = "1.3.0"


class PipelineError(RuntimeError):
    pass


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_config(path):
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    if config.get("schema_version") != 1:
        raise PipelineError("Expected schema_version 1")
    validate_paths(config)
    runs = config.get("runs", [])
    if not runs or len({(r["subject"], r["session"]) for r in runs}) != len(runs):
        raise PipelineError("runs must contain unique subject/session pairs")
    for run in runs:
        if not all(IDENTIFIER.fullmatch(run[k]) for k in ("subject", "session")):
            raise PipelineError("Subject and session labels must be bare alphanumeric BIDS labels")
    if not IDENTIFIER.fullmatch(config.get("task", "rest")):
        raise PipelineError("Invalid BIDS task label")
    if config.get("cpus", 0) < 1 or config.get("memory_mb", 0) < 1000:
        raise PipelineError("Invalid CPU or memory budget")
    return config


def validate_paths(config):
    paths = {}
    for key in PATH_KEYS:
        path = Path(config["paths"][key]).expanduser()
        if not path.is_absolute() or "," in str(path):
            raise PipelineError(f"{key}: absolute path without commas required for Docker --mount")
        paths[key] = path.resolve()
        repo = Path(__file__).resolve().parents[3]
        if paths[key] == repo or repo in paths[key].parents or paths[key] in repo.parents:
            raise PipelineError("Data and runtime paths must be outside the source repository")
        if paths[key] == Path("/"):
            raise PipelineError("Filesystem root cannot be mounted")
    for i, key in enumerate(PATH_KEYS):
        for other in PATH_KEYS[i + 1:]:
            a, b = paths[key], paths[other]
            if a == b or a in b.parents or b in a.parents:
                raise PipelineError(f"Path collision: {key} and {other}")
    license_path = Path(config["fs_license"]).expanduser()
    if not license_path.is_absolute() or "," in str(license_path):
        raise PipelineError("FreeSurfer license must be an absolute path without commas")
    for key, path in paths.items():
        if key != "bids" and (path == license_path.resolve() or path in license_path.resolve().parents):
            raise PipelineError("License must not be inside a mutable runtime directory")
    return paths


def select_run(config, subject, session=None):
    subject = subject.removeprefix("sub-")
    session = session.removeprefix("ses-") if session else None
    matches = [r for r in config["runs"] if r["subject"] == subject and (session is None or r["session"] == session)]
    if len(matches) != 1:
        raise PipelineError("Subject/session must select exactly one configured run")
    return matches[0]


def configuration_for_run(config, selected):
    """Allow isolated XCP-D datasets/caches for session-dependent configuration hashes."""
    overrides = selected.get("paths", {})
    if not isinstance(overrides, dict) or set(overrides) - {"xcpd_output", "xcpd_work"}:
        raise PipelineError("Run path overrides may only select xcpd_output and xcpd_work")
    result = copy.deepcopy(config)
    result["paths"].update(overrides)
    result["paths"] = {key: str(value) for key, value in validate_paths(result).items()}
    return result, {key: selected[key] for key in ("subject", "session")}


def check_inputs(config, stage, run):
    paths = validate_paths(config)
    root = paths["bids" if stage == "fmriprep" else "fmriprep_output"]
    session_dir = root / f"sub-{run['subject']}" / f"ses-{run['session']}"
    if not session_dir.is_dir():
        raise PipelineError(f"Missing selected session: {session_dir}")
    description = root / "dataset_description.json"
    if not description.is_file():
        raise PipelineError(f"Missing {description}")
    with description.open(encoding="utf-8") as f:
        json.load(f)
    task = config.get("task", "rest")
    if stage == "fmriprep":
        bolds = sorted((session_dir / "func").glob(f"*_task-{task}_*bold.nii*"))
        anatomicals = list((session_dir / "anat").glob("*_T1w.nii*"))
        anatomicals += list((root / f"sub-{run['subject']}" / "anat").glob("*_T1w.nii*"))
        if not bolds or not anatomicals:
            raise PipelineError("Selected session requires a rest BOLD series and a T1w image")
    else:
        bolds = sorted((session_dir / "func").glob(f"*_task-{task}_*space-MNI152NLin2009cAsym*desc-preproc_bold.nii*"))
        if not bolds:
            raise PipelineError("No selected standard-space fMRIPrep BOLD derivative")
    if not Path(config["fs_license"]).is_file():
        raise PipelineError("FreeSurfer license file not found (contents are never logged)")
    return root


def build_command(config, stage, run, image=None):
    paths = validate_paths(config)
    subject, session = run["subject"], run["session"]
    image = image or config["images"][stage]
    input_path = paths["bids" if stage == "fmriprep" else "fmriprep_output"]
    output_path = paths[f"{stage}_output"]
    work_path = paths[f"{stage}_work"] / f"sub-{subject}" / f"ses-{session}"
    mounts = [(input_path, "/input", True), (output_path, "/output", False),
              (work_path, "/work", False), (paths["templateflow"], "/templateflow", False),
              (Path(config["fs_license"]).resolve(), "/license.txt", True)]
    command = ["docker", "run", "--rm", "--pull", "never", "--platform", config["platform"],
               "--cpus", str(config["cpus"]), "--memory", config["docker_memory"],
               "--name", f"adni-{stage}-{subject}-{session}"]
    for source, target, readonly in mounts:
        spec = f"type=bind,src={source},dst={target}" + (",readonly" if readonly else "")
        command += ["--mount", spec]
    command += ["--env", "TEMPLATEFLOW_HOME=/templateflow", image, "/input", "/output", "participant",
                "--participant-label", subject,
                "--session-label" if stage == "fmriprep" else "--session-id", session,
                "--task-id", config.get("task", "rest"),
                "--nprocs", str(config["cpus"]), "--omp-nthreads", str(config["omp_nthreads"]),
                "--mem-mb", str(config["memory_mb"]), "--fs-license-file", "/license.txt",
                "--random-seed", str(config["random_seed"]), "--output-layout", "bids",
                "--notrack", "--stop-on-first-crash", "-w", "/work"]
    if stage == "fmriprep":
        command += ["--subject-anatomical-reference", "sessionwise", "--output-spaces",
                    "MNI152NLin2009cAsym:res-2", "--fs-no-reconall", "--return-all-components",
                    "--use-syn-sdc", "error"]
    else:
        post = config["postprocessing"]
        command += ["--mode", "linc", "--file-format", "nifti", "--input-type", "fmriprep",
                    "--dummy-scans", "auto", "--nuisance-regressors", "acompcor",
                    "--despike", "n", "--smoothing", str(post["smoothing_fwhm_mm"]),
                    "--motion-filter-type", "none", "--head-radius", "50",
                    "--fd-thresh", str(post["fd_threshold_mm"]), "--censor-between", "0",
                    "--min-time", str(post["minimum_retained_seconds"]),
                    "--lower-bpf", str(post["high_pass_hz"]), "--upper-bpf", str(post["low_pass_hz"]),
                    "--bpf-order", "2", "--output-type", "censored", "--combine-runs", "n",
                    "--linc-qc", "y", "--abcc-qc", "n", "--warp-surfaces-native2std", "n",
                    "--skip", "alff", "reho", "parcellation"]
    return command


def resolve_image(image):
    proc = subprocess.run(["docker", "image", "inspect", image], check=True, capture_output=True, text=True)
    data = json.loads(proc.stdout)[0]
    repository = image.split("@")[0].rsplit(":", 1)[0]
    digests = [d for d in data.get("RepoDigests", []) if d.startswith(repository + "@sha256:")]
    if not digests:
        raise PipelineError(f"Image has no immutable repository digest: {image}")
    return {"requested": image, "resolved": sorted(digests)[0], "image_id": data["Id"],
            "architecture": data.get("Architecture"), "os": data.get("Os")}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_input(root, subject):
    """Hash selected participant plus inherited dataset-root metadata; no raw bytes saved."""
    root = root.resolve()
    files = [p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")]
    subject_root = root / f"sub-{subject}"
    for current, dirs, names in os.walk(subject_root, followlinks=False):
        for directory in dirs:
            if (Path(current) / directory).is_symlink():
                raise PipelineError("Stage real input files; directory symlinks are not accepted")
        files.extend(Path(current) / name for name in names if not name.startswith("."))
    result = {}
    for path in sorted(files):
        resolved = path.resolve()
        if root not in resolved.parents:
            raise PipelineError(f"Input symlink escapes its root: {path}")
        before = path.stat()
        digest = sha256(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise PipelineError(f"Input changed while hashing: {path}")
        result[str(path.relative_to(root))] = {"bytes": after.st_size, "sha256": digest}
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cache_signature(stage, command, image, inputs):
    """Identity of the actual stage invocation, not unrelated configuration/code."""
    payload = {"schema_version": 1, "stage": stage, "command": command,
               "image": {k: image.get(k) for k in ("resolved", "image_id", "architecture", "os")},
               "inputs": inputs}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "identity": payload}


def guard_cache(work_path, signature):
    """Refuse unknown or changed cache provenance; never adopt/delete an old cache."""
    work_path.mkdir(parents=True, exist_ok=True)
    signature_path = work_path / CACHE_SIGNATURE_NAME
    recovery = ("Use a new empty work directory (and a new output/runtime root for a changed protocol). "
                "Keep the existing cache; do not delete it or invent/adopt a signature.")
    if signature_path.exists():
        try:
            saved = json.loads(signature_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PipelineError(f"Unreadable cache signature: {signature_path}. {recovery}") from exc
        if saved != signature:
            raise PipelineError(f"Cache identity changed: {signature_path}. {recovery}")
    elif any(work_path.iterdir()):
        raise PipelineError(f"Nonempty work directory has no cache signature: {work_path}. {recovery}")
    else:
        # The global execution lock protects this write. Exclusive creation also
        # prevents accidental replacement if a different runner races us.
        with signature_path.open("x", encoding="utf-8") as f:
            json.dump(signature, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return {"path": str(signature_path), "sha256": signature["sha256"]}


def capture_citations(output_root, run, log_dir):
    """Snapshot available boilerplate per attempt, including failed attempts."""
    output_root = output_root.resolve()
    subject_root = output_root / f"sub-{run['subject']}"
    session_root = subject_root / f"ses-{run['session']}"
    folders = [output_root / "logs"]
    folders += [root / name for root in (subject_root, session_root) for name in ("log", "logs")]
    candidates = sorted({p for folder in folders if folder.is_dir()
                         for p in folder.rglob("CITATION*") if p.is_file()})
    result = []
    for source in candidates:
        if output_root not in source.resolve().parents:
            raise PipelineError(f"Citation symlink escapes derivative root: {source}")
        relative = source.relative_to(output_root)
        destination = log_dir / "citations" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        result.append({"source": str(source), "copied_to": str(destination.relative_to(log_dir)),
                       "bytes": destination.stat().st_size, "sha256": sha256(destination)})
    return result


def acquire_lock(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PipelineError(f"Pipeline lock exists: {path}; verify no container/process is active before manual recovery") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "host": socket.gethostname(), "created": utcnow()}, f)


def xcpd_run_lock(paths, run):
    """Shared by XCP-D execution and finalization, independent of other subjects."""
    return paths["logs"] / f"xcpd_sub-{run['subject']}_ses-{run['session']}.lock"


def capture_sources(log_dir, record, runner_source, repair_source=None):
    (log_dir / "runner_source.py").write_bytes(runner_source)
    record.update({"runner_sha256": hashlib.sha256(runner_source).hexdigest(),
                   "runner_source": "runner_source.py", "runner_version": RUNNER_VERSION})
    if repair_source is not None:
        (log_dir / "repair_xcpd_metadata_source.py").write_bytes(repair_source)
        record["metadata_repair_source"] = {
            "path": "repair_xcpd_metadata_source.py",
            "sha256": hashlib.sha256(repair_source).hexdigest(),
            "version": xcpd_metadata.VERSION}


def apply_xcpd_metadata_repair(paths, run, record, log_dir, repair_function):
    """Persist the hook boundary even when repair raises after Docker succeeds."""
    record["status"] = "finalizing_metadata"
    result = record["metadata_repair"] = {"status": "running", "started_at": utcnow()}
    record_path = log_dir / ("finalization.json" if record.get("command") == "finalize-xcpd" else "run.json")
    write_json(record_path, record)
    try:
        repaired = repair_function(paths["xcpd_output"], run["subject"], run["session"],
                                   paths["logs"] / "metadata_repairs", apply=True)
        result["result"] = repaired
        if repaired.get("status") not in ("applied", "already_valid_no_op"):
            raise PipelineError("Metadata repair did not confirm applied or already-valid output")
        result["status"] = "completed"
    except BaseException as exc:
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        result["ended_at"] = utcnow()


def execute(config, config_path, stage, run):
    # These objects are captured before the container starts. Replacing files on
    # disk during a long run cannot substitute the recorded or executed helper.
    runner_source = RUNNER_SOURCE
    repair_source = xcpd_metadata.SOURCE_BYTES if stage == "xcpd" else None
    repair_function = xcpd_metadata.repair_run
    input_root = check_inputs(config, stage, run)
    paths = validate_paths(config)
    paths["logs"].mkdir(parents=True, exist_ok=True)
    lock = paths["logs"] / "pipeline.lock"
    acquire_lock(lock)
    log_dir = None
    record = None
    selected_lock = None
    try:
        if stage == "xcpd":
            candidate_lock = xcpd_run_lock(paths, run)
            acquire_lock(candidate_lock)
            selected_lock = candidate_lock
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        log_dir = paths["logs"] / f"{timestamp}_{stage}_sub-{run['subject']}_ses-{run['session']}_{uuid.uuid4().hex[:8]}"
        log_dir.mkdir()
        record = {"started_at": utcnow(), "stage": stage, "run": run, "status": "preparing",
                  "config_path": str(config_path.resolve()), "config": config}
        capture_sources(log_dir, record, runner_source, repair_source)
        write_json(log_dir / "run.json", record)
        image = resolve_image(config["images"][stage])
        if image["os"] != "linux" or image["architecture"] != "amd64":
            raise PipelineError("Expected the pinned linux/amd64 image")
        command = build_command(config, stage, run, image=image["resolved"])
        record.update({"image": image, "command": command})
        before = snapshot_input(input_root, run["subject"])
        write_json(log_dir / "input_before.json", before)
        for key in (f"{stage}_output", f"{stage}_work", "templateflow"):
            paths[key].mkdir(parents=True, exist_ok=True)
        work_path = paths[f"{stage}_work"] / f"sub-{run['subject']}" / f"ses-{run['session']}"
        record["cache_signature"] = guard_cache(work_path, cache_signature(stage, command, image, before))
        record["status"] = "running"
        write_json(log_dir / "run.json", record)
        print(f"Run provenance: {log_dir}", flush=True)
        print(shlex.join(command), flush=True)
        try:
            with (log_dir / "console.log").open("w", encoding="utf-8") as log:
                proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
            record["exit_code"] = proc.returncode
        finally:
            try:
                after = snapshot_input(input_root, run["subject"])
                write_json(log_dir / "input_after.json", after)
                record["input_unchanged"] = before == after
            finally:
                record["citation_snapshots"] = capture_citations(paths[f"{stage}_output"], run, log_dir)
        if not record["input_unchanged"]:
            raise PipelineError("Input integrity changed during execution")
        if proc.returncode:
            raise PipelineError(f"Container exited {proc.returncode}; see {log_dir / 'console.log'}")
        if stage == "xcpd":
            apply_xcpd_metadata_repair(paths, run, record, log_dir, repair_function)
        record["status"] = "execution_completed_qc_required"
        record["pipeline_exit_code"] = 0
        return 0
    except BaseException as exc:
        if record is not None:
            record["status"] = "failed"
            record["pipeline_exit_code"] = 1
            record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            if record is not None:
                record["ended_at"] = utcnow()
                write_json(log_dir / "run.json", record)
        finally:
            if selected_lock is not None:
                selected_lock.unlink(missing_ok=True)
            lock.unlink(missing_ok=True)


def latest_completed_xcpd_run(paths, run):
    """Never fall back to an older success after a newer selected attempt fails."""
    candidates = []
    pattern = f"*_xcpd_sub-{run['subject']}_ses-{run['session']}_*/run.json"
    for path in paths["logs"].glob(pattern):
        source = path.read_bytes()
        value = json.loads(source)
        if value.get("stage") != "xcpd" or value.get("run") != run:
            raise PipelineError(f"Run identity conflicts with provenance directory: {path}")
        try:
            started = dt.datetime.fromisoformat(value["started_at"])
            if started.tzinfo is None:
                raise ValueError("timestamp has no timezone")
        except (KeyError, TypeError, ValueError) as exc:
            raise PipelineError(f"Invalid run start time: {path}") from exc
        candidates.append((started, str(path), path, source, value))
    if not candidates:
        raise PipelineError("No selected XCP-D execution record exists")
    _, _, path, source, value = max(candidates, key=lambda item: item[:2])
    if (value.get("status") != "execution_completed_qc_required" or
            type(value.get("exit_code")) is not int or value["exit_code"] != 0 or
            value.get("input_unchanged") is not True):
        raise PipelineError(f"Latest selected XCP-D attempt is not an unchanged-input successful execution: {path}")
    saved_output = value.get("config", {}).get("paths", {}).get("xcpd_output")
    if not saved_output or Path(saved_output).expanduser().resolve() != paths["xcpd_output"]:
        raise PipelineError("Latest XCP-D execution used a different output directory")
    return path, source, value


def finalize_xcpd(config, config_path, run):
    """Repair a completed selected run without rewriting its execution record."""
    runner_source = RUNNER_SOURCE
    repair_source, repair_function = xcpd_metadata.SOURCE_BYTES, xcpd_metadata.repair_run
    paths = validate_paths(config)
    paths["logs"].mkdir(parents=True, exist_ok=True)
    # Deliberately no global pipeline lock: another participant's fMRIPrep can
    # continue. The helper additionally locks its precise target NIfTI file.
    lock = xcpd_run_lock(paths, run)
    acquire_lock(lock)
    record, log_dir = None, None
    try:
        source_path, source_bytes, _ = latest_completed_xcpd_run(paths, run)
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        log_dir = paths["logs"] / "metadata_finalizations" / (
            f"{timestamp}_sub-{run['subject']}_ses-{run['session']}_{uuid.uuid4().hex[:8]}")
        log_dir.mkdir(parents=True)
        record = {"started_at": utcnow(), "stage": "xcpd", "command": "finalize-xcpd",
                  "run": run, "status": "preparing", "config_path": str(config_path.resolve()),
                  "config": config, "source_run": str(source_path),
                  "source_run_sha256": hashlib.sha256(source_bytes).hexdigest(),
                  "source_run_snapshot": "original_run.json"}
        (log_dir / "original_run.json").write_bytes(source_bytes)
        capture_sources(log_dir, record, runner_source, repair_source)
        write_json(log_dir / "finalization.json", record)
        print(f"Finalization provenance: {log_dir}", flush=True)
        # Detect a legacy/external writer that does not honor the selected lock.
        latest_path, latest_bytes, _ = latest_completed_xcpd_run(paths, run)
        if latest_path != source_path or latest_bytes != source_bytes:
            raise PipelineError("Selected XCP-D execution record changed before finalization")
        apply_xcpd_metadata_repair(paths, run, record, log_dir, repair_function)
        record.update({"status": "metadata_finalization_completed_qc_required", "exit_code": 0})
        return 0
    except BaseException as exc:
        if record is not None:
            record.update({"status": "failed", "exit_code": 1, "error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        try:
            if record is not None:
                record["ended_at"] = utcnow()
                write_json(log_dir / "finalization.json", record)
        finally:
            lock.unlink(missing_ok=True)


def nifti_shape(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as f:
        header = f.read(544)
    endian = "<" if struct.unpack("<i", header[:4])[0] in (348, 540) else ">"
    size = struct.unpack(endian + "i", header[:4])[0]
    if size == 348:
        dims = struct.unpack_from(endian + "8h", header, 40)
    elif size == 540:
        dims = struct.unpack_from(endian + "8q", header, 16)
    else:
        raise PipelineError(f"Invalid NIfTI header: {path}")
    if not 1 <= dims[0] <= 7 or any(v <= 0 for v in dims[1:dims[0] + 1]):
        raise PipelineError(f"Invalid NIfTI shape: {path}")
    return list(dims[1:dims[0] + 1])


def verify(config, stage, run):
    """Structural completeness only; not a substitute for scientific/visual QC."""
    root = validate_paths(config)[f"{stage}_output"]
    session = root / f"sub-{run['subject']}" / f"ses-{run['session']}"
    desc = "preproc" if stage == "fmriprep" else "denoised"
    bolds = sorted((session / "func").glob(f"*_task-{config.get('task', 'rest')}_*desc-{desc}_bold.nii*"))
    if stage == "fmriprep":
        bolds = [p for p in bolds if "space-MNI152NLin2009cAsym" in p.name]
    if not bolds:
        raise PipelineError(f"No expected {stage} BOLD output")
    details = []
    for bold in bolds:
        shape = nifti_shape(bold)
        if len(shape) != 4:
            raise PipelineError(f"Expected 4D BOLD: {bold}")
        item = {"file": str(bold.relative_to(root)), "shape": shape, "sha256": sha256(bold)}
        if stage == "fmriprep":
            prefix = bold.name.split("_space-")[0]
            confound = bold.parent / f"{prefix}_desc-confounds_timeseries.tsv"
            with confound.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
            if len(rows) != shape[3]:
                raise PipelineError("Confounds row count differs from preprocessed BOLD volume count")
            item["confounds_rows"] = len(rows)
        details.append(item)
    reports = list(root.glob(f"sub-{run['subject']}*.html"))
    reports += list((root / f"sub-{run['subject']}").rglob("*.html"))
    if not reports or not (root / "dataset_description.json").is_file():
        raise PipelineError("Missing HTML report or derivative dataset_description.json")
    return {"status": "structural_checks_passed_visual_and_scientific_qc_required", "stage": stage,
            "run": run, "outputs": details, "reports": [str(p.relative_to(root)) for p in reports]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", choices=("dry-run", "run", "verify", "finalize-xcpd"))
    parser.add_argument("--stage", choices=("fmriprep", "xcpd"), required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--session")
    args = parser.parse_args(argv)
    if args.command == "finalize-xcpd" and args.stage != "xcpd":
        parser.error("finalize-xcpd requires --stage xcpd")
    try:
        config = read_config(args.config)
        run = select_run(config, args.subject, args.session)
        config, run = configuration_for_run(config, run)
        if args.command == "dry-run":
            check_inputs(config, args.stage, run)
            print(json.dumps({"executed": False, "image_digest_resolved_at_run": True,
                              "argv": build_command(config, args.stage, run)}, indent=2))
            return 0
        if args.command == "verify":
            print(json.dumps(verify(config, args.stage, run), indent=2))
            return 0
        if args.command == "finalize-xcpd":
            return finalize_xcpd(config, args.config, run)
        return execute(config, args.config, args.stage, run)
    except (PipelineError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
