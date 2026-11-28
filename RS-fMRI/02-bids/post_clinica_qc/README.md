# Stage 5 — Converted-image QC

**What:** Join DICOM/BIDS metadata and apply scan/session heuristics.

**Output:** A mastersheet plus `final_heuristics.tsv`, `missing_t1w.tsv` and `missing_data.tsv`.

The four-stage study command uses the [verified EPI–T1 pair check](../bids_identity/README.md) after direct conversion. This optional mastersheet workflow reads historical conversion tables.

## Run

From `RS-fMRI/`, after [setup](../../docs/installation.md). In the private YAML, `paths.clinica_bids_dir` identifies your BIDS root and `paths.clinica_conversion_info_dir` its Clinica conversion tables. The first command builds the mastersheet in a private working directory. `--input-csv` in the second command must point to that exact table.

```sh
mkdir -p "$RESULTS/qc/step5a/data"
(
  cd "$RESULTS/qc/step5a"
  python "$ADNI_PIPELINE/s5_post_clinica_qc/create_mastersheet/main.py" \
    --config "$PIPELINE_CONFIG"
)
python 02-bids/post_clinica_qc/create_report/run_session_heuristics.py \
  --input-csv "$RESULTS/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv" \
  --output-dir "$RESULTS/qc/step5"
```

The mastersheet writes `data/` beneath its working directory. Pass the resulting `final_heuristics.tsv` to [5.C](../validate_handoff/README.md).

## Evidence and limits

Sources: [Rutherford et al. (2026)](https://doi.org/10.21203/rs.3.rs-11132707/v1); [Arani et al. (2024)](https://doi.org/10.1002/alz.14162). The [Stage 5 evidence record](../../docs/stage_evidence.md#stage-5) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
