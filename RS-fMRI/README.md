# 🧠 RS-fMRI Pipeline

Contribution and maintenance rules: [Repository instructions.md](<Repository instructions.md>)

This pipeline **pins statMINDlab's ADNI fMRI protocol as a Git submodule** and maintains lab additions under `02_custom/`. This README describes the complete execution order across upstream and Custom Steps.

- Upstream: [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3)
- Pinned commit: `e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3` — [versions and validation scope](03_config/versions.md)
- Upstream data selection, Clinica, MRIQC, fMRIPrep and base QC form the main workflow. A historical Research Selection Table is not required.
- Additional steps execute independently through explicit input/output paths. Adding a directory does not execute a step automatically.
- This initial implementation has code and synthetic-data validation. It does not establish full-cohort ADNI preprocessing or completed scientific inclusion decisions.

## 📁 Structure

```text
RS-fMRI/
├── 01_upstream/ADNI_fMRI_protocol/  # Submodule pinned to the upstream commit
├── 02_custom/
│   ├── s3a_source_qc/            # Source QC, NFQ, deletion and identity audits
│   ├── s5c_validate_handoff/     # Step 5 TSV → Step 6/7 input handoff
│   ├── s7a_volume_workflow/     # Existing Docker volume profile, audit and recovery
│   ├── s7b_sessionwise_preprocessing/ # Existing SB queue and surface/CIFTI adapter
│   ├── s8a_motion_duration_qc/    # Retained duration from actual FD and TR
│   ├── s9a_validate_clinical/    # Scan dates, diagnostic ties and demographics
│   ├── s9b_validate_inclusion/   # Source QC, clinical and confirmed-exclusion gate
│   ├── s10_xcpd_integrated_qc/   # S8, XCP-D, ROI/FC, imaging QC and archival gates
│   └── s11_atlas_bold/           # Pinned atlas library and audited ROI BOLD means
├── 03_config/                     # Public configuration examples and version locks
├── 04_workflow/                   # Version checks, external configuration and command plans
├── 05_tests/                      # Synthetic and upstream compatibility tests
├── 06_docs/                       # Installation, data preparation, extension and updates
└── 07_reproducibility/            # Public toy inputs, commands and numerical comparison
```

Top-level numbers `01`–`06` classify directories. Actual execution follows the upstream and Custom Step positions in the table below.

Run the [copy-and-paste reproducibility walkthrough](07_reproducibility/README.md) for a synthetic reference, pinned public T1w/BOLD inputs, actual Docker commands and peer comparison. The real CC0 NIfTI sample is bundled as ordinary Git files under [public_data](07_reproducibility/public_data/ds000030-1.0.0/README.md).

Use the [macOS/Linux execution guide](06_docs/platform_execution.md) for shared analysis settings, host setup, each upstream/custom stage, and the explicit publisher/controller/archival portability boundaries. The pinned upstream submodule stays unchanged.

