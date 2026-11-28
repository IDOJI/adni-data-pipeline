"""Read-only, geometry-aware comparisons and frozen empirical tolerance policies.

Inspired by Chatelain et al., DOI 10.1109/TC.2024.3475586. This is an
empirical repeat-run envelope, not their random-rounding statistical test.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
from pathlib import Path

import nibabel as nib
import numpy as np

SCHEMA = 1
METRICS = ("max_abs", "mae", "nrmse", "p99_abs", "disagreement")
WRITE_BOUNDARIES = {}
PATTERNS = {
    "preprocessing": [
        "preprocess/derivatives/fmriprep/sub-*/**/*_desc-preproc_T1w.nii.gz",
        "preprocess/derivatives/fmriprep/sub-*/**/*_desc-preproc_bold.nii.gz",
        "preprocess/derivatives/fmriprep/sub-*/**/*_bold.dtseries.nii",
        "preprocess/derivatives/fmriprep/sub-*/**/*_desc-brain_mask.nii.gz",
        "preprocess/derivatives/fmriprep/sub-*/**/*_dseg.nii.gz",
        "preprocess/derivatives/fmriprep/sub-*/**/*_white.surf.gii",
        "preprocess/derivatives/fmriprep/sub-*/**/*_pial.surf.gii",
    ],
    "postprocessing": [
        "postprocess/derivatives/sub-*/**/*_desc-denoised_bold.nii.gz",
        "postprocess/derivatives/sub-*/**/*_desc-denoised_bold.dtseries.nii",
        "postprocess/derivatives/sub-*/**/*_timeseries.tsv",
        "postprocess/derivatives/sub-*/**/*_relmat.tsv",
        "postprocess/derivatives/sub-*/**/*_outliers.tsv",
        "postprocess/derivatives/sub-*/**/*_motion.tsv",
        "postprocess/derivatives/sub-*/**/*_design.tsv",
        "postprocess/derivatives/sub-*/**/*_desc-linc_qc.tsv",
        "postprocess/derivatives/sub-*/**/*_stat-coverage_bold.tsv",
        "postprocess/derivatives/sub-*/**/*_boldmap.nii.gz",
        "postprocess/derivatives/sub-*/**/*_boldmap.dscalar.nii",
    ],
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def protect(root, device):
    WRITE_BOUNDARIES[Path(root).resolve()] = device


def check_write(path):
    path = Path(path).absolute()
    for root, device in WRITE_BOUNDARIES.items():
        if path == root or path.is_relative_to(root):
            if not root.is_dir() or root.stat().st_dev != device:
                raise RuntimeError("Experiment volume is unavailable or changed; no shadow directory will be created")


def save(path, value, exclusive=False):
    path = Path(path)
    check_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x") as stream:
            stream.write(payload)
    else:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(payload)
        temp.replace(path)


def read(path):
    return json.loads(Path(path).read_text())


def inventory(root):
    root = Path(root)
    result = {}
    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            for path in root.glob(pattern):
                if path.is_file():
                    result[str(path.relative_to(root))] = category
    for category in PATTERNS:
        if category not in result.values():
            raise ValueError("Missing completed " + category + " products")
    required = ("_desc-preproc_bold.nii.gz", "_bold.dtseries.nii")
    if not any(p.endswith(required) and p.startswith("preprocess/") for p in result):
        raise ValueError("Missing preprocessed BOLD")
    if not any("_desc-denoised_bold" in p for p in result):
        raise ValueError("Missing denoised BOLD")
    for suffix in ("_timeseries.tsv", "_relmat.tsv", "_outliers.tsv", "_desc-linc_qc.tsv"):
        if not any(p.startswith("postprocess/") and p.endswith(suffix) for p in result):
            raise ValueError("Missing required postprocessing product: " + suffix)
    return dict(sorted(result.items()))


def measure(a, b, categorical=False):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        raise ValueError("Array dimensions differ")
    a, b = a.astype(np.float64), b.astype(np.float64)
    for check in (np.isnan, np.isposinf, np.isneginf):
        if not np.array_equal(check(a), check(b)):
            raise ValueError("NaN/infinity locations differ")
    good = np.isfinite(a)
    if not good.any():
        raise ValueError("No finite values to compare")
    a, b = a[good], b[good]
    delta = np.abs(a - b)
    if categorical:
        return {"disagreement": float(np.mean(a != b))}
    rms = float(np.sqrt(np.mean(a * a)))
    rmse = float(np.sqrt(np.mean(delta * delta)))
    return {"max_abs": float(delta.max()), "mae": float(delta.mean()),
            "p99_abs": float(np.quantile(delta, .99)),
            "nrmse": rmse / max(rms, np.finfo(float).eps)}


def table(path):
    with Path(path).open(newline="") as stream:
        rows = list(csv.reader(stream, delimiter="\t"))
    if len(rows) < 2 or len(set(rows[0])) != len(rows[0]):
        raise ValueError("Missing rows or duplicate TSV column labels")
    if any(len(row) != len(rows[0]) for row in rows[1:]):
        raise ValueError("Ragged TSV")
    return rows[0], rows[1:]


def compare_table(left, right):
    ah, ar = table(left)
    bh, br = table(right)
    if ah != bh or len(ar) != len(br):
        raise ValueError("TSV labels/order or row count differs")
    exact_file = str(left).endswith(("_outliers.tsv", "_frames.tsv"))
    metrics = {}
    values_a, values_b = [], []
    for i, label in enumerate(ah):
        a, b = [row[i] for row in ar], [row[i] for row in br]
        identity = (not label or label.lower() in ("index", "roi", "region", "node", "name", "label", "participant_id", "volume", "frame"))
        exact = exact_file or identity or label.startswith(("num_", "non_steady_state_outlier", "motion_outlier"))
        if exact:
            if a != b:
                raise ValueError("Discrete labels, frame selections or counts differ: " + label)
            continue
        try:
            na = np.asarray([float("nan") if x in ("n/a", "NA", "") else float(x) for x in a])
            nb = np.asarray([float("nan") if x in ("n/a", "NA", "") else float(x) for x in b])
        except ValueError:
            if a != b:
                raise ValueError("Text identity differs: " + label)
            continue
        # Entirely missing coverage parcels are allowed only with identical masks.
        if np.isnan(na).all() and np.isnan(nb).all():
            continue
        metrics[label] = measure(na, nb)
        values_a.append(na)
        values_b.append(nb)
    if str(left).endswith("_relmat.tsv"):
        if not values_a or len(values_a) != len(ar):
            raise ValueError("Connectivity matrix must be square and labeled")
        aa, bb = np.asarray(values_a).T, np.asarray(values_b).T
        upper = np.triu_indices(len(ar), 1)
        metrics = {"upper_triangle": measure(aa[upper], bb[upper])}
    return metrics or {"discrete": {"disagreement": 0.0}}


def compare_product(left, right):
    if str(left).endswith(".tsv"):
        return compare_table(left, right)
    a, b = nib.load(left), nib.load(right)
    if type(a) is not type(b):
        raise ValueError("Image type or shape differs")
    if not isinstance(a, nib.gifti.GiftiImage) and a.shape != b.shape:
        raise ValueError("Image type or shape differs")
    if isinstance(a, nib.Cifti2Image):
        for i in range(a.ndim):
            if not np.all(a.header.get_axis(i) == b.header.get_axis(i)):
                raise ValueError("CIFTI brain models, labels or temporal axis differ")
    elif isinstance(a, nib.gifti.GiftiImage):
        if len(a.darrays) != len(b.darrays):
            raise ValueError("GIFTI array count differs")
        result = {}
        for i, (x, y) in enumerate(zip(a.darrays, b.darrays)):
            if x.intent != y.intent or x.coordsys.dataspace != y.coordsys.dataspace or x.coordsys.xformspace != y.coordsys.xformspace or not np.array_equal(x.coordsys.xform, y.coordsys.xform):
                raise ValueError("GIFTI intent or coordinate system differs")
            categorical = x.intent == nib.nifti1.intent_codes["NIFTI_INTENT_TRIANGLE"]
            if categorical and not np.array_equal(x.data, y.data):
                raise ValueError("Surface topology differs")
            result[str(i)] = measure(x.data, y.data, categorical)
        return result
    else:
        if not np.allclose(a.affine, b.affine, rtol=0, atol=1e-6):
            raise ValueError("Physical voxel grid differs")
        if a.header.get_xyzt_units() != b.header.get_xyzt_units() or not np.allclose(a.header.get_zooms(), b.header.get_zooms(), rtol=0, atol=1e-6):
            raise ValueError("Voxel size, TR or units differ")
    categorical = str(left).endswith(("_mask.nii.gz", "_dseg.nii.gz"))
    return {"values": measure(np.asanyarray(a.dataobj), np.asanyarray(b.dataobj), categorical)}


def completed(root):
    record = read(Path(root) / "trial.json")
    if record.get("status") != "success" or record.get("input_unchanged") is not True:
        raise ValueError("Trial is not a successful input-preserving execution")
    for stage in ("fmriprep", "xcpd"):
        execution = record.get("executions", {}).get(stage, {})
        if execution.get("exit_code") != 0 or execution.get("actual_started_at") is None:
            raise ValueError("Missing actual successful container execution: " + stage)
        if not np.isfinite(execution.get("wall_seconds", float("nan"))) or execution["wall_seconds"] <= 0:
            raise ValueError("Missing measured stage time")
    inv = inventory(root)
    expected = record.get("products_sha256", {})
    if set(inv) != set(expected):
        raise ValueError("Product inventory differs from completion receipt")
    for rel, expected_hash in expected.items():
        if sha(Path(root) / rel) != expected_hash:
            raise ValueError("Product changed after completion: " + rel)
    return record, inv


def compare(left, right):
    lr, li = completed(left)
    rr, ri = completed(right)
    if lr["analysis_identity"] != rr["analysis_identity"]:
        raise ValueError("Inputs, scientific settings, CPU budget, images or code differ")
    if li != ri:
        raise ValueError("Product inventory differs between trials")
    results = {}
    for rel in li:
        try:
            results[rel] = {"metrics": compare_product(Path(left) / rel, Path(right) / rel)}
        except (ValueError, OSError) as exc:
            results[rel] = {"error": str(exc)}
    return {"left": str(left), "right": str(right), "analysis_identity": lr["analysis_identity"],
            "products": results, "structure_pass": not any("error" in v for v in results.values())}


def calibrate(references, multiplier=1.25, floors=None):
    references = [Path(p).resolve() for p in references]
    if len(references) < 3 or len(set(references)) != len(references):
        raise ValueError("At least three distinct reference runs are required")
    if not np.isfinite(multiplier) or multiplier < 1:
        raise ValueError("Calibration multiplier must be finite and at least one")
    floors = floors or {"max_abs": 1e-6, "mae": 1e-6, "p99_abs": 1e-6, "nrmse": 1e-6, "disagreement": 0.0}
    if set(floors) != set(METRICS) or any(not np.isfinite(v) or v < 0 for v in floors.values()):
        raise ValueError("Declare finite nonnegative floors for every metric")
    records = [completed(p)[0] for p in references]
    if any(r["threads"] != 1 for r in records):
        raise ValueError("Calibration references must use one numerical thread")
    if len({r["trial_id"] for r in records}) != len(records):
        raise ValueError("Copied reference receipts are not independent executions")
    bounds = {}
    for a, b in itertools.combinations(references, 2):
        result = compare(a, b)
        if not result["structure_pass"]:
            raise ValueError("Reference structure/frame choices are unstable; review instead of relaxing tolerances")
        for product, value in result["products"].items():
            for column, values in value["metrics"].items():
                target = bounds.setdefault(product, {}).setdefault(column, {})
                for metric, observed in values.items():
                    target[metric] = max(target.get(metric, 0), floors[metric], multiplier * observed)
    policy = {"schema": SCHEMA, "method": "empirical_reference_envelope_v1", "analysis_identity": records[0]["analysis_identity"],
              "reference_receipts": {str(p): sha(p / "trial.json") for p in references},
              "reference_count": len(references), "multiplier": multiplier, "engineering_floors": floors,
              "bounds": bounds, "scope": "Technical repeatability on these inputs; scientific equivalence is not established"}
    return {**policy, "policy_sha256": digest(policy)}


def evaluate(result, policy):
    body = {k: v for k, v in policy.items() if k != "policy_sha256"}
    if digest(body) != policy.get("policy_sha256"):
        raise ValueError("Tolerance policy changed after freezing")
    for path, expected in policy["reference_receipts"].items():
        if sha(Path(path) / "trial.json") != expected:
            raise ValueError("Calibration reference receipt changed after freezing")
    if result["analysis_identity"] != policy["analysis_identity"]:
        raise ValueError("Tolerance policy is for another analysis/input")
    failures = []
    if set(result["products"]) != set(policy["bounds"]):
        failures.append("product_set")
    for product, value in result["products"].items():
        if "error" in value:
            failures.append(product + ": " + value["error"])
            continue
        bounds = policy["bounds"].get(product, {})
        if set(bounds) != set(value["metrics"]):
            failures.append(product + ": metric_columns")
        for column, values in value["metrics"].items():
            for metric, observed in values.items():
                bound = bounds.get(column, {}).get(metric)
                if bound is None or observed > bound:
                    failures.append(f"{product}:{column}:{metric}")
    return {"technical_status": "FAIL" if failures else "PASS", "failures": failures,
            "policy_sha256": policy["policy_sha256"], "scientific_equivalence": "not_established"}
