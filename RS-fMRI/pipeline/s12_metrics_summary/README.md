# Stage 12 — Scalar table and report links

**What:** Read calculated values from verified S10 archives and export one row per pair/run.

**Output:** Per-pair `results/metrics.csv`, `metrics.tsv`, `metrics_dictionary.csv`, `export_manifest.json` and `index.html`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python 04_workflow/lab.py export-results \
  --archive-root /ABS/archive --status /ABS/runtime/metrics-status.json
```

Add `--watch` to scan for new completed archives every 120 seconds. The direct equivalent is:

```sh
python pipeline/s12_metrics_summary/run.py \
  --archive-root /ABS/archive --status /ABS/runtime/metrics-status.json
```

Includes FreeSurfer volumes/thickness, S8/XCP-D QC and regional ReHo/ALFF/coverage. Open `results/index.html` for native report links. Missing values remain NA; time series and FC matrices stay in their original files. Step 11 is not required.
