# Protocol reference

| Folder in this repository | Open it for |
|---|---|
| [Study stages](../README.md) | Each stage contains its implementation, guide and a `run.py` entry point. |
| [pipeline/](../pipeline/README.md) | Shared utilities and compatibility paths for earlier commands |
| [config/](../config) · [workflow/](../workflow) | Configuration templates and managed batch runs |
| [tests/](../tests) · [07_reproducibility/](../07_reproducibility/README.md) | Software checks and practice data |
| [docs/](.) · [provenance/](../provenance) | Setup, research methods and source history |

## Steps and commands


Click the code name for its inputs, outputs and execution command. Run commands from `RS-fMRI/` after [setup](installation.md).

| Step | Does | Produces | Code / commands |
|---|---|---|---|
| 1 | Obtain ADNI access | Approved account | [Manual portal step](../01-selection/setup_account/README.md) |
| 2 | Download images and Study Files | DICOM, metadata and clinical CSVs | [Manual portal step](../02-bids/download/README.md) |
| 3 | Inventory downloaded DICOMs | Inventory CSV and subject list | [create_dicom_dir_csv.sh](../02-bids/organize/README.md) |
| 3.A | Check source QC, NFQ and image identity | image_qc.tsv | [run.py](../01-selection/source_qc/README.md) |
| 3.B | Preserve collection images and propose T1 references by actual scan date | Row-level phase/scanner inventory, strict download list, pairing manifest and optional historical ID comparison | [run.py](../01-selection/image_selection/README.md) |
| 4 | Convert DICOM to BIDS | NIfTI, JSON and conversion records | [Convert each Image ID with dcm2niix](../02-bids/dcm2niix/README.md) |
| 4.B | Fill verified Philips SliceTiming | Updated sidecars and audit TSV | [insert_philips_slicetiming.py](../02-bids/slice_timing/README.md) |
| 5 | Optional historical mastersheet and scan-parameter checks | Mastersheet and final_heuristics.tsv | [main.py + run_session_heuristics.py](../02-bids/post_clinica_qc/README.md) |
| 5.C | Audit source eligibility and generate session lists | Subject/session CSVs | [run.py](../02-bids/validate_handoff/README.md) |
| 5.D | Verify a same-day EPI–T1 pair and scanner consistency | Binding receipt and prepared runtime | [binding.py + guarded_runner_seeded.py](../02-bids/bids_identity/README.md) |
| 6 | Measure image quality | IQM tables and HTML reports | [guarded_runner_seeded.py + iqm_seeded.py](../03-imaging/mriqc/README.md) |
| 7 | Preprocess T1w and BOLD | Aligned images, confounds and reports | [Choose the fMRIPrep profile](../03-imaging/fmriprep/README.md) |
| 7.A | Run the alternative volume/aCompCor profile | Volume derivatives and denoised BOLD | [pipeline_seeded.py](../03-imaging/volume_workflow/README.md) |
| 7.B | Run sessionwise preprocessing and deliver the pair | Volume, surface/CIFTI and FreeSurfer outputs | [run_seeded.py + publish_pairs.py](../03-imaging/sessionwise_preprocessing/README.md) |
| 7.C | Record ANTs registration progress | Iteration logs and progress.json | [run.py](../03-imaging/ants_iteration_logging/README.md) |
| 7.D | Summarize processing time | attempts.tsv, cases.tsv, summary.json | [run.py](../03-imaging/processing_timing/README.md) |
| 8 | Summarize motion and FreeSurfer Euler values | motion_summary.tsv, euler_summary.tsv | [summarize_motion_from_confounds.py](../03-imaging/final_qc/README.md) |
| 8.A | Check retained low-motion duration | paper_motion_summary.tsv and frame masks | [run.py](../03-imaging/motion_duration_qc/README.md) |
| 9 | Join imaging and cognitive scores | Merged CSV and clinical HTML plots | [build_imaging_input.py + adni_swimlane_clinical.py](../03-imaging/clinical_imaging_merge/README.md) |
| 9.A | Check diagnoses against scan dates | clinical_validation.tsv | [run.py](../03-imaging/validate_clinical/README.md) |
| 9.B | Combine source and clinical eligibility | Retained, held and excluded tables | [run.py](../03-imaging/validate_inclusion/README.md) |
| 10 | Denoise BOLD and review imaging QC | Denoised BOLD, ROI/FC, ReHo/ALFF and QC | [pipeline_seeded.py](../03-imaging/xcpd_integrated_qc/README.md) |
| 11 | Extract BOLD means with a selected atlas | timeseries.tsv and ROI coverage | [run.py](../03-imaging/atlas_bold/README.md) |
| 12 | Collect scalar metrics and report links | metrics.csv, dictionary and index.html | [lab.py export-results](../03-imaging/metrics_summary/README.md) |
| 13 | Compare isolated OMP/ITK thread trials against frozen repeat-run tolerances | Actual execution evidence, stage timings, comparison policies and HTML/JSON reports | [run.py](../03-imaging/reproducibility/README.md) |
| 14 | Audit the cross-sectional cohort and fit scanner ComBat on verified XCP-D FC | Original and adjusted edges, design, attrition, estimates and diagnostics | [lab.py harmonize-fc](../04-harmonization/fc_harmonization/README.md) |

