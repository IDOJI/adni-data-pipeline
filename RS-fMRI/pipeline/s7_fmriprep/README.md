# Stage 7 — fMRIPrep

**What:** Preprocess T1w/BOLD, perform skull stripping and registration, and estimate confounds.

**Output:** `derivatives/fmriprep/`: preprocessed images, confounds, surfaces/CIFTI, FreeSurfer results and HTML reports.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

For new ADNI selections, complete [3.B date-based proposals](../s3b_image_selection/README.md) and [5.D exact-pair preparation/intake](../s5d_bids_identity/README.md), then use the guarded sessionwise entry point:

```sh
# Preview.
python pipeline/s5d_bids_identity/guarded_runner_seeded.py dry-run \
  --config /ABS/new-pair-runtime/verified-config.yaml --stage fmriprep
# Execute.
python pipeline/s5d_bids_identity/guarded_runner_seeded.py run \
  --config /ABS/new-pair-runtime/verified-config.yaml --stage fmriprep
```

Uses fMRIPrep 25.2.7, master seed 1123, fixed skull-stripping initialization and OMP1. Each prepared BIDS view contains exactly the verified T1 and EPI; a session filter alone can admit additional T1 images. Existing independently verified batch handoffs use the [batch runner](../../06_docs/local_batch.md). Legacy launch helpers remain for frozen configurations, not as a substitute for exact image authorization.

## Evidence and limits

Sources: [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4). The [Stage 7 evidence record](../../06_docs/stage_evidence.md#stage-7) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