## 🚀 Initial installation

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
git submodule update --init 01_upstream/ADNI_fMRI_protocol
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python 04_workflow/lab.py doctor
python -m pytest -q
```

This environment supports handoff tools and tests. Prepare Clinica, MRIQC, fMRIPrep, R and Slurm/Apptainer separately using upstream instructions. See the [installation guide](06_docs/installation.md).

## 🗺️ Complete execution order

| Order | Stage | Code | Main inputs/outputs and completion conditions | Host notes |
|---|---|---|---|---|
| 1 | Account & Access | [Upstream Step 1](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s1_setup_account/README.md) | ADNI access approval | [Mac/Linux](06_docs/platform_execution.md#s1) |
| 2 | Download | [Upstream Step 2](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s2_download/README.md) | Download images/metadata/clinical tables through the original UI and preserve collection CSVs | [Mac/Linux](06_docs/platform_execution.md#s2) |
| 3 | Organize & Download QC | [Upstream Step 3](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s3_organize/README.md) | Compare DICOM inventory with download lists | [Mac/Linux](06_docs/platform_execution.md#s3) |
| **3.A** | **Source QC and NFQ validation** | [Custom](02_custom/s3a_source_qc/README.md) | Audit source IDs/dates/UIDs/quality/deletions/NFQ; connect evidence to 5.C | [Mac/Linux](06_docs/platform_execution.md#s3a) |
| 4 | Clinica | [Upstream Step 4](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s4_clinica/README.md) | DICOM → BIDS; preserve conversion_info | [Mac/Linux](06_docs/platform_execution.md#s4) |
| 4.B | Philips SliceTiming | [Upstream Step 4b](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s4b_slice_timing/README.md) | Dry-run first; review actual image identity and slice-axis correspondence | [Mac/Linux](06_docs/platform_execution.md#s4b) |
| 5.A–B | Post-Clinica QC | [Upstream Step 5](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s5_post_clinica_qc/README.md) | Mastersheet → final_heuristics.tsv | [Mac/Linux](06_docs/platform_execution.md#s5ab) |
| **5.C** | **Input handoff validation** | [Custom](02_custom/s5c_validate_handoff/README.md) | Compare selected BOLD with 3.A evidence; block failures/conflicts, mark pending and generate 6/7 inputs | [Mac/Linux](06_docs/platform_execution.md#s5c) |
| **5.D** | **Exact-pair BIDS identity** | [Custom](02_custom/s5d_bids_identity/README.md) | Hash/UID/header verification and guarded exact EPI–T1 dispatch; synthetic example included | [Mac/Linux](06_docs/platform_execution.md#s5d) |
| 6 | MRIQC | [Upstream Step 6](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s6_mriqc/README.md) | Generate IQMs/reports; verify IQM fitting scope against Step-5 survivors | [Mac/Linux](06_docs/platform_execution.md#s6) |
| 7 | fMRIPrep | [Upstream Step 7](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s7_fmriprep/README.md) | Explicitly pass 5.C session CSVs; generate images, confounds and reports | [Mac/Linux](06_docs/platform_execution.md#s7) |
| **7.A** | **Separate Docker volume profile** | [Custom](02_custom/s7a_volume_workflow/README.md) | Existing aCompCor profile, independent audit and metadata repair; separate from upstream 7 and S10 | [Mac/Linux](06_docs/platform_execution.md#s7a) |
| **7.B** | **Live sessionwise preprocessing** | [Custom](02_custom/s7b_sessionwise_preprocessing/README.md) | Existing queue compatibility; new subjects use integrated source, active jobs retain their original runner | [Mac/Linux](06_docs/platform_execution.md#s7b) |
| **7.C** | **ANTs iteration logs** | [Custom](02_custom/s7c_ants_iteration_logging/README.md) | Optional logging transport before a new fMRIPrep launch; no queue or image-settings change | [Mac/Linux](06_docs/platform_execution.md#s7c) |
| 8 | Final QC | [Upstream Step 8](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s8_final_qc/README.md) | Motion, Euler, MRIQC and inclusion/exclusion reasons | [Mac/Linux](06_docs/platform_execution.md#s8) |
| **8.A** | **Motion retained-duration checks** | [Custom](02_custom/s8a_motion_duration_qc/README.md) | Actual TR × retained frames, FD proportion, initial-frame sensitivity and masks | [Mac/Linux](06_docs/platform_execution.md#s8a) |
| 9 | Clinical Merge | [Upstream Step 9](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s9_clinical_imaging_merge/README.md) | Upstream cognitive-score linkage/reports; preserve original outputs | [Mac/Linux](06_docs/platform_execution.md#s9) |
| **9.A** | **Clinical validation** | [Custom](02_custom/s9a_validate_clinical/README.md) | Actual scan dates, all nearest diagnoses, 28-day window, Dementia/suspected etiology and PTDEMOG/APOE | [Mac/Linux](06_docs/platform_execution.md#s9a) |
| **9.B** | **Final inclusion validation** | [Custom](02_custom/s9b_validate_inclusion/README.md) | Combine source QC, clinical validation and confirmed ST/conversion failures; retain pending under nearest/28-day policy | [Mac/Linux](06_docs/platform_execution.md#s9b) |
| **10** | **XCP-D and integrated imaging QC** | [Custom](02_custom/s10_xcpd_integrated_qc/README.md) | Completed S7 pair → S8 metrics → provisional XCP-D → validation/human review → explicit cohort finalization; export 9.A links | [Mac/Linux](06_docs/platform_execution.md#s10) |
| **11** | **Atlas-based BOLD signals** | [Custom](02_custom/s11_atlas_bold/README.md) | Select a pinned matching-space atlas; audit labels/coverage and extract ROI means from reviewed BOLD | [Mac/Linux](06_docs/platform_execution.md#s11) |
| **12** | **One-row scalar results and HTML** | [Custom](02_custom/s12_metrics_summary/README.md) | Verified S10 archive → volume/thickness/ReHo/ALFF/QC table and native reports; independent of optional 11 | [Mac/Linux](06_docs/platform_execution.md#s12) |

Steps 1.A/1.B have not been defined and are not created yet. Add them when needed using the [Custom Step guide](06_docs/pipeline_guide.md).

## 🧩 XCP-D execution order

Connect upstream 1–7 → **S8/8.A + S10 pre-QC → XCP-D → quantitative/visual review → cohort imaging-QC finalization → S9/9.A clinical validation → 9.B final inclusion validation**. S10 can start as a separate worker once S7 pairs complete. `watch/collect` never makes final inclusion decisions. See the [S10 README](02_custom/s10_xcpd_integrated_qc/README.md) for commands, pair-input contracts and archival gates, and the [consolidation guide](06_docs/xcpd_consolidation.md) for directory retirement and service-transition boundaries.

Preserve 7.A's existing aCompCor profile separately from S10's 36P/GSR profile; do not mix their results. Pass S10 finalization's `final_included_runs.tsv` and `clinical_scan_links.tsv` together to 9.A. Imaging QC alone does not establish full research inclusion.

## 🧠 Atlas library and BOLD extraction

After S10 imaging review → 9.A → 9.B, [Step 11](02_custom/s11_atlas_bold/README.md) can extract a separately selected atlas from the intended BOLD derivative. The library links Neuroparc, CBIG, Nilearn and TemplateFlow at fixed commits, with 252 registered file variants. Install these optional sources explicitly; ordinary setup and CI initialize only the core ADNI submodule.

```sh
python 02_custom/s11_atlas_bold/sources.py install
python 02_custom/s11_atlas_bold/sources.py fetch-templateflow
python 02_custom/s11_atlas_bold/run.py list --space MNI152NLin6Asym
```

Use the [extraction command](02_custom/s11_atlas_bold/README.md#execution) with 9.B evidence and an actual image/run mapping. No space aliasing or cross-template registration is inferred. Masked/lost ROIs stay in the audit and expected columns; failed coverage produces a nonzero status. S10's existing atlas/FC products remain separate. See the [locking and space guide](06_docs/atlas_library.md).

## 🔎 Scope of ported Research rules

The [validation-rule mapping](06_docs/research_validation_rules.md) distinguishes rules adapted from source QC/NFQ/clinical code from items requiring actual-image validation. Historical RDS files and download-ID lists do not become central inputs; independently compare upstream-selected images with external raw sources.

Run 3.A with explicit Study Files paths using its [execution commands](02_custom/s3a_source_qc/README.md#execution). Pass the resulting `step3a` artifact to 5.C below. Files and Obsidian paths are not discovered automatically.

## ⚙️ Configuration and handoffs

Store private configuration in `03_config/lab_config.local.yaml` or outside the repository. Keep research inputs and generated results outside the repository; the explicitly approved CC0 public sample is included under `07_reproducibility/public_data/`.

```sh
cp 03_config/lab_config.example.yaml 03_config/lab_config.local.yaml
# Set actual absolute data/scratch/container/license paths before running.
python 04_workflow/lab.py prepare-config \
  --lab-config 03_config/lab_config.local.yaml \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/config/run-001
