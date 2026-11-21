# Stage 6 — Measure image quality with MRIQC

MRIQC computes anatomical and functional image-quality metrics (IQMs) and native HTML reports. For a [verified pair that passed intake](../s5d_bids_identity/README.md), the only case-specific argument is `--config`. `CFG` points to the YAML generated for that pair. It already identifies the subject, session and input files.

The [pair runner](../s5d_bids_identity/guarded_runner_seeded.py) rechecks the input identity and calls the [sessionwise backend](../s7b_sessionwise_preprocessing/run_seeded.py). Preview its Docker command, then run it in the foreground:

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py dry-run --stage mriqc --config "$CFG"
```

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py run --stage mriqc --config "$CFG"
```

Open the T1w and BOLD reports under `$CASE/derivatives/mriqc/`. The latest MRIQC `run.json` in `$CASE/logs/` should show `execution_completed_QC_required`, `exit_code: 0` and `input_unchanged: true` before [7.B · fMRIPrep](../s7b_sessionwise_preprocessing/README.md). A manually configured standalone 7.B case uses `run_seeded.py --config ... run --stage mriqc --subject ...` as described in [7.B](../s7b_sessionwise_preprocessing/README.md#standalone-configuration).

For a cohort, `--config` below identifies the private IQM table configuration for the full fitting population. R fitting requires `rrobot` with `iso_seed` support. Use a new output folder.

```sh
python 04_workflow/iqm_seeded.py --config "$DATA/config/iqm-cohort.yaml" \
  --out-dir "$RESULTS/iqm-cohort" --execute
```
