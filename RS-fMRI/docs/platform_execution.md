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
| <a id="s1"></a>1 | [Obtain ADNI access](../01-selection/setup_account/README.md) |
| <a id="s2"></a>2 | [Download images and Study Files](../02-bids/download/README.md) |
| <a id="s3"></a>3 | [Inventory downloaded DICOMs](../02-bids/organize/README.md) |
| <a id="s3a"></a>3.A | [Check source QC, NFQ and image identity](../01-selection/source_qc/README.md) |
| <a id="s4"></a>4 | [Convert DICOM to BIDS](../02-bids/dcm2niix/README.md) |
| <a id="s4b"></a>4.B | [Fill verified Philips SliceTiming](../02-bids/slice_timing/README.md) |
| <a id="s5ab"></a>5 | [Check converted images and scan parameters](../02-bids/post_clinica_qc/README.md) |
| <a id="s5c"></a>5.C | [Create MRIQC/fMRIPrep input lists](../02-bids/validate_handoff/README.md) |
| <a id="s5d"></a>5.D | [Verify an exact EPI–T1 pair](../02-bids/bids_identity/README.md) |
| <a id="s6"></a>6 | [Measure image quality](../03-imaging/mriqc/README.md) |
| <a id="s7"></a>7 | [Preprocess T1w and BOLD](../03-imaging/fmriprep/README.md) |
| <a id="s7a"></a>7.A | [Run the alternative volume/aCompCor profile](../03-imaging/volume_workflow/README.md) |
| <a id="s7b"></a>7.B | [Run sessionwise MRIQC/fMRIPrep in Docker](../03-imaging/sessionwise_preprocessing/README.md) |
| <a id="s7c"></a>7.C | [Record ANTs registration progress](../03-imaging/ants_iteration_logging/README.md) |
| <a id="s7d"></a>7.D | [Summarize processing time](../03-imaging/processing_timing/README.md) |
| <a id="s8"></a>8 | [Summarize motion and FreeSurfer Euler values](../03-imaging/final_qc/README.md) |
| <a id="s8a"></a>8.A | [Check retained low-motion duration](../03-imaging/motion_duration_qc/README.md) |
| <a id="s9"></a>9 | [Join imaging and cognitive scores](../03-imaging/clinical_imaging_merge/README.md) |
| <a id="s9a"></a>9.A | [Check diagnoses against scan dates](../03-imaging/validate_clinical/README.md) |
| <a id="s9b"></a>9.B | [Combine source and clinical eligibility](../03-imaging/validate_inclusion/README.md) |
| <a id="s10"></a>10 | [Denoise BOLD and review imaging QC](../03-imaging/xcpd_integrated_qc/README.md) |
| <a id="s11"></a>11 | [Extract BOLD means with a selected atlas](../pipeline/s11_atlas_bold/README.md) |
| <a id="s12"></a>12 | [Collect scalar metrics and report links](../03-imaging/metrics_summary/README.md) |

## Cross-host comparison

Run the [public example](../07_reproducibility/README.md) in separate roots, then compare its numerical outputs. Synthetic CI passes do not establish a full cross-machine imaging baseline.
