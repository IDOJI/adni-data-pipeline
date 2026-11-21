# Stage 5 — Converted-image QC

**What:** Join DICOM/BIDS metadata and apply scan/session heuristics.

**Output:** A mastersheet plus `final_heuristics.tsv`, `missing_t1w.tsv` and `missing_data.tsv`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). In the private YAML, `paths.clinica_bids_dir` identifies your BIDS root and `paths.clinica_conversion_info_dir` its Clinica conversion tables. The first command builds the mastersheet in a private working directory. `--input-csv` in the second command must point to that exact table.

```sh
mkdir -p "$RESULTS/qc/step5a/data"
(
  cd "$RESULTS/qc/step5a"
  python "$ADNI_PIPELINE/s5_post_clinica_qc/create_mastersheet/main.py" \
    --config "$PIPELINE_CONFIG"
)
python pipeline/s5_post_clinica_qc/create_report/run_session_heuristics.py \
  --input-csv "$RESULTS/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv" \
  --output-dir "$RESULTS/qc/step5"
```

The mastersheet writes `data/` beneath its working directory. Pass the resulting `final_heuristics.tsv` to [5.C](../s5c_validate_handoff/README.md).
