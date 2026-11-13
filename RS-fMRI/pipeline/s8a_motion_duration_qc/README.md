# Step 8.A — Retained duration after motion censoring

## Execution

```sh
python pipeline/s8a_motion_duration_qc/run.py \
  --bids-root /ABSOLUTE/PATH/ADNI_DATA/rawdata \
  --derivatives-root /ABSOLUTE/PATH/ADNI_DATA/derivatives/fmriprep \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/motion-duration-run-001
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Reads original BIDS TR/frame counts and fMRIPrep confounds, then computes retained duration and the separate non-steady-state sensitivity.

**Results:** `paper_motion_summary.tsv`, original-frame masks and `paper_motion_provenance.json` in a new external directory. Images are not edited.

## Purpose

This independent Stage imports the existing local `paper_motion_qc.py`. It checks retained time after motion exclusion, which upstream s8 does not calculate, and separately evaluates the 30%/300-second criteria from [Rutherford et al. v3](https://arxiv.org/pdf/2602.03278v3).

## Input

- Original BIDS 4D `*_bold.nii.gz` and JSON `RepetitionTime` for each run.
- FD and non-steady-state indicator columns in fMRIPrep `*_desc-confounds_timeseries.tsv`.
- The current implementation uses `sub-*/ses-*/func/` and direct JSON sidecars matching run/acq. Sessionless BIDS, inherited JSON and multi-echo variants are not automatically supported without extension and validation.

## Processing

Compare actual NIfTI frame counts, time units and TR with JSON/confounds. Calculate whether the proportion of frames with FD >0.5 mm is ≤30% and retained low-motion time is ≥300 seconds. Treat the first undefined FD as 0, as in the original tool, and preserve non-steady-state exclusion as a separate sensitivity result.

## Output

`paper_motion_summary.tsv`, per-run masks with original frame indices, and `paper_motion_provenance.json` containing input hashes, thresholds and results. Image frames are not deleted. Outputs are not automatically merged into upstream inclusion tables and do not replace MRIQC, Euler, coverage or visual QC.

## Validation

Synthetic images test exact 300-second/30% boundaries, overlapping motion/initial-frame exclusions, missing FD, TR/row-count mismatch, unchanged inputs and overwrite protection. Full-cohort scientific inclusion has not been established.

## Dependencies

Python 3.11+, NumPy, pandas and NiBabel. The initial imported code hash is recorded in `03_config/imported_sources.json`.

## macOS and Linux

The Python CLI, actual TR/frame checks, FD0.5/30%/300-second criteria and separate non-steady-state sensitivity are shared. Use real BIDS/derivative paths and a new external output directory on the selected host. This stage needs no Docker when reading existing outputs.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s8a) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
