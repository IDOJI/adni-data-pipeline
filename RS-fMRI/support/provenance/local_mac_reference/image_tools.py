"""Reused, previously tested imaging QC helpers; standalone local copy.
Source: adni-rsfmri-pipeline/qc_images.py
Source SHA-256: 4f22b7419efb7b72c48b02e9ee912c53f1dcf7effe5d4c2717c090c07ff683bd
"""
from pathlib import Path
import hashlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import plotting

class QCError(ValueError):
    pass

def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(2 ** 20), b""):
            result.update(chunk)
    return result.hexdigest()

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
