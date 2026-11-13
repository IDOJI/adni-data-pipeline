# 🧠 RS-fMRI Pipeline

For new local preprocessing batches, use the [fixed-seed profile](06_docs/seed_reproducibility.md) and `04_workflow/local_batch_seeded.py`. It covers MRIQC, fMRIPrep skull stripping, XCP-D and R cohort fitting. Existing source-locked services and historical commands retain their original execution identity.

## 🚀 Initial installation

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r 01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/requirements.txt
python 04_workflow/lab.py doctor
python -m pytest -q
```

This environment supports handoff tools and tests. Prepare Clinica, MRIQC, fMRIPrep, R and Slurm/Apptainer separately using upstream instructions. See the [installation guide](06_docs/installation.md).

## ▶ Terminal commands by step

Open the [command-first stage guide](06_docs/platform_execution.md#common-setup), set up the paths once, then select the current stage in the execution table below. Each stage shows **what to type first**, followed by **what it does, where the results appear, and macOS/Linux requirements**. Steps 1–2 are explicitly manual portal actions. The [Custom Step READMEs](02_custom/) open with their execution blocks too.

Use the [offline/public walkthrough](07_reproducibility/README.md) when practicing without licensed ADNI inputs. Preview, real calculation and persistent watcher commands are labeled separately; the table is a navigation map rather than one unattended end-to-end command.

Contribution and maintenance rules: [Repository instructions.md](<Repository instructions.md>)

For an existing live installation, use the [independent-runtime handoff](06_docs/repository_independence.md) to finish a captured cohort, move interpreters and executable source into this repository, verify the old checkout is no longer read, and leave admission stopped. CPU quotas are managed separately from scientific pipeline settings.

This pipeline **includes statMINDlab-derived ADNI protocol code as ordinary editable source** under `01_upstream/ADNI_fMRI_protocol/` and maintains lab additions under `02_custom/`. See the [source integration and preserved history](06_docs/source_integration.md). This README describes the complete execution order across upstream and Custom Steps.

- Upstream: [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3)
- Original import commit: `e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3` — [versions and validation scope](03_config/versions.md)
- Upstream data selection, Clinica, MRIQC, fMRIPrep and base QC form the main workflow. A historical Research Selection Table is not required.
- Additional steps execute independently through explicit input/output paths. Adding a directory does not execute a step automatically.
- This initial implementation has code and synthetic-data validation. It does not establish full-cohort ADNI preprocessing or completed scientific inclusion decisions.

## 📁 Structure

```text
RS-fMRI/
├── 01_upstream/ADNI_fMRI_protocol/  # Ordinary owned source; attribution retained
├── 02_custom/
│   ├── s3a_source_qc/            # Source QC, NFQ, deletion and identity audits
│   ├── s5c_validate_handoff/     # Step 5 TSV → Step 6/7 input handoff
│   ├── s5d_bids_identity/        # Optional verified exact EPI–T1 dispatch
│   ├── s7a_volume_workflow/     # Existing Docker volume profile, audit and recovery
│   ├── s7b_sessionwise_preprocessing/ # Existing SB queue and surface/CIFTI adapter
│   ├── s7c_ants_iteration_logging/ # Prospective ANTs iteration logs and idle activation
│   ├── s8a_motion_duration_qc/    # Retained duration from actual FD and TR
│   ├── s9a_validate_clinical/    # Scan dates, diagnostic ties and demographics
│   ├── s9b_validate_inclusion/   # Source QC, clinical and confirmed-exclusion gate
│   ├── s10_xcpd_integrated_qc/   # S8, XCP-D, ROI/FC, imaging QC and archival gates
│   ├── s11_atlas_bold/           # Pinned atlas library and audited ROI BOLD means
│   └── s12_metrics_summary/      # One-row structural/function metrics and HTML report links
├── 03_config/                     # Public configuration examples and version locks
├── 04_workflow/                   # Version checks, external configuration and command plans
├── 05_tests/                      # Synthetic and upstream compatibility tests
├── 06_docs/                       # Installation, data preparation, extension and updates
└── 07_reproducibility/            # Public toy inputs, commands and numerical comparison
```

Top-level numbers `01`–`07` classify directories. Actual execution follows the upstream and Custom Step positions in the table below.

For runnable stage-by-stage examples, start with the [reproducibility walkthrough](07_reproducibility/README.md). It includes an offline synthetic reference, pinned public T1w/BOLD inputs, actual imaging commands and peer comparison without private ADNI data.

The real CC0 NIfTI sample is bundled as ordinary Git files under [public_data](07_reproducibility/public_data/ds000030-1.0.0/README.md).

Use the [macOS/Linux execution guide](06_docs/platform_execution.md) for shared analysis settings, host setup, each upstream/custom stage, and the explicit publisher/controller/archival portability boundaries. The imported protocol is maintained in this repository; its original baseline remains recorded.

## 🗺️ Complete execution order

| Order | Stage | Code | Main inputs/outputs and completion conditions | Terminal command and host notes |
|---|---|---|---|---|
| 1 | Account & Access | [Protocol Step 1](01_upstream/ADNI_fMRI_protocol/s1_setup_account/README.md) | ADNI access approval | [Run S1](06_docs/platform_execution.md#s1) |
| 2 | Download | [Protocol Step 2](01_upstream/ADNI_fMRI_protocol/s2_download/README.md) | Download images/metadata/clinical tables through the original UI and preserve collection CSVs | [Run S2](06_docs/platform_execution.md#s2) |
| 3 | Organize & Download QC | [Protocol Step 3](01_upstream/ADNI_fMRI_protocol/s3_organize/README.md) | Compare DICOM inventory with download lists | [Run S3](06_docs/platform_execution.md#s3) |
| **3.A** | **Source QC and NFQ validation** | [Custom](02_custom/s3a_source_qc/README.md) | Audit source IDs/dates/UIDs/quality/deletions/NFQ; connect evidence to 5.C | [Run S3A](06_docs/platform_execution.md#s3a) |
| 4 | Clinica | [Protocol Step 4](01_upstream/ADNI_fMRI_protocol/s4_clinica/README.md) | DICOM → BIDS; preserve conversion_info | [Run S4](06_docs/platform_execution.md#s4) |
| 4.B | Philips SliceTiming | [Protocol Step 4b](01_upstream/ADNI_fMRI_protocol/s4b_slice_timing/README.md) | Dry-run first; review actual image identity and slice-axis correspondence | [Run S4B](06_docs/platform_execution.md#s4b) |
| 5.A–B | Post-Clinica QC | [Protocol Step 5](01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/README.md) | Mastersheet → final_heuristics.tsv | [Run S5AB](06_docs/platform_execution.md#s5ab) |
| **5.C** | **Input handoff validation** | [Custom](02_custom/s5c_validate_handoff/README.md) | Compare selected BOLD with 3.A evidence; block failures/conflicts, mark pending and generate 6/7 inputs | [Run S5C](06_docs/platform_execution.md#s5c) |
| **5.D** | **Optional BIDS identity and exact-pair dispatch** | [Custom](02_custom/s5d_bids_identity/README.md) | Preserve external EPI proposals, verify actual Image ID/UID/hash evidence, hold unresolved cases and pass exact verified pairs through a guarded 7.B entry point | [Run S5D](06_docs/platform_execution.md#s5d) |
| 6 | MRIQC | [Protocol Step 6](01_upstream/ADNI_fMRI_protocol/s6_mriqc/README.md) | Generate IQMs/reports; verify IQM fitting scope against Step-5 survivors | [Run S6](06_docs/platform_execution.md#s6) |
| 7 | fMRIPrep | [Protocol Step 7](01_upstream/ADNI_fMRI_protocol/s7_fmriprep/README.md) | Explicitly pass 5.C session CSVs; generate images, confounds and reports | [Run S7](06_docs/platform_execution.md#s7) |
| **7.A** | **Separate Docker volume profile** | [Custom](02_custom/s7a_volume_workflow/README.md) | Existing aCompCor profile, independent audit and metadata repair; separate from upstream 7 and S10 | [Run S7A](06_docs/platform_execution.md#s7a) |
| **7.B** | **Live sessionwise preprocessing** | [Custom](02_custom/s7b_sessionwise_preprocessing/README.md) | Existing queue compatibility; new subjects use integrated source, active jobs retain their original runner; transient controller errors are logged and retried; optional independent heartbeat watchdog | [Run S7B](06_docs/platform_execution.md#s7b) |
| **7.C** | **Live ANTs iteration logging** | [Custom](02_custom/s7c_ants_iteration_logging/README.md) | Instrument future 7.B/frozen stage launches; preserve scientific/cache identity and log iterations live; defer controller activation until idle | [Run S7C](06_docs/platform_execution.md#s7c) |
| **7.D** | **Processing-time records** | [Custom](02_custom/s7d_processing_timing/README.md) | Per-attempt MRIQC/fMRIPrep/XCP-D times, preprocessing/postprocessing totals and overall observed wall time | [Run S7D](02_custom/s7d_processing_timing/README.md) |
| 8 | Final QC | [Protocol Step 8](01_upstream/ADNI_fMRI_protocol/s8_final_qc/README.md) | Motion, Euler, MRIQC and inclusion/exclusion reasons | [Run S8](06_docs/platform_execution.md#s8) |
| **8.A** | **Motion retained-duration checks** | [Custom](02_custom/s8a_motion_duration_qc/README.md) | Actual TR × retained frames, FD proportion, initial-frame sensitivity and masks | [Run S8A](06_docs/platform_execution.md#s8a) |
| 9 | Clinical Merge | [Protocol Step 9](01_upstream/ADNI_fMRI_protocol/s9_clinical_imaging_merge/README.md) | Upstream cognitive-score linkage/reports; preserve original outputs | [Run S9](06_docs/platform_execution.md#s9) |
| **9.A** | **Clinical validation** | [Custom](02_custom/s9a_validate_clinical/README.md) | Actual scan dates, all nearest diagnoses, 28-day window, Dementia/suspected etiology and PTDEMOG/APOE | [Run S9A](06_docs/platform_execution.md#s9a) |
| **9.B** | **Final inclusion validation** | [Custom](02_custom/s9b_validate_inclusion/README.md) | Combine source QC, clinical validation and confirmed ST/conversion failures; retain pending under nearest/28-day policy | [Run S9B](06_docs/platform_execution.md#s9b) |
| **10** | **XCP-D and integrated imaging QC** | [Custom](02_custom/s10_xcpd_integrated_qc/README.md) | Completed S7 pair → S8 metrics → provisional XCP-D → validation/human review → explicit cohort finalization; export 9.A links | [Run S10](06_docs/platform_execution.md#s10) |
| **11** | **Atlas-based BOLD signals** | [Custom](02_custom/s11_atlas_bold/README.md) | Select a pinned matching-space atlas; audit labels/coverage and extract ROI means from reviewed BOLD | [Run S11](06_docs/platform_execution.md#s11) |
| After 11 (planned) | Selected-atlas FC and cohort harmonization | [Design and evidence](06_docs/fc_harmonization.md) | ROI time series → Pearson FC → Fisher-z edges → reviewed batch/covariate model → ComBat baseline and evaluation; documentation only, no runnable adapter yet | [Mac/Linux](06_docs/platform_execution.md#cross-host-comparison) |
| **12** | **Per-run scalar metrics and reports** | [Custom](02_custom/s12_metrics_summary/README.md) | Verified S10 archive → one-row structural/ReHo/ALFF/QC CSV and native-report HTML links; preserve NA and final-inclusion pending | [Run S12](06_docs/platform_execution.md#s12) |

Steps 1.A/1.B have not been defined and are not created yet. Add them when needed using the [Custom Step guide](06_docs/pipeline_guide.md).

## 🧩 XCP-D execution order

Connect upstream 1–7 → **S8/8.A + S10 pre-QC → XCP-D → quantitative/visual review → cohort imaging-QC finalization → S9/9.A clinical validation → 9.B final inclusion validation**. S10 can start as a separate worker once S7 pairs complete. `watch/collect` never makes final inclusion decisions. See the [S10 README](02_custom/s10_xcpd_integrated_qc/README.md) for commands, pair-input contracts and archival gates, and the [consolidation guide](06_docs/xcpd_consolidation.md) for directory retirement and service-transition boundaries.

Preserve 7.A's existing aCompCor profile separately from S10's 36P/GSR profile; do not mix their results. Pass S10 finalization's `final_included_runs.tsv` and `clinical_scan_links.tsv` together to 9.A. Imaging QC alone does not establish full research inclusion.

## Processing-time reports

```sh
# Later execution, after preparation and the source-only hook check in Step 7.D:
export PREPROC_CONFIG="/ABSOLUTE/PATH/preprocessing.local.yaml"
export ADNI_SUBJECT="ADNI999S9999"
python 02_custom/s7b_sessionwise_preprocessing/run.py \
  --config "$PREPROC_CONFIG" run --stage mriqc --subject "$ADNI_SUBJECT"
