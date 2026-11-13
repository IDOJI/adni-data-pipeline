#!/usr/bin/env python3
"""Consolidate completed execution and image-review evidence for this pilot."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import qc
import run as local


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def verify_hash(path, expected):
    require(path.is_file() and local.sha(path) == expected, f"Artifact identity mismatch: {path}")


def software_evidence():
    local_root = local.REPO / "local_mac"
    installation = read(local_root / "validation/installation.json")
    latest_path = local_root / "validation/latest-software-validation.json"
    if not latest_path.exists():
        latest_path = local_root / "validation/pilot-profile-validation-20261029.json"
    latest = read(latest_path)
    test_log = Path(latest["full_test_suite"]["log"]).resolve()
    require((local_root / "validation").resolve() in test_log.parents, "Test log is outside the validation folder")
    verify_hash(test_log, latest["full_test_suite"]["sha256"])
    for relative, expected in latest["tested_source_sha256"].items():
        source = (local_root / relative).resolve()
        require(local_root.resolve() in source.parents, "Test source is outside the local implementation")
        verify_hash(source, expected)
    return {"initial_upstream": installation["upstream_unit_tests"],
            "initial_local": installation["local_unit_tests"],
            "latest_full_suite": latest["full_test_suite"],
            "latest_validation_manifest": str(latest_path), "latest_validation_manifest_sha256": local.sha(latest_path)}


def summarize(cfg):
    root = local.runtime(cfg)
    executions = []
    for stage in ("mriqc", "fmriprep"):
        image = local.image_record(cfg["images"][stage])
        for case in cfg["runs"]:
            path, value = qc.latest_run(cfg, case, stage)
            argv, _ = local.command(cfg, stage, case, image["resolved"])
            require(value["command"] == argv and value["runner_sha256"] == local.sha(local.__file__),
                    "Execution does not match the installed runner/options")
            ended = value["container_ended_at"]
            elapsed = (datetime.fromisoformat(ended) - datetime.fromisoformat(value["started_at"])).total_seconds()
            executions.append({"stage": stage, "case": case, "profile": value["profile"],
                               "started_at": value["started_at"], "container_ended_at": ended,
                               "elapsed_seconds": elapsed, "exit_code": value["exit_code"],
                               "input_unchanged": value["input_unchanged"],
                               "execution_record": str(path.relative_to(root)), "record_sha256": local.sha(path),
                               "resolved_image": value["image"]["resolved"]})
    group_path = max((root / "logs").glob("mriqc_group_*/run.json"))
    group = read(group_path)
    require(group.get("exit_code") == 0 and group.get("IQMs_unchanged"), "MRIQC group is incomplete")
    iqm = read(root / "results/mriqc/IQM_validation.json")
    require(len(iqm["checks"]) == 2 * len(cfg["runs"]) and all(x["required_metrics_finite"] for x in iqm["checks"]),
            "MRIQC metric checks are incomplete")
    numeric_audit = read(root / "qc/mriqc_numeric_audit.json")
    require(numeric_audit["all_numeric_metrics_finite"], "Nonfinite MRIQC numeric metrics")
    fprep = read(root / "qc/fmriprep_validation.json")
    require(len(fprep["visits"]) == len(cfg["runs"]), "fMRIPrep checks are incomplete")
    spatial = []
    for case in cfg["runs"]:
        folder = root / "qc/spatial" / f"sub-{case['subject']}_ses-{case['session']}"
        value = read(folder / "spatial_QC.json")
        require(value["status"] == "numerical_voxel_checks_completed_visual_review_required", "Spatial checks are incomplete")
        require(len(value["images"]) == 2 and all(x["nonfinite_value_count"] == 0 for x in value["images"]),
                "Nonfinite or missing standard-space BOLD")
        for item in value["images"]:
            verify_hash(root / item["file"], item["sha256"])
        for item in value["mosaics"]:
            verify_hash(folder / item["file"], item["sha256"])
        spatial.append({"case": case, "manifest": str((folder / 'spatial_QC.json').relative_to(root)),
                        "images": [{k: v for k, v in x.items() if k != "per_frame"} for x in value["images"]]})
    for item in fprep["visits"]:
        verify_hash(Path(item["cifti"]["file"]), item["cifti"]["sha256"])
        for surface in item["functional_surfaces"]:
            verify_hash(root / surface["file"], surface["sha256"])
    review_checks = []
    for stage in ("mriqc", "fmriprep"):
        folder = root / "qc/report_renders" / stage
        render = read(folder / "render_manifest.json")
        for item in render["images"]:
            require(item["source_unchanged"], "A source report changed during rendering")
            verify_hash(root / item["source"], item["source_sha256"])
            verify_hash(folder / item["png"], item["png_sha256"])
        review_path = root / "qc" / f"{stage}_visual_review.json"
        review = read(review_path)
        require(len(review["reviews"]) == len(cfg["runs"]), "Missing visit visual review")
        for item in review["reviews"]:
            require(len(item["images"]) >= 3, "Visual review evidence is incomplete")
            for figure in item["images"]:
                verify_hash(root / figure["file"], figure["sha256"])
        review_checks.append({"stage": stage, "rendered_states": len(render["images"]),
                              "review_file": str(review_path.relative_to(root)), "review_sha256": local.sha(review_path)})
    final = pd.read_csv(root / "results/final_qc/pilot_final_qc_status.tsv", sep="\t", dtype={"site": str})
    require(len(final) == len(cfg["runs"]), "Final QC table lost selected visits")
    require(all(row.site == qc.site_code(row.sub) for row in final.itertuples()),
            "ADNI site identifier lost its three-digit representation")
    result = {"time": local.now(), "status": "technical_pilot_completed_research_inclusion_pending",
              "executions": executions, "MRIQC_group_record": str(group_path.relative_to(root)),
              "MRIQC_required_metrics_finite": True, "MRIQC_numeric_audit": numeric_audit,
              "fmriprep_validation": fprep,
              "spatial_checks": spatial, "saved_visual_reviews": review_checks,
              "final_QC": json.loads(final.to_json(orient="records")),
              "software_tests": software_evidence(),
              "scientific_limits": ["Two visits are not a representative MRIQC outlier or sitewise Euler reference cohort.",
                                    "ADNI4 is outside upstream phase/TR scope and was processed as a technical extension.",
                                    "Assistant image review does not replace researcher inclusion decisions.",
                                    "These outputs have spatial preprocessing and confound estimation, without XCP-D denoising."]}
    path = root / "qc/pilot_validation_summary.json"
    local.dump(path, result)
    print(json.dumps({"status": result["status"], "file": str(path), "executions": len(executions)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.yaml"))
    args = parser.parse_args()
    summarize(local.load(args.config))


if __name__ == "__main__":
    main()