```

The generated `upstream.yaml` preserves the upstream configuration schema without modifying `config/config_adni.yaml` in the submodule. Connect Steps 5.A/B as follows, replacing placeholders with actual paths.

```sh
export ADNI_CONFIG=/ABSOLUTE/PATH/ADNI_DATA/config/run-001/upstream.yaml
export PYTHONPATH="$PWD/01_upstream/ADNI_fMRI_protocol${PYTHONPATH:+:$PYTHONPATH}"
export RSFMRI_ROOT="$PWD"
mkdir -p /ABSOLUTE/PATH/ADNI_DATA/qc/step5a
(cd /ABSOLUTE/PATH/ADNI_DATA/qc/step5a && python "$RSFMRI_ROOT/01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/create_mastersheet/main.py" --config "$ADNI_CONFIG")
python 01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/create_report/run_session_heuristics.py \
  --input-csv /ABSOLUTE/PATH/anchor_plus_dicom_nifti_struct.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step5
python 02_custom/s5c_validate_handoff/run.py \
  --input /ABSOLUTE/PATH/ADNI_DATA/qc/step5/final_heuristics.tsv \
  --source-qc /ABSOLUTE/PATH/ADNI_DATA/qc/step3a \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step5c
python 04_workflow/lab.py prepare-config \
  --lab-config 03_config/lab_config.local.yaml \
  --handoff /ABSOLUTE/PATH/ADNI_DATA/qc/step5c \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/config/run-001-handoff
