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

## Evidence and limits

Sources: [Fischl et al. (2002)](https://pubmed.ncbi.nlm.nih.gov/11832223/); [Fischl and Dale (2000)](https://doi.org/10.1073/pnas.200033797); [Zang et al. (2004)](https://doi.org/10.1016/j.neuroimage.2003.12.030); [Zang et al. (2007)](https://doi.org/10.1016/j.braindev.2006.07.002); [Mehta et al. (2024)](https://doi.org/10.1162/imag_a_00257). The [Stage 12 evidence record](../../06_docs/stage_evidence.md#stage-12) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
