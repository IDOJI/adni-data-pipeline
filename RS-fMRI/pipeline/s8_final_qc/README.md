# Stage 8 — Motion and anatomical quality

The motion script reads framewise displacement (FD) and DVARS from fMRIPrep confounds. The Euler script reads left and right hemisphere values from FreeSurfer reconstruction logs. Run these after [7.B](../s7b_sessionwise_preprocessing/README.md) succeeds.

**Motion.** `--derivatives-dir` is the fMRIPrep dataset root containing `sub-*/ses-*/func/`. `--output-dir` receives the summary and per-frame table. The paths below follow the [manual run layout](../../06_docs/installation.md#paths-for-a-manual-run).

```sh
python pipeline/s8_final_qc/summarize_motion_from_confounds.py \
  --derivatives-dir "$CASE/derivatives/fmriprep" --output-dir "$RESULTS/qc/step8"
```

**Euler values.** `--freesurfer-dir` is the parent of the reconstructed subjects. `--output-tsv` is a file. Run from the QC directory so temporary files from the optional FreeSurfer fallback stay there.

```sh
(
  cd "$RESULTS/qc/step8" &&
  python "$ADNI_PIPELINE/s8_final_qc/extract_euler_from_freesurfer.py" \
    --freesurfer-dir "$CASE/derivatives/fmriprep/sourcedata/freesurfer" \
    --output-tsv "$RESULTS/qc/step8/euler_summary.tsv"
)
```

Check `motion_summary.tsv`, `motion_timeseries.tsv` and `euler_summary.tsv` for the expected session. Missing Euler values need review. Continue to [8.A · retained duration](../s8a_motion_duration_qc/README.md).

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
