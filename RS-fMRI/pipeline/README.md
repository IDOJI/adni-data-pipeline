# 🧭 Find a processing stage

For the copy-and-paste commands, start with the [four-stage study guide](../README.md). The numbered folders here contain the methods those commands call. Lettered stages such as 3.A and 5.D keep their original names so existing commands and run records remain traceable.

| Study stage | Processing folders |
|---|---|
| 🔎 [1 · Select scans](../stages/01-selection/README.md) | [Source quality records](s3a_source_qc/README.md) → [collection audit and date-based pairing](s3b_image_selection/README.md) |
| 📦 [2 · Download and convert](../stages/02-bids/README.md) | [IDA download](s2_download/README.md) → [dcm2niix by Image ID](s4_dcm2niix/README.md) → [Philips slice timing when needed](s4b_slice_timing/README.md) → [verify the converted image pairs](s5d_bids_identity/README.md) |
| 🧠 [3 · Process and review](../stages/03-imaging/README.md) | [Check acquisition settings](s5_post_clinica_qc/README.md) → [MRIQC](s6_mriqc/README.md) → [fMRIPrep](s7b_sessionwise_preprocessing/README.md) → [motion and surface QC](s8_final_qc/README.md) → [XCP-D and final imaging QC](s10_xcpd_integrated_qc/README.md) → [clinical checks](s9a_validate_clinical/README.md) → [eligibility](s9b_validate_inclusion/README.md) |
| 📊 [4 · Harmonize connectivity](../stages/04-harmonization/README.md) | [Fit cross-sectional ComBat on XCP-D connectivity](s14_fc_harmonization/README.md) |

The [full index](../06_docs/protocol-index.md#steps-and-commands) also covers the volume-only profile, atlas extraction, scalar export and reproducibility experiments. For sources and assumptions, see the [stage evidence register](../06_docs/stage_evidence.md).

Adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol). The original [GPL license](LICENSE) and [citation](CITATION.cff) are retained.
