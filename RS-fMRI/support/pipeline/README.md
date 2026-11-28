# 🧭 Find a processing stage

For the copy-and-paste commands, start with the [four-stage study guide](../../README.md). Implementation files live in the four study-stage directories. The historical paths here keep earlier commands and run records usable.

| Study stage | Processing folders |
|---|---|
| 🔎 [1 · Select scans](../../01-selection/README.md) | [Source quality records](../../01-selection/source_qc/README.md) → [collection audit and date-based pairing](../../01-selection/image_selection/README.md) |
| 📦 [2 · Download and convert](../../02-bids/README.md) | [IDA download](../../02-bids/download/README.md) → [dcm2niix by Image ID](../../02-bids/dcm2niix/README.md) → [Philips slice timing when needed](../../02-bids/slice_timing/README.md) → [verify the converted image pairs](../../02-bids/bids_identity/README.md) |
| 🧠 [3 · Process and review](../../03-imaging/README.md) | [Check acquisition settings](../../02-bids/post_clinica_qc/README.md) → [MRIQC](../../03-imaging/mriqc/README.md) → [fMRIPrep](../../03-imaging/sessionwise_preprocessing/README.md) → [motion and surface QC](../../03-imaging/final_qc/README.md) → [XCP-D and final imaging QC](../../03-imaging/xcpd_integrated_qc/README.md) → [clinical checks](../../03-imaging/validate_clinical/README.md) → [eligibility](../../03-imaging/validate_inclusion/README.md) |
| 📊 [4 · Harmonize connectivity](../../04-harmonization/README.md) | [Fit cross-sectional ComBat on XCP-D connectivity](../../04-harmonization/fc_harmonization/README.md) |

The [full index](../docs/protocol-index.md#steps-and-commands) also covers the volume-only profile, atlas extraction, scalar export and reproducibility experiments. For sources and assumptions, see the [stage evidence register](../docs/stage_evidence.md).

Adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol). The original [GPL license](LICENSE) and [citation](CITATION.cff) are retained.
