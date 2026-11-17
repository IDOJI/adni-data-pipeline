# Stage 7.D — Processing-time summary

**What:** Read existing MRIQC/fMRIPrep/XCP-D execution records and total their durations.

**Output:** `<root>/timing/attempts.tsv`, `cases.tsv`, `summary.json` and readable `*.display.tsv` tables.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python pipeline/s7d_processing_timing/run.py --root /ABS/pair-runtime
# Optional continuous refresh:
python pipeline/s7d_processing_timing/run.py --root /ABS/pair-runtime --watch --interval 30
# Include receipts moved to an archive:
python pipeline/s7d_processing_timing/run.py \
  --root /ABS/pair-runtime --archive-root /ABS/archive
```

7.B/S10 update these reports automatically. Preprocessing = MRIQC + fMRIPrep; postprocessing = XCP-D. Stage sums include retries; wall span includes waiting. Missing timings stay missing. The separate [Docker observer](../../06_docs/processing_timing.md) measures active container time.

## Evidence and limits

Sources: [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4); [Mehta et al. (2024)](https://doi.org/10.1162/imag_a_00257). The [Stage 7.D evidence record](../../06_docs/stage_evidence.md#stage-7-d) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. This stage is operational instrumentation; no paper is claimed to validate its logs/timing as an imaging-quality measure.
