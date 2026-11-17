# Stage 6 — MRIQC

**What:** Calculate anatomical/functional image-quality metrics and HTML reports for a prepared case.

**Output:** `derivatives/mriqc/` IQM JSONs and HTML reports under the case runtime.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

For a case already prepared and accepted by [7.B](../s7b_sessionwise_preprocessing/README.md):

```sh
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml run --stage mriqc --subject ADNI999S9999
```

For cohort outlier fitting, supply full-cohort IQM tables through the R configuration:

```sh
python 04_workflow/iqm_seeded.py \
  --config /ABS/iqm-cohort.yaml --out-dir /ABS/new-iqm-results --execute
```

R fitting requires `rrobot` with `iso_seed` support. One participant is insufficient for cohort outlier thresholds. Receipt-bound pairs use the [5.D guarded runner](../s5d_bids_identity/README.md).

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
