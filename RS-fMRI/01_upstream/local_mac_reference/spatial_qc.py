#!/usr/bin/env python3
"""Numerical voxel checks and saved spatial review images for the new runs."""
from __future__ import annotations

import argparse
from pathlib import Path

import nibabel as nib
import numpy as np

import image_tools as images
import qc
import run as local


def inspect(cfg):
    root = local.runtime(cfg)
    output = root / "derivatives/fmriprep"
    target = root / "qc/spatial"
    target.mkdir(parents=True, exist_ok=True)
    for case in cfg["runs"]:
        execution, _ = qc.latest_run(cfg, case, "fmriprep")
        sub, ses = "sub-" + case["subject"], "ses-" + case["session"]
        case_target = target / f"{sub}_{ses}"
        case_target.mkdir(exist_ok=True)
        folder = output / sub / ses
        prefix = f"{sub}_{ses}_task-rest"
        record = {"started_at": local.now(), "case": case, "execution": str(execution),
                  "status": "running", "images": [], "mosaics": [],
                  "visual_review": "requires_saved_image_inspection"}
        manifest = case_target / "spatial_QC.json"
        local.dump(manifest, record)
        for space in ("MNI152NLin2009cAsym", "MNI152NLin6Asym"):
            series = qc.one((folder / "func").glob(f"{prefix}*space-{space}*_desc-preproc_bold.nii.gz"), "standard-space BOLD")
            mask = qc.one((folder / "func").glob(f"{prefix}*space-{space}*_desc-brain_mask.nii.gz"), "matching BOLD mask")
            stats, mean = images.stream_stats(series, mask)
            stats["file"] = str(series.relative_to(root))
            stats["space"] = space
            record["images"].append(stats)
            if stats["nonfinite_value_count"]:
                raise ValueError(f"Nonfinite values in {series}")
            path = case_target / f"{space}_mean_BOLD_mask.png"
            images.plot_mosaic(mean, path, f"{sub}/{ses}: {space}; cyan = BOLD mask",
                               contours=[(mask, "cyan")], fixed_mni=True)
            record["mosaics"].append({"file": path.name, "sha256": local.sha(path), "sources": [str(series), str(mask)]})
            t1 = qc.one((folder / "anat").glob(f"{sub}_{ses}*space-{space}*_desc-preproc_T1w.nii.gz"), "standard-space T1w")
            path = case_target / f"{space}_T1w_BOLD_alignment.png"
            images.plot_mosaic(t1, path, f"{sub}/{ses}: {space} T1w; gold = mean BOLD edges",
                               edges=[(mean, "gold")], fixed_mni=True)
            record["mosaics"].append({"file": path.name, "sha256": local.sha(path), "sources": [str(t1), str(series)]})
            template = qc.one((root / "templateflow" / f"tpl-{space}").glob(f"tpl-{space}_res-01_T1w.nii.gz"), "template T1w")
            path = case_target / f"{space}_template_T1w_alignment.png"
            images.plot_mosaic(template, path, f"{sub}/{ses}: {space} template; cyan = processed T1w edges",
                               edges=[(t1, "cyan")], fixed_mni=True)
            record["mosaics"].append({"file": path.name, "sha256": local.sha(path), "sources": [str(template), str(t1)]})
            local.dump(manifest, record)
        # Native anatomical reference and discrete tissue boundaries.
        native = qc.one((folder / "anat").glob(f"{sub}_{ses}_desc-preproc_T1w.nii.gz"), "native T1w")
        mask = qc.one((folder / "anat").glob(f"{sub}_{ses}_desc-brain_mask.nii.gz"), "native T1w mask")
        seg = qc.one((folder / "anat").glob(f"{sub}_{ses}_dseg.nii.gz"), "native tissue segmentation")
        for source in (native, mask, seg):
            if not np.isfinite(np.asanyarray(nib.load(source).dataobj)).all():
                raise ValueError(f"Nonfinite anatomical image: {source}")
        path = case_target / "native_T1w_mask_tissues.png"
        images.plot_mosaic(native, path, f"{sub}/{ses}: native T1w; cyan = mask, gold = tissue contours",
                           contours=[(mask, "cyan")], label_contours=[(seg, "gold")], cut_mask=mask)
        record["mosaics"].append({"file": path.name, "sha256": local.sha(path), "sources": [str(native), str(mask), str(seg)]})
        record.update(status="numerical_voxel_checks_completed_visual_review_required", ended_at=local.now())
        local.dump(manifest, record)
        print(f"Saved {case_target}", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.yaml"))
    a = p.parse_args()
    inspect(local.load(a.config))


if __name__ == "__main__":
    main()
