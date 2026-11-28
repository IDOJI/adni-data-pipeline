# Stage 6 — Measure image quality with MRIQC

MRIQC computes anatomical and functional image-quality metrics (IQMs) and native HTML reports. For a [verified pair that passed intake](../../02-bids/bids_identity/README.md), the only case-specific argument is `--config`. `CFG` points to the YAML generated for that pair. It already identifies the subject, session and input files.

The [pair runner](../../02-bids/bids_identity/guarded_runner_seeded.py) rechecks the input identity and calls the [sessionwise backend](../sessionwise_preprocessing/run_seeded.py). Preview its Docker command, then run it in the foreground:

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py dry-run --stage mriqc --config "$CFG"
```

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py run --stage mriqc --config "$CFG"
```

Open the T1w and BOLD reports under `$CASE/derivatives/mriqc/`. The latest MRIQC `run.json` in `$CASE/logs/` should show `execution_completed_QC_required`, `exit_code: 0` and `input_unchanged: true` before [7.B · fMRIPrep](../sessionwise_preprocessing/README.md). A manually configured standalone 7.B case uses `run_seeded.py --config ... run --stage mriqc --subject ...` as described in [7.B](../sessionwise_preprocessing/README.md#standalone-configuration).

For a cohort, `--config` below identifies the private IQM table configuration for the full fitting population. R fitting requires `rrobot` with `iso_seed` support. Use a new output folder.

```sh
python 04_workflow/iqm_seeded.py --config "$DATA/config/iqm-cohort.yaml" \
  --out-dir "$RESULTS/iqm-cohort" --execute
```

The cohort export preserves every observed participant/session, including rows
with incomplete metrics or a missing modality. `excluded_any` is `TRUE` for a
known outlier, `FALSE` only when all required metrics and fitted thresholds are
finite and within bounds, and `NA` for an unresolved decision. `qc_status_any`
reports `excluded`, `included` or `missing`; `qc_metrics_complete`,
`qc_missing_metrics` and `qc_invalid_thresholds` retain the reason. An established
failure remains excluded even if other metrics are missing. Supply this table
to S10 with its `sub`/`ses` columns intact; unresolved rows must not be relabeled
as included. A numerical fitting error stops fitting rather than issuing a pass.

Synthetic R regression checks cover `NA`, `NaN`, both infinities, invalid fitted
thresholds, missing T1 rows and known failures alongside missing metrics. They
exercise the decision/export functions with fixed test thresholds; they do not
validate SHASH estimation on a real cohort or approve imaging inclusion.

## Evidence and limits

Sources: [Esteban et al. (2017)](https://doi.org/10.1371/journal.pone.0184661); [Rutherford et al. (2026)](https://doi.org/10.21203/rs.3.rs-11132707/v1). The [Stage 6 evidence record](../../docs/stage_evidence.md#stage-6) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
