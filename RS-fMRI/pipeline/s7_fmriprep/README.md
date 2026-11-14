# Stage 7 — fMRIPrep

**What:** Preprocess T1w/BOLD, perform skull stripping and registration, and estimate confounds.

**Output:** `derivatives/fmriprep/`: preprocessed images, confounds, surfaces/CIFTI, FreeSurfer results and HTML reports.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Use the sessionwise Docker entry point after [7.B preparation](../s7b_sessionwise_preprocessing/README.md):

```sh
# Preview.
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml dry-run --stage fmriprep --subject ADNI999S9999
# Execute.
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml run --stage fmriprep --subject ADNI999S9999
```

Uses fMRIPrep 25.2.7, master seed 1123, fixed skull-stripping initialization and OMP1. Receipt-bound pairs use [5.D](../s5d_bids_identity/README.md); whole batches use the [batch runner](../../06_docs/local_batch.md).
