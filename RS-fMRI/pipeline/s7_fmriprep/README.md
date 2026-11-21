# Stage 7 — Preprocess T1w and BOLD with fMRIPrep

fMRIPrep estimates head motion, corrects distortion and registers the functional images to anatomical and standard space. Its outputs include preprocessed BOLD, confounds for denoising and an HTML registration report.

Choose the stage that matches the intended outputs. Each linked page gives its own configuration fields, commands and verification steps.

| Input and objective | Stage to run | Where to look afterwards |
|---|---|---|
| Verified ADNI pair, FreeSurfer reconstruction and 91k CIFTI | [7.B · sessionwise fMRIPrep](../s7b_sessionwise_preprocessing/README.md) after [MRIQC](../s6_mriqc/README.md) | `$CASE/derivatives/fmriprep/` |
| Same 7.B run with ANTs iteration logs | [7.C · logging launcher](../s7c_ants_iteration_logging/README.md) | Same derivatives plus attempt logs |
| One BIDS session, volume-only processing | [7.A · volume workflow](../s7a_volume_workflow/README.md) | Configured `fmriprep_output` |

The seeded profiles use fMRIPrep 25.2.7, seed 1123, fixed skull-stripping initialization and one numerical thread. [Seed settings](../../06_docs/seed_reproducibility.md)