python 02_custom/s7b_sessionwise_preprocessing/run.py \
  --config "$PREPROC_CONFIG" run --stage fmriprep --subject "$ADNI_SUBJECT"
```

When you execute these real imaging commands with the timing-enabled 7.B runner, each completion/failure records its duration and refreshes the reports automatically. After the completed pair has been published in the S10 input layout, its XCP-D execution records time through the same mechanism:

```sh
export XCPD_CONFIG="/ABSOLUTE/PATH/xcpd.local.json"
python 02_custom/s10_xcpd_integrated_qc/pipeline.py \
  --config "$XCPD_CONFIG" pilot
```

No timing service is required for the new completion hooks. A working checkout may preserve legacy runner files without those hooks: check the source first using [Step 7.D's static check](02_custom/s7d_processing_timing/README.md#1-check-automatic-recording-without-running-the-pipeline). Such a copy needs an explicit timing collector or a separate timing-enabled checkout; merely having Step 7.D installed is insufficient. Preserve active deployment/cache identities.

The 7.B YAML `runtime` determines its attempt-log root. S10 uses JSON `root` and published `<source_pair>/s10/<config_id>/runs/<run_key>/attempt-NNN/execution.json`. In the shared pair workflow, set `ADNI_RUNTIME_ROOT` to the common root containing `runs/`, `results/` and `continuous5/`; timing reports live there:

```sh
export ADNI_RUNTIME_ROOT="/ABSOLUTE/PATH/shared-pair-runtime"
cat "$ADNI_RUNTIME_ROOT/timing/summary.json"
head -n 6 "$ADNI_RUNTIME_ROOT/timing/attempts.display.tsv"
head -n 6 "$ADNI_RUNTIME_ROOT/timing/cases.display.tsv"
```

`attempts.tsv` gives MRIQC/fMRIPrep/XCP-D start/end and seconds/hours per attempt. `cases.tsv` gives per-case stage totals; `summary.json` gives aggregate preprocessing, postprocessing and overall observed wall time. `stage_seconds_sum` counts processing intervals, including failures/retries; `observed_wall_seconds` spans the first start to latest finish and includes waiting/validation. It is not a final cohort total while work is pending. Standalone 7.B uses `<runtime>/timing/` unless the shared-root promotion condition applies; public imaging uses `<PUBLIC_ROOT>/timing/`. See [Step 7.D](02_custom/s7d_processing_timing/README.md) for exact paths, null/incomplete values and optional manual collection. Documentation/source inspection does not require running any imaging or collector command.

The optional Docker event observer `04_workflow/processing_timing.py` has a separate measurement contract: container execution windows with observed pause/sleep subtracted, fMRIPrep + XCP-D combined and MRIQC separate. Both implementations share only the display formatter. Step 7.D adds `attempts.display.tsv` and `cases.display.tsv` while preserving numeric TSVs. The observer's human `processing_times.csv` displays explicit time units; numeric integrations read `processing_times.raw.csv`. These values must not be merged with Step 7.D's wall span or counted again as additional work. See [measurement and file-schema comparison](02_custom/s7d_processing_timing/README.md#5-separate-docker-execution-observer-and-display-formats) for provenance, S12 ownership and host-coverage limits.

## 🧠 Atlas library and BOLD extraction

After S10 imaging review → 9.A → 9.B, [Step 11](02_custom/s11_atlas_bold/README.md) can extract a separately selected atlas from the intended BOLD derivative. The library links Neuroparc, CBIG, Nilearn and TemplateFlow at fixed commits, with 252 registered file variants. Install these optional sources explicitly; ordinary setup and CI use protocol files already included in Git.

```sh
python 02_custom/s11_atlas_bold/sources.py install
python 02_custom/s11_atlas_bold/sources.py fetch-templateflow
python 02_custom/s11_atlas_bold/run.py list --space MNI152NLin6Asym
```

Use the [extraction command](02_custom/s11_atlas_bold/README.md#execution) with 9.B evidence and an actual image/run mapping. No space aliasing or cross-template registration is inferred. Masked/lost ROIs stay in the audit and expected columns; failed coverage produces a nonzero status. S10's existing atlas/FC products remain separate. See the [locking and space guide](06_docs/atlas_library.md).

## 🔗 FC calculation and harmonization after atlas selection

The [FC and harmonization guide](06_docs/fc_harmonization.md) documents the intended continuation from Step 11: **ROI time series → Pearson FC → Fisher-z edges → cohort-level harmonization → group/network analysis**. ComBat is the proposed first baseline to evaluate, supported by direct ADNI applications; it is not an automatic requirement or a claim of established usage frequency.

The guide connects [neuroCombat (Python)](https://github.com/Jfortin1/neuroCombat), [neuroCombat (R)](https://github.com/Jfortin1/neuroCombat_Rpackage), [neuroHarmonize](https://github.com/rpomponio/neuroHarmonize) and [FCHarmony](https://github.com/andy1764/FCHarmony), with reviewed documentation revisions, primary papers, batch/phase confounding, covariate and train/test rules, and proposed input/output contracts. These are reference links; no new dependencies or submodules are installed. Selected-atlas FC and harmonization adapters remain planned. S10's existing FC and Step 12's scalar/report branch retain their separate roles.

## 🔎 Scope of ported Research rules

The [validation-rule mapping](06_docs/research_validation_rules.md) distinguishes rules adapted from source QC/NFQ/clinical code from items requiring actual-image validation. Historical RDS files and download-ID lists do not become central inputs; independently compare upstream-selected images with external raw sources.

Run 3.A with explicit Study Files paths using its [execution commands](02_custom/s3a_source_qc/README.md#execution). Pass the resulting `step3a` artifact to 5.C below. Files and Obsidian paths are not discovered automatically.

## Exact-pair BIDS identity handoff

[Step 5.D](02_custom/s5d_bids_identity/README.md) is an optional file-identity and execution gate for explicit external EPI–T1 proposals. It preserves every EPI row, verifies current BIDS files against unique source UIDs and independent Image ID/hash evidence, and keeps unresolved cases held. Its guarded entry point isolates one exact verified pair, rejects extra T1 images and rechecks fingerprints immediately before delegation to 7.B. For explicitly authorized continuation, an external registry can gate the existing queue: verify completed-stage evidence, observe current owners, and continue only missing stages with the original backend, configuration and cache signatures. Unregistered queue rows remain held, and existing maintenance holds and shared compute limits remain in force. It does not change upstream selection or launch calculations automatically.

## ⚙️ Configuration and handoffs

Store private configuration in `03_config/lab_config.local.yaml` or outside the repository. Keep all data and results outside the repository.

```sh
cp 03_config/lab_config.example.yaml 03_config/lab_config.local.yaml
# Set actual absolute data/scratch/container/license paths before running.
python 04_workflow/lab.py prepare-config \
  --lab-config 03_config/lab_config.local.yaml \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/config/run-001
