#!/usr/bin/env python3
"""Audit all numeric IQMs without inferring distributional quality thresholds."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import run as local


def numbers(value, prefix=""):
    if isinstance(value, dict):
        for name, item in value.items():
            yield from numbers(item, f"{prefix}.{name}" if prefix else name)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from numbers(item, f"{prefix}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield prefix, value


def audit(cfg):
    root = local.runtime(cfg)
    validation = json.loads((root / "results/mriqc/IQM_validation.json").read_text())
    rows = []
    for entry in validation["checks"]:
        source = root / entry["IQM_file"]
        value = json.loads(source.read_text())
        metric_values = {name: item for name, item in value.items() if name not in ("bids_meta", "provenance")}
        pairs = list(numbers(metric_values))
        rows.append({"file": entry["IQM_file"], "sha256": local.sha(source),
                     "sub": entry["sub"], "modality": entry["modality"],
                     "numeric_metric_values": len(pairs),
                     "nonfinite_keys": [name for name, item in pairs if not math.isfinite(item)]})
    record = {"time": local.now(), "scope": "All numeric MRIQC metrics, excluding metadata/provenance; no quality cutoff inferred.",
              "audit_script_sha256": local.sha(__file__), "files": rows,
              "all_numeric_metrics_finite": all(not row["nonfinite_keys"] for row in rows)}
    local.dump(root / "qc/mriqc_numeric_audit.json", record)
    if not record["all_numeric_metrics_finite"]:
        raise ValueError("Nonfinite MRIQC metrics: inspect qc/mriqc_numeric_audit.json")
    print(json.dumps({"files": len(rows), "numeric_metrics": sum(row["numeric_metric_values"] for row in rows),
                      "all_numeric_metrics_finite": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.yaml"))
    args = parser.parse_args()
    audit(local.load(args.config))


if __name__ == "__main__":
    main()
