# Stage 7 — Preprocess T1w and BOLD with fMRIPrep

fMRIPrep prepares the anatomy, estimates head motion, corrects distortion and aligns functional images to anatomical and standard space. It saves the aligned BOLD image, motion estimates and other potential noise signals in a confounds table. XCP-D then uses the selected columns to remove modeled noise from the time series. For example, motion correction realigns displaced volumes in space, while subsequent FD censoring removes selected time points from the denoised series.

Choose the stage that matches the intended outputs. Each linked page gives its own configuration fields, commands and verification steps.

| Input and objective | Stage to run | Where to look afterwards |
|---|---|---|
| Verified ADNI pair, FreeSurfer reconstruction and 91k CIFTI | [7.B · sessionwise fMRIPrep](../sessionwise_preprocessing/README.md) after [MRIQC](../mriqc/README.md) | `$CASE/derivatives/fmriprep/` |
| Same 7.B run with ANTs iteration logs | [7.C · logging launcher](../ants_iteration_logging/README.md) | Same derivatives plus attempt logs |
| One BIDS session, volume-only processing | [7.A · volume workflow](../volume_workflow/README.md) | Configured `fmriprep_output` |

The seeded profiles use fMRIPrep 25.2.7, seed 1123, fixed skull-stripping initialization and one numerical thread. [Seed settings](../docs/seed_reproducibility.md)

For the public profile values and what each command-line option does, see the [7.A volume options](../volume_workflow/README.md#what-the-volume-fmriprep-options-do) or the [7.B surface-enabled options](../sessionwise_preprocessing/README.md#what-the-fmriprep-options-do).

For new ADNI selections, complete [3.B date-based proposals](../../01-selection/image_selection/README.md) and [5.D exact-pair preparation](../../02-bids/bids_identity/README.md) before 7.B. The prepared BIDS view contains the verified EPI and T1w.

## Evidence and limits

Sources: [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4). The [Stage 7 evidence record](../../support/docs/stage_evidence.md#stage-7) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