## Run one resting-state session by hand

Start with [installation and your two paths](installation.md#paths-for-a-manual-run). Run each stage from the `RS-fMRI/` directory in the same terminal. The stage pages contain the commands, the settings to change and the files to check before continuing.

### Route A — Verified ADNI pair

[5.D · match the EPI and T1w and check intake](../02-bids/bids_identity/README.md) → [6 · run MRIQC](../03-imaging/mriqc/README.md) → [7.B · run fMRIPrep](../03-imaging/sessionwise_preprocessing/README.md) (or [7.C · run it with registration logs](../03-imaging/ants_iteration_logging/README.md)) → [8 · inspect motion and surfaces](../03-imaging/final_qc/README.md) → [8.A · check retained time](../03-imaging/motion_duration_qc/README.md) → [7.B · publish the completed pair locally](../03-imaging/sessionwise_preprocessing/README.md#publish-the-completed-pair) → [10 · denoise and verify outputs](../03-imaging/xcpd_integrated_qc/README.md).

Use this route for surface-enabled preprocessing and 36P denoising with global signal regression. To read a command, see [how 7.B corrects distortion and builds surfaces](../03-imaging/sessionwise_preprocessing/README.md#what-the-fmriprep-options-do) and [how Step 10 models noise, censors frames and computes connectivity](../03-imaging/xcpd_integrated_qc/README.md#what-the-xcp-d-options-do). For DICOM downloads, begin at [Steps 1–5](#steps-and-commands). An existing managed cohort uses its [batch controller](../03-imaging/docs/local_batch.md).

### Route B — One-session BIDS dataset

Follow [7.A · volume-only fMRIPrep and aCompCor XCP-D](../03-imaging/volume_workflow/README.md) for a BIDS session with T1w and resting BOLD. The preview guides cover [fMRIPrep volume preprocessing](../03-imaging/volume_workflow/README.md#what-the-volume-fmriprep-options-do) and [XCP-D aCompCor denoising](../03-imaging/volume_workflow/README.md#what-the-volume-xcp-d-options-do).

Use the optional [thread reproducibility experiment](../03-imaging/reproducibility/README.md)
to measure other OMP/ITK limits in isolated runs before changing production.
Its optional priority launcher uses the next eligible shared slot without waiting
for the whole production queue to finish; the shared five-subject cap remains.


## Configuration

Keep data, private configuration and results outside this repository, for example under `ADNI_DATA/config/` and `ADNI_DATA/results/`.

| Task | Configuration / guide |
|---|---|
| Collection metadata and date-based T1 proposals | [image_selection.example.json](../01-selection/config/image_selection.example.json) · [policy and evidence](../01-selection/docs/date_based_selection.md) |
| New local batch: preprocessing + XCP-D | [local_batch.seeded.example.json](../03-imaging/config/local_batch.seeded.example.json) · [commands](../03-imaging/docs/local_batch.md) |
| XCP-D for completed pairs | [xcpd_linc.seeded.example.json](../03-imaging/config/xcpd_linc.seeded.example.json) |
| Alternative volume profile | [config.seeded.example.json](../03-imaging/volume_workflow/config.seeded.example.json) |
| Post-XCP-D FC harmonization | [fc_harmonization.example.json](../04-harmonization/config/fc_harmonization.example.json) · [methods and sources](../04-harmonization/docs/fc_harmonization.md) |
| Optional thread/tolerance experiment | [thread_reproducibility.example.json](../03-imaging/config/thread_reproducibility.example.json) |
| Shared paths for optional utilities | [lab_config.example.yaml](../config/lab_config.example.yaml) · [generate YAML](installation.md#configuration) |

Check quantitative QC and native HTML reports before final inclusion. Code tests and successful processing alone do not approve research inclusion.

S10 uses `dummy_scans=auto` and the explicit `sessionwise-euler-nss-v1` policy in new seeded configurations. Nonfinite or missing QC evidence remains pending; known failures remain excluded. Euler outliers are evaluated per reconstruction/session with a participant-balanced site reference. Sites with insufficient reference subjects need documented anatomical review. Existing runtimes retain their frozen configuration; revised outputs require a fresh runtime.

## Reference

[Stage evidence and policy](stage_evidence.md) · [Studies using fMRIPrep and XCP-D](../03-imaging/docs/fmriprep_xcpd_literature.md)

[Seed settings](../03-imaging/docs/seed_reproducibility.md) · [Host requirements](platform_execution.md) · [Validation](validation.md) · [Updates](update_guide.md)

Adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3). Original [GPL license](../pipeline/LICENSE), [CITATION.cff](../pipeline/CITATION.cff) and [attribution](../NOTICE.md) are retained.
