# Stage 7.D — Processing-time summary

**What:** Read existing MRIQC/fMRIPrep/XCP-D execution records and total their durations.

**Output:** `<root>/timing/attempts.tsv`, `cases.tsv`, `summary.json` and readable `*.display.tsv` tables.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). `--root` is the results root containing the run records. Add `--archive-root` only when you also want to include receipts in an existing archive. A single invocation creates a snapshot; `--watch` refreshes it until you stop that command.

```sh
python pipeline/s7d_processing_timing/run.py --root "$RESULTS"
```

For an optional continuous refresh:

```sh
python pipeline/s7d_processing_timing/run.py --root "$RESULTS" --watch --interval 30
```

To include receipts moved to an archive in a snapshot:

```sh
python pipeline/s7d_processing_timing/run.py \
  --root "$RESULTS" --archive-root "$DATA/archive"
```

7.B/S10 update these reports automatically. Preprocessing = MRIQC + fMRIPrep; postprocessing = XCP-D. Stage sums include retries; wall span includes waiting. Missing timings stay missing. The separate [Docker observer](../../06_docs/processing_timing.md) measures active container time.
