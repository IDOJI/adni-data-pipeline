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

## Reconcile conversion with the image inventory

Create the [3.B image inventory](../s3b_image_selection/README.md) before interpreting conversion output as the complete candidate set. Clinica can select only one image per participant/visit/modality; a participant list does not force conversion of the exact Image IDs proposed by 3.B. Its selection rules and supported ADNI phases are described in the [official converter documentation](https://aramislab.paris.inria.fr/clinica/docs/public/latest/Converters/ADNI2BIDS/).

Keep the original collection exports and conversion records. Reconcile each proposed EPI/T1 Image ID, actual date and series UID with the resulting BIDS files, then supply independent conversion/hash evidence to [5.D](../s5d_bids_identity/README.md). Multiple EPI images with the same VISCODE must remain separately auditable. Missing proposed images stay held; do not substitute another scan or relabel a different acquisition to satisfy the proposal.

The existing converter helpers do not guarantee conversion of every image in the all-date reference pool. Recovering an omitted candidate requires a reviewed conversion path and new identity evidence. Neither successful conversion nor an existing T1 file approves pairing, registration quality or scientific inclusion.
