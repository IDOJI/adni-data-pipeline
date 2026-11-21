# RS-fMRI pipeline

Convert ADNI images into preprocessed/denoised BOLD, quality reports, ROI signals and analysis tables.

[Run one resting-state session by hand](#run-one-resting-state-session-by-hand) or [run a local batch](06_docs/local_batch.md). To practice without ADNI data, use the [public or synthetic examples](07_reproducibility/README.md).

New local runs use **seed 1123**, **fMRIPrep 25.2.7**, skull stripping and **one numerical thread**. Keep a new runtime for a new seed or source version.

## Structure

```text
RS-fMRI/
├── pipeline/           # All stages: s1_* through s12_*
├── 03_config/          # Configuration examples
├── 04_workflow/        # Batch runners and shared tools
├── 05_tests/           # Tests
├── 06_docs/            # Setup and reference
├── 07_reproducibility/ # Runnable examples
└── provenance/         # Historical source references
```

## Steps and commands

Main flow: **1–5 → MRIQC/fMRIPrep (6/7.B) → S8/S10 QC and XCP-D → clinical/final checks (9.A/9.B) → atlas signals (11)**. Step 12 independently exports completed archive metrics. **7.A is an alternative profile**; 7.C/7.D provide logs and timing.

Click the code name for its inputs, outputs and execution command. Run commands from `RS-fMRI/` after [setup](06_docs/installation.md).

| Step | Does | Produces | Code / commands |
|---|---|---|---|
| 1 | Obtain ADNI access | Approved account | [Manual portal step](pipeline/s1_setup_account/README.md) |
| 2 | Download images and Study Files | DICOM, metadata and clinical CSVs | [Manual portal step](pipeline/s2_download/README.md) |
| 3 | Inventory downloaded DICOMs | Inventory CSV and subject list | [create_dicom_dir_csv.sh](pipeline/s3_organize/README.md) |
| 3.A | Check source QC, NFQ and image identity | image_qc.tsv | [run.py](pipeline/s3a_source_qc/README.md) |
| 4 | Convert DICOM to BIDS | NIfTI, JSON and conversion records | [Clinica / Slurm helpers](pipeline/s4_clinica/README.md) |
| 4.B | Fill verified Philips SliceTiming | Updated sidecars and audit TSV | [insert_philips_slicetiming.py](pipeline/s4b_slice_timing/README.md) |
| 5 | Check converted images and scan parameters | Mastersheet and final_heuristics.tsv | [main.py + run_session_heuristics.py](pipeline/s5_post_clinica_qc/README.md) |
| 5.C | Create MRIQC/fMRIPrep input lists | Subject/session CSVs | [run.py](pipeline/s5c_validate_handoff/README.md) |
| 5.D | Verify an exact EPI–T1 pair | Binding receipt and prepared runtime | [binding.py + guarded_runner_seeded.py](pipeline/s5d_bids_identity/README.md) |
| 6 | Measure image quality | IQM tables and HTML reports | [run_seeded.py + iqm_seeded.py](pipeline/s6_mriqc/README.md) |
| 7 | Preprocess T1w and BOLD | Aligned images, confounds and reports | [run_seeded.py](pipeline/s7_fmriprep/README.md) |
| 7.A | Run the alternative volume/aCompCor profile | Volume derivatives and denoised BOLD | [pipeline_seeded.py](pipeline/s7a_volume_workflow/README.md) |
| 7.B | Run sessionwise MRIQC/fMRIPrep in Docker | Volume, surface/CIFTI and FreeSurfer outputs | [run_seeded.py](pipeline/s7b_sessionwise_preprocessing/README.md) |
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

## Run one resting-state session by hand

Choose one route for a new results directory. Each numbered block runs one stage in the foreground. Wait for it to finish and check its output before pasting the next block.

| What you have | Where to start | What you will get |
|---|---|---|
| An ADNI resting-state EPI and same-day T1w with source identity and QC evidence | [Verified ADNI pair](#route-a--verified-adni-pair) | MRIQC, surface-enabled fMRIPrep, motion/FreeSurfer QC and 36P/GSR XCP-D |
| A one-session BIDS dataset with T1w and resting BOLD | [Volume workflow](#route-b--one-session-bids-dataset) | Volume-only fMRIPrep and aCompCor XCP-D |
| DICOMs or an original download ZIP | [Steps 1–5 below](#steps-and-commands) | Access, conversion to BIDS, sidecars and source evidence for the imaging stages |

### Set up once and choose two paths

From a terminal with Git and Python 3.11+, use a new clone, or start at the `cd` line in an existing clone's parent folder. Install and start Docker, enable `linux/amd64` containers and share the input and output drives with Docker. The published configurations request a 16 GiB container limit for Route A and 24 GiB for Route B. Allow space for images, derivatives, the copied templates and work caches. Route A's pair publication uses macOS `/bin/cp -cR` and a filesystem that supports symbolic links. [Host requirements](06_docs/platform_execution.md)

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r pipeline/s5_post_clinica_qc/requirements.txt
python 04_workflow/lab.py doctor
```

Change **only the two paths** below. `DATA` is a private input folder. Put your valid FreeSurfer `license.txt` and a downloaded, usable `templateflow/` cache there. `RESULTS` is a **new directory name** under an existing writable parent, outside the repository and input tree. Use paths without commas or colons. Work in this terminal from `RS-fMRI/`. To resume in a new terminal, return there, activate `.venv` and repeat this block with the same paths. Keep the prepared results, work caches and logs.

```sh
export DATA="/absolute/path/to/your/input-folder"
export RESULTS="/absolute/path/to/your/new-results-folder"
export CASE="$RESULTS/pair/processing"
export CFG="$RESULTS/pair/verified-config.yaml"
export GUARD="pipeline/s5d_bids_identity/guarded_runner_seeded.py"
export XCP="pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py"
```

Load the pinned Docker images once. This block reads their digests from the repository. It adds the version tags needed by the session runner and stops if an existing tag points at another image. These are large downloads.

```sh
python - <<'PY'
import json, subprocess
from pathlib import Path
batch = json.loads(Path("03_config/local_batch.seeded.example.json").read_text())
xcp = json.loads(Path("03_config/xcpd_linc.seeded.example.json").read_text())
for reference in [*batch["pinned_images"].values(), xcp["image"]]:
    subprocess.run(["docker", "pull", "--platform", "linux/amd64", reference], check=True)
for stage, reference in batch["pinned_images"].items():
    tag = batch["preprocessing_template"]["images"][stage]
    inspect = subprocess.run(["docker", "image", "inspect", tag], capture_output=True, text=True)
    if inspect.returncode:
        subprocess.run(["docker", "tag", reference, tag], check=True)
    item = json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]
    resolved = next((d for d in item["RepoDigests"] if d.split("@")[0] == reference.split("@")[0]), None)
    if resolved != reference or (item["Os"], item["Architecture"]) != ("linux", "amd64"):
        raise SystemExit(f"Check the local image for {tag} before processing")
    print(stage, resolved)
PY
```

### Route A — Verified ADNI pair

**1. Bind the EPI to its T1w and prepare a private copy (5.D).** Supply either `$DATA/binding/07.binding-receipt.json` from [5.D](pipeline/s5d_bids_identity/README.md), with its referenced files and code still accessible, or the following inputs under `DATA` to generate a fresh receipt. The second form uses `bids/`, `candidate-audit.csv`, `04.epi-analysis-manifest.csv`, `pairing-run-manifest.json` and `hash-evidence.csv`. The last file is independent conversion evidence with `SOURCE_PTID`, `STUDY_DATE`, `MODALITY`, `SOURCE_IMAGE_ID` and `NIFTI_SHA256`. The pairing receipt must still resolve its original inputs and outputs.

The [path setup helper](04_workflow/manual_pair.py) uses the verified image IDs, series UIDs, dates, hashes and headers. It selects the sole preprocessing-ready pair and copies its two compressed NIfTI files and two sidecars. If several pairs qualify, use its `--epi-key` option to select one explicitly. The BOLD sidecar needs a documented `PhaseEncodingDirection` (distortion axis and sign) and `SliceTiming` (acquisition time of each slice). Check these against the acquisition evidence.

```sh
python 04_workflow/manual_pair.py prepare-adni --data "$DATA" --results "$RESULTS"
```

**2. Check identity and intake (5.D → 6).** The guard rechecks the four files. Intake evaluates scan depth, duration, TR and the other protocol heuristics. Continue only if `strict_upstream_eligible` is `True` for the selected pair. `failed_checks` identifies a hold.

```sh
python "$GUARD" check --config "$CFG" &&
python "$GUARD" intake --config "$CFG" &&
cat "$CASE/results/step5/intake_decisions.tsv"
```

**3. Measure image quality with MRIQC (6).** Preview shows the Docker arguments. The following `run` computes anatomical and functional image-quality metrics and writes the native HTML reports under `$CASE/derivatives/mriqc/`. Review these before preprocessing.

```sh
python "$GUARD" dry-run --stage mriqc --config "$CFG" &&
python "$GUARD" run --stage mriqc --config "$CFG"
```

**4. Preprocess T1w and BOLD with fMRIPrep (7.B, with 7.C logging).** This estimates head motion, performs sessionwise anatomical reconstruction, applies SyN distortion correction and aligns BOLD to the anatomical and template spaces. It also produces FreeSurfer surfaces, 91k CIFTI, confounds and an HTML report. The 7.C wrapper records ANTs registration iterations for this same run. Seed 1123 and one numerical thread come from the seeded configuration.

```sh
SUB=$(python -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["runs"][0]["subject"])' "$CFG") &&
python "$GUARD" check --config "$CFG" &&
python "$GUARD" dry-run --stage fmriprep --config "$CFG" &&
python pipeline/s7c_ants_iteration_logging/run.py \
  --runner pipeline/s7b_sessionwise_preprocessing/run_seeded.py -- \
  --config "$CFG" run --stage fmriprep --subject "$SUB"
```

The preprocessed volumes and `*_desc-confounds_timeseries.tsv` are under `$CASE/derivatives/fmriprep/`. Each actual attempt in `$CASE/logs/` has `console.log` and `run.json` with its command, image and inputs. For both MRIQC and fMRIPrep look for `execution_completed_QC_required`, `exit_code: 0` and `input_unchanged: true`. The fMRIPrep attempt also records the effective Docker command in `ants_logging.json`. To run 7.B without iteration logs instead, use `python "$GUARD" run --stage fmriprep --config "$CFG"` once.

**5. Summarize movement and surface quality (8).** The first command calculates framewise displacement (FD) from the confounds. The second extracts Euler values from FreeSurfer reconstruction. Read `motion_summary.tsv` and `euler_summary.tsv` in `$RESULTS/qc/8/`. Missing Euler values require review.

```sh
python pipeline/s8_final_qc/summarize_motion_from_confounds.py \
  --derivatives-dir "$CASE/derivatives/fmriprep" --output-dir "$RESULTS/qc/8" &&
(python_script="$PWD/pipeline/s8_final_qc/extract_euler_from_freesurfer.py"
 cd "$RESULTS/qc/8" && python "$python_script" \
  --freesurfer-dir "$CASE/derivatives/fmriprep/sourcedata/freesurfer" \
  --output-tsv "$RESULTS/qc/8/euler_summary.tsv")
```

**6. Check how much low-motion data remains (8.A).** The script matches original BOLD time points to confound rows. It reports whether at most 30% of frames exceed 0.5 mm FD and at least 300 seconds remain. Inspect `paper_motion_summary.tsv` and the per-frame masks.

```sh
python pipeline/s8a_motion_duration_qc/run.py \
  --bids-root "$CASE/bids" --derivatives-root "$CASE/derivatives/fmriprep" \
  --output-dir "$RESULTS/qc/8a"
```

**7. Deliver the completed pair to XCP-D.** The helper checks both successful run records, their input hashes and required output files. The repository's [pair publisher](pipeline/s7b_sessionwise_preprocessing/publish_pairs.py) then copies both derivative trees into the scan-date folder under `$RESULTS/results/`. The printed path contains `pair_metadata.json`. Publication is local to your results drive.

```sh
python 04_workflow/manual_pair.py publish --results "$RESULTS"
```

**8. Check the XCP-D candidate (10).** Preflight checks the paths and pinned XCP-D version. The dry run evaluates the published pair and saves the proposed Docker command in `postprocessing/*/dry_run.json`. Expect `candidates: 1` for an eligible single run. For zero candidates, inspect `postprocessing/*/events.jsonl` if present and the pair's `s10/*/pre_qc.json` before proceeding.

```sh
python "$XCP" --config "$RESULTS/xcpd.json" preflight &&
python "$XCP" --config "$RESULTS/xcpd.json" dry-run
```

**9. Denoise the eligible run (10).** `pilot` processes one candidate. This profile uses 36 nuisance regressors including global signal, 0.01–0.08 Hz filtering, 6 mm smoothing, a 0.3 mm FD threshold and a 240-second minimum. Successful outputs include denoised BOLD, 4S256Parcels time series and connectivity, ReHo and ALFF under the pair's `s10/*/runs/*/attempt-*/derivatives/`.

```sh
python "$XCP" --config "$RESULTS/xcpd.json" pilot
```

**10. Verify the outcome and review the reports.** `collect` writes `final_qc_master.tsv` in `$RESULTS/postprocessing/` under the configuration ID. The following check reads the latest XCP-D attempt in this single-pair run. A short scan can legitimately be skipped. A held, skipped or failed run has no verified denoised result. Review the pair's `qc_report.html` and the native image reports to decide research inclusion.

```sh
python "$XCP" --config "$RESULTS/xcpd.json" collect &&
python - "$RESULTS" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]) / "results"
attempts = sorted(root.glob("*/*/s10/*/runs/*/attempt-*/execution.json"))
if not attempts:
    raise SystemExit("No XCP-D execution record. Check pre_qc.json and events.jsonl.")
path = attempts[-1]
run = json.loads(path.read_text())
print(path, run.get("status"), "exit", run.get("exit_code"), flush=True)
if (run.get("status"), run.get("exit_code"), run.get("input_unchanged")) != ("success", 0, True):
    raise SystemExit("Denoising was not verified. Review the execution record.")
qc = json.loads(path.with_name("output_validation.json").read_text())
if qc.get("functional_outputs_valid") is not True:
    raise SystemExit("Output validation requires review.")
print("Validated denoised outputs:", path.parent / "derivatives")
PY
```

For a timing summary after any completed stage, run `python pipeline/s7d_processing_timing/run.py --root "$RESULTS"`. Clinical joins (9/9.A/9.B), custom atlas extraction (11) and archive export (12) use additional inputs listed in the [stage table](#steps-and-commands).

### Route B — One-session BIDS dataset

Choose this route for the repository's **volume-only** protocol. Under `$DATA/bids/`, supply `dataset_description.json`, one `sub-*/ses-*/` with `func/*_task-rest*_bold.nii.gz` and the matching BIDS metadata, plus a T1w in the session or subject `anat/`. Check acquisition metadata for the requested SyN correction. Use the two paths and resources from setup and a new `RESULTS` for this route.

**1. Prepare the volume configuration.** This discovers the BIDS labels, copies TemplateFlow to the results drive and fills the published [7.A profile](pipeline/s7a_volume_workflow/README.md).

```sh
python 04_workflow/manual_pair.py prepare-volume --data "$DATA" --results "$RESULTS"
```

**2. Preview the fMRIPrep command.** Define this shell function once in each terminal. It passes the discovered labels to the repository's seeded 7.A runner and propagates its exit status. `dry-run` prints the Docker command.

```sh
volume_stage() {
  python - "$RESULTS/volume.json" "$@" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path("pipeline/s7a_volume_workflow").resolve()))
import pipeline_seeded
config, action, stage = sys.argv[1:]
run, = json.loads(Path(config).read_text())["runs"]
sys.exit(pipeline_seeded.main(["--config", config, action, "--stage", stage,
                               "--subject", run["subject"], "--session", run["session"]]))
PY
}
volume_stage dry-run fmriprep
```

**3. Run fMRIPrep and verify the derivatives.** This profile delivers standard-space BOLD in MNI152NLin2009cAsym at 2 mm, plus confounds and a report under `$RESULTS/fmriprep_output/`. It skips FreeSurfer reconstruction.

```sh
volume_stage run fmriprep && volume_stage verify fmriprep
```

**4. Run XCP-D and verify the denoised BOLD.** This uses aCompCor without global signal regression, 0.5 mm FD censoring and a 240-second minimum. Inspect `$RESULTS/xcpd_output/` and `$RESULTS/logs/`. The profile skips parcellation, ALFF and ReHo.

```sh
volume_stage dry-run xcpd &&
volume_stage run xcpd &&
volume_stage verify xcpd
```

### Optional cohort and analysis steps

The [stage table](#steps-and-commands) links each program, including the manual download and DICOM conversion steps. If you are starting from DICOM, do the [inventory](pipeline/s3_organize/README.md), [source QC](pipeline/s3a_source_qc/README.md), [Clinica conversion](pipeline/s4_clinica/README.md), [Philips timing review when applicable](pipeline/s4b_slice_timing/README.md), [converted-image QC](pipeline/s5_post_clinica_qc/README.md) and [handoff validation](pipeline/s5c_validate_handoff/README.md) before binding. Preserve the acquisition evidence used for 5.D. The single-pair walkthrough assumes the pair is cleared for manual processing. For a managed cohort, use its existing [batch registration and admission rules](06_docs/local_batch.md).

<details>
<summary>Run clinical validation, eligibility checks or archive export when their inputs are ready</summary>

**Clinical checks (9.A).** Put the reviewed cohort's matched `final_included_runs.tsv` and `clinical_scan_links.tsv` under `$DATA/review/` and the original `DXSUM.csv` and `PTDEMOG.csv` under `$DATA/clinical/`. This validates diagnosis against the scan date using a 28-day window and reports missing and ambiguous records. The single-pair `collect` step leaves final inclusion open.

```sh
python pipeline/s9a_validate_clinical/run.py \
  --included "$DATA/review/final_included_runs.tsv" \
  --scan-links "$DATA/review/clinical_scan_links.tsv" \
  --dxsum "$DATA/clinical/DXSUM.csv" --ptdemog "$DATA/clinical/PTDEMOG.csv" \
  --max-dx-days 28 --dx-direction nearest --output-dir "$RESULTS/qc/9a"
```

**Eligibility (9.B).** Supply the original 3.A artifact directory at `$DATA/review/source-qc/` and the reviewed slice-timing exclusions at `$DATA/review/confirmed-st-absence.csv`. This joins evidence by image identity and writes separate retained, pending, held and excluded tables. Supply the optional `--conversion-failures` file when the cohort has confirmed conversion exclusions.

```sh
python pipeline/s9b_validate_inclusion/run.py \
  --source-qc "$DATA/review/source-qc" --clinical "$RESULTS/qc/9a" \
  --confirmed-st-absence "$DATA/review/confirmed-st-absence.csv" \
  --output-dir "$RESULTS/qc/9b"
```

**Atlas signals (11).** Route A already produces the 4S256Parcels time series. For a different atlas, list the catalog for the output space, then follow the [frame/run mapping](pipeline/s11_atlas_bold/adapters.md) and [extraction commands](pipeline/s11_atlas_bold/README.md) with reviewed inclusion evidence, a matching mask and the acquisition-frame mapping for censored data.

```sh
python pipeline/s11_atlas_bold/run.py list --space MNI152NLin6Asym
```

**Archive metrics (12).** For a verified, writable S10 archive under `$RESULTS/archive/`, this exports `results/metrics.csv` and an HTML index inside each archived pair. A locally published preprocessing pair still needs the archive receipts required by this exporter.

```sh
python 04_workflow/lab.py export-results \
  --archive-root "$RESULTS/archive" --status "$RESULTS/metrics-status.json"
```

</details>

## Configuration

Keep data, private configuration and results outside this repository, for example under `ADNI_DATA/config/` and `ADNI_DATA/results/`.

| Task | Configuration / guide |
|---|---|
| New local batch: preprocessing + XCP-D | [local_batch.seeded.example.json](03_config/local_batch.seeded.example.json) · [commands](06_docs/local_batch.md) |
| XCP-D for completed pairs | [xcpd_linc.seeded.example.json](03_config/xcpd_linc.seeded.example.json) |
| Alternative volume profile | [config.seeded.example.json](pipeline/s7a_volume_workflow/config.seeded.example.json) |
| DICOM/Clinica and shared paths | [lab_config.example.yaml](03_config/lab_config.example.yaml) · [generate YAML](06_docs/installation.md#configuration) |

Check quantitative QC and native HTML reports before final inclusion. Code tests and successful processing alone do not approve research inclusion.

## Reference

[Seed settings](06_docs/seed_reproducibility.md) · [Host requirements](06_docs/platform_execution.md) · [Validation](06_docs/validation.md) · [Updates](06_docs/update_guide.md)

Adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3). Original [GPL license](pipeline/LICENSE), [CITATION.cff](pipeline/CITATION.cff) and [attribution](NOTICE.md) are retained.
