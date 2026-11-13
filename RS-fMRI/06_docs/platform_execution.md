# macOS and Linux execution by stage

## Common setup

```sh
git clone --branch main https://github.com/IDOJI/adni-data-pipeline.git "$HOME/adni-platform-source"
cd "$HOME/adni-platform-source/RS-fMRI"
python3 -m venv "$HOME/.venvs/adni-platform"
source "$HOME/.venvs/adni-platform/bin/activate"
python -m pip install -r 07_reproducibility/requirements.lock.txt
python -m pip install -r pipeline/s5_post_clinica_qc/requirements.txt
python 04_workflow/lab.py doctor
export PUBLIC_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/adni-public.XXXXXX")/run"
python 07_reproducibility/public.py fetch --root "$PUBLIC_ROOT"
```

From a new source checkout, create a wrapper environment and inspect the included source/provenance; no core submodule initialization is needed. Keep private inputs/work/results outside the repository; the included CC0 sample is the explicit public-data exception.

`fetch` copies and hash-checks the real MRI files included in Git without accessing OpenNeuro. The pinned core requirements support the example tools; the additional upstream requirements supply DICOM parsing and Plotly reporting for 5.A/5.B/9. Those upstream extras are not version-locked by the core example file. For the full development suite, install `requirements.txt` and run the repository tests as documented in [installation](installation.md). Use the [complete example](../07_reproducibility/README.md) for the separate synthetic reference, expected results and all ten synthetic stages.

The following stages apply to both hosts unless a host-specific boundary is stated. Real ADNI commands still require authorized external Study Files, selected inputs and private configuration. The public subject does not supply ADNI clinical/source evidence.

### Set paths for private ADNI commands

```sh
export RSFMRI_ROOT="$PWD"
export ADNI_PIPELINE="$RSFMRI_ROOT/pipeline"
export ADNI_DATA_ROOT=/ABSOLUTE/PATH/ADNI_DATA
export PIPELINE_CONFIG=/ABSOLUTE/PATH/ADNI_DATA/config/run-001/pipeline.yaml
export ADNI_CONFIG="$PIPELINE_CONFIG"
export PYTHONPATH="$ADNI_PIPELINE${PYTHONPATH:+:$PYTHONPATH}"
test -d "$ADNI_DATA_ROOT"
test -f "$PIPELINE_CONFIG"
```

Run this block from `RS-fMRI/` after activating the environment. Replace `/ABSOLUTE/PATH` with this host's actual paths and use an existing rendered external YAML. To create it first, follow [configuration and handoffs](../README.md#-configuration-and-handoffs). `ADNI_CONFIG` and `PYTHONPATH` let upstream scripts load that configuration and their pinned utilities; they do not change scientific settings. Commands below using `ADNI_DATA_ROOT` are ADNI commands. Commands using `PUBLIC_ROOT` are the separate public-image example.

Read one stage at a time: **terminal command → what it does → results and host requirements**. This is a command reference, not a block to execute from S1 through S12 without checking prerequisites. The initial command is explicitly marked as a preview when it only plans work.

Use **the same selected image pairs, source metadata, container digests, analysis profile and QC policy** on both hosts. Change host paths, container access and service management explicitly. A Linux host does not make the Mac controller, publisher or external-disk checker portable automatically.

This guide documents the implementation present in the repository. It adds instructions only: no running container, scientific option, service or retry policy is changed.

## Support and validation

| Layer | macOS | Native Linux x86-64 |
|---|---|---|
| Python source/handoff/QC/clinical/atlas/scalar tools | Code and synthetic checks; external paths required | Ubuntu CI runs code/synthetic checks with Python 3.11/3.12; external paths required |
| Public MRIQC/fMRIPrep/XCP-D demo | Docker Desktop, `linux/amd64`; Apple Silicon uses emulation | Docker Engine, same `linux/amd64` images and application options |
| Full public-subject imaging baseline | Inputs and command construction verified; full calculation not established by the public example | Full calculation and cross-host imaging equivalence not established |
| Existing five-subject controller | Contains Mac-specific startup/keep-awake integration | Requires a controller/service port; installing Linux is insufficient |
| 7.B pair publication and S10 archival | Uses Mac copy/volume commands | Requires copy and mounted-volume validation adapters |

An ARM64 Linux machine still differs from the pinned AMD64 container architecture. WSL2 can provide a Linux shell/Docker integration, but the complete WSL deployment has not been validated here. Native Windows Python/PowerShell is not the target for the Bash examples or Unix locking code.

## macOS

Install Python 3.11+ and Git, and prepare [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) for imaging execution. Python-only stages do not require Docker. Validate the engine before launching a new job:

```sh
python3 --version
git --version
docker info --format '{{.OSType}} / {{.Architecture}}'
```

