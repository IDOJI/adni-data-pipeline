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
