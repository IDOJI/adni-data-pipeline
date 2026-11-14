# Stage 5 — Converted-image QC

**What:** Join DICOM/BIDS metadata and apply scan/session heuristics.

**Output:** A mastersheet plus `final_heuristics.tsv`, `missing_t1w.tsv` and `missing_data.tsv`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
mkdir -p "$DATA/qc/step5a"
(
  cd "$DATA/qc/step5a"
  python "$ADNI_PIPELINE/s5_post_clinica_qc/create_mastersheet/main.py" \
    --config "$PIPELINE_CONFIG"
)
python pipeline/s5_post_clinica_qc/create_report/run_session_heuristics.py \
  --input-csv "$DATA/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv" \
  --output-dir "$DATA/qc/step5"
```

The mastersheet writes `data/` beneath its working directory. Pass the resulting `final_heuristics.tsv` to [5.C](../s5c_validate_handoff/README.md).