Keep the images pinned to `linux/amd64`. Intel Macs match that CPU architecture; Apple Silicon uses AMD64 emulation. Check the selected VM backend and its emulation support rather than assuming every backend supports Rosetta. Docker currently documents that Docker VMM on Mac does not support Rosetta; see [VM backend details](https://docs.docker.com/desktop/features/vmm/). Configure a new host or an idle engine separately from running calculations. XCP-D also documents Apple-Silicon caveats in its [versioned usage guide](https://xcp-d.readthedocs.io/en/26.2.0/usage.html).

Example private host paths:

```sh
export ADNI_DATA_ROOT="$HOME/adni-data"
export ADNI_WORK_ROOT="$HOME/adni-work"
export FS_LICENSE="$HOME/freesurfer/license.txt"
mkdir -p "$ADNI_DATA_ROOT" "$ADNI_WORK_ROOT"
```

Use the actual mounted `/Volumes/<volume>/...` archive path only after verifying the intended disk. Docker Desktop must be able to access the selected bind-mount paths. Its VM allocation, a container's `--memory` limit and the workflow's `--mem-mb` are different limits; preserve the effective per-run settings in provenance.

## Linux

For an Intel/AMD notebook or server, use a supported Ubuntu LTS and [Docker Engine for Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Docker Desktop is not required for this route. Prepare Git, a Python 3.11+ virtual environment and access to the Docker daemon using the official installation procedure. Run the same engine checks shown for macOS; the Docker OS must be `linux`.

Example private host paths:

```sh
export ADNI_DATA_ROOT="$HOME/adni-data"
export ADNI_WORK_ROOT="$HOME/adni-work"
export FS_LICENSE="$HOME/freesurfer/license.txt"
mkdir -p "$ADNI_DATA_ROOT" "$ADNI_WORK_ROOT"
```

Place work/cache directories on a local Linux filesystem, with an external archive mounted at a separately verified path such as `/mnt/<volume>/...`. Container paths such as `/data`, `/out` and `/work` remain the same; their host-side bind sources change. Do not copy Mac `/Volumes/...` values into a Linux configuration. Docker containers supply the imaging binaries; host Python packages alone do not install the complete imaging environment.

A Linux notebook does not provide Slurm simply because it runs Linux. Use the Docker route for a local workstation, or the integrated protocol’s Slurm/Apptainer route only on an actual configured cluster. No Linux service unit, mounted-volume adapter or live five-subject queue is installed by this documentation.

## S1

**Manual action — no terminal command:** Obtain ADNI approval and accept the required access/usage terms in the ADNI portal.

**Account and access.** The same ADNI access/usage requirements apply on either OS. Complete the upstream access steps personally; no local container or synthetic test supplies ADNI authorization. See the local protocol links in the [execution table](../README.md#-complete-execution-order).

## S2

**Manual action — no terminal command:** Download the reviewed ADNI image collection and Study Files through the authorized ADNI portal; preserve the collection CSVs.

**Download.** Preserve the same selected image IDs, collection CSVs and raw metadata on both hosts. Store licensed ADNI inputs under the external data root. The included OpenNeuro example starts from NIfTI and does not reproduce ADNI portal downloads or become ADNI source-QC evidence.

## S3

```sh
bash "$ADNI_PIPELINE/s3_organize/create_dicom_dir_csv.sh" \
  --config "$PIPELINE_CONFIG"
```

**What this does:** Builds the actual downloaded-DICOM inventory from the configured DICOM root.

**Results:** `unzipped_dicom_dirs_inventory.csv` in that DICOM root; the utility rewrites this inventory file, so preserve an earlier inventory if needed.

### How it works and host requirements

**Organization and download inventory.** Run the pinned Bash inventory utility through a reviewed external configuration on either POSIX host. Its paths must refer to that host's actual DICOM tree. `lab.py plan` prints the upstream stage-3 command; it does not execute it. Keep the original archive and compare the same member/image identities before reusing extracted inputs.

For the private upstream route, supply an existing rendered configuration:

```sh
: "${PIPELINE_CONFIG:?Set the absolute external pipeline YAML path}"
python 04_workflow/lab.py plan --config "$PIPELINE_CONFIG"
```

This prints plans for the supported entry points, including dry-run Slurm commands. Review working directories and cluster assumptions before running a printed command. The planner is not a general Mac/Linux scheduler.

## S3A

```sh
python pipeline/s3a_source_qc/run.py \
  --mriqc-table /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MRIQC.csv \
  --adni3-qc /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MAYO_ADNI3.csv \
  --go2-qc /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MAYO_GO2.csv \
  --deleted-scans /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DELMRSCANS.csv \
  --nfq GO2_3=/ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/NFQ.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step3a
```

**What this does:** Audits source image identity, ADNI quality/NFQ records and deletion evidence before downstream handoff.

**Results:** `image_qc.tsv`, source-row evidence and a hash-bound `artifact.json` in the selected output directory.

### How it works and host requirements

**Source QC/NFQ.** Run the same Python CLI on macOS and Linux with host-correct Study Files paths. Preserve source hashes, quality rules, pending status and identity/deletion conflicts. The [3.A execution example](../pipeline/s3a_source_qc/README.md#execution) and offline `toy.py --step 3a` use the same implementation. No Docker, Slurm or service manager is required by this step.

## S4

```sh
mkdir -p "$(python -m utils.config_tools paths.slurm_jobs_dir --config "$PIPELINE_CONFIG")"
bash "$ADNI_PIPELINE/s4_clinica/create_slurm_script_per_sub.sh" \
  --config "$PIPELINE_CONFIG"
```

**What this does:** Generates per-subject Clinica Slurm scripts from the configured subject list and reviewed template. This block creates jobs, not converted images.

**Results:** Subject-specific job files under the configured `paths.slurm_jobs_dir`. Review the template paths, environment and notification settings before submitting.

### How it works and host requirements

**Clinica conversion.** The integrated protocol’s per-subject generator/submission route targets a configured Slurm environment. macOS needs an explicitly prepared Clinica/dcm2niix environment or a reviewed Linux conversion host; running a Slurm template in Terminal does not create a Mac launcher. Native Linux needs the converter dependencies too; a notebook still has no scheduler by default. Review the external conversion job's paths/environment/notification settings before submission.

Keep the converter version and conversion records when comparing hosts. Already converted NIfTI inputs need verified identity/metadata and the intended EPI–T1 pair; do not reconvert solely because the host OS changed. The public example preserves its source NIfTI bytes and adds only its documented execution layout.

### Submit only on the reviewed Slurm host

```sh
bash "$ADNI_PIPELINE/s4_clinica/adni_submit_slurm.sh" \
  --config "$PIPELINE_CONFIG"
```

This submits the generated jobs and starts actual conversion through the configured template. It requires real Slurm/Clinica dependencies. After completion, review the pinned merge utility and its conversion-info handling before merging outputs; do not treat job generation as successful conversion.

## S4B

```sh
python "$ADNI_PIPELINE/s4b_slice_timing/insert_philips_slicetiming.py" \
  --config "$PIPELINE_CONFIG" --dry-run
```

**What this does:** Previews Philips SliceTiming updates using the configured metadata and BIDS files.

**Results:** The configured report TSV; `--dry-run` leaves BOLD JSON sidecars unchanged. Removing that flag performs in-place sidecar writes and requires reviewed identity/slice-axis evidence.

### How it works and host requirements

**Philips SliceTiming.** The Python dry-run path is the same on both hosts. `lab.py plan` includes the configured `insert_philips_slicetiming.py --dry-run` command. Inspect actual image identity, slice-axis correspondence and metadata evidence before an authorized write. Changing host OS never supplies missing slice timing or licenses a guessed acquisition order.

## S5AB

```sh
mkdir -p "$ADNI_DATA_ROOT/qc/step5a"
(
  cd "$ADNI_DATA_ROOT/qc/step5a"
  python "$ADNI_PIPELINE/s5_post_clinica_qc/create_mastersheet/main.py" \
    --config "$PIPELINE_CONFIG"
)
python "$ADNI_PIPELINE/s5_post_clinica_qc/create_report/run_session_heuristics.py" \
  --input-csv "$ADNI_DATA_ROOT/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv" \
  --output-dir "$ADNI_DATA_ROOT/qc/step5"
```

**What this does:** Builds the upstream image/metadata mastersheet in an external working directory, then runs the session-level post-Clinica heuristics.

**Results:** `qc/step5a/data/anchor_plus_dicom_nifti_struct.csv` and Step-5 TSVs including `qc/step5/final_heuristics.tsv`. The subshell confines the mastersheet's relative `data/` output to the external tree.

### How it works and host requirements

**Post-Clinica 5.A/5.B.** Use the same upstream heuristics/mastersheet rules. Prepare the required Python/R environments on the selected host and use external output directories. In particular, 5.A writes a relative `data/` directory: the planner places its working directory under external `qc/step5a`, not in the source tree. Review hardcoded/script-specific settings as well as the rendered YAML. This guide does not replace the original R selection scripts with a synthetic handoff.

## S5C

```sh
python pipeline/s5c_validate_handoff/run.py \
  --input /ABSOLUTE/PATH/ADNI_DATA/qc/step5/final_heuristics.tsv \
  --source-qc /ABSOLUTE/PATH/ADNI_DATA/qc/step3a \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step5c
```

**What this does:** Validates the sessions already retained by Step 5, checks the supplied 3.A evidence, and writes the CSV/TSV inputs expected by Steps 6 and 7.

**Results:** `mriqc_subjects.csv`, `post_clinica.csv`, `mriqc_sessions.csv`, `valid_sessions.tsv` and `handoff.json`; blocked/pending cases remain audited.

### How it works and host requirements

**Handoff validation.** Use the same Python CLI, including the 3.A source artifact when applying that gate. Retain the TSV/CSV delimiter contracts and the exact `mriqc_sessions.csv` handoff. Upstream MRIQC remains subject-scoped; a Linux host does not fix that session-selection boundary. Rebuild path-bearing provenance for a new host rather than editing old hash-bound receipts.

## S5D

```sh
python pipeline/s5d_bids_identity/binding.py --config /external/binding-config.json
python pipeline/s5d_bids_identity/guarded_runner.py verify-pair \
  --receipt /external/binding/07.binding-receipt.json --epi-key EXTERNAL_EPI_KEY
python pipeline/s5d_bids_identity/guarded_runner.py prepare \
  --receipt /external/binding/07.binding-receipt.json --epi-key EXTERNAL_EPI_KEY \
  --runtime /external/NEW_ISOLATED_PAIR --template /external/step7b-template.yaml
python pipeline/s5d_bids_identity/guarded_runner.py intake --config /external/NEW_ISOLATED_PAIR/verified-config.yaml
python pipeline/s5d_bids_identity/guarded_runner.py dry-run --stage fmriprep --config /external/NEW_ISOLATED_PAIR/verified-config.yaml
```

**What this does:** Checks the proposed EPI–T1 pair against source UIDs, Image IDs, dates and independent file hashes, then prepares an isolated verified input view.

**Results:** Binding/audit tables, `07.binding-receipt.json`, and a separate prepared runtime for dispatch-eligible pairs. The preview does not run fMRIPrep.

### How it works and host requirements

**Exact EPI–T1 binding.** Set the external BIDS roots, registry, independent hash evidence and output directory to the new host. Run `binding.py --config ...`, then use the guarded entry point for an eligible exact pair. Preserve actual image dates/IDs, proposed pairing and held rows. `guarded_runner.py` delegates computation to 7.B; it does not make the Mac controller or pair publisher Linux-compatible.

## S6

```sh
(
  cd "$ADNI_PIPELINE"
  bash s6_mriqc/adni_mriqc.slurm --config "$PIPELINE_CONFIG" --dry-run
)
```

**What this does:** Creates the ADNI MRIQC array-job preview from the configured Step-5.C inputs. This initial block writes job files without submitting imaging jobs.

**Results:** Configured external MRIQC scripts/job inputs. The upstream launcher is participant-scoped; review the session/fitting population before real execution.

### Execute on the reviewed Slurm/Apptainer host

```sh
(
  cd "$ADNI_PIPELINE"
  bash s6_mriqc/adni_mriqc.slurm --config "$PIPELINE_CONFIG"
)
```

This submits real jobs. It requires configured Slurm/Apptainer infrastructure; a local Mac/Linux notebook needs the prepared single-case Docker route in [7.B](../pipeline/s7b_sessionwise_preprocessing/README.md#execution) instead. Use the guarded runner when inputs came from 5.D. Preserve the selected route's analysis profile.

### Standalone public-image Docker example

```sh
python 07_reproducibility/public.py pull --root "$PUBLIC_ROOT" --execute
python 07_reproducibility/public.py mriqc --root "$PUBLIC_ROOT"
python 07_reproducibility/public.py mriqc --root "$PUBLIC_ROOT" --execute
```

These commands use `PUBLIC_ROOT`, not ADNI Study Files or the private ADNI runtime. A command with `--execute` starts real computation; omit that flag for the public command preview.

### How it works and host requirements

**MRIQC.** On a local Mac use Docker Desktop; on native Linux x86-64 use Docker Engine. The public example uses the same digest, selected BIDS filter, modality/session scope and application arguments on both hosts. After common setup, an existing valid FreeSurfer license is needed for later stages, not MRIQC itself.

The first public-example command pulls the pinned containers. Later execution can also download multi-GB template/atlas payloads.

Within the public block, the middle command prints the actual Docker argv and the final command runs it. Inspect native IQMs and HTML under `derivatives/mriqc/`. A single public subject cannot calibrate cohort outlier thresholds. For ADNI use reviewed 5.C/5.D inputs and 7.B's configured single-case launcher, or the upstream cluster route on actual Slurm/Apptainer infrastructure.

## S7

```sh
(
  cd "$ADNI_PIPELINE"
  bash s7_fmriprep/run_fmriprep_bids_filter_array_all.sh \
    --config "$PIPELINE_CONFIG" \
    --sessions-csv "$ADNI_DATA_ROOT/qc/step5c/mriqc_sessions.csv" --dry-run
)
```

**What this does:** Creates the ADNI fMRIPrep array-job preview with the explicit Step-5.C sessions. It writes job/filter files without launching fMRIPrep.

**Results:** Configured external scripts and BIDS filters. Review the selected image/session scope and actual cluster/image/resource paths before submission.

### Execute on the reviewed Slurm/Apptainer host

```sh
(
  cd "$ADNI_PIPELINE"
  bash s7_fmriprep/run_fmriprep_bids_filter_array_all.sh \
    --config "$PIPELINE_CONFIG" \
    --sessions-csv "$ADNI_DATA_ROOT/qc/step5c/mriqc_sessions.csv"
)
```

This submits real jobs. It requires configured Slurm/Apptainer infrastructure; a local Mac/Linux notebook needs the prepared single-case Docker route in [7.B](../pipeline/s7b_sessionwise_preprocessing/README.md#execution) instead. Use the guarded runner when inputs came from 5.D. Preserve the selected route's analysis profile.

### Standalone public-image Docker example

```sh
: "${FS_LICENSE:?Set the absolute path to your valid FreeSurfer license.txt}"
test -f "$FS_LICENSE"
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" --license "$FS_LICENSE"
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" --license "$FS_LICENSE" --ants-verbose --execute
```

These commands use `PUBLIC_ROOT`, not ADNI Study Files or the private ADNI runtime. A command with `--execute` starts real computation; omit that flag for the public command preview. S7C shows the same logging-enabled fMRIPrep launch, so choose it once.

### How it works and host requirements

**fMRIPrep.** The same local-container route applies on both hosts. Preserve the profile's version/digest, sessionwise reference, susceptibility correction, standard/surface/CIFTI outputs, seed and process/thread settings. The public example's imaging options are in `public.py`; changing OS does not justify switching to the separate 7.A profile or changing analysis flags.

Outputs are under `derivatives/fmriprep/`, work under `work/fmriprep/`, and native report/FreeSurfer/confounds evidence must be checked after completion. The command starts a real long calculation. Omit `--execute` to inspect the base command. Never infer successful completion from a live container alone.

The upstream Step-7 launcher is a separate Slurm/Apptainer route, and 7.B is the explicit-pair Docker adapter. Neither upstream Slurm nor the Mac queue becomes a local Linux scheduler automatically.

## S7A

```sh
python pipeline/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json dry-run --stage fmriprep --subject 999S9999
```

**What this does:** First prints the Docker command for the separate volume/aCompCor profile. The explicitly selected `run` commands below perform the imaging calculations.

**Results:** External volume-profile derivatives and attempt evidence; `verify` checks the recorded stage output. Keep this profile separate from 7.B/S10.

### How it works and host requirements

**Alternative volume/aCompCor profile.** Its single-case Docker command/audit tools use external paths on both hosts. Preserve this profile's own MNI2009c, aCompCor/no-GSR, FD0.5 and surface-disabled settings and separate caches. It is not the S7/S10 surface-enabled 36P-LINC reference. Follow its [execution contract](../pipeline/s7a_volume_workflow/README.md#execution); no new Linux full-imaging validation is claimed.

For real processing, use the separate [7.A execution commands](../pipeline/s7a_volume_workflow/README.md#execute-the-selected-profile) after checking the preview.

## S7B

```sh
: "${STEP7B_CONFIG:?Set the external verified 7.B YAML path}"
: "${ADNI_SUBJECT:?Set the bare subject label recorded in that configuration}"
python pipeline/s7b_sessionwise_preprocessing/run.py --config "$STEP7B_CONFIG" dry-run --stage fmriprep --subject "$ADNI_SUBJECT"
```

**What this does:** First inspects the configured single-case fMRIPrep command. The explicit `run` form below launches the selected case with the sessionwise surface-enabled profile.

**Results:** External work, derivatives and attempt logs for that case. Publishing completed pairs and operating a live queue are separate actions.

### How it works and host requirements

**Sessionwise launcher, publication and queue.** Distinguish three pieces:

1. `run.py` prepares/selects one configured case and builds Docker argv using host bind sources. Its single-case dry-run and reviewed run path are the Linux-compatible starting point, with real Linux execution still requiring validation.
2. `publish_pairs.py` invokes macOS `/bin/cp -cR`. GNU/Linux `cp` does not provide that same clone option. A Linux publisher must preserve run/pair identity, unchanged source evidence, relative report assets and copy validation before S10 can consume the strict ADNI pair layout.
3. `04_workflow/queue_service.py` starts `/usr/bin/caffeinate`. The private Mac live deployment uses host startup/watchdog integration. Linux needs a port and reviewed service configuration; replacing `launchctl` with a unit name in a config is not enough.

The inspection command above is shared once its private config uses valid host paths.

This may create external filter/work directories and requires the pinned image to be installed, but launches no imaging job. This documentation does not implement the missing Linux publisher/controller. Public `public.py` imaging examples use their own standalone output layout and do not assert that the entire private ADNI chain is portable.

### Run one already prepared case

```sh
python pipeline/s7b_sessionwise_preprocessing/run.py \
  --config "$STEP7B_CONFIG" run --stage fmriprep --subject "$ADNI_SUBJECT"
```

This launches real fMRIPrep; use the guarded 5.D entry point for receipt-bound pairs. See the [7.B execution contract](../pipeline/s7b_sessionwise_preprocessing/README.md#execution) for MRIQC intake and the separate Mac queue.

## S7C

```sh
: "${PUBLIC_ROOT:?Complete common setup and the public MRIQC stage first}"
: "${FS_LICENSE:?Set your valid external FreeSurfer license file}"
python 07_reproducibility/public.py fmriprep \
  --root "$PUBLIC_ROOT" --license "$FS_LICENSE" --ants-verbose --execute
```

**What this does:** Starts a new public-example fMRIPrep calculation with the existing ANTs logging wrapper. This is an alternative launch for S7, not a second run after S7 has already completed.

**Results:** fMRIPrep outputs plus `ants_logging.json` and per-invocation raw/parsed iteration logs under the public root.

### How it works and host requirements

**ANTs logging.** The wrapper lives inside the unchanged Linux container, so the same `--ants-verbose` public command applies to both hosts. Keep the original image PATH, computational argv and logging provenance. Use the existing wrapper rather than changing registration iteration schedules. Mac controller activation/keep-awake logic is separate from this transport and needs a Linux service implementation if used there.

## S8

```sh
python "$ADNI_PIPELINE/s8_final_qc/summarize_motion_from_confounds.py" \
  --derivatives-dir "$ADNI_DATA_ROOT/derivatives/fmriprep" \
  --output-dir "$ADNI_DATA_ROOT/qc/step8"
python "$ADNI_PIPELINE/s8_final_qc/extract_euler_from_freesurfer.py" \
  --freesurfer-dir "$ADNI_DATA_ROOT/derivatives/sourcedata/freesurfer" \
  --output-tsv "$ADNI_DATA_ROOT/qc/step8/euler_summary.tsv"
```

**What this does:** Reads completed ADNI fMRIPrep confounds and FreeSurfer logs to summarize motion and Euler metrics. A fallback Euler calculation needs FreeSurfer binaries.

**Results:** `qc/step8/motion_summary.tsv`, `motion_timeseries.tsv` and `euler_summary.tsv`. These measurements still require MRIQC population checks, missing-value handling and visual review before a reviewed inclusion table is used by 9/9.A.

### Standalone public-image motion check

```sh
python 07_reproducibility/public.py motion --root "$PUBLIC_ROOT" --execute
```

The public command writes `PUBLIC_ROOT/qc/8/` and `qc/8a/`; it does not generate ADNI clinical or final-inclusion evidence.

### How it works and host requirements

**Motion/Euler/MRIQC/visual QC.** The same confounds and stats parsers apply on both hosts. The commands above use the public fMRIPrep output.

This writes S8 motion and 8.A duration outputs, not a full research-inclusion decision. FreeSurfer Euler extraction can parse existing logs; any fallback that invokes FreeSurfer binaries requires the corresponding environment/container. Do not treat host Python installation alone as that imaging environment. Review native HTML and preserve MRIQC fitting population, Euler rules, missing-value handling and pending decisions.

## S8A

```sh
python pipeline/s8a_motion_duration_qc/run.py \
  --bids-root "$ADNI_DATA_ROOT/rawdata" \
  --derivatives-root "$ADNI_DATA_ROOT/derivatives/fmriprep" \
  --output-dir "$ADNI_DATA_ROOT/qc/motion-duration-run-001"
```

**What this does:** Reads original BIDS TR/frame counts and fMRIPrep confounds, then computes retained duration and the separate non-steady-state sensitivity.

**Results:** `paper_motion_summary.tsv`, original-frame masks and `paper_motion_provenance.json` in a new external directory. Images are not edited.

### How it works and host requirements

**Motion duration.** Use the same actual BIDS/JSON TR, frame count and confounds on both hosts. Preserve FD >0.5 mm, maximum 30% and minimum 300 seconds, including the separately reported non-steady-state sensitivity. This remains different from S10's FD0.3/240-second XCP-D settings. The tool creates summaries/masks only; it does not edit the images.

## S9

```sh
mkdir -p "$ADNI_DATA_ROOT/qc/step9"
python "$ADNI_PIPELINE/s9_clinical_imaging_merge/build_imaging_input.py" \
  --included "$ADNI_DATA_ROOT/qc/final/included_reviewed_sessions.tsv" \
  --mastersheet "$ADNI_DATA_ROOT/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv" \
  --dxsum "$ADNI_DATA_ROOT/LONI_download/clindata/DXSUM.csv" \
  --max-dx-days 28 \
  --output "$ADNI_DATA_ROOT/qc/step9/included_sessions_merged.csv"
python "$ADNI_PIPELINE/s9_clinical_imaging_merge/adni_swimlane_clinical.py" \
  --imaging "$ADNI_DATA_ROOT/qc/step9/included_sessions_merged.csv" \
  --dxsum "$ADNI_DATA_ROOT/LONI_download/clindata/DXSUM.csv" \
  --max-days 28 \
  --save-merged "$ADNI_DATA_ROOT/qc/step9/merged_sessions.csv" \
  --output "$ADNI_DATA_ROOT/qc/step9/adni_swimlane_clinical.html" \
  --hist-output "$ADNI_DATA_ROOT/qc/step9/adni_gap_histogram.html" \
  --combined-output "$ADNI_DATA_ROOT/qc/step9/adni_combined_figure.html"
```

**What this does:** Builds the upstream imaging input, links visits within the explicit 28-day reporting window and writes the original clinical-alignment figures. Add `--adas`, `--mmse`, `--cdr` and `--moca` with the actual CSV paths to include those scores.

**Results:** Merged CSVs and three HTML figures under `qc/step9/`. This reporting algorithm is separate from 9.A: its date imputation, one-use matching and upstream AD label do not become validated clinical evidence.

### How it works and host requirements

**Upstream clinical merge.** Use the same authorized clinical tables and original merge rules, with Python/R packages and paths prepared on the selected host. There is no ADNI clinical dataset in the public MRI example. Upstream cognitive-score linkage remains distinct from the independent 9.A/9.B validators.

## S9A

```sh
python pipeline/s9a_validate_clinical/run.py \
  --included /ABSOLUTE/PATH/ADNI_DATA/qc/final/included_reviewed_sessions.tsv \
  --scan-links /ABSOLUTE/PATH/ADNI_DATA/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv \
  --dxsum /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DXSUM.csv \
  --ptdemog /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/PTDEMOG.csv \
  --max-dx-days 28 --dx-direction nearest \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9a
```

**What this does:** Links reviewed imaging runs to source clinical rows using actual scan dates and nearest diagnoses within 28 days, retaining ties and demographic evidence.

**Results:** `clinical_validation.tsv`, clinical-pass rows, source-row audits and a hash-bound artifact in the selected output directory.

### How it works and host requirements

**Clinical validation.** The Python CLI is shared. Preserve actual scan dates, nearest/28-day matching, ties, TEAM exclusion and participant-static demographics rules. Keep missing education/APOE and future-visit evidence visible. A host change does not authorize replacing inputs or changing the clinical matching window.

## S9B

```sh
python pipeline/s9b_validate_inclusion/run.py \
  --source-qc /ABSOLUTE/PATH/ADNI_DATA/qc/step3a \
  --clinical /ABSOLUTE/PATH/ADNI_DATA/qc/step9a \
  --confirmed-st-absence /ABSOLUTE/PATH/ADNI_DATA/qc/confirmed-st-absence.csv \
  --conversion-failures /ABSOLUTE/PATH/ADNI_DATA/qc/confirmed-conversion-failures.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9b
```

**What this does:** Combines 3.A, corrected 9.A and reviewed ST/conversion exclusion evidence while preserving pending and held states.

**Results:** `inclusion_audit.tsv`, retained/pending/held/excluded tables and `artifact.json`. Metadata eligibility does not establish final analysis readiness.

### How it works and host requirements

**Metadata inclusion validation.** Run the same Python CLI against freshly verified 3.A and corrected 9.A artifacts and an explicitly reviewed ST/conversion ledger. Preserve eligible/pending/held/excluded distinctions and `ANALYSIS_READY=False`. This stage does not make a copied runtime archive or an unreviewed Linux result scientifically included.

## S10

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config /ABSOLUTE/PATH/xcpd.local.json preflight
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config /ABSOLUTE/PATH/xcpd.local.json dry-run
```

**What this does:** Checks the private ADNI completed-pair configuration and prints its XCP-D plan. These commands do not start the imaging calculation.

**Results:** Preflight/plan evidence for the configured runtime. Run the separately documented [pilot or watch command](../pipeline/s10_xcpd_integrated_qc/README.md#execution) after checking those inputs; they create the real denoised BOLD, ROI/FC, reports and QC outputs.

### Standalone public-image XCP-D calculation

```sh
python 07_reproducibility/public.py xcpd --root "$PUBLIC_ROOT" --license "$FS_LICENSE"
python 07_reproducibility/public.py xcpd --root "$PUBLIC_ROOT" --license "$FS_LICENSE" --execute
```

The public `--execute` command starts real XCP-D processing after public fMRIPrep finishes, then writes `xcpd/output_validation.json`. Its output layout is separate from the strict private completed-pair layout.

### How it works and host requirements

**XCP-D and integrated QC.** The core Docker calculation and validator use the same images/options on both hosts. Run the commands above after a successful public fMRIPrep run.

The second command performs real 36P-LINC processing and technical validation; native participant/executive HTML and `output_validation.json` remain available. Preserve actual censoring, frames, ROI/FC labels/coverage and ReHo/ALFF checks.

The integrated ADNI `pipeline.py` requires its completed-pair layout **and** authentic S6/S7 execution identity/evidence. A flat Linux derivative tree cannot be adopted by inventing receipts. Address the 7.B publisher boundary first. The core `pipeline.py` uses Unix `fcntl` locks, which apply to Mac/Linux but not native Windows.

**External archival is a separate host adapter.** `offload_completed.py` currently verifies the mounted volume using macOS `diskutil info -plist` and its UUID/writable fields. It is not a native Linux archiver as written. A Linux port must check actual mount/device identity and writable state, verify copied bytes/links and postprocessing evidence, publish its archive receipt, then reclaim local data. Do not bypass these gates or fabricate an archive-ready/relocation receipt to continue into S12. Linux `systemd` can manage an implemented service, but does not supply the missing volume/copy validation itself.

## S11

```sh
python pipeline/s11_atlas_bold/sources.py status
python pipeline/s11_atlas_bold/run.py list --space MNI152NLin6Asym
```

**What this does:** Checks which pinned atlas sources are present and lists atlas choices for the declared BOLD space; this inspection does not extract signals.

**Results:** Source status and catalog IDs in the terminal. Use the complete extraction command immediately below for actual ROI means.

### How it works and host requirements

**Atlas BOLD extraction.** Use the same pinned atlas, exact space/grid/labels and reviewed run/frame mapping on both hosts. Install/fetch atlas sources explicitly through the source manager; source downloads can be large. Run `sources.py status` and the extraction CLI from this step's [guide](../pipeline/s11_atlas_bold/README.md#execution). Keep source hashes and any changed host paths in new evidence; never use resampling as a substitute for cross-template registration. Extraction performs no new denoising or final inclusion.

### Extract the selected atlas

```sh
python pipeline/s11_atlas_bold/run.py extract \
  --bold /ABSOLUTE/PATH/ADNI_DATA/derivatives/sub-ADNI999S9999_ses-M000_task-rest_run-1_space-MNI152NLin6Asym_desc-denoised_bold.nii.gz \
  --mask /ABSOLUTE/PATH/ADNI_DATA/derivatives/sub-ADNI999S9999_ses-M000_task-rest_run-1_space-MNI152NLin6Asym_desc-brain_mask.nii.gz \
  --atlas cbig_Schaefer2018_400Parcels_7Networks_order_FSLMNI152_2mm \
  --space MNI152NLin6Asym --input-kind denoised \
  --inclusion /ABSOLUTE/PATH/ADNI_DATA/qc/step9b --image-id 999999999 \
  --resample-labels --min-coverage 0.5 \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/atlas-signals/run-001/Schaefer400
```

Replace the synthetic identity and paths with the reviewed run. Install missing atlas sources using the [Step 11 source commands](../pipeline/s11_atlas_bold/README.md#execution) first. This example produces the time-series/labels/frames/coverage artifact bundle; extraction is distinct from FC estimation.

## S12

```sh
: "${ADNI_ARCHIVE_ROOT:?Set the actual verified archive root mounted on this host}"
python 04_workflow/lab.py export-results --archive-root "$ADNI_ARCHIVE_ROOT" --status "$HOME/adni-metrics-status.json"
```

**What this does:** Reads already calculated values from verified archives and exports one scalar row per pair/run plus links to native HTML reports.

**Results:** Each pair/run receives `results/metrics.csv`, `metrics.tsv`, a units/source dictionary, `export_manifest.json` and `index.html`.

### How it works and host requirements

**Scalar tables and HTML links.** The Python exporter can read an existing verified archive on either host once the archive contract, paths and relative report assets are valid. It reads previously computed values rather than running FreeSurfer/XCP-D again. A Linux archive must first have a genuinely implemented and validated archival transition; manually setting the Mac relocation status string is not validation.

For lightweight repeated scans, the step's explicit `--watch` loop is portable Python. Installing launchd timers on Mac or a reviewed Linux service is a separate deployment task. Preserve one row per pair/run, NA, source/units dictionaries and pending final inclusion.

## Cross-host comparison

Use a new output/work directory per host with the same repository revision, bundled source hashes, container digests, profile, seed and thread counts. Work caches and absolute-path execution receipts are host-bound; this guide does not migrate an active Mac calculation to Linux or repair old Nipype paths.

Start with the [synthetic reference](../07_reproducibility/README.md#a-offline-example-step-by-step), then complete the real public imaging example on each host before comparing its outputs. Use the existing [comparison command and scope](../07_reproducibility/README.md#c-compare-two-peoples-results). Bit-identical compressed files are not promised: assess identity, settings, grid/order/missingness and decoded numerical differences separately. Record CPU architecture, image IDs/digests and effective threads; engineering tolerances are not scientific equivalence criteria. Final registration/segmentation review and cohort inclusion remain research decisions.

## Sources and scope

- [Docker Desktop Mac installation](https://docs.docker.com/desktop/setup/install/mac-install/) and [VM/emulation backends](https://docs.docker.com/desktop/features/vmm/).
- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Docker WSL2 integration](https://docs.docker.com/desktop/features/wsl/) and [Linux-filesystem bind-mount guidance](https://docs.docker.com/desktop/features/wsl/best-practices/).
- [fMRIPrep 25.2.7 usage](https://fmriprep.org/en/25.2.7/usage.html) and [XCP-D 26.2.0 usage](https://xcp-d.readthedocs.io/en/26.2.0/usage.html).
- Repository evidence: `run.py`/`publish_pairs.py` in 7.B, `queue_service.py`, S10 `pipeline.py`/`offload_completed.py`, the integrated protocol stage scripts, and `.github/workflows/tests.yml`.

These links and implementation boundaries were reviewed on 2026-11-06. Source/CI checks establish software contracts and synthetic behavior. This documentation does not establish a new full Linux/Mac imaging baseline or port the missing operational adapters.
