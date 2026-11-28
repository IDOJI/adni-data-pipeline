#!/usr/bin/env python3
"""Stream voxel checks and render review mosaics; never declare scientific QC passed.

Run inside the pinned fMRIPrep image, with the dataset mounted read-only:
  python /code/qc_images.py --data-root /data --output-dir /qc \
      --subject 999S9999 --session 20250708 --stage fmriprep
Only one 3-D time point is loaded at a time. The whole 4-D series is never loaded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import uuid

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import plotting
from audit_outputs import xcpd_output_root


class QCError(ValueError):
    pass


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(2 ** 20), b""):
            result.update(chunk)
    return result.hexdigest()


def json_write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def validate_paths(data_root, output_dir):
    data_root, output_dir = Path(data_root).resolve(), Path(output_dir).resolve()
    if not data_root.is_dir():
        raise QCError(f"Data root does not exist: {data_root}")
    if data_root == output_dir or data_root in output_dir.parents or output_dir in data_root.parents:
        raise QCError("Input dataset and QC output must be disjoint directory trees")
    return data_root, output_dir


def numeric_summary(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if not values.size:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {"count": int(values.size), "min": float(values.min()),
            "median": float(np.median(values)), "max": float(values.max())}


def stream_stats(path, mask_path=None, max_working_mib=512):
    """Welford temporal variance, excluding nonfinite values voxel by voxel.

    Count all raw voxel values, including background. A supplied brain mask adds
    separate in-brain counts; zero-variance background is not classified as failure.
    Conservative workspace cap covers 3-D accumulators and plotting products,
    not the imaging runtime's baseline memory or compressed-file read index.
    """
    path = Path(path)
    before = path.stat()
    image = nib.load(path, mmap="r")
    if len(image.shape) != 4 or image.shape[3] < 2:
        raise QCError(f"Expected a 4-D time series with >=2 frames: {path}")
    shape, frames = image.shape[:3], image.shape[3]
    estimated_bytes = int(np.prod(shape)) * 96
    if estimated_bytes > max_working_mib * 2 ** 20:
        raise QCError(f"3-D workspace estimate {estimated_bytes} exceeds requested cap")
    count = np.zeros(shape, dtype=np.uint32)
    mean = np.zeros(shape, dtype=np.float64)
    m2 = np.zeros(shape, dtype=np.float64)
    mask = None
    if mask_path is not None:
        mask_img = nib.load(mask_path, mmap="r")
        if len(mask_img.shape) != 3 or mask_img.shape != shape or not np.allclose(mask_img.affine, image.affine, atol=1e-4):
            raise QCError(f"Brain mask and series grids differ: {mask_path}")
        mask = np.asarray(mask_img.dataobj) > 0
    total_nonfinite = total_nan = positive_inf = negative_inf = brain_nonfinite = 0
    minimum, maximum = np.inf, -np.inf
    per_frame = []
    for frame in range(frames):
        volume = np.asarray(image.dataobj[..., frame], dtype=np.float32)
        finite = np.isfinite(volume)
        bad = int(volume.size - np.count_nonzero(finite))
        total_nonfinite += bad
        total_nan += int(np.count_nonzero(np.isnan(volume)))
        positive_inf += int(np.count_nonzero(np.isposinf(volume)))
        negative_inf += int(np.count_nonzero(np.isneginf(volume)))
        if mask is not None:
            brain_nonfinite += int(np.count_nonzero(mask & ~finite))
        if np.any(finite):
            values = volume[finite].astype(np.float64, copy=False)
            minimum = min(minimum, float(values.min()))
            maximum = max(maximum, float(values.max()))
            delta = values - mean[finite]
            count[finite] += 1
            mean[finite] += delta / count[finite]
            m2[finite] += delta * (values - mean[finite])
        per_frame.append({"frame_zero_based": frame, "nonfinite_values": bad})
    variance = np.zeros(shape, dtype=np.float64)
    np.divide(m2, count.astype(np.float64) - 1, out=variance, where=count > 1)
    variance[count < 2] = np.nan
    mean[count == 0] = np.nan
    constant = (count >= 2) & (variance == 0)
    stats = {
        "shape": list(image.shape), "raw_volume_count": int(frames),
        "voxel_sizes": [float(v) for v in image.header.get_zooms()],
        "axis_codes": list(nib.aff2axcodes(image.affine)), "affine": image.affine.tolist(),
        "total_value_count": int(np.prod(image.shape)),
        "finite_value_count": int(np.prod(image.shape)) - total_nonfinite,
        "nonfinite_value_count": total_nonfinite, "nan_value_count": total_nan,
        "positive_infinity_value_count": positive_inf, "negative_infinity_value_count": negative_inf,
        "spatial_voxels_with_any_nonfinite_frame": int(np.count_nonzero(count < frames)),
        "all_nonfinite_spatial_voxels": int(np.count_nonzero(count == 0)),
        "constant_temporal_voxels": int(np.count_nonzero(constant)),
        "finite_signal_min": float(minimum) if np.isfinite(minimum) else None,
        "finite_signal_max": float(maximum) if np.isfinite(maximum) else None,
        "sample_temporal_variance": numeric_summary(variance),
        "per_frame": per_frame,
        "streaming": {"maximum_loaded_frames": 1, "workspace_estimate_bytes": estimated_bytes,
                      "configured_workspace_cap_mib": max_working_mib,
                      "baseline_runtime_and_compression_index_excluded": True},
    }
    if mask is not None:
        stats["brain_mask"] = {"file": str(mask_path), "voxel_count": int(mask.sum()),
                               "nonfinite_value_count": brain_nonfinite,
                               "constant_temporal_voxels": int(np.count_nonzero(mask & constant)),
                               "sample_temporal_variance": numeric_summary(variance[mask])}
    stats["sha256"] = sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise QCError(f"Image changed while QC was reading it: {path}")
    stats["bytes"] = after.st_size
    return stats, nib.Nifti1Image(mean.astype(np.float32), image.affine)


def unique_match(paths, description, required=False):
    paths = sorted(set(paths))
    if len(paths) > 1:
        raise QCError(f"Ambiguous {description}: {[str(p) for p in paths]}")
    if required and not paths:
        raise QCError(f"Missing {description}")
    return paths[0] if paths else None


def image_sidecar(path):
    return Path(str(path).removesuffix(".nii.gz").removesuffix(".nii") + ".json")


def mask_axial_cuts(mask, count=7, trim_fraction=0.10):
    """Choose world-z cuts inside the occupied brain-mask range, including oblique grids."""
    image = nib.load(mask) if isinstance(mask, (str, Path)) else mask
    if len(image.shape) != 3 or count < 2 or not 0 <= trim_fraction < 0.5:
        raise QCError("Expected a 3-D mask, >=2 cuts, and a trim fraction in [0, 0.5)")
    data = np.asarray(image.dataobj)
    indices = np.nonzero(np.isfinite(data) & (data > 0))
    if not indices[0].size:
        raise QCError("Cannot choose axial cuts from an empty brain mask")
    z = sum(image.affine[2, axis] * indices[axis] for axis in range(3)) + image.affine[2, 3]
    lower, upper = float(z.min()), float(z.max())
    if upper <= lower:
        raise QCError("Brain mask has no world-z extent")
    margin = (upper - lower) * trim_fraction
    return np.linspace(lower + margin, upper - margin, count).tolist()


def plot_mosaic(background, path, title, edges=(), contours=(), fixed_mni=False,
                label_contours=(), cut_mask=None):
    """Use intensity edges only for continuous images; discrete tissues use contours."""
    image = nib.load(background) if isinstance(background, (str, Path)) else background
    if fixed_mni:
        cuts = [-30, -15, 0, 15, 30, 45, 60]
    elif cut_mask is not None:
        cuts = mask_axial_cuts(cut_mask)
    else:
        # Nilearn chooses data-bearing slices when an integer is supplied.
        cuts = 7
    display = plotting.plot_anat(image, display_mode="z", cut_coords=cuts,
                                 title=title, draw_cross=False, annotate=True,
                                 black_bg=True, dim=0, colorbar=False)
    try:
        for img, color in edges:
            display.add_edges(img, color=color)
        for img, color in contours:
            display.add_contours(img, levels=[0.5], colors=[color], linewidths=0.6)
        for img, color in label_contours:
            # FAST labels: 1=CSF, 2=GM, 3=WM. Canny edges on label images
            # produce spurious lines and divide-by-zero warnings on empty slices.
            display.add_contours(img, levels=[1.5, 2.5], colors=[color, color], linewidths=0.6)
        display.savefig(str(path), dpi=150)
    finally:
        display.close()
        plt.close("all")
    return cuts


def process(args):
    data_root, output_dir = validate_paths(args.data_root, args.output_dir)
    subject, session = args.subject.removeprefix("sub-"), args.session.removeprefix("ses-")
    if not all(re.fullmatch(r"[A-Za-z0-9]+", v) for v in (subject, session)):
        raise QCError("Subject/session must be alphanumeric BIDS labels")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / f"sub-{subject}_ses-{session}_{args.stage}_{stamp}_{uuid.uuid4().hex[:8]}"
    target.mkdir(parents=True)
    manifest = {"created_at": utcnow(), "subject": subject, "session": session, "stage": args.stage,
                "status": "running", "review_status": "not_reviewed",
                "interpretation": "Quantitative integrity checks and visual-review aids; no scientific acceptance decision.",
                "runtime": {"python": platform.python_version(), "nibabel": nib.__version__,
                            "numpy": np.__version__, "matplotlib": matplotlib.__version__,
                            "script_sha256": sha256(Path(__file__))},
                "data_root": str(data_root), "images": [], "mosaics": [], "missing": [], "errors": []}
    json_write(target / "qc_image_manifest.json", manifest)
    prefix = f"sub-{subject}/ses-{session}"
    raw_dir = data_root / "bids" / prefix
    fprep_dir = data_root / "derivatives/fmriprep" / prefix
    xcp_dir = xcpd_output_root(data_root, subject, session) / prefix
    manifest["xcpd_output_root"] = str(xcp_dir.parent.parent)
    template = data_root / "templateflow/tpl-MNI152NLin2009cAsym/tpl-MNI152NLin2009cAsym_res-02_T1w.nii.gz"
    if args.template:
        template = Path(args.template)
    means = {}
    try:
        raw = unique_match((raw_dir / "func").glob("*_task-rest_*bold.nii*"), "raw BOLD")
        preproc = unique_match((fprep_dir / "func").glob("*_task-rest_*space-MNI152NLin2009cAsym*desc-preproc_bold.nii*"), "MNI BOLD")
        stages = [("raw", raw), ("fmriprep_mni", preproc)]
        if args.stage == "all":
            denoised = unique_match((xcp_dir / "func").glob("*_task-rest_*desc-denoised_bold.nii*"), "denoised BOLD")
            smoothed = unique_match((xcp_dir / "func").glob("*_task-rest_*desc-denoisedSmoothed_bold.nii*"), "smoothed BOLD")
            stages += [("xcpd_denoised", denoised), ("xcpd_smoothed", smoothed)]
        brain_mask = unique_match((fprep_dir / "func").glob("*_task-rest_*space-MNI152NLin2009cAsym*desc-brain_mask.nii*"), "MNI functional mask")
        for name, path in stages:
            if path is None:
                manifest["missing"].append(name)
                continue
            try:
                mask = brain_mask if name != "raw" else None
                stats, mean = stream_stats(path, mask, args.max_working_mib)
                item = {"stage": name, "file": str(path.relative_to(data_root)), **stats}
                sidecar = image_sidecar(path)
                if sidecar.is_file():
                    source_metadata = json.loads(sidecar.read_text(encoding="utf-8"))
                    item["metadata"] = {key: source_metadata[key] for key in
                                        ("RepetitionTime", "Sources", "SpatialReference", "SkullStripped", "SmoothingFWHM", "DenoisingMethod")
                                        if key in source_metadata}
                    item["sidecar_sha256"] = sha256(sidecar)
                manifest["images"].append(item)
                means[name] = mean
                # Denoised temporal means should approach zero and are unsuitable
                # as anatomical alignment backgrounds; their variance is audited.
                if name == "raw":
                    destination = target / "raw_mean_bold.png"
                    plot_mosaic(mean, destination, f"{subject} / {session}: raw mean BOLD (native)")
                    manifest["mosaics"].append({"file": destination.name, "purpose": "Native raw BOLD coverage / gross artifacts", "sources": [str(path.relative_to(data_root))]})
                if name == "fmriprep_mni":
                    destination = target / "mni_mean_bold_mask.png"
                    plot_mosaic(mean, destination, f"{subject}: MNI mean BOLD; cyan = brain mask", contours=[(brain_mask, "cyan")] if brain_mask else [], fixed_mni=True)
                    manifest["mosaics"].append({"file": destination.name, "purpose": "BOLD mask coverage", "sources": [str(path.relative_to(data_root))] + ([str(brain_mask.relative_to(data_root))] if brain_mask else [])})
            except Exception as exc:
                manifest["errors"].append({"stage": name, "error": f"{type(exc).__name__}: {exc}"})
            json_write(target / "qc_image_manifest.json", manifest)
        anat_dir = fprep_dir / "anat"
        mni_t1 = unique_match(anat_dir.glob("*space-MNI152NLin2009cAsym*desc-preproc_T1w.nii*"), "MNI T1w")
        native_t1 = unique_match([p for p in anat_dir.glob("*desc-preproc_T1w.nii*") if "_space-" not in p.name], "native T1w")
        native_mask = unique_match([p for p in anat_dir.glob("*desc-brain_mask.nii*") if "_space-" not in p.name], "native T1w mask")
        native_seg = unique_match([p for p in anat_dir.glob("*dseg.nii*") if "_space-" not in p.name], "native tissue segmentation")
        if template.is_file() and "fmriprep_mni" in means:
            destination = target / "template_bold_alignment.png"
            plot_mosaic(template, destination, f"{subject}: MNI template; gold = BOLD edges", edges=[(means["fmriprep_mni"], "gold")], fixed_mni=True)
            manifest["mosaics"].append({"file": destination.name, "purpose": "BOLD/template alignment", "sources": [str(template), str(preproc.relative_to(data_root))], "template_sha256": sha256(template)})
        if template.is_file() and mni_t1:
            destination = target / "template_t1_alignment.png"
            plot_mosaic(template, destination, f"{subject}: MNI template; cyan = T1w edges", edges=[(mni_t1, "cyan")], fixed_mni=True)
            manifest["mosaics"].append({"file": destination.name, "purpose": "T1w/template alignment", "sources": [str(template), str(mni_t1.relative_to(data_root))], "template_sha256": sha256(template)})
        if mni_t1 and "fmriprep_mni" in means:
            destination = target / "t1_bold_alignment.png"
            plot_mosaic(mni_t1, destination, f"{subject}: MNI T1w; gold = BOLD edges", edges=[(means["fmriprep_mni"], "gold")], fixed_mni=True)
            manifest["mosaics"].append({"file": destination.name, "purpose": "T1w/BOLD alignment in common MNI space", "sources": [str(mni_t1.relative_to(data_root)), str(preproc.relative_to(data_root))]})
        if native_t1:
            destination = target / "native_t1_mask_segmentation.png"
            contours = [(native_mask, "cyan")] if native_mask else []
            tissues = [(native_seg, "gold")] if native_seg else []
            cuts = plot_mosaic(native_t1, destination, f"{subject}: native T1w; cyan = mask, gold = GM/WM contours",
                               label_contours=tissues, contours=contours, cut_mask=native_mask)
            manifest["mosaics"].append({"file": destination.name, "purpose": "T1w extraction and discrete tissue boundaries",
                                       "axial_cut_coordinates_mm": cuts, "mask_range_trim_fraction": 0.10 if native_mask else None,
                                       "tissue_contour_levels": [1.5, 2.5] if native_seg else [],
                                       "sources": [str(p.relative_to(data_root)) for p in (native_t1, native_mask, native_seg) if p]})
        source_digests = {str(data_root / item["file"]): item["sha256"] for item in manifest["images"]}
        for item in manifest["mosaics"]:
            item["sha256"] = sha256(target / item["file"])
            item["source_sha256"] = {}
            for source in item["sources"]:
                source_path = Path(source) if Path(source).is_absolute() else data_root / source
                key = str(source_path)
                if key not in source_digests:
                    source_digests[key] = sha256(source_path)
                item["source_sha256"][source] = source_digests[key]
        nonfinite = sum(i["nonfinite_value_count"] for i in manifest["images"])
        manifest["nonfinite_values_across_audited_images"] = nonfinite
        manifest["status"] = "incomplete_requires_review" if manifest["missing"] or manifest["errors"] else "completed_with_findings_requires_review" if nonfinite else "completed_requires_visual_and_scientific_review"
    except Exception as exc:
        manifest["errors"].append({"error": f"{type(exc).__name__}: {exc}"})
        manifest["status"] = "failed_requires_review"
    manifest["ended_at"] = utcnow()
    json_write(target / "qc_image_manifest.json", manifest)
    print(json.dumps({"manifest": str(target / "qc_image_manifest.json"), "status": manifest["status"], "mosaics": len(manifest["mosaics"])}))
    return 2 if manifest["missing"] or manifest["errors"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--stage", choices=["fmriprep", "all"], default="all")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--max-working-mib", type=float, default=512)
    args = parser.parse_args(argv)
    try:
        return process(args)
    except (QCError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
