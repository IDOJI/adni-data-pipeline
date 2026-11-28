# RS-fMRI pipeline

Convert ADNI images into preprocessed/denoised BOLD, quality reports, ROI signals and analysis tables.

[Select images by acquisition date](06_docs/date_based_selection.md), then [run a verified session by hand](#run-one-resting-state-session-by-hand) or [run a local batch](06_docs/local_batch.md). To practice, use the [public or synthetic examples](07_reproducibility/README.md).

New local runs use **seed 1123**, **fMRIPrep 25.2.7**, skull stripping and **one numerical thread**. Keep a new runtime for a new seed or source version.

## Run one resting-state session by hand

Start with [installation and your two paths](06_docs/installation.md#paths-for-a-manual-run). Run each stage from the `RS-fMRI/` directory in the same terminal. The stage pages contain the commands, the settings to change and the files to check before continuing.

### Route A — Verified ADNI pair

[5.D · match the EPI and T1w and check intake](pipeline/s5d_bids_identity/README.md) → [6 · run MRIQC](pipeline/s6_mriqc/README.md) → [7.B · run fMRIPrep](pipeline/s7b_sessionwise_preprocessing/README.md) (or [7.C · run it with registration logs](pipeline/s7c_ants_iteration_logging/README.md)) → [8 · inspect motion and surfaces](pipeline/s8_final_qc/README.md) → [8.A · check retained time](pipeline/s8a_motion_duration_qc/README.md) → [7.B · publish the completed pair locally](pipeline/s7b_sessionwise_preprocessing/README.md#publish-the-completed-pair) → [10 · denoise and verify outputs](pipeline/s10_xcpd_integrated_qc/README.md).

Use this route for surface-enabled preprocessing and 36P denoising with global signal regression. To read a command, see [how 7.B corrects distortion and builds surfaces](pipeline/s7b_sessionwise_preprocessing/README.md#what-the-fmriprep-options-do) and [how Step 10 models noise, censors frames and computes connectivity](pipeline/s10_xcpd_integrated_qc/README.md#what-the-xcp-d-options-do). For DICOM downloads, begin at [Steps 1–5](#steps-and-commands). An existing managed cohort uses its [batch controller](06_docs/local_batch.md).

### Route B — One-session BIDS dataset

Follow [7.A · volume-only fMRIPrep and aCompCor XCP-D](pipeline/s7a_volume_workflow/README.md) for a BIDS session with T1w and resting BOLD. The preview guides cover [fMRIPrep volume preprocessing](pipeline/s7a_volume_workflow/README.md#what-the-volume-fmriprep-options-do) and [XCP-D aCompCor denoising](pipeline/s7a_volume_workflow/README.md#what-the-volume-xcp-d-options-do).

Use the optional [thread reproducibility experiment](pipeline/s13_reproducibility/README.md)
to measure other OMP/ITK limits in isolated runs before changing production.
Its optional priority launcher uses the next eligible shared slot without waiting
for the whole production queue to finish; the shared five-subject cap remains.

## Structure

```text
RS-fMRI/
├── pipeline/           # All stages: s1_* through s14_*
├── 03_config/          # Configuration examples
├── 04_workflow/        # Batch runners and shared tools
├── 05_tests/           # Tests
├── 06_docs/            # Setup and reference
├── 07_reproducibility/ # Runnable examples
└── provenance/         # Historical source references
```

## Steps and commands

Main flow: **1/2 metadata export → 3.A source QC → 3.B date-based proposals → image download/3/4/4.B/5 → 5.D exact binding → guarded MRIQC/fMRIPrep (6/7.B) → S8/S10 QC and XCP-D → clinical/final checks (9.A/9.B) → atlas signals (11)**. Same VISCODE is not evidence of the same acquisition date. Every Search row is audited; download requires confirmed T1w/resting BOLD; images retrieved for QC inspection are labeled separately from source-QC passes; cross-date pairs, ties and missing evidence remain held. Step 12 independently exports completed archive metrics. **7.A is an alternative profile**; 7.C/7.D provide logs and timing.

For cross-sectional FC, [Step 14](pipeline/s14_fc_harmonization/README.md) joins finalized Step 10 connectomes to Step 9.B and reviewed scanner metadata. Steps 11, 12 and 13 are optional for this route.

Click the code name for its inputs, outputs and execution command. Run commands from `RS-fMRI/` after [setup](06_docs/installation.md).

| Step | Does | Produces | Code / commands |
|---|---|---|---|
| 1 | Obtain ADNI access | Approved account | [Manual portal step](pipeline/s1_setup_account/README.md) |
| 2 | Download images and Study Files | DICOM, metadata and clinical CSVs | [Manual portal step](pipeline/s2_download/README.md) |
| 3 | Inventory downloaded DICOMs | Inventory CSV and subject list | [create_dicom_dir_csv.sh](pipeline/s3_organize/README.md) |
| 3.A | Check source QC, NFQ and image identity | image_qc.tsv | [run.py](pipeline/s3a_source_qc/README.md) |
| 3.B | Preserve collection images and propose T1 references by actual scan date | Row-level phase/scanner inventory, strict download list, pairing manifest and optional historical ID comparison | [run.py](pipeline/s3b_image_selection/README.md) |
| 4 | Convert DICOM to BIDS | NIfTI, JSON and conversion records | [Clinica / Slurm helpers](pipeline/s4_clinica/README.md) |
| 4.B | Fill verified Philips SliceTiming | Updated sidecars and audit TSV | [insert_philips_slicetiming.py](pipeline/s4b_slice_timing/README.md) |
| 5 | Check converted images and scan parameters | Mastersheet and final_heuristics.tsv | [main.py + run_session_heuristics.py](pipeline/s5_post_clinica_qc/README.md) |
| 5.C | Audit source eligibility and generate session lists | Subject/session CSVs | [run.py](pipeline/s5c_validate_handoff/README.md) |
| 5.D | Verify a same-day EPI–T1 pair and scanner consistency | Binding receipt and prepared runtime | [binding.py + guarded_runner_seeded.py](pipeline/s5d_bids_identity/README.md) |
| 6 | Measure image quality | IQM tables and HTML reports | [guarded_runner_seeded.py + iqm_seeded.py](pipeline/s6_mriqc/README.md) |
| 7 | Preprocess T1w and BOLD | Aligned images, confounds and reports | [Choose the fMRIPrep profile](pipeline/s7_fmriprep/README.md) |
| 7.A | Run the alternative volume/aCompCor profile | Volume derivatives and denoised BOLD | [pipeline_seeded.py](pipeline/s7a_volume_workflow/README.md) |
| 7.B | Run sessionwise preprocessing and deliver the pair | Volume, surface/CIFTI and FreeSurfer outputs | [run_seeded.py + publish_pairs.py](pipeline/s7b_sessionwise_preprocessing/README.md) |
| 7.C | Record ANTs registration progress | Iteration logs and progress.json | [run.py](pipeline/s7c_ants_iteration_logging/README.md) |
| 7.D | Summarize processing time | attempts.tsv, cases.tsv, summary.json | [run.py](pipeline/s7d_processing_timing/README.md) |
| 8 | Summarize motion and FreeSurfer Euler values | motion_summary.tsv, euler_summary.tsv | [summarize_motion_from_confounds.py](pipeline/s8_final_qc/README.md) |
| 8.A | Check retained low-motion duration | paper_motion_summary.tsv and frame masks | [run.py](pipeline/s8a_motion_duration_qc/README.md) |
| 9 | Join imaging and cognitive scores | Merged CSV and clinical HTML plots | [build_imaging_input.py + adni_swimlane_clinical.py](pipeline/s9_clinical_imaging_merge/README.md) |
| 9.A | Check diagnoses against scan dates | clinical_validation.tsv | [run.py](pipeline/s9a_validate_clinical/README.md) |
| 9.B | Combine source and clinical eligibility | Retained, held and excluded tables | [run.py](pipeline/s9b_validate_inclusion/README.md) |
| 10 | Denoise BOLD and review imaging QC | Denoised BOLD, ROI/FC, ReHo/ALFF and QC | [pipeline_seeded.py](pipeline/s10_xcpd_integrated_qc/README.md) |
| 11 | Extract BOLD means with a selected atlas | timeseries.tsv and ROI coverage | [run.py](pipeline/s11_atlas_bold/README.md) |
| 12 | Collect scalar metrics and report links | metrics.csv, dictionary and index.html | [lab.py export-results](pipeline/s12_metrics_summary/README.md) |
| 13 | Compare isolated OMP/ITK thread trials against frozen repeat-run tolerances | Actual execution evidence, stage timings, comparison policies and HTML/JSON reports | [run.py](pipeline/s13_reproducibility/README.md) |
| 14 | Audit the cross-sectional cohort and fit scanner ComBat on verified XCP-D FC | Original and adjusted edges, design, attrition, estimates and diagnostics | [lab.py harmonize-fc](pipeline/s14_fc_harmonization/README.md) |

## Configuration

Keep data, private configuration and results outside this repository, for example under `ADNI_DATA/config/` and `ADNI_DATA/results/`.

| Task | Configuration / guide |
|---|---|
| Collection metadata and date-based T1 proposals | [image_selection.example.json](03_config/image_selection.example.json) · [policy and evidence](06_docs/date_based_selection.md) |
| New local batch: preprocessing + XCP-D | [local_batch.seeded.example.json](03_config/local_batch.seeded.example.json) · [commands](06_docs/local_batch.md) |
| XCP-D for completed pairs | [xcpd_linc.seeded.example.json](03_config/xcpd_linc.seeded.example.json) |
| Alternative volume profile | [config.seeded.example.json](pipeline/s7a_volume_workflow/config.seeded.example.json) |
| Post-XCP-D FC harmonization | [fc_harmonization.example.json](03_config/fc_harmonization.example.json) · [methods and sources](06_docs/fc_harmonization.md) |
| Optional thread/tolerance experiment | [thread_reproducibility.example.json](03_config/thread_reproducibility.example.json) |
| DICOM/Clinica and shared paths | [lab_config.example.yaml](03_config/lab_config.example.yaml) · [generate YAML](06_docs/installation.md#configuration) |

Check quantitative QC and native HTML reports before final inclusion. Code tests and successful processing alone do not approve research inclusion.

S10 uses `dummy_scans=auto` and the explicit `sessionwise-euler-nss-v1` policy in new seeded configurations. Nonfinite or missing QC evidence remains pending; known failures remain excluded. Euler outliers are evaluated per reconstruction/session with a participant-balanced site reference. Sites with insufficient reference subjects need documented anatomical review. Existing runtimes retain their frozen configuration; revised outputs require a fresh runtime.

## Reference

[Stage evidence and policy](06_docs/stage_evidence.md) · [Studies using fMRIPrep and XCP-D](06_docs/fmriprep_xcpd_literature.md)

[Seed settings](06_docs/seed_reproducibility.md) · [Host requirements](06_docs/platform_execution.md) · [Validation](06_docs/validation.md) · [Updates](06_docs/update_guide.md)

Adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3). Original [GPL license](pipeline/LICENSE), [CITATION.cff](pipeline/CITATION.cff) and [attribution](NOTICE.md) are retained.
