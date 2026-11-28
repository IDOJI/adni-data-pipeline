# Stage 7.D — Processing-time summary

**What:** Read existing MRIQC/fMRIPrep/XCP-D execution records and total their durations.

**Output:** `<root>/timing/attempts.tsv`, `cases.tsv`, `summary.json` and readable `*.display.tsv` tables.

## Run

From `RS-fMRI/`, after [setup](../../support/docs/installation.md). `--root` is the results root containing the run records. Add `--archive-root` only when you also want to include receipts in an existing archive. A single invocation creates a snapshot; `--watch` refreshes it until you stop that command.

```sh
python 03-imaging/processing_timing/run.py --root "$RESULTS"
```

For an optional continuous refresh:

```sh
python 03-imaging/processing_timing/run.py --root "$RESULTS" --watch --interval 30
```

To include receipts moved to an archive in a snapshot:

```sh
python 03-imaging/processing_timing/run.py \
  --root "$RESULTS" --archive-root "$DATA/archive"
```

7.B/S10 update these reports automatically. Preprocessing = MRIQC + fMRIPrep; postprocessing = XCP-D. Stage sums include retries; wall span includes waiting. Missing timings stay missing. The separate [Docker observer](../docs/processing_timing.md) measures active container time.

## Evidence and limits

Sources: [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4); [Mehta et al. (2024)](https://doi.org/10.1162/imag_a_00257). The [Stage 7.D evidence record](../../support/docs/stage_evidence.md#stage-7-d) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. This stage is operational instrumentation; no paper is claimed to validate its logs/timing as an imaging-quality measure.
