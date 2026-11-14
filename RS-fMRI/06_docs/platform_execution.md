# Host requirements and stage commands

## Common setup

Follow [installation and path setup](installation.md). Use the same inputs, source revision, container digests, seed 1123 and analysis profile when comparing computers.

| Task | macOS | Linux |
|---|---|---|
| QC, clinical, atlas and export Python tools | Python environment | Same commands |
| Single-case/public imaging | Docker Desktop | Docker Engine |
| Slurm/Apptainer scripts | Configured cluster required | Configured cluster required |
| Batch publisher/controller and disk offloader | macOS implementation | Copy, service and volume-check adapters required |

## macOS

Docker uses `linux/amd64` images; Apple Silicon uses emulation. Allow access to external bind-mount paths and provide enough Docker VM memory for the configured containers.

## Linux

Use the same pinned `linux/amd64` images. Replace host paths with local Linux paths. Installing Docker does not port the macOS batch publisher (`cp -cR`), keep-awake controller or disk checks (`diskutil`).

```sh
python3 --version
docker info --format '{{.OSType}} / {{.Architecture}}'
```

## Stage commands

Each link gives the function, outputs and commands; no separate command copy is maintained here.

| Step | Guide |
|---|---|
| <a id="s1"></a>1 | [Obtain ADNI access](../pipeline/s1_setup_account/README.md) |
| <a id="s2"></a>2 | [Download images and Study Files](../pipeline/s2_download/README.md) |
| <a id="s3"></a>3 | [Inventory downloaded DICOMs](../pipeline/s3_organize/README.md) |
| <a id="s3a"></a>3.A | [Check source QC, NFQ and image identity](../pipeline/s3a_source_qc/README.md) |
| <a id="s4"></a>4 | [Convert DICOM to BIDS](../pipeline/s4_clinica/README.md) |
| <a id="s4b"></a>4.B | [Fill verified Philips SliceTiming](../pipeline/s4b_slice_timing/README.md) |
| <a id="s5ab"></a>5 | [Check converted images and scan parameters](../pipeline/s5_post_clinica_qc/README.md) |
| <a id="s5c"></a>5.C | [Create MRIQC/fMRIPrep input lists](../pipeline/s5c_validate_handoff/README.md) |
| <a id="s5d"></a>5.D | [Verify an exact EPI–T1 pair](../pipeline/s5d_bids_identity/README.md) |
| <a id="s6"></a>6 | [Measure image quality](../pipeline/s6_mriqc/README.md) |
| <a id="s7"></a>7 | [Preprocess T1w and BOLD](../pipeline/s7_fmriprep/README.md) |
| <a id="s7a"></a>7.A | [Run the alternative volume/aCompCor profile](../pipeline/s7a_volume_workflow/README.md) |
| <a id="s7b"></a>7.B | [Run sessionwise MRIQC/fMRIPrep in Docker](../pipeline/s7b_sessionwise_preprocessing/README.md) |
| <a id="s7c"></a>7.C | [Record ANTs registration progress](../pipeline/s7c_ants_iteration_logging/README.md) |
| <a id="s7d"></a>7.D | [Summarize processing time](../pipeline/s7d_processing_timing/README.md) |
| <a id="s8"></a>8 | [Summarize motion and FreeSurfer Euler values](../pipeline/s8_final_qc/README.md) |
| <a id="s8a"></a>8.A | [Check retained low-motion duration](../pipeline/s8a_motion_duration_qc/README.md) |
| <a id="s9"></a>9 | [Join imaging and cognitive scores](../pipeline/s9_clinical_imaging_merge/README.md) |
| <a id="s9a"></a>9.A | [Check diagnoses against scan dates](../pipeline/s9a_validate_clinical/README.md) |
| <a id="s9b"></a>9.B | [Combine source and clinical eligibility](../pipeline/s9b_validate_inclusion/README.md) |
| <a id="s10"></a>10 | [Denoise BOLD and review imaging QC](../pipeline/s10_xcpd_integrated_qc/README.md) |
| <a id="s11"></a>11 | [Extract BOLD means with a selected atlas](../pipeline/s11_atlas_bold/README.md) |
| <a id="s12"></a>12 | [Collect scalar metrics and report links](../pipeline/s12_metrics_summary/README.md) |

## Cross-host comparison

Run the [public example](../07_reproducibility/README.md) in separate roots, then compare its numerical outputs. Synthetic CI passes do not establish a full cross-machine imaging baseline.
