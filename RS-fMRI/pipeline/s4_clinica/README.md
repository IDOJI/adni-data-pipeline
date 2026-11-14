# Stage 4 — DICOM to BIDS

**What:** Convert selected DICOMs using Clinica and dcm2niix.

**Output:** BIDS NIfTI/JSON files and conversion records under the selected BIDS output.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

In an installed Clinica environment:

```sh
clinica convert adni-to-bids -m T1 -m FMRI \
  --subjects_list "$DATA/config/subjects.txt" \
  "$DATA/LONI_download/sourcedata" \
  /ABS/clinica-conversion-tables "$DATA/rawdata"
```

For Slurm, configure `paths.slurm_template` with your cluster paths/account, then generate jobs:

```sh
mkdir -p "$(python -m utils.config_tools paths.slurm_jobs_dir --config "$PIPELINE_CONFIG")"
bash pipeline/s4_clinica/create_slurm_script_per_sub.sh --config "$PIPELINE_CONFIG"
# Submit only after reviewing the generated scripts:
bash pipeline/s4_clinica/adni_submit_slurm.sh --config "$PIPELINE_CONFIG"
```

The supplied Slurm template contains example cluster paths; edit an external copy before submission. For Philips scans, continue to [4.B](../s4b_slice_timing/README.md).
