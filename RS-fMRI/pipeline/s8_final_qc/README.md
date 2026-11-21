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
