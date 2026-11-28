# 🧠 Resting-state fMRI in four stages

[🔎 Select scans](#select) → [📦 Download and convert](#convert) → [🧠 Process and review](#process) → [📊 Harmonize connectivity](#harmonize)

You can use the same study-folder path for all four stages. If you already have BIDS or finalized XCP-D results, use the shortcut in the relevant stage.

<a id="setup"></a>

## 🗂️ Set up your study folder

Complete [installation](06_docs/installation.md) once. In a terminal, go to this repository's **RS-fMRI** folder and activate its Python environment. Change the *one* study path below to a private folder on your computer. Keep the quotes if its name contains spaces.

```sh
# From the top of the cloned repository
cd RS-fMRI
source .venv/bin/activate
export STUDY="/absolute/path/to/my ADNI study"
mkdir -p "$STUDY/collections" "$STUDY/LONI_download/clindata" "$STUDY/review"
```

Keep using this terminal. In a new terminal, return to this directory, activate the environment and set the same `STUDY` again. The scripts read these locations by default.

```text
Your private study folder/
├── collections/             T1.csv and EPI.csv exported from ADNI
├── LONI_download/
│   ├── clindata/            ADNI Study Files (CSV)
│   └── sourcedata/          Extracted DICOMs, starting with the participant folders
├── review/                  Conversion evidence, reviewed exclusions and scanner labels
├── license.txt              Your FreeSurfer license (stage 3)
├── templateflow/            Populated local template cache (stage 3)
├── 01-selection/            Created by stage 1
├── 02-bids/                 Created by stage 2
├── 03-imaging/              Created by stage 3
└── 04-harmonization/        Created by stage 4
```

<a id="select"></a>

## 1 · 🔎 Select the scans

**Bring** the two IDA collection CSVs and the original ADNI source-quality tables. Use `collections/T1.csv` for structural scans and `collections/EPI.csv` for resting-state scans. Include **Phase**, **acquisition date**, **Image ID**, **participant ID** and description in each export. Include **Age at the scan** if you plan to harmonize connectivity. Place `MRIQC.csv`, `MAYO_ADNI3.csv`, `MAYO_GO2.csv`, `DELMRSCANS.csv` and `NFQ.csv` in `LONI_download/clindata/`. Here `MRIQC.csv` is a table supplied by ADNI. The MRIQC software runs in stage 3.

```sh
python start/01_select.py "$STUDY"
```

**Open** `01-selection/images/09.download-candidates.txt` for the IDs to request. The script checks source QC and proposes a structural reference by actual scan date. `05.pairing-review.csv` explains uncertain matches. `10.download-for-qc-review.csv` identifies images that can be retrieved for inspection but still need quality evidence. Different export filenames? Pass their paths, for example `--t1 "/path/to/structural.csv" --epi "/path/to/rest.csv"`. [Selection details](pipeline/s3b_image_selection/README.md)

<a id="convert"></a>

## 2 · 📦 Download the images and convert them to BIDS

**In the ADNI portal**, sign in and download the Image IDs from stage 1 in DICOM format. Extract them under `LONI_download/sourcedata/<participant>/<series>/<date>/<ImageID>/`. Put Clinica's required clinical/conversion Study Files in `clindata/` alongside the quality tables. Install Clinica and dcm2niix so the terminal can find both programs. [Clinica's download and conversion guide](https://aramislab.paris.inria.fr/clinica/docs/public/latest/Converters/ADNI2BIDS/)

```sh
python start/02_bids.py "$STUDY" convert
```

**Check the conversion**, then run the second command. Use the converter's source records to reconcile ID, participant, date and series UID. Supply your independently recorded fingerprints in `review/conversion-hashes.csv` with columns `SOURCE_PTID,STUDY_DATE,MODALITY,SOURCE_IMAGE_ID,NIFTI_SHA256`. The last column is the SHA-256 of the converted NIfTI linked to that original image. A filename alone cannot supply this evidence. For a Philips acquisition with missing slice timing, review the [source-based repair procedure](pipeline/s4b_slice_timing/README.md) before binding. [Conversion checks](pipeline/s4_clinica/README.md#reconcile-conversion-with-the-image-inventory) · [Evidence format](pipeline/s5d_bids_identity/README.md)

```sh
python start/02_bids.py "$STUDY" bind
```

**Open** `02-bids/binding/04.epi-execution-manifest.csv` to see which pairs can proceed and why others were held. The BIDS files are in `02-bids/rawdata/`. **Already have BIDS?** Skip `convert` and run `bind` with `--bids "/path/to/rawdata" --evidence "/path/to/conversion-hashes.csv"`. It still checks the original stage 1 selection.

<a id="process"></a>

## 3 · 🧠 Run preprocessing, denoising and quality checks

**Bring** the stage 2 binding receipt, your FreeSurfer license and a populated TemplateFlow cache. Use the [pinned Docker images and setup instructions](06_docs/installation.md#paths-for-a-manual-run). This local route uses the macOS clone-capable publisher; keep the study on a compatible volume such as APFS and share its location with Docker Desktop. The commands below start real processing.

```sh
python start/03_process.py "$STUDY" run
```

The script checks the acquisition settings for each verified pair, runs **MRIQC** to measure image quality, runs **fMRIPrep** to align the scans, then runs **XCP-D** to denoise BOLD and calculate connectivity. It prints the path to `visual_review.tsv` under `03-imaging/postprocessing/`. Each acquisition has its own work and execution logs in `03-imaging/cases/I<image-id>/`. To start from a previous verified selection, add `--binding "/path/to/07.binding-receipt.json"`. If multiple acquisitions share a visit or dated output, review them and pass the chosen keys in a text file with `--pairs "/path/to/epi-keys.txt"`.

**Review the whole cohort.** Once processing is complete, fit the cohort MRIQC quality thresholds using the [seeded R environment](06_docs/seed_reproducibility.md). Look at the flags in `03-imaging/cohort-iqms/all_IQMs_with_QC_flags_clean.tsv`. Open the HTML reports listed in `visual_review.tsv`, especially for flagged registrations and brain masks. Record the requested decisions, reviewer and date there. [Visual review fields](pipeline/s10_xcpd_integrated_qc/README.md) · [Illustrated MRIQC/fMRIPrep examples and exclusion criteria (Table 3)](https://doi.org/10.3389/fnimg.2022.1073734)

```sh
python start/03_process.py "$STUDY" iqms
```

**After review**, finalize imaging QC. If your cohort already has a reviewed MRIQC flags table, skip `iqms` and add `--mriqc-flags "/path/to/flags.tsv"` to this command. Pending reviews remain visible in the final table.

```sh
python start/03_process.py "$STUDY" finalize --cohort-complete
```

**Check clinical eligibility.** Put `DXSUM.csv` and `PTDEMOG.csv` in `clindata/`. The script also reads `ADSL.csv`, `DM.csv` and `APOERES.csv` when supplied there. Add `review/confirmed-st-absence.csv` with columns `IMAGE_ID,PTID,MRI_STUDY_DATE,ST_STATUS,EVIDENCE_REF`. A header-only file means the review identified no confirmed slice-timing exclusions. For documented conversion exclusions, add `--conversion-failures "/path/to/failures.csv"`. [Clinical checks](pipeline/s9a_validate_clinical/README.md) · [Exclusion records](pipeline/s9b_validate_inclusion/README.md)

```sh
python start/03_process.py "$STUDY" clinical
```

**Open** the printed final imaging QC table and `03-imaging/inclusion/inclusion_audit.tsv`. The first records imaging decisions. The second links scans to source QC and clinical eligibility. Stage 4 uses both. To apply clinical checks to existing imaging results, add `--final-qc "/path/to/finalizations/run/final_qc_master.tsv" --source-qc "/path/to/step3a" --scan-links "/path/to/audited-scan-links.tsv"`.

<a id="harmonize"></a>

## 4 · 📊 Harmonize functional connectivity

**Bring** the final imaging and clinical results plus `review/scanners.tsv`. This tab-separated file identifies the physical scanner for each EPI image and records where you verified it. Use the [scanner table example](pipeline/s14_fc_harmonization/README.md#prepare-private-inputs). The model adjusts the **4S256 connectivity edges** across scanners and retains age, sex and diagnosis as covariates. This profile uses one eligible scan per person.

```sh
python start/04_harmonize.py "$STUDY" audit
```

**Open** `04-harmonization/audit/decisions.tsv` and `batch_design.tsv`. Check who was selected and whether scanner groups cover comparable ages and diagnoses. This profile requires at least two batches and at least five selected participants per batch. When the audit passes and you have reviewed the design, run the fit.

```sh
python start/04_harmonize.py "$STUDY" fit
```

**Open** `04-harmonization/fit/fc.npz` for original and adjusted connectivity, `edges.tsv` for ROI pairs, and `diagnostics.json` for before/after checks. **Already at this stage?** Supply the paths to your existing results. Use the same overrides for `fit`. For a revised analysis, use `--output "/path/to/new-result"` to keep both versions. [Method, papers and implementations](06_docs/fc_harmonization.md)

```sh
python start/04_harmonize.py "$STUDY" audit \
  --final-qc "/path/to/finalizations/run/final_qc_master.tsv" \
  --inclusion "/path/to/step9b" --scanners "/path/to/scanners.tsv"
```

<a id="structure"></a>

## 🧭 Find the code

| Folder in this repository | Open it for |
|---|---|
| [start/](start/) | The four terminal scripts above. Each accepts `--help`. |
| [pipeline/](pipeline/README.md) | The scientific stages, options, outputs and citations |
| [03_config/](03_config/) · [04_workflow/](04_workflow/) | Configuration templates and managed batch runs |
| [05_tests/](05_tests/) · [07_reproducibility/](07_reproducibility/README.md) | Software checks and practice data |
| [06_docs/](06_docs/) · [provenance/](provenance/) | Setup, research methods and source history |

## Steps and commands

<details>
<summary>Show the full index of scientific stages and alternative routes</summary>

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

</details>

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
