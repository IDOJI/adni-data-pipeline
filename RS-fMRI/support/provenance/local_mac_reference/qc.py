#!/usr/bin/env python3
"""Collect actual statMIND pilot outputs and keep scientific inclusion pending.

Uses the upstream motion and Euler utilities. Does not fit cohort IQM/Euler
reference distributions from the two selected test visits.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import nibabel as nib
import numpy as np
import pandas as pd

import run as local

T1_METRICS = ("cjv", "efc", "fwhm_avg", "cnr", "snr_total", "tpm_overlap_csf", "tpm_overlap_gm", "tpm_overlap_wm")
BOLD_METRICS = ("aor", "aqi", "efc", "fd_mean", "dvars_std", "fwhm_avg", "snr", "tsnr")


def one(paths, purpose):
    paths = sorted(set(paths))
    if len(paths) != 1:
        raise ValueError(f"Expected one {purpose}, found {len(paths)}: {paths}")
    return paths[0]


def latest_run(cfg, case, stage):
    paths = sorted((local.runtime(cfg) / "logs").glob(
        f"*_{stage}_sub-{case['subject']}_ses-{case['session']}/run.json"))
    if not paths:
        raise ValueError(f"No execution record for {stage} {case['subject']}")
    path = paths[-1]
    value = json.loads(path.read_text())
    if value.get("status") != "execution_completed_QC_required" or value.get("exit_code") != 0:
        raise ValueError(f"Latest selected execution is not completed: {path}")
    if not value.get("input_unchanged") or local.selected_inputs(cfg, case) != value["input_after"]:
        raise ValueError(f"Input identity changed since execution: {path}")
    return path, value


def collect_mriqc(cfg):
    root = local.runtime(cfg)
    output = root / "derivatives/mriqc"
    all_rows, bold_rows, t1_rows, checks = [], [], [], []
    for case in cfg["runs"]:
        record_path, record = latest_run(cfg, case, "mriqc")
        prefix = f"sub-{case['subject']}_ses-{case['session']}"
        folder = output / f"sub-{case['subject']}" / f"ses-{case['session']}"
        row = {"sub": "sub-" + case["subject"], "ses": "ses-" + case["session"], "phase": case["phase"]}
        for suffix, directory, metrics in (("T1w", "anat", T1_METRICS), ("bold", "func", BOLD_METRICS)):
            path = one((folder / directory).glob(f"{prefix}*_{suffix}.json"), f"{suffix} IQMs")
            value = json.loads(path.read_text())
            selected = {m: float(value[m]) for m in metrics}
            if not all(np.isfinite(v) for v in selected.values()):
                raise ValueError(f"Missing or nonfinite required MRIQC metrics: {path}")
            report = one(output.glob(f"{prefix}*_{suffix}.html"), f"{suffix} participant HTML")
            if report.stat().st_size < 1000:
                raise ValueError(f"Incomplete MRIQC HTML report: {report}")
            ids = {"participant_id": row["sub"], "ses_id": row["ses"]}
            (t1_rows if suffix == "T1w" else bold_rows).append(
                {**ids, **{(m + "_T1w" if suffix == "T1w" else m): v for m, v in selected.items()}})
            row.update({f"{suffix}_{m}": v for m, v in selected.items()})
            checks.append({"sub": row["sub"], "ses": row["ses"], "modality": suffix,
                           "IQM_file": str(path.relative_to(root)), "IQM_sha256": local.sha(path),
                           "HTML_file": str(report.relative_to(root)), "HTML_sha256": local.sha(report),
                           "required_metrics_finite": True,
                           "execution_record": str(record_path.relative_to(root)),
                           "image": record["image"], "profile": record["profile"]})
        all_rows.append(row)
    target = root / "results/mriqc"
    target.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(target / "pilot_IQMs.tsv", sep="\t", index=False)
    pd.DataFrame(t1_rows).to_csv(target / "group_T1w_full.tsv", sep="\t", index=False)
    pd.DataFrame(bold_rows).to_csv(target / "group_bold_full.tsv", sep="\t", index=False)
    local.dump(target / "IQM_validation.json", {"time": local.now(), "checks": checks,
                "status": "technical_metric_and_report_checks_passed",
                "cohort_outlier_fit": "not_estimated_from_two_pilot_visits",
                "scientific_inclusion": "requires_representative_cohort_reference_and_visual_review"})
    print(json.dumps({"visits": len(all_rows), "validated_IQM_files": len(checks), "output": str(target)}))


def mriqc_group(cfg):
    root = local.runtime(cfg)
    for case in cfg["runs"]:
        latest_run(cfg, case, "mriqc")
    lock = root / "pipeline.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    folder = root / "logs" / ("mriqc_group_" + local.now().replace(":", "").replace(".", ""))
    folder.mkdir()
    record = {"started_at": local.now(), "status": "running", "stage": "mriqc_group"}
    try:
        image = local.image_record(cfg["images"]["mriqc"])
        output = root / "derivatives/mriqc"
        before = {str(p): local.sha(p) for p in output.glob("sub-*/ses-*/*/*.json")}
        argv = ["docker", "run", "--rm", "--platform", "linux/amd64", "--cpus", "2", "--memory", "4g",
                "--mount", f"type=bind,src={root / 'bids'},dst=/data,readonly",
                "--mount", f"type=bind,src={output},dst=/out", image["resolved"],
                "/data", "/out", "group", "--no-sub", "--notrack"]
        record.update(image=image, command=argv, IQM_hashes_before=before)
        local.dump(folder / "run.json", record)
        with (folder / "console.log").open("w") as log:
            result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=False)
        after = {str(p): local.sha(p) for p in output.glob("sub-*/ses-*/*/*.json")}
        record.update(exit_code=result.returncode, IQM_hashes_after=after, IQMs_unchanged=before == after)
        if result.returncode or before != after:
            raise ValueError("MRIQC group failed or modified participant IQMs")
        for name in ("group_T1w.tsv", "group_bold.tsv", "group_T1w.html", "group_bold.html"):
            if not (output / name).is_file():
                raise ValueError(f"Missing MRIQC group output: {name}")
        record["status"] = "execution_completed_QC_required"
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        record["ended_at"] = local.now()
        local.dump(folder / "run.json", record)
        lock.unlink()
    print(json.dumps({"status": record["status"], "record": str(folder / 'run.json')}))


def check_cifti(path, expected_frames, tr):
    image = nib.load(path)
    if not isinstance(image, nib.Cifti2Image) or len(image.shape) != 2:
        raise ValueError("Expected a dense CIFTI-2 time series")
    time_axis, brain_axis = image.header.get_axis(0), image.header.get_axis(1)
    if not isinstance(time_axis, nib.cifti2.SeriesAxis) or not isinstance(brain_axis, nib.cifti2.BrainModelAxis):
        raise ValueError("Unexpected CIFTI axes")
    if image.shape != (expected_frames, 91282) or time_axis.unit != "SECOND" or not np.isclose(time_axis.step, tr, atol=1e-5):
        raise ValueError(f"CIFTI shape/TR mismatch: {image.shape}, {time_axis.step}")
    structures = {name: len(model) for name, _, model in brain_axis.iter_structures()}
    if not {"CIFTI_STRUCTURE_CORTEX_LEFT", "CIFTI_STRUCTURE_CORTEX_RIGHT"}.issubset(structures):
        raise ValueError("Missing one or both cortical brain models")
    for cortex in ("CIFTI_STRUCTURE_CORTEX_LEFT", "CIFTI_STRUCTURE_CORTEX_RIGHT"):
        if brain_axis.nvertices[cortex] != 32492:
            raise ValueError("Expected fsLR 32k cortical surface meshes in 91k CIFTI")
    nonfinite = 0
    mean = np.zeros(image.shape[1], dtype=np.float64)
    m2 = np.zeros_like(mean)
    count = np.zeros(image.shape[1], dtype=np.uint32)
    for start in range(0, image.shape[0], 24):
        for frame in np.asarray(image.dataobj[start:start + 24], dtype=np.float64):
            finite = np.isfinite(frame)
            nonfinite += int((~finite).sum())
            delta = frame[finite] - mean[finite]
            count[finite] += 1
            mean[finite] += delta / count[finite]
            m2[finite] += delta * (frame[finite] - mean[finite])
    if nonfinite:
        raise ValueError(f"Nonfinite CIFTI values: {nonfinite}")
    return {"file": str(path), "sha256": local.sha(path), "shape": list(image.shape),
            "TR_seconds": float(time_axis.step), "time_axis_start": float(time_axis.start),
            "time_axis_unit": time_axis.unit, "brain_models": structures,
            "nonfinite_values": nonfinite, "constant_grayordinates": int((m2 == 0).sum()),
            "type": "fMRIPrep spatially_preprocessed_not_nuisance_regressed_or_bandpass_filtered"}


def check_fmriprep(cfg):
    root = local.runtime(cfg)
    output = root / "derivatives/fmriprep"
    checks = []
    for case in cfg["runs"]:
        execution, record = latest_run(cfg, case, "fmriprep")
        paths = local.paths_for(cfg, case)
        raw = nib.load(paths["bold"])
        tr = float(json.loads(paths["bold_json"].read_text())["RepetitionTime"])
        folder = output / f"sub-{case['subject']}" / f"ses-{case['session']}"
        prefix = f"sub-{case['subject']}_ses-{case['session']}_task-rest"
        confounds = one((folder / "func").glob(f"{prefix}*_desc-confounds_timeseries.tsv"), "confounds")
        frame = pd.read_csv(confounds, sep="\t")
        if len(frame) != raw.shape[3] or "framewise_displacement" not in frame:
            raise ValueError("Confound row count/FD mismatch")
        surfaces = list((folder / "func").glob(f"{prefix}*space-fsaverage*bold.func.gii"))
        if len(surfaces) != 2:
            raise ValueError(f"Expected both fsaverage hemisphere functional outputs; found {surfaces}")
        surface_details = []
        for path in surfaces:
            gii = nib.load(path)
            shape = np.asarray(gii.agg_data()).shape
            if sorted(shape) != sorted((raw.shape[3], 10242)):
                raise ValueError(f"Unexpected fsaverage 10k dimensions: {path}, {shape}")
            if not np.isfinite(gii.agg_data()).all():
                raise ValueError("Nonfinite functional surface values")
            surface_details.append({"file": str(path.relative_to(root)), "shape": list(shape), "sha256": local.sha(path)})
        cifti = one((folder / "func").glob(f"{prefix}*bold.dtseries.nii"), "91k dense CIFTI")
        cifti_details = check_cifti(cifti, raw.shape[3], tr)
        for space in ("MNI152NLin6Asym", "MNI152NLin2009cAsym"):
            image = one((folder / "func").glob(f"{prefix}*space-{space}*_desc-preproc_bold.nii.gz"), f"{space} BOLD")
            nii = nib.load(image)
            if nii.shape[3] != raw.shape[3] or not np.isclose(nii.header.get_zooms()[3], tr, atol=1e-5):
                raise ValueError("Spatial NIfTI output shape/TR mismatch")
            if nii.header.get_xyzt_units() != ("mm", "sec"):
                raise ValueError("Spatial NIfTI output must declare millimetres and seconds")
            if space == "MNI152NLin6Asym" and not np.allclose(nii.header.get_zooms()[:3], 2):
                raise ValueError("MNI152NLin6Asym output must use the requested 2-mm grid")
        report = output / f"sub-{case['subject']}.html"
        if not report.is_file() or report.stat().st_size < 1000:
            raise ValueError("Missing fMRIPrep assembled HTML report")
        fs_root = output / "sourcedata/freesurfer"
        fs_case = one(fs_root.glob(f"sub-{case['subject']}*"), "FreeSurfer subject/session directory")
        for name in ("lh.white", "rh.white", "lh.pial", "rh.pial", "lh.orig.nofix", "rh.orig.nofix"):
            if not (fs_case / "surf" / name).is_file():
                raise ValueError(f"Missing reconstructed surface: {name}")
        checks.append({"case": case, "execution": str(execution.relative_to(root)), "profile": record["profile"],
                       "input_unchanged": True, "confound_rows": len(frame), "confounds_sha256": local.sha(confounds),
                       "cifti": cifti_details, "functional_surfaces": surface_details,
                       "freesurfer_directory": str(fs_case.relative_to(root)), "HTML": str(report.relative_to(root)),
                       "status": "technical_checks_passed_visual_review_and_cohort_calibration_required"})
    local.dump(root / "qc/fmriprep_validation.json", {"time": local.now(), "visits": checks})
    print(json.dumps({"fmriprep_visits_checked": len(checks), "status": "technical_checks_passed"}))


def site_code(subject):
    value = re.sub(r"^sub-(?:ADNI)?", "", str(subject))
    match = re.match(r"(\d{3})S", value)
    if not match:
        raise ValueError(f"Cannot derive ADNI site from {subject}")
    return match.group(1)


def parse_euler_output(text):
    for line in text.splitlines():
        if re.search(r"\beuler\b", line, re.I):
            # Actual FreeSurfer output has several equals signs before the
            # final characteristic: euler # = v-e+f = ... = -136 --> 69 holes.
            match = re.search(r"=\s*(-?\d+)\s*(?:-->|$)", line)
            if match is None:
                match = re.search(r"euler\s+(?:number|characteristic)\s*[=:]\s*(-?\d+)", line, re.I)
            if match:
                return float(match.group(1))
    raise ValueError("Euler characteristic not found in FreeSurfer output")


def final_qc(cfg):
    root = local.runtime(cfg)
    output = root / "derivatives/fmriprep"
    target = root / "results/final_qc"
    target.mkdir(parents=True, exist_ok=True)
    for case in cfg["runs"]:
        latest_run(cfg, case, "fmriprep")
    local.run_logged([sys.executable, local.REPO / "s8_final_qc/summarize_motion_from_confounds.py",
                      "--derivatives-dir", output, "--output-dir", target], root / "logs/motion_summary.log")
    # The upstream log parser is tried first; local fallback below uses argv,
    # per-file stdout and a regex rather than the upstream fixed word index.
    extractor = local.import_file("upstream_euler", local.REPO / "s8_final_qc/extract_euler_from_freesurfer.py")
    euler_rows = []
    for case in cfg["runs"]:
        fs_root = output / "sourcedata/freesurfer"
        fs_case = one(fs_root.glob(f"sub-{case['subject']}*"), "FreeSurfer subject/session directory")
        log = fs_case / "scripts/recon-all.log"
        lh, rh = extractor.parse_euler_from_log(log)
        extraction = "upstream_recon_all_log_parser"
        if lh is None or rh is None:
            image = local.image_record(cfg["images"]["fmriprep"])
            values = []
            for hemi in ("lh", "rh"):
                surface = fs_case / "surf" / f"{hemi}.orig.nofix"
                argv = ["docker", "run", "--rm", "--platform", "linux/amd64", "--cpus", "1", "--memory", "1g",
                        "--mount", f"type=bind,src={surface},dst=/surface,readonly",
                        "--mount", f"type=bind,src={cfg['freesurfer_license']},dst=/license.txt,readonly",
                        "--env", "FS_LICENSE=/license.txt", "--entrypoint", "mris_euler_number",
                        image["resolved"], "/surface"]
                result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
                transcript = target / f"sub-{case['subject']}_ses-{case['session']}_{hemi}_euler.txt"
                transcript.write_text(result.stdout)
                if result.returncode:
                    raise ValueError(f"Euler extraction failed: {transcript}")
                values.append(parse_euler_output(result.stdout))
            lh, rh = values
            extraction = "same_pinned_mris_euler_number_regex_fallback"
        euler_rows.append({"fs_subject": fs_case.name, "sub": "sub-" + case["subject"],
                            "ses": "ses-" + case["session"], "site": site_code("sub-" + case["subject"]),
                            "lh_en": lh, "rh_en": rh, "avg_en": (lh + rh) / 2,
                            "extraction": extraction, "recon_all_log_sha256": local.sha(log)})
    pd.DataFrame(euler_rows).to_csv(target / "euler_summary.tsv", sep="\t", index=False)
    motion = pd.read_csv(target / "motion_summary.tsv", sep="\t")
    intake = pd.read_csv(root / "results/step5/intake_decisions.tsv", sep="\t")
    iqms = pd.read_csv(root / "results/mriqc/pilot_IQMs.tsv", sep="\t")
    result = motion.merge(pd.DataFrame(euler_rows), on=["sub", "ses"], validate="one_to_one")
    result = result.merge(intake[["sub", "ses", "strict_upstream_eligible", "failed_checks"]], on=["sub", "ses"], validate="one_to_one")
    result = result.merge(iqms, on=["sub", "ses"], validate="one_to_one")
    if len(result) != len(cfg["runs"]):
        raise ValueError("Final QC lost or duplicated one or more selected visits")
    result["motion_mean_pass"] = result["mean_fd_p"] <= 0.5
    result["motion_proportion_pass"] = result["prop_fd_p_over_thresh"] <= 0.30
    result["MRIQC_cohort_outlier_status"] = "not_calibrated_from_two_pilot_visits"
    result["Euler_site_reference_status"] = "not_calibrated_one_pilot_per_site"
    result["research_inclusion"] = np.where(result["strict_upstream_eligible"],
        "pending_representative_cohort_calibration_and_researcher_visual_QC", "outside_official_protocol_technical_extension_only")
    result.to_csv(target / "pilot_final_qc_status.tsv", sep="\t", index=False)
    local.dump(target / "final_qc_provenance.json", {"time": local.now(), "status": "pilot_QC_tests_completed_with_research_decisions_pending",
               "upstream_motion_script_sha256": local.sha(local.REPO / "s8_final_qc/summarize_motion_from_confounds.py"),
               "upstream_euler_script_sha256": local.sha(extractor.__file__),
               "motion_denominator": "All fMRIPrep frames, including initial nonsteady-state frames, matching the upstream utility.",
               "site_mapping": "Strip optional sub- and ADNI prefixes, then use the true three-digit ADNI site.",
               "outlier_policy": "No fabricated MRIQC or sitewise Euler pass from a two-visit pilot; no scientific included_sessions table promoted.",
               "processing_scope": "BIDS entry, MRIQC, fMRIPrep with surfaces/CIFTI and final QC utilities; no XCP-D denoising or clinical merge in this protocol test."})
    print(result[["sub", "ses", "mean_fd_p", "avg_en", "research_inclusion"]].to_string(index=False))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("mriqc", "group", "fmriprep", "final"))
    p.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.yaml"))
    a = p.parse_args(argv)
    cfg = local.load(a.config)
    {"mriqc": collect_mriqc, "group": mriqc_group, "fmriprep": check_fmriprep, "final": final_qc}[a.action](cfg)


if __name__ == "__main__":
    main()
