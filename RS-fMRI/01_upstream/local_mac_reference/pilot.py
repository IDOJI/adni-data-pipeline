#!/usr/bin/env python3
"""Resume and complete this two-visit installation/processing validation."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

import pandas as pd
import qc
import run as local
import spatial_qc


def finished(cfg, stage, case):
    try:
        _, record = qc.latest_run(cfg, case, stage)
    except ValueError:
        return False
    im = local.image_record(cfg["images"][stage])
    expected, _ = local.command(cfg, stage, case, im["resolved"])
    if record["command"] != expected or record["runner_sha256"] != local.sha(local.__file__):
        raise ValueError("Completed attempt has different code/options; choose a new runtime/work identity")
    return True


def profile_for(cfg, case):
    table = pd.read_csv(local.runtime(cfg) / "results/step5/intake_decisions.tsv", sep="\t")
    row = table.loc[(table["sub"] == "sub-" + case["subject"]) & (table["ses"] == "ses-" + case["session"])].iloc[0]
    if row["strict_upstream_eligible"]:
        return "strict"
    failed = row["failed_checks"]
    failures = set() if pd.isna(failed) or not str(failed).strip() else set(str(failed).split(";"))
    if case["phase"] == "ADNI4" and failures <= {"filter_invalid_repetition_time"}:
        return "technical-extension"
    raise ValueError("Visit fails additional intake rules; inspect before starting a technical extension")


def snapshot_sources(folder, config, source_dir=None):
    source_dir = Path(source_dir) if source_dir else Path(__file__).parent
    for name in ("pilot.py", "run.py", "qc.py", "spatial_qc.py", "image_tools.py"):
        shutil.copy2(source_dir / name, folder / name)
    shutil.copy2(config, folder / "config_source.yaml")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.yaml"))
    a = p.parse_args()
    cfg = local.load(a.config)
    root = local.runtime(cfg)
    folder = root / "logs" / ("pilot_" + local.now().replace(":", "").replace(".", ""))
    folder.mkdir(parents=True)
    lock = root / "orchestration.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    record = {"started_at": local.now(), "pid": os.getpid(), "status": "running", "events": [],
              "scientific_inclusion": "requires_representative_cohort_calibration_and_researcher_review"}
    snapshot_sources(folder, a.config)

    def event(action, **values):
        record["events"].append({"time": local.now(), "action": action, **values})
        local.dump(folder / "run.json", record)
        print(json.dumps(record["events"][-1]), flush=True)

    try:
        # A previously started single-stage invocation may still be finishing.
        if (root / "pipeline.lock").exists():
            event("waiting_for_existing_selected_stage")
        while (root / "pipeline.lock").exists():
            try:
                current = json.loads((root / "pipeline.lock").read_text())
            except FileNotFoundError:
                break
            try:
                os.kill(int(current["pid"]), 0)
            except ProcessLookupError as exc:
                raise ValueError("Stale execution lock: inspect before removing") from exc
            time.sleep(5)
        local.prepare(cfg)
        local.intake(cfg)
        event("BIDS_intake_completed")
        for case in cfg["runs"]:
            if finished(cfg, "mriqc", case):
                event("reuse_verified_completed_mriqc", subject=case["subject"])
            else:
                event("starting_mriqc", subject=case["subject"])
                local.run_stage(cfg, "mriqc", case, profile_for(cfg, case))
                event("completed_mriqc", subject=case["subject"])
        qc.collect_mriqc(cfg)
        qc.mriqc_group(cfg)
        event("MRIQC_metrics_and_group_reports_completed")
        for case in cfg["runs"]:
            if finished(cfg, "fmriprep", case):
                event("reuse_verified_completed_fmriprep", subject=case["subject"])
            else:
                event("starting_fmriprep_surfaces_and_91k", subject=case["subject"])
                local.run_stage(cfg, "fmriprep", case, profile_for(cfg, case))
                event("completed_fmriprep", subject=case["subject"])
        qc.check_fmriprep(cfg)
        qc.final_qc(cfg)
        event("CIFTI_surface_motion_and_Euler_checks_completed")
        spatial_qc.inspect(cfg)
        event("spatial_numerical_checks_and_mosaics_completed")
        record["status"] = "processing_and_numerical_validation_completed_visual_review_required"
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        record["ended_at"] = local.now()
        local.dump(folder / "run.json", record)
        lock.unlink()


if __name__ == "__main__":
    main()
