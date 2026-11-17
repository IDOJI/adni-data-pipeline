# Stage 8.A — Retained duration

**What:** Check low-motion time using actual BOLD TR/frame counts and fMRIPrep confounds.

**Output:** `paper_motion_summary.tsv`, original-frame masks and `paper_motion_provenance.json`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python pipeline/s8a_motion_duration_qc/run.py \
  --bids-root "$DATA/rawdata" --derivatives-root /ABS/fmriprep \
  --output-dir "$DATA/qc/motion-duration-run-001"
```

Checks FD > 0.5 mm in ≤30% of frames and at least 300 seconds retained. Initial non-steady-state removal is reported separately. This reports masks without editing images; XCP-D uses its own censoring settings.

## Evidence and limits

Sources: [Power et al. (2012)](https://doi.org/10.1016/j.neuroimage.2011.10.018); [Rutherford et al. (2026)](https://doi.org/10.21203/rs.3.rs-11132707/v1). The [Stage 8.A evidence record](../../06_docs/stage_evidence.md#stage-8-a) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
