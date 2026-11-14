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