python 04_workflow/lab.py plan \
  --config /ABSOLUTE/PATH/ADNI_DATA/config/run-001-handoff/upstream.yaml \
  --handoff /ABSOLUTE/PATH/ADNI_DATA/qc/step5c
```

`plan` prints commands without submitting work. Upstream `--dry-run` may create job files; review paths and Slurm directives before running the printed commands. There is no full-workflow automatic execution engine yet.

Additional checks after Step 8:

```sh
python 02_custom/s8a_motion_duration_qc/run.py \
  --bids-root /ABSOLUTE/PATH/ADNI_DATA/rawdata \
  --derivatives-root /ABSOLUTE/PATH/ADNI_DATA/derivatives/fmriprep \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/motion-duration-run-001
```

Step 8.A creates QC evidence without automatically changing upstream inclusion tables or image frames. Pass 5.C's `valid_sessions.tsv` to Step 8's `--valid-sessions` to prevent blocked sessions from reentering. Supply a separate reviewed inclusion table incorporating 8.A, visual-QC failures and holds to Steps 9/9.A.

Run Step 9.A clinical validation as follows. `--included` is the reviewed inclusion table above; `--scan-links` is the upstream fMRI mastersheet or an explicit CSV with equivalent identity information.

```sh
python 02_custom/s9a_validate_clinical/run.py \
  --included /ABSOLUTE/PATH/ADNI_DATA/qc/final/included_reviewed_sessions.tsv \
  --scan-links /ABSOLUTE/PATH/ADNI_DATA/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv \
  --dxsum /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DXSUM.csv \
  --ptdemog /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/PTDEMOG.csv \
  --max-dx-days 28 --dx-direction nearest \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9a
```

Optionally supply APOE/ADSL/DM through `--apoe`, `--adsl` and `--dm`. `clinical_validation.tsv` preserves every input run with pass/hold and reasons; `clinically_validated_sessions.tsv` additionally stores the clinical-pass subset. A clinical pass alone does not establish analysis readiness.

## 🔗 Step 9.B final inclusion validation

Run the reviewed imaging inclusion table through **9.A v2 → 9.B**. Step 9.A excludes TEAM records and fills structurally missing sex values only from consistent, eligible same-scope visits, retaining raw-row evidence. Supply both ADSL and DM for cross-source sex validation. Regenerate old v1 results in a new directory.

```sh
python 02_custom/s9b_validate_inclusion/run.py \
  --source-qc /ABSOLUTE/PATH/ADNI_DATA/qc/step3a \
  --clinical /ABSOLUTE/PATH/ADNI_DATA/qc/step9a \
  --confirmed-st-absence /ABSOLUTE/PATH/ADNI_DATA/qc/confirmed-st-absence.csv \
  --conversion-failures /ABSOLUTE/PATH/ADNI_DATA/qc/confirmed-conversion-failures.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9b
