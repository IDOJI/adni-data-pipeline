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
