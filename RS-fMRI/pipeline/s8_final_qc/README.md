# Stage 8 — Motion and anatomy QC

**What:** Extract motion measures from fMRIPrep confounds and Euler values from FreeSurfer logs.

**Output:** `motion_summary.tsv`, motion time series and `euler_summary.tsv`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python pipeline/s8_final_qc/summarize_motion_from_confounds.py \
  --derivatives-dir /ABS/fmriprep --output-dir "$DATA/qc/step8"
python pipeline/s8_final_qc/extract_euler_from_freesurfer.py \
  --freesurfer-dir /ABS/fmriprep/sourcedata/freesurfer \
  --output-tsv "$DATA/qc/step8/euler_summary.tsv"
```

[S10](../s10_xcpd_integrated_qc/README.md) collects these metrics for completed pairs and combines them with MRIQC and visual review for cohort imaging QC.

Only the first undefined FD is treated as zero. Missing/nonfinite later FD values,
negative FD or empty motion series stop summary generation.

The standalone `finalize_inclusion.py` accepts CSV or TSV MRIQC flags and writes
`included_sessions.tsv`, `excluded_sessions.tsv` and `pending_review.tsv`. Missing
Euler/MRIQC matches and incomplete metrics remain pending; an explicitly supplied
missing file is an error. Euler decisions are session-specific, with the same
project minimum of 10 distinct reference participants per site (configurable with
`--euler-min-reference-subjects`, minimum 3). The standalone command does not resolve
small-site anatomical review; use S10's documented review fields. Its tables still
require the separate source, clinical and study-specific inclusion checks.

## Evidence and limits

Sources: [Power et al. (2012)](https://doi.org/10.1016/j.neuroimage.2011.10.018); [Rosen et al. (2018)](https://doi.org/10.1016/j.neuroimage.2017.12.059). The [Stage 8 evidence record](../../06_docs/stage_evidence.md#stage-8) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
