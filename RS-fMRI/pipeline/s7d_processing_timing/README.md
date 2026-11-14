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