```

The gate requires nearest diagnoses within 28 days and preserves source-QC pending candidates. Known source-QC blocks, clinical failures and confirmed ST absence cannot reenter. `retained_sessions.tsv` contains eligible and pending rows; `inclusion_audit.tsv` preserves every run and decision. Use the [confirmed-evidence schemas](02_custom/s9b_validate_inclusion/README.md#input): a missing ST record does not establish confirmed absence. Imaging-review status is preserved; `ANALYSIS_READY=False` remains explicit.

## ⚠️ Current scope boundaries

- Upstream supports ADNI GO/2/3. ADNI4 requires separate extension and validation.
- The upstream Step 6 launcher operates per participant. The 5.C CSV handoff resolves delimiters and duplicate participants but **does not add session restriction**. Compare/restrict group IQMs to `valid_sessions.tsv` before fitting outliers.
- Upstream Step 8 reads IQMs with a default CSV reader. Check delimiters and prepare a verified CSV rather than passing s6 TSV output directly. Missing QC does not establish research inclusion.
- Distinguish upstream Step 9's `DIAGNOSIS=3 → AD` label from current DXSUM Dementia definitions. Explicitly set both `build_imaging_input.py --max-dx-days` and the downstream `--max-days`. Use 9.A's source-validated diagnoses for analysis; upstream AD labels do not establish clinical or biological AD.
- The 5.C source-QC gate applies to selected BOLD ID/date/UID. Actual T1-reference pairing, image headers/ST axes, coverage and visual QC require separate validation. Format-only use without source QC remains possible but is not reported as completed source-QC validation.
- Mac volume-pilot and XCP-D code is consolidated under 7.A/S10 custom steps. S10 requires the referenced task's published completed-pair layout; it does not automatically convert flat Slurm outputs or 7.A outputs without FreeSurfer. Record 8.A's 300-second and XCP-D's 240-second criteria separately.
- See [installation and Mac limits](06_docs/installation.md), [data preparation](06_docs/data_preparation.md), [validation](06_docs/validation.md) and [upstream updates](06_docs/update_guide.md).

## 🔄 Updating to validated versions

Existing clones using the initial unnumbered layout must first follow the [one-time migration guide](06_docs/update_guide.md#one-time-migration-from-the-initial-unnumbered-layout).

```sh
git pull --ff-only
git submodule update --init 01_upstream/ADNI_fMRI_protocol
python 04_workflow/lab.py doctor
```

These commands restore the commit recorded by the parent repository. Adopt new upstream versions on a separate test branch following the [update guide](06_docs/update_guide.md). Versioning uses the gitlink mechanism described in [official Git submodule documentation](https://git-scm.com/docs/gitsubmodules).

## 📚 Attribution and license

Use the upstream [CITATION.cff](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/CITATION.cff) for authorship and citation. Added-code sources are recorded in [NOTICE](NOTICE.md); [LICENSE](../LICENSE) states the upstream-compatible GPL-3.0 terms. Original ADNI data is not redistributed.

## Live automation

See the [live-service handoff guide](06_docs/live_service_handoff.md) for switching existing preprocessing/XCP-D controllers to this repository while preserving running containers, historical configuration IDs, completed results, caches and the shared compute limit.

### Step 11 adapters and coverage investigation

Execution order: **9.B metadata inclusion → actual raw BIDS/derivative run link → original acquisition frame map → Step 11 extraction → descriptive coverage diagnosis**. See the [Step 11 adapter commands](02_custom/s11_atlas_bold/README.md#original-acquisition-frames-and-actual-bids-run-evidence). Supply the hash-bound `--run-link` with the original 9.B artifact and image ID; `eligible`/`pending` remain separate. Supply `--frame-map` to preserve original frame numbers and time gaps in `frames.tsv`. Never reapply a pre-censor mask to a shortened XCP-D image. The adapter's nominal raw time does not include slice-timing offsets.

Low-coverage investigation compares the unchanged EPI mask with BOLD reference, T1, GM probability and anatomical mask. It writes evidence for review and retains the original QC failures. Coverage 0.5, minimum one voxel, nearest/28-day clinical matching and pending preservation are unchanged; the adapters do not authorize final cohort inclusion or relax study-specific duration criteria.

## Reproducible examples and scalar export

[Step-by-step terminal blocks](07_reproducibility/README.md) cover actual source/handoff/clinical/QC/extraction/export code using labeled synthetic fixtures, plus MRIQC/fMRIPrep/XCP-D on a pinned CC0 public subject. The quick example has a committed analytical reference; a real public-subject imaging reference has not yet been computed. Comparison checks source/code/options and selected numerical products separately.

After validated archival, run `python 04_workflow/lab.py export-results --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics.json`. `--watch` opts into a plain 120-second scan loop; no imaging is launched. Optional Step 11 is not required by Step 12. Final research inclusion stays pending.
