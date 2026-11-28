"""Isolated end-to-end thread trials using the owned 7.B and S10 builders."""
from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib
import uuid

import nibabel as nib

from compare import check_write, inventory, read, save, sha

LAB = Path(__file__).resolve().parents[2]
THREAD_ENV = ("OMP_NUM_THREADS", "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS")
BLAS_ENV = ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def module(relative):
    path = LAB / relative
    spec = importlib.util.spec_from_file_location("thread_trial_" + uuid.uuid4().hex, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def checked_copy(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    expected = sha(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha(destination) != expected or sha(source) != expected:
        raise ValueError("Input changed while copying: " + str(source))
    return expected


def tree_hashes(root):
    root = Path(root).resolve()
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            raise ValueError("Input/cache symlink escapes snapshot: " + str(path))
        if path.is_file():
            result[str(path.relative_to(root))] = sha(path)
    return result


def check_tree(root, expected):
    if tree_hashes(root) != expected:
        raise ValueError("Frozen input/cache inventory or contents changed: " + str(root))


def images(image_names):
    result = {}
    for stage, name in image_names.items():
        item = json.loads(subprocess.check_output(["docker", "image", "inspect", name], text=True, timeout=30))[0]
        repository = name.split("@", 1)[0].rsplit(":", 1)[0] if "@" not in name else name.split("@", 1)[0]
        matches = [d for d in item.get("RepoDigests", []) if d.startswith(repository + "@sha256:")]
        if len(matches) != 1 or item.get("Architecture") != "amd64":
            raise ValueError("Require one installed amd64 immutable image digest: " + name)
        if "@" in name and name not in matches:
            raise ValueError("Requested image digest not installed")
        result[stage] = {"resolved": matches[0], "image_id": item["Id"], "architecture": "amd64", "os": item["Os"]}
    return result


def numerical_command(argv, threads, name, experiment):
    """Change only declared thread controls and Docker transport, never algorithms."""
    argv = list(map(str, argv))
    at = next(i for i, value in enumerate(argv) if "@sha256:" in value and not value.startswith(("/", "type=")))
    options, application = argv[:at], argv[at:]
    if options[:2] != ["docker", "run"]:
        raise ValueError("Expected a Docker run command")
    controlled = {*THREAD_ENV, *BLAS_ENV, "ANTS_RANDOM_SEED", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE"}
    clean = []
    i = 0
    while i < len(options):
        if options[i] == "--rm":
            i += 1
            continue
        if options[i] in ("-e", "--env") and options[i + 1].split("=", 1)[0] in controlled:
            i += 2
            continue
        if options[i] == "--name":
            clean += ["--name", name]
            i += 2
            continue
        clean.append(options[i])
        i += 1
    if "--omp-nthreads" not in application:
        raise ValueError("Application has no declared thread control")
    application[application.index("--omp-nthreads") + 1] = str(threads)
    seed = application[application.index("--random-seed") + 1]
    for key in THREAD_ENV:
        clean += ["--env", key + "=" + str(threads)]
    for key in BLAS_ENV:
        clean += ["--env", key + "=1"]
    for key, value in (("ANTS_RANDOM_SEED", seed), ("PYTHONHASHSEED", seed), ("PYTHONDONTWRITEBYTECODE", "1")):
        clean += ["--env", key + "=" + value]
    clean += ["--pull", "never", "--network", "none", "--label", "adni.reproducibility=" + experiment]
    return clean + application


def inspect_container(name):
    proc = subprocess.run(["docker", "inspect", name], text=True, capture_output=True, timeout=25)
    if proc.returncode:
        return None
    item = json.loads(proc.stdout)[0]
    return {"id": item["Id"], "name": item["Name"], "image": item["Image"], "state": item["State"],
            "mounts": item["Mounts"], "host_config": {k: item["HostConfig"].get(k) for k in ("NanoCpus", "Memory", "NetworkMode")}}


def docker_names():
    return subprocess.check_output(["docker", "ps", "--format", "{{.Names}}"], text=True, timeout=25).splitlines()


def execute_container(argv, log, expected_image, experiment, threads, logging=False):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    effective = module("pipeline/s7c_ants_iteration_logging/run.py").augment(argv, log.parent) if logging else argv
    name = effective[effective.index("--name") + 1]
    expected_cpus = round(float(effective[effective.index("--cpus") + 1]) * 10**9)
    expected_memory = int(effective[effective.index("--memory") + 1][:-1]) * 2**30
    receipt = log.parent / "container_execution.json"
    if receipt.exists():
        raise FileExistsError("Do not reuse a measured attempt: " + str(receipt))
    record = {"started_at": now(), "status": "starting", "effective_command": effective,
              "threads": threads, "experiment": experiment, "foreign_containers": [], "exit_code": None}
    save(receipt, record)
    began = time.monotonic()
    with log.open("x") as stream:
        child = subprocess.Popen(effective, stdout=stream, stderr=subprocess.STDOUT)
        while True:
            actual = inspect_container(name)
            if actual and actual["state"].get("StartedAt", "").startswith("0001-") is False:
                if actual["image"] != expected_image:
                    # Preserve all containers, including a suspect owned execution, for review.
                    record["image_mismatch"] = True
                if actual["host_config"]["NanoCpus"] != expected_cpus or actual["host_config"]["Memory"] != expected_memory:
                    record["resource_mismatch"] = True
                record.setdefault("actual_started_at", actual["state"]["StartedAt"])
                record.setdefault("container_at_start", actual)
                record["status"] = "running"
            others = [n for n in docker_names() if n != name]
            record["foreign_containers"] = sorted(set(record["foreign_containers"]) | set(others))
            record["wall_seconds"] = time.monotonic() - began
            save(receipt, record)
            if child.poll() is not None:
                break
            time.sleep(15)
    final = inspect_container(name)
    record.update(exit_code=child.returncode, ended_at=now(), wall_seconds=time.monotonic() - began,
                  container_at_end=final, isolated=not record["foreign_containers"], status="failed")
    if final and (final["host_config"]["NanoCpus"] != expected_cpus or final["host_config"]["Memory"] != expected_memory):
        record["resource_mismatch"] = True
    if final and record.get("actual_started_at") and child.returncode == 0 and final["state"].get("ExitCode") == 0 and not final["state"].get("OOMKilled") and not record.get("image_mismatch") and not record.get("resource_mismatch"):
        record["status"] = "success"
    save(receipt, record)
    if record["status"] != "success":
        raise RuntimeError("Container did not complete successfully: " + str(receipt))
    return record


def verify_application_threads(directory, filename, threads, cpus):
    configs = list(Path(directory).rglob(filename))
    if len(configs) != 1:
        raise ValueError("Require one actual application configuration: " + filename)
    actual = tomllib.loads(configs[0].read_text()).get("nipype", {})
    if actual.get("omp_nthreads") != threads or actual.get("nprocs") != cpus:
        raise ValueError("Actual application thread/process settings differ from the trial")
    return {"path": str(configs[0]), "sha256": sha(configs[0]), "omp_nthreads": threads, "nprocs": cpus}


class Transport:
    """Observe the original backend's execution without patching live modules."""
    def __init__(self, image, experiment, threads):
        self.image, self.experiment, self.threads = image, experiment, threads
        self.record = None

    def __getattr__(self, key):
        return getattr(subprocess, key)

    def run(self, argv, *args, **kwargs):
        if list(argv[:2]) != ["docker", "run"]:
            return subprocess.run(argv, *args, **kwargs)
        stream = kwargs["stdout"]
        # run_stage opens console.log before invoking the transport. Use another,
        # exclusive log while retaining its original receipt and source snapshot.
        log = Path(stream.name).with_name("measured_console.log")
        self.record = execute_container(argv, log, self.image, self.experiment, self.threads, logging=True)
        return subprocess.CompletedProcess(argv, self.record["exit_code"])


def run_trial(root, plan, case, threads, repeat):
    import yaml

    label = f"{case['id']}-t{threads:02d}-r{repeat:02d}"
    trial = Path(root) / "trials" / label
    check_write(trial)
    if trial.exists():
        old = read(trial / "trial.json")
        if old.get("status") == "success":
            return trial
        raise ValueError("Existing incomplete attempt is preserved; review it before planning a new experiment")
    trial.mkdir(parents=True)
    inputs = Path(root) / "inputs" / case["id"]
    before = tree_hashes(inputs / "bids")
    if before != case["bids_hashes"]:
        raise ValueError("Frozen BIDS changed")
    base_cfg = read(inputs / "preprocessing.json")
    identity = {"case": case["id"], "bids": before, "settings": case["scientific_settings"],
                "images": plan["images"], "source_hashes": plan["source_hashes"],
                "cpu_budget": plan["workflow_cpus"], "memory_mb": plan["workflow_memory_mb"],
                "docker_memory": plan["docker_memory"], "seed": plan["random_seed"],
                "blas_threads": 1, "platform": "linux/amd64", "host": plan["host"]}
    record = {"trial_id": label + "-" + uuid.uuid4().hex, "threads": threads, "repeat": repeat,
              "started_at": now(), "status": "preparing", "analysis_identity": identity, "executions": {}}
    save(trial / "trial.json", record, exclusive=True)
    try:
        cfg = copy.deepcopy(base_cfg)
        cfg.update(runtime=str(trial / "preprocess"), source_bids=str(inputs / "bids"),
                   source_manifest=str(inputs / "source_manifest.json"), source_phase_evidence=str(inputs / "phase.json"),
                   source_templateflow=str(Path(root) / "templateflow"),
                   seed_policy="thread-benchmark-v1", work_revision=label,
                   random_seed=plan["random_seed"])
        cfg["resources"] = {"cpus": plan["workflow_cpus"], "omp_nthreads": threads,
                            "workflow_memory_mb": plan["workflow_memory_mb"], "docker_memory": plan["docker_memory"]}
        backend = module("pipeline/s7b_sessionwise_preprocessing/run.py")
        backend.prepare(cfg)
        backend.intake(cfg)
        image = plan["images"]["fmriprep"]
        backend.image_record = lambda tag: image
        original_command = backend.command

        def build(c, stage, visit, image_digest):
            argv, work = original_command(c, stage, visit, image_digest)
            argv += ["--skull-strip-fixed-seed"]
            # Existing production CPU/watchdog services intentionally do not own
            # this namespace. The shared subject lease still counts this trial.
            name = "adni-repro-fmriprep-" + visit["subject"] + "-" + label
            return numerical_command(argv, threads, name, plan["experiment_id"]), work

        backend.command = build
        transport = Transport(image["image_id"], plan["experiment_id"], threads)
        backend.subprocess = transport
        save(trial / "preprocessing.json", cfg)
        record["status"] = "fmriprep_running"
        save(trial / "trial.json", record)
        backend.run_stage(cfg, "fmriprep", cfg["runs"][0], case["profile"])
        record["executions"]["fmriprep"] = transport.record
        pre = read(next((trial / "preprocess/logs").glob("*_fmriprep_*/run.json")))
        if pre.get("exit_code") != 0 or pre.get("input_unchanged") is not True:
            raise ValueError("Original 7.B completion/input verification failed")
        record["executions"]["fmriprep"]["application_threads"] = verify_application_threads(
            trial / "preprocess/derivatives/fmriprep", "fmriprep.toml", threads, plan["workflow_cpus"])
        save(trial / "trial.json", record)
        post = module("pipeline/s10_xcpd_integrated_qc/pipeline.py")
        xcfg = copy.deepcopy(plan["xcpd_settings"])
        xcfg["resources"] = {"cpus": plan["workflow_cpus"], "omp_nthreads": threads,
                             "mem_mb": plan["workflow_memory_mb"], "docker_memory": plan["docker_memory"]}
        xcfg.update(_config_id=label, random_seed=plan["random_seed"])
        visit = cfg["runs"][0]
        derivatives = trial / "preprocess/derivatives/fmriprep"
        pattern = "*space-fsLR*bold.dtseries.nii" if xcfg["file_format"] == "cifti" else "*space-MNI152NLin6Asym*desc-preproc_bold.nii.gz"
        candidates = list(derivatives.glob("sub-*/**/func/" + pattern))
        if len(candidates) != 1:
            raise ValueError("Require one exact preprocessed BOLD for XCP-D")
        image_data = nib.load(candidates[0])
        cifti = isinstance(image_data, nib.Cifti2Image)
        row = {k: "" for k in ("sub", "ses", "task", "run", "acq", "dir", "echo", "rec")}
        row.update(sub="sub-" + visit["subject"], ses="ses-" + visit["session"], task="task-rest",
                   source_bold_file=str(candidates[0]), n_original_volumes=image_data.shape[0] if cifti else image_data.shape[3],
                   tr=float(image_data.header.get_axis(0).step) if cifti else float(image_data.header.get_zooms()[3]))
        job = trial / "postprocess"
        for directory in (job / "derivatives", job / "work", job / "cache"):
            directory.mkdir(parents=True)
        save(job / "bids_filter.json", post.bids_filter(row, xcfg))
        save(job / "configuration.json", xcfg)
        args = ["docker", "run", "--name", "adni-repro-xcpd-" + visit["subject"] + "-" + label,
                "--platform", "linux/amd64", "--cpus", str(plan["workflow_cpus"]), "--memory", plan["docker_memory"]]
        for source, target, ro in ((derivatives, "/input", True), (job, "/job", False),
                                   (trial / "preprocess/templateflow", "/templateflow", False),
                                   (Path(cfg["freesurfer_license"]), "/license.txt", True)):
            if "," in str(source):
                raise ValueError("Docker bind paths cannot contain commas")
            args += ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if ro else "")]
        args += ["--env", "TEMPLATEFLOW_HOME=/templateflow", "--env", "MPLCONFIGDIR=/job/cache",
                 plan["images"]["xcpd"]["resolved"], *post.xcp_args(xcfg, row)]
        args = numerical_command(args, threads, args[args.index("--name") + 1], plan["experiment_id"])
        record["status"] = "xcpd_running"
        save(trial / "trial.json", record)
        record["executions"]["xcpd"] = execute_container(args, job / "logs/console.log", plan["images"]["xcpd"]["image_id"], plan["experiment_id"], threads)
        validation = post.validate_outputs(job, row, xcfg, 0)
        save(job / "output_validation.json", validation)
        if not validation["functional_outputs_valid"]:
            raise ValueError("S10 output validation failed")
        record["executions"]["xcpd"]["application_threads"] = verify_application_threads(
            job / "derivatives", "xcp_d.toml", threads, plan["workflow_cpus"])
        check_tree(inputs / "bids", before)
        record.update(input_unchanged=True, ended_at=now(), status="success",
                      products_sha256={rel: sha(trial / rel) for rel in inventory(trial)},
                      isolated=all(v["isolated"] for v in record["executions"].values()))
        save(trial / "trial.json", record)
        if plan.get("prune_owned_work"):
            # Only regenerateable scratch inside this newly owned, successful trial.
            for relative in ("preprocess/work", "postprocess/work", "postprocess/cache"):
                target = trial / relative
                if target.is_symlink() or not target.resolve().is_relative_to(trial.resolve()):
                    raise ValueError("Refusing scratch cleanup outside owned trial")
                shutil.rmtree(target)
            record["owned_scratch_pruned"] = True
            save(trial / "trial.json", record)
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}", ended_at=now())
        record["input_unchanged"] = tree_hashes(inputs / "bids") == before
        save(trial / "trial.json", record)
        raise
    return trial
