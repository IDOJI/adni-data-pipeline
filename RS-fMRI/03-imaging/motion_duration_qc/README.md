# Stage 8.A — Retained low-motion duration

This step matches the original BOLD frame count and repetition time to the fMRIPrep confounds. It writes a frame mask and reports whether at most 30% of frames exceed 0.5 mm FD and at least 300 seconds remain. It also reports initial non-steady-state frames separately.

Use the two inputs from the **same session**. `--bids-root` is the raw BIDS copy, `--derivatives-root` is the fMRIPrep output and `--output-dir` is a new QC directory. The [manual path setup](../../docs/installation.md#paths-for-a-manual-run) supplies `CASE` and `RESULTS`.

```sh
python 03-imaging/motion_duration_qc/run.py \
  --bids-root "$CASE/bids" --derivatives-root "$CASE/derivatives/fmriprep" \
  --output-dir "$RESULTS/qc/step8a"
```

Read `paper_motion_summary.tsv`, the frame masks and `paper_motion_provenance.json`. Keep them with the original time series. For the manual ADNI route, [publish the completed pair](../sessionwise_preprocessing/README.md#publish-the-completed-pair) before Step 10. XCP-D applies its own FD and minimum-duration thresholds.

Checks FD > 0.5 mm in ≤30% of frames and at least 300 seconds retained. Initial non-steady-state removal is reported separately. This reports masks without editing images; XCP-D uses its own censoring settings.

## Evidence and limits

Sources: [Power et al. (2012)](https://doi.org/10.1016/j.neuroimage.2011.10.018); [Rutherford et al. (2026)](https://doi.org/10.21203/rs.3.rs-11132707/v1). The [Stage 8.A evidence record](../../docs/stage_evidence.md#stage-8-a) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
