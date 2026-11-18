# Stage 3 — DICOM inventory

**What:** Inventory extracted DICOM folders and build the conversion subject list.

**Output:** `<raw_dicom_dir>/unzipped_dicom_dirs_inventory.csv` and the configured subject-list text file.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Extract your downloaded archives first. Set `paths.raw_dicom_dir` and output paths in `$PIPELINE_CONFIG`.

```sh
bash pipeline/s3_organize/create_dicom_dir_csv.sh --config "$PIPELINE_CONFIG"
bash pipeline/s3_organize/make_subject_list_for_conversions.sh --config "$PIPELINE_CONFIG"
```

Compare the inventory against the downloaded collection CSV before [conversion](../s4_clinica/README.md).

## Evidence and limits

Sources: [Gorgolewski et al. (2016)](https://doi.org/10.1038/sdata.2016.44). The [Stage 3 evidence record](../../06_docs/stage_evidence.md#stage-3) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
