#!/usr/bin/env python3
"""Mac Docker entrypoint for the integrated statMIND-derived ADNI protocol.

The integrated Python QC modules are used directly. This stage supplies
an existing-BIDS intake and Docker transport within the unified pipeline.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import pandas as pd
import yaml

VERSION = "1.0.0"
REPO = Path(__file__).resolve().parents[2] / "pipeline"
if str(REPO.parent / "04_workflow") not in sys.path:
    sys.path.insert(0, str(REPO.parent / "04_workflow"))
from protocol_source import inspect_protocol
from processing_time import add_timing, refresh_safely


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def load(path):
    cfg = yaml.safe_load(Path(path).read_text())
    root = Path(cfg["runtime"]).resolve()
    source = Path(cfg["source_bids"]).resolve()
    if root == source or root in source.parents or source in root.parents:
        raise ValueError("New runtime and existing BIDS source must be disjoint")
    if not cfg["runs"]:
        raise ValueError("At least one visit is required")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(cfg.get("work_revision", "v1"))):
        raise ValueError("Work revision must be a simple directory label")
    for case in cfg["runs"]:
        for key in ("subject", "session"):
            case[key] = str(case[key])
            if not re.fullmatch(r"[A-Za-z0-9]+", case[key]):
                raise ValueError("BIDS subject/session labels must be alphanumeric")
    return cfg


def runtime(cfg):
    return Path(cfg["runtime"]).resolve()


def environment():
    env = os.environ.copy()
    env["PATH"] = str(REPO.parent / ".venv/bin") + os.pathsep + env.get("PATH", "")
    env["R_LIBS_USER"] = str(REPO.parent / ".R-library")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run_logged(argv, logfile, cwd=REPO):
    logfile = Path(logfile)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("w") as output:
        result = subprocess.run([str(v) for v in argv], cwd=cwd, env=environment(),
                                stdout=output, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"Exit {result.returncode}; see {logfile}")


def copy_verified(source, target, expected=None):
    source, target = Path(source), Path(target)
    source_hash = sha(source)
    if expected and source_hash != expected:
        raise ValueError(f"Source hash mismatch: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha(target) != source_hash:
            raise ValueError(f"Refusing to overwrite a different existing file: {target}")
    else:
        shutil.copy2(source, target)
    if sha(target) != source_hash:
        raise ValueError(f"Copy verification failed: {target}")
    return {"source": str(source), "target": str(target), "sha256": source_hash}


def prepare(cfg):
    root, source = runtime(cfg), Path(cfg["source_bids"])
    for name in ("bids", "derivatives", "work", "logs", "results", "qc", "filters"):
        (root / name).mkdir(parents=True, exist_ok=True)
    old = json.loads(Path(cfg["source_manifest"]).read_text())
    expected = {item["path"]: item["sha256"] for item in old["files"]}
    selected = {f"sub-{c['subject']}/ses-{c['session']}" for c in cfg["runs"]}
    records = []
    for relative, digest in expected.items():
        if "/".join(Path(relative).parts[:2]) in selected:
            records.append(copy_verified(source / relative, root / "bids" / relative, digest))
    if len(records) != 4 * len(cfg["runs"]):
        raise ValueError("This intake expects one T1w/BOLD image and sidecar per visit")
    for name in ("dataset_description.json", "participants.tsv", "participants.json", ".bidsignore"):
        if (source / name).is_file():
            records.append(copy_verified(source / name, root / "bids" / name))
    copy_verified(cfg["source_phase_evidence"], root / "qc/phase_evidence.json")
    cache_source = Path(cfg["source_templateflow"])
    if not (root / "templateflow").exists():
        shutil.copytree(cache_source, root / "templateflow")
    dump(root / "logs/intake_manifest.json", {
        "created_at": now(), "source_bids": str(source), "original_source": old["source"],
        "files": records, "raw_images_and_sidecars": 4 * len(cfg["runs"]),
        "phase_evidence": "qc/phase_evidence.json", "mode": "existing_BIDS_no_DICOM_conversion_claim",
    })
    print(json.dumps({"prepared": str(root), "verified_files": len(records)}))


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def paths_for(cfg, case):
    folder = runtime(cfg) / "bids" / f"sub-{case['subject']}" / f"ses-{case['session']}"
    prefix = f"sub-{case['subject']}_ses-{case['session']}"
    return {"bold": folder / "func" / f"{prefix}_task-rest_bold.nii.gz",
            "bold_json": folder / "func" / f"{prefix}_task-rest_bold.json",
            "t1w": folder / "anat" / f"{prefix}_T1w.nii.gz",
            "t1w_json": folder / "anat" / f"{prefix}_T1w.json"}


def intake(cfg):
    root = runtime(cfg)
    parser = import_file("upstream_nifti_parser", REPO / "s5_post_clinica_qc/create_mastersheet/parsers/nifti_parser.py")
    rows, identity = [], []
    for case in cfg["runs"]:
        paths = paths_for(cfg, case)
        values = parser.NiftiParser(str(paths["bold"]), str(paths["bold_json"])).parse()
        values.update({"Image_ID": case["bold_image_id"], "Subject_ID": case["ptid"],
                       "VISCODE": case["session"], "sub": "sub-" + case["subject"],
                       "ses": "ses-" + case["session"], "phase": case["phase"],
                       "NIfTI_path": str(paths["bold"]), "JSON_path": str(paths["bold_json"]),
                       "NIfTI_exists": paths["bold"].is_file(), "JSON_exists": paths["bold_json"].is_file(),
                       "T1w_exists": paths["t1w"].is_file()})
        values.setdefault("json_CoilString", None)
        values.setdefault("json_PercentPhaseFOV", None)
        rows.append(values)
        identity.append({**case, "sub": values["sub"], "ses": values["ses"],
                         "VISCODE_note": "BIDS date session, not a fabricated clinical VISCODE",
                         "coil_string_missing": values["json_CoilString"] is None})
    target = root / "results/step5"
    target.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    anchor = target / "bids_anchor_metadata.csv"
    frame.to_csv(anchor, index=False)
    pd.DataFrame(identity).to_csv(target / "identity_map.tsv", sep="\t", index=False)
    run_logged([sys.executable, REPO / "s5_post_clinica_qc/create_report/run_session_heuristics.py",
                "--input-csv", anchor, "--output-dir", target / "strict_upstream",
                "--fmriprep-subjects-csv", target / "strict_subjects.csv"],
               root / "logs/step5_heuristics.log")
    scripts = REPO / "s5_post_clinica_qc/create_report/scripts"
    heuristic = import_file("upstream_heuristics", scripts / "heuristics.py")
    columns = import_file("upstream_columns", scripts / "config.py").CONFIG
    checks = ("filter_missing_data_adnidap", "filter_missing_data", "filter_missing_t1w",
              "filter_low_scan_depth", "filter_invalid_repetition_time", "filter_short_duration",
              "filter_low_percent_phase_fov", "filter_out_bad_coils")
    # Parse exactly the saved CSV, matching the upstream CLI's pandas types.
    saved = pd.read_csv(anchor)
    decisions = []
    for idx, case in enumerate(cfg["runs"]):
        row = saved.iloc[[idx]]
        result = {"sub": "sub-" + case["subject"], "ses": "ses-" + case["session"],
                  "phase": case["phase"], "phase_supported_upstream": case["phase"] in ("ADNIGO", "ADNI2", "ADNI3")}
        for name in checks:
            result[name] = bool(getattr(heuristic, name)(row, columns).iloc[0])
        result["all_heuristics_pass"] = all(result[name] for name in checks)
        result["strict_upstream_eligible"] = result["phase_supported_upstream"] and result["all_heuristics_pass"]
        result["failed_checks"] = ";".join(name for name in checks if not result[name])
        decisions.append(result)
    pd.DataFrame(decisions).to_csv(target / "intake_decisions.tsv", sep="\t", index=False)
    dump(target / "intake_provenance.json", {"time": now(), "anchor_sha256": sha(anchor),
         "source_parser": str(Path(parser.__file__).relative_to(REPO)), "source_parser_sha256": sha(parser.__file__),
         "source_heuristics_sha256": sha(heuristic.__file__), "DICOM_processing": "not_applicable_existing_BIDS",
         "protocol_source": inspect_protocol(REPO.parent), "upstream_commit": inspect_protocol(REPO.parent)["upstream_commit"]})
    print(json.dumps(decisions, indent=2))


def selected_inputs(cfg, case):
    root = runtime(cfg) / "bids"
    files = list(paths_for(cfg, case).values()) + [root / "dataset_description.json"]
    return {str(p.relative_to(root)): sha(p) for p in sorted(files)}


def image_record(tag):
    item = json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]
    repo = tag.rsplit(":", 1)[0]
    digests = [s for s in item.get("RepoDigests", []) if s.startswith(repo + "@")]
    if not digests:
        raise ValueError(f"No immutable repository digest for installed image {tag}")
    return {"tag": tag, "resolved": digests[0], "image_id": item["Id"],
            "architecture": item["Architecture"], "os": item["Os"]}


def filter_path(cfg, case, stage):
    p = runtime(cfg) / "filters" / f"sub-{case['subject']}_ses-{case['session']}_{stage}.json"
    value = {"bold": {"session": case["session"], "task": "rest"},
             "t1w": {"session": case["session"]}, "t2w": {"session": case["session"]}}
    if stage == "mriqc":
        value = {"bold": value["bold"], "T1w": value["t1w"]}
    dump(p, value)
    return p


def command(cfg, stage, case, image):
    root, r = runtime(cfg), cfg["resources"]
    work = root / "work" / stage / cfg.get("work_revision", "v1") / f"sub-{case['subject']}" / f"ses-{case['session']}"
    output = root / "derivatives" / stage
    filt = filter_path(cfg, case, stage)
    for directory in (work, output):
        directory.mkdir(parents=True, exist_ok=True)
    args = ["docker", "run", "--rm", "--name", f"statmind-{stage}-{case['subject']}-{case['session']}",
            "--platform", "linux/amd64", "--cpus", str(r["cpus"]), "--memory", r["docker_memory"]]
    for source, dest, readonly in [(root / "bids", "/data", True), (output, "/out", False),
                                    (work, "/work", False), (root / "templateflow", "/templateflow", False),
                                    (filt, "/config/filter.json", True)]:
        args += ["--mount", f"type=bind,src={source},dst={dest}" + (",readonly" if readonly else "")]
    args += ["--env", "TEMPLATEFLOW_HOME=/templateflow", "--env", f"OMP_NUM_THREADS={r['omp_nthreads']}"]
    if stage == "fmriprep":
        fs = output / "sourcedata/freesurfer"
        fs.mkdir(parents=True, exist_ok=True)
        args += ["--mount", f"type=bind,src={cfg['freesurfer_license']},dst=/license.txt,readonly",
                 "--mount", f"type=bind,src={fs},dst=/fsdir"]
    args += [image, "/data", "/out", "participant", "--participant-label", case["subject"],
             "--bids-filter-file", "/config/filter.json", "--nprocs", str(r["cpus"]),
             "--omp-nthreads", str(r["omp_nthreads"]), "--notrack", "-w", "/work"]
    if stage == "mriqc":
        args += ["--modalities", "T1w", "bold", "--session-id", case["session"],
                 "--no-sub", "--mem-gb", str((r["workflow_memory_mb"] + 999) // 1000)]
    else:
        args += ["--task-id", "rest", "--subject-anatomical-reference", "sessionwise",
                 "--force", "syn-sdc", "--ignore", "fieldmaps", "--use-syn-sdc", "error",
                 "--output-spaces", *cfg["output_spaces"], "--cifti-output", "91k",
                 "--fs-license-file", "/license.txt", "--fs-subjects-dir", "/fsdir",
                 "--mem-mb", str(r["workflow_memory_mb"]), "--random-seed", str(cfg["random_seed"]),
                 "--stop-on-first-crash"]
    return args, work


def run_stage(cfg, stage, case, profile):
    root = runtime(cfg)
    decisions = pd.read_csv(root / "results/step5/intake_decisions.tsv", sep="\t")
    eligible = decisions.loc[(decisions["sub"] == "sub-" + case["subject"]) &
                             (decisions["ses"] == "ses-" + case["session"]), "strict_upstream_eligible"]
    if len(eligible) != 1:
        raise ValueError("Missing or ambiguous recorded intake decision")
    if not bool(eligible.iloc[0]) and profile != "technical-extension":
        raise ValueError("Visit fails official intake; use an explicitly recorded technical-extension test")
    lock = root / "pipeline.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, json.dumps({"pid": os.getpid(), "stage": stage, "case": case, "started_at": now()}).encode())
    os.close(fd)
    record = None
    try:
        im = image_record(cfg["images"][stage])
        argv, work = command(cfg, stage, case, im["resolved"])
        inputs = selected_inputs(cfg, case)
        filterfile = root / "filters" / f"sub-{case['subject']}_ses-{case['session']}_{stage}.json"
        signature = {"command": argv, "input_sha256": inputs,
                     "filter_sha256": sha(filterfile), "runner_sha256": sha(__file__)}
        sigfile = work / ".cache-signature.json"
        if sigfile.exists():
            if json.loads(sigfile.read_text()) != signature:
                raise ValueError("Cache identity differs; retain it and choose a new work directory")
        elif any(work.iterdir()):
            raise ValueError("Refusing unknown existing work cache")
        else:
            dump(sigfile, signature)
        token = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        folder = root / "logs" / f"{token}_{stage}_sub-{case['subject']}_ses-{case['session']}"
        folder.mkdir(parents=True)
        shutil.copy2(__file__, folder / "runner_source.py")
        record = {"started_at": now(), "stage": stage, "case": case, "profile": profile,
                  "strict_upstream_eligible": bool(eligible.iloc[0]), "status": "running", "runner_version": VERSION,
                  "runner_sha256": sha(__file__), "config": cfg, "image": im, "command": argv,
                  "input_before": inputs, "protocol_source": inspect_protocol(REPO.parent), "upstream_commit": inspect_protocol(REPO.parent)["upstream_commit"]}
        dump(folder / "run.json", record)
        print(f"Running {stage}: {folder}", flush=True)
        record["execution_started_at"] = now()
        dump(folder / "run.json", record)
        with (folder / "console.log").open("w") as log:
            child = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=False)
        record["container_ended_at"] = now()
        record["exit_code"] = child.returncode
        after = selected_inputs(cfg, case)
        record["input_after"] = after
        record["input_unchanged"] = inputs == after
        record["status"] = "execution_completed_QC_required" if child.returncode == 0 and inputs == after else "failed"
        citations = root / "derivatives" / stage / "logs"
        for p in citations.glob("CITATION.*"):
            destination = folder / "citations" / p.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(p, destination)
        record["ended_at"] = now()
        add_timing(record)
        dump(folder / "run.json", record)
        refresh_safely(root)
        if record["status"] == "failed":
            raise RuntimeError(f"Execution failed; see {folder / 'console.log'}")
        print(json.dumps({"status": record["status"], "record": str(folder / "run.json")}))
    except Exception as exc:
        if record is not None:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}", ended_at=now())
            add_timing(record)
            dump(folder / "run.json", record)
            refresh_safely(root)
        raise
    finally:
        lock.unlink()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("action", choices=("prepare", "intake", "run", "dry-run"))
    p.add_argument("--stage", choices=("mriqc", "fmriprep"))
    p.add_argument("--subject")
    p.add_argument("--profile", choices=("strict", "technical-extension"), default="strict")
    a = p.parse_args(argv)
    cfg = load(a.config)
    if a.action == "prepare":
        prepare(cfg)
    elif a.action == "intake":
        intake(cfg)
    else:
        cases = [c for c in cfg["runs"] if c["subject"] == a.subject]
        if len(cases) != 1 or a.stage is None:
            p.error("Select one configured subject and stage")
        if a.action == "dry-run":
            im = image_record(cfg["images"][a.stage])
            print(json.dumps(command(cfg, a.stage, cases[0], im["resolved"])[0], indent=2))
        else:
            run_stage(cfg, a.stage, cases[0], a.profile)


if __name__ == "__main__":
    main()
