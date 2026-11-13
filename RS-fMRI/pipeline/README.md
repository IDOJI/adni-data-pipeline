# ADNI RS-fMRI pipeline

This is the single maintained implementation for this repository. Acquisition preparation, preprocessing, quality control, clinical validation and postprocessing live together in the stage directories below.

The initial structure and core scripts were adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3). This repository maintains the combined pipeline independently. Original [GPL-3.0 license](LICENSE), [citation metadata](CITATION.cff) and [citation guidance](CITATION.md) are retained; see [NOTICE](../NOTICE.md) and the [source history](../06_docs/source_integration.md).

Start with the [complete stage guide](../README.md), [installation](../06_docs/installation.md) and [fixed-seed execution guide](../06_docs/seed_reproducibility.md). New fixed-seed runs use master seed **1123** and one numerical worker thread. Existing results and deployment-bound settings keep their recorded identities.

| Stages | Responsibility |
|---|---|
| `s1_setup_account`, `s2_download` | Access and source acquisition |
| `s3_organize`, `s3a_source_qc` | Organize inputs, source QC and provenance |
| `s4_clinica`, `s4b_slice_timing` | DICOM-to-BIDS conversion and slice metadata checks |
| `s5_post_clinica_qc`, `s5c_validate_handoff`, `s5d_bids_identity` | Selection, handoff and exact EPI–T1 identity gates |
| `s6_mriqc`, `s7_fmriprep`, `s7a_volume_workflow`, `s7b_sessionwise_preprocessing` | IQMs and preprocessing; 7.A is a separate volume/aCompCor profile |
| `s7c_ants_iteration_logging`, `s7d_processing_timing` | Execution logs and timing |
| `s8_final_qc`, `s8a_motion_duration_qc` | Motion, anatomy and inclusion evidence |
| `s9_clinical_imaging_merge`, `s9a_validate_clinical`, `s9b_validate_inclusion` | Clinical linkage and reviewed research inclusion |
| `s10_xcpd_integrated_qc` | Denoising, imaging QC and postprocessing products |
| `s11_atlas_bold`, `s12_metrics_summary` | Atlas signals and scalar/report exports |

`config/`, `env/`, `utils/` and `_shared.py` support these stages. Public deployment examples are in `../03_config/`; orchestration is in `../04_workflow/`. Optional atlas libraries retain their own pinned commits and licenses. Historical notebook/local source snapshots are in `../provenance/` and are not alternate production pipelines.

Scientific selection rules, imaging profiles and validation requirements remain explicit. Folder consolidation does not establish full-cohort scientific validity or automatically rerun data. Use a new runtime for the unified source and seed 1123; do not apply it to an old work cache.