```

The generated `upstream.yaml` preserves the upstream configuration schema without modifying `config/config_adni.yaml` in the integrated protocol source. Connect Steps 5.A/B as follows, replacing placeholders with actual paths.

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
python 04_workflow/lab.py doctor
```

These commands update owned source. Review later original-repository changes through the [update guide](06_docs/update_guide.md); SNP and atlas gitlinks retain separate versioning.

## 📚 Attribution and license

Use the upstream [CITATION.cff](01_upstream/ADNI_fMRI_protocol/CITATION.cff) for authorship and citation. Added-code sources are recorded in [NOTICE](NOTICE.md); [LICENSE](../LICENSE) states the upstream-compatible GPL-3.0 terms. Original ADNI data is not redistributed.

## External source-copy gate and continuous verified feeding

An optional local timer can check an external source ZIP every three hours, then verify its full member CRCs before switching the existing private runtime to that resident copy. The verified feeder prepares and validates subsequent batches at idle boundaries and connects the existing MRIQC → fMRIPrep → S8/XCP-D → verified archival → S12 services. See the [7.B external-archive contract](02_custom/s7b_sessionwise_preprocessing/README.md#external-archive-readiness-and-verified-batch-feeding). Incomplete sources and identity/pairing conflicts remain held; source installation alone does not establish active computation.

## Live ANTs iteration logging

Execution order: **7.B/frozen backend → [7.C logging transport](02_custom/s7c_ants_iteration_logging/README.md) → MRIQC/fMRIPrep → S8/S10 → verified archive → S12**. Future queue stage launches record live `antsRegistration --verbose 1` raw channels and parsed iteration/stage/level evidence outside the repository. Computational arguments, images, seeds and original backend cache identities are retained; existing active containers are not retrofitted. See the 7.C input/output and validation contract before enabling a live controller handoff.

## Live automation

See the [live-service handoff guide](06_docs/live_service_handoff.md) for switching existing preprocessing/XCP-D controllers to this repository while preserving running containers, historical configuration IDs, completed results, caches and the shared compute limit.

## Per-run scalar export after archival

Reporting branch: **S10 output validation → verified archive/local cleanup → S12 per-run scalar tables and HTML report browser**. It preserves pending scientific inclusion and can run before cohort-wide finalization. Optional Step 11 atlas extraction is independent.

Use the integrated command from `RS-fMRI/`:

```sh
python 04_workflow/lab.py export-results --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json
# Explicit persistent watcher; no preprocessing or model/API calls:
python 04_workflow/lab.py export-results --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json --watch
# Print a Step-12 command alongside the existing upstream plan, without exporting:
python 04_workflow/lab.py plan --config /ABS/PATH/generated/upstream.yaml --archive-root /ABS/PATH/archive --metrics-status /ABS/PATH/runtime/metrics-status.json
```


[Custom Step 12](02_custom/s12_metrics_summary/README.md) reads verified S10 archives and writes one-row CSV/TSV summaries plus a native-report HTML browser under each pair's `results/`. Inputs, units, missing-data behavior, multi-run isolation and validation are specified in the step contract. The optional local watcher handles newly archived pairs without model calls; it does not establish final inclusion.

### Step 11 adapters and coverage investigation

Execution order: **9.B metadata inclusion → actual raw BIDS/derivative run link → original acquisition frame map → Step 11 extraction → descriptive coverage diagnosis**. See the [Step 11 adapter commands](02_custom/s11_atlas_bold/README.md#original-acquisition-frames-and-actual-bids-run-evidence). Supply the hash-bound `--run-link` with the original 9.B artifact and image ID; `eligible`/`pending` remain separate. Supply `--frame-map` to preserve original frame numbers and time gaps in `frames.tsv`. Never reapply a pre-censor mask to a shortened XCP-D image. The adapter's nominal raw time does not include slice-timing offsets.

Low-coverage investigation compares the unchanged EPI mask with BOLD reference, T1, GM probability and anatomical mask. It writes evidence for review and retains the original QC failures. Coverage 0.5, minimum one voxel, nearest/28-day clinical matching and pending preservation are unchanged; the adapters do not authorize final cohort inclusion or relax study-specific duration criteria.

## Idle relocation of an existing runtime

After a current verified batch completes preprocessing, S8/XCP-D validation, archival and S12 export, the optional [7.B runtime relocation procedure](02_custom/s7b_sessionwise_preprocessing/README.md#idle-runtime-relocation) can pause idle services, move the runtime to an empty location on the same filesystem and resume after deployment/Docker checks. `04_workflow/runtime_relocation.py` preserves prior absolute paths through a compatibility symlink instead of rewriting historical scientific configuration or caches. New batch admission must be suspended before arming this external one-time watcher; active imaging calculations are never interrupted by it.

## XCP-D execution-resource recovery

The live compatibility workflow can apply a separately recorded [execution-resource override and terminal-worker monitor](02_custom/s10_xcpd_integrated_qc/README.md#execution-resources-and-terminal-worker-failures). Historical scientific configuration and completed results remain immutable; new attempt commands and `execution_environment.json` identify actual resource settings. Confirmed OOM or broken worker pools are treated as failed attempts rather than indefinitely running containers, and retries remain bounded. Inspect real retry output validation before considering recovery complete.

## Rolling admission and individual QC retention

The [7.B verified feeder](02_custom/s7b_sessionwise_preprocessing/README.md#external-archive-readiness-and-verified-batch-feeding) refills individual positions after verified external archival, maintaining a maximum five-subject rolling window instead of waiting for a whole batch. Existing active calculations remain intact through isolated subject workers and an idle-owner handoff. Each [S10 pair QC report](02_custom/s10_xcpd_integrated_qc/README.md#individual-qc-reports-and-retention-of-rejected-runs) records reasons, measured values and thresholds; rejected and skipped runs retain all available files in the verified external archive. Final research inclusion remains deferred.


The optional rolling feeder retains active owners and completed deliveries until verified archival, but removes exhausted execution failures from admission counting. Failed records, original work caches and bounded retry budgets are preserved; repaired retries have explicit priority and cannot exceed the five-subject window. See the [7.B recovery contract](02_custom/s7b_sessionwise_preprocessing/README.md#bounded-failure-recovery).


An optional, fingerprinted source-review skip policy takes precedence over retry priority and prior technical exceptions. It excludes pairs with existing unresolved source/protocol review flags or failed input verification before extraction, stage dispatch and automatic postprocessing. Skip reasons and per-pair JSON/HTML reports remain outside the repository; completed historical outputs are retained. Ordinary pending final-QC fields do not automatically exclude every pair. See the [7.B source-review skip contract](02_custom/s7b_sessionwise_preprocessing/README.md#automatic-source-review-skips).


Processing durations can be recorded automatically by the independent [Docker lifecycle timing observer](06_docs/processing_timing.md). It captures terminal events, separates failed attempts and queue holds, preserves timing quality and adds per-pair result CSV/JSON after S12 output ownership is established. Active imaging workers and frozen backends remain intact.

## Unattended host-local input batches

For a reserved, hash-verified handoff that must retain results locally, use the [native local batch supervisor](06_docs/local_batch.md). It delegates to 5.D → strict 7.B/7.C → S8/S10, shares the host-wide five-subject limit, preserves review holds and failed caches, and exposes local status without model/API calls. This separate opt-in service does not resume an older admission queue or install an external offloader.
