# Stage 9 — Clinical score merge

**What:** Join included imaging sessions to diagnosis and cognitive-score tables.

**Output:** A merged session CSV and clinical timeline/gap HTML plots.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). `--included` takes your reviewed session table. `--mastersheet` supplies its scan-to-visit links and `--dxsum` the diagnosis history. For the plots, point each score flag at the original clinical CSV for that instrument. The files written by the two commands go under `RESULTS/clinical/`.

```sh
python pipeline/s9_clinical_imaging_merge/build_imaging_input.py \
  --included "$DATA/review/included_sessions.tsv" \
  --mastersheet "$RESULTS/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv" \
  --dxsum "$DATA/LONI_download/clindata/DXSUM.csv" \
  --output "$RESULTS/clinical/included_sessions_merged.csv"
python pipeline/s9_clinical_imaging_merge/adni_swimlane_clinical.py \
  --imaging "$RESULTS/clinical/included_sessions_merged.csv" \
  --adas "$DATA/LONI_download/clindata/ADAS.csv" \
  --mmse "$DATA/LONI_download/clindata/MMSE.csv" \
  --cdr "$DATA/LONI_download/clindata/CDR.csv" \
  --dxsum "$DATA/LONI_download/clindata/DXSUM.csv" \
  --moca "$DATA/LONI_download/clindata/MOCA.csv" \
  --save-merged "$RESULTS/clinical/merged_sessions.csv" \
  --output "$RESULTS/clinical/timeline.html" --hist-output "$RESULTS/clinical/gaps.html" \
  --combined-output "$RESULTS/clinical/combined.html"
```

Use [9.A](../s9a_validate_clinical/README.md) for scan-date diagnosis validation and [9.B](../s9b_validate_inclusion/README.md) for the final eligibility gate.
