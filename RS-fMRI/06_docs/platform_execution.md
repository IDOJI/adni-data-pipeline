# macOS and Linux execution by stage

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

A Linux notebook does not provide Slurm simply because it runs Linux. Use the Docker route for a local workstation, or the pinned upstream Slurm/Apptainer route only on an actual configured cluster. No Linux service unit, mounted-volume adapter or live five-subject queue is installed by this documentation.

## Common setup

From a new source checkout, initialize only the core upstream submodule, create a wrapper environment and check the pin. Keep private inputs/work/results outside the repository; the included CC0 sample is the explicit public-data exception.

```sh
git clone --branch main https://github.com/IDOJI/adni-data-pipeline.git "$HOME/adni-platform-source"
cd "$HOME/adni-platform-source/RS-fMRI"
git submodule update --init 01_upstream/ADNI_fMRI_protocol
python3 -m venv "$HOME/.venvs/adni-platform"
source "$HOME/.venvs/adni-platform/bin/activate"
python -m pip install -r 07_reproducibility/requirements.lock.txt
python 04_workflow/lab.py doctor
export PUBLIC_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/adni-public.XXXXXX")/run"
python 07_reproducibility/public.py fetch --root "$PUBLIC_ROOT"
```

`fetch` copies and hash-checks the real MRI files included in Git without accessing OpenNeuro. The pinned core requirements above support the example tools. For the full development suite, install `requirements.txt` and run the repository tests as documented in [installation](installation.md). Use the [complete example](../07_reproducibility/README.md) for the separate synthetic reference, expected results and all ten synthetic stages.

The following stages apply to both hosts unless a host-specific boundary is stated. Real ADNI commands still require authorized external Study Files, selected inputs and private configuration. The public subject does not supply ADNI clinical/source evidence.

## S1

**Account and access.** The same ADNI access/usage requirements apply on either OS. Complete the upstream access steps personally; no local container or synthetic test supplies ADNI authorization. See the pinned upstream link in the [execution table](../README.md#-complete-execution-order).

## S2

**Download.** Preserve the same selected image IDs, collection CSVs and raw metadata on both hosts. Store licensed ADNI inputs under the external data root. The included OpenNeuro example starts from NIfTI and does not reproduce ADNI portal downloads or become ADNI source-QC evidence.

## S3

**Organization and download inventory.** Run the pinned Bash inventory utility through a reviewed external configuration on either POSIX host. Its paths must refer to that host's actual DICOM tree. `lab.py plan` prints the upstream stage-3 command; it does not execute it. Keep the original archive and compare the same member/image identities before reusing extracted inputs.

For the private upstream route, supply an existing rendered configuration:

```sh
: "${UPSTREAM_CONFIG:?Set the absolute external upstream YAML path}"
python 04_workflow/lab.py plan --config "$UPSTREAM_CONFIG"
```

This prints plans for the supported entry points, including dry-run Slurm commands. Review working directories and cluster assumptions before running a printed command. The planner is not a general Mac/Linux scheduler.

## S3A

**Source QC/NFQ.** Run the same Python CLI on macOS and Linux with host-correct Study Files paths. Preserve source hashes, quality rules, pending status and identity/deletion conflicts. The [3.A execution example](../02_custom/s3a_source_qc/README.md#execution) and offline `toy.py --step 3a` use the same implementation. No Docker, Slurm or service manager is required by this step.

## S4

**Clinica conversion.** The pinned upstream per-subject generator/submission route targets a configured Slurm environment. macOS needs an explicitly prepared Clinica/dcm2niix environment or a reviewed Linux conversion host; running a Slurm template in Terminal does not create a Mac launcher. Native Linux needs the converter dependencies too; a notebook still has no scheduler by default. Review the external conversion job's paths/environment/notification settings before submission.

Keep the converter version and conversion records when comparing hosts. Already converted NIfTI inputs need verified identity/metadata and the intended EPI–T1 pair; do not reconvert solely because the host OS changed. The public example preserves its source NIfTI bytes and adds only its documented execution layout.

## S4B

**Philips SliceTiming.** The Python dry-run path is the same on both hosts. `lab.py plan` includes the configured `insert_philips_slicetiming.py --dry-run` command. Inspect actual image identity, slice-axis correspondence and metadata evidence before an authorized write. Changing host OS never supplies missing slice timing or licenses a guessed acquisition order.

## S5AB

**Post-Clinica 5.A/5.B.** Use the same upstream heuristics/mastersheet rules. Prepare the required Python/R environments on the selected host and use external output directories. In particular, 5.A writes a relative `data/` directory: the planner places its working directory under external `qc/step5a`, not in the source tree. Review hardcoded/script-specific settings as well as the rendered YAML. This guide does not replace the original R selection scripts with a synthetic handoff.

## S5C

**Handoff validation.** Use the same Python CLI, including the 3.A source artifact when applying that gate. Retain the TSV/CSV delimiter contracts and the exact `mriqc_sessions.csv` handoff. Upstream MRIQC remains subject-scoped; a Linux host does not fix that session-selection boundary. Rebuild path-bearing provenance for a new host rather than editing old hash-bound receipts.

## S5D

**Exact EPI–T1 binding.** Set the external BIDS roots, registry, independent hash evidence and output directory to the new host. Run `binding.py --config ...`, then use the guarded entry point for an eligible exact pair. Preserve actual image dates/IDs, proposed pairing and held rows. `guarded_runner.py` delegates computation to 7.B; it does not make the Mac controller or pair publisher Linux-compatible.

## S6

**MRIQC.** On a local Mac use Docker Desktop; on native Linux x86-64 use Docker Engine. The public example uses the same digest, selected BIDS filter, modality/session scope and application arguments on both hosts. After common setup, an existing valid FreeSurfer license is needed for later stages, not MRIQC itself.

The following pulls the pinned containers and may also lead to multi-GB template/atlas downloads during later execution:

```sh
python 07_reproducibility/public.py pull --root "$PUBLIC_ROOT" --execute
python 07_reproducibility/public.py mriqc --root "$PUBLIC_ROOT"
python 07_reproducibility/public.py mriqc --root "$PUBLIC_ROOT" --execute
```

The middle command prints the actual Docker argv; the final command runs it. Inspect native IQMs and HTML under `derivatives/mriqc/`. A single public subject cannot calibrate cohort outlier thresholds. For ADNI use reviewed 5.C/5.D inputs and 7.B's configured single-case launcher, or the upstream cluster route on actual Slurm/Apptainer infrastructure.

## S7

**fMRIPrep.** The same local-container route applies on both hosts. Preserve the profile's version/digest, sessionwise reference, susceptibility correction, standard/surface/CIFTI outputs, seed and process/thread settings. The public example's imaging options are in `public.py`; changing OS does not justify switching to the separate 7.A profile or changing analysis flags.

```sh
: "${FS_LICENSE:?Set the absolute path to your valid FreeSurfer license.txt}"
test -f "$FS_LICENSE"
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" --license "$FS_LICENSE"
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" --license "$FS_LICENSE" --ants-verbose --execute
```

Outputs are under `derivatives/fmriprep/`, work under `work/fmriprep/`, and native report/FreeSurfer/confounds evidence must be checked after completion. The command starts a real long calculation. Omit `--execute` to inspect the base command. Never infer successful completion from a live container alone.

The upstream Step-7 launcher is a separate Slurm/Apptainer route, and 7.B is the explicit-pair Docker adapter. Neither upstream Slurm nor the Mac queue becomes a local Linux scheduler automatically.

## S7A

**Alternative volume/aCompCor profile.** Its single-case Docker command/audit tools use external paths on both hosts. Preserve this profile's own MNI2009c, aCompCor/no-GSR, FD0.5 and surface-disabled settings and separate caches. It is not the S7/S10 surface-enabled 36P-LINC reference. Follow its [execution contract](../02_custom/s7a_volume_workflow/README.md#execution); no new Linux full-imaging validation is claimed.

## S7B

**Sessionwise launcher, publication and queue.** Distinguish three pieces:

1. `run.py` prepares/selects one configured case and builds Docker argv using host bind sources. Its single-case dry-run and reviewed run path are the Linux-compatible starting point, with real Linux execution still requiring validation.
2. `publish_pairs.py` invokes macOS `/bin/cp -cR`. GNU/Linux `cp` does not provide that same clone option. A Linux publisher must preserve run/pair identity, unchanged source evidence, relative report assets and copy validation before S10 can consume the strict ADNI pair layout.
3. `04_workflow/queue_service.py` starts `/usr/bin/caffeinate`. The private Mac live deployment uses host startup/watchdog integration. Linux needs a port and reviewed service configuration; replacing `launchctl` with a unit name in a config is not enough.

The existing single-case inspection command is shared once its private config uses valid host paths:

```sh
: "${STEP7B_CONFIG:?Set the external verified 7.B YAML path}"
: "${ADNI_SUBJECT:?Set the bare subject label recorded in that configuration}"
python 02_custom/s7b_sessionwise_preprocessing/run.py --config "$STEP7B_CONFIG" dry-run --stage fmriprep --subject "$ADNI_SUBJECT"
```

This may create external filter/work directories and requires the pinned image to be installed, but launches no imaging job. This documentation does not implement the missing Linux publisher/controller. Public `public.py` imaging examples use their own standalone output layout and do not assert that the entire private ADNI chain is portable.

## S7C

**ANTs logging.** The wrapper lives inside the unchanged Linux container, so the same `--ants-verbose` public command applies to both hosts. Keep the original image PATH, computational argv and logging provenance. Use the existing wrapper rather than changing registration iteration schedules. Mac controller activation/keep-awake logic is separate from this transport and needs a Linux service implementation if used there.

## S8

**Motion/Euler/MRIQC/visual QC.** The same confounds and stats parsers apply on both hosts. For the public fMRIPrep output:

```sh
python 07_reproducibility/public.py motion --root "$PUBLIC_ROOT" --execute
```

This writes S8 motion and 8.A duration outputs, not a full research-inclusion decision. FreeSurfer Euler extraction can parse existing logs; any fallback that invokes FreeSurfer binaries requires the corresponding environment/container. Do not treat host Python installation alone as that imaging environment. Review native HTML and preserve MRIQC fitting population, Euler rules, missing-value handling and pending decisions.

## S8A

**Motion duration.** Use the same actual BIDS/JSON TR, frame count and confounds on both hosts. Preserve FD >0.5 mm, maximum 30% and minimum 300 seconds, including the separately reported non-steady-state sensitivity. This remains different from S10's FD0.3/240-second XCP-D settings. The tool creates summaries/masks only; it does not edit the images.

## S9

**Upstream clinical merge.** Use the same authorized clinical tables and original merge rules, with Python/R packages and paths prepared on the selected host. There is no ADNI clinical dataset in the public MRI example. Upstream cognitive-score linkage remains distinct from the independent 9.A/9.B validators.

## S9A

**Clinical validation.** The Python CLI is shared. Preserve actual scan dates, nearest/28-day matching, ties, TEAM exclusion and participant-static demographics rules. Keep missing education/APOE and future-visit evidence visible. A host change does not authorize replacing inputs or changing the clinical matching window.

## S9B

**Metadata inclusion validation.** Run the same Python CLI against freshly verified 3.A and corrected 9.A artifacts and an explicitly reviewed ST/conversion ledger. Preserve eligible/pending/held/excluded distinctions and `ANALYSIS_READY=False`. This stage does not make a copied runtime archive or an unreviewed Linux result scientifically included.

## S10

**XCP-D and integrated QC.** The core Docker calculation and validator use the same images/options on both hosts. After a successful public fMRIPrep run:

```sh
python 07_reproducibility/public.py xcpd --root "$PUBLIC_ROOT" --license "$FS_LICENSE"
python 07_reproducibility/public.py xcpd --root "$PUBLIC_ROOT" --license "$FS_LICENSE" --execute
```

The second command performs real 36P-LINC processing and technical validation; native participant/executive HTML and `output_validation.json` remain available. Preserve actual censoring, frames, ROI/FC labels/coverage and ReHo/ALFF checks.

The integrated ADNI `pipeline.py` requires its completed-pair layout **and** authentic S6/S7 execution identity/evidence. A flat Linux derivative tree cannot be adopted by inventing receipts. Address the 7.B publisher boundary first. The core `pipeline.py` uses Unix `fcntl` locks, which apply to Mac/Linux but not native Windows.

**External archival is a separate host adapter.** `offload_completed.py` currently verifies the mounted volume using macOS `diskutil info -plist` and its UUID/writable fields. It is not a native Linux archiver as written. A Linux port must check actual mount/device identity and writable state, verify copied bytes/links and postprocessing evidence, publish its archive receipt, then reclaim local data. Do not bypass these gates or fabricate an archive-ready/relocation receipt to continue into S12. Linux `systemd` can manage an implemented service, but does not supply the missing volume/copy validation itself.

## S11

**Atlas BOLD extraction.** Use the same pinned atlas, exact space/grid/labels and reviewed run/frame mapping on both hosts. Install/fetch atlas sources explicitly through the source manager; source downloads can be large. Run `sources.py status` and the extraction CLI from this step's [guide](../02_custom/s11_atlas_bold/README.md#execution). Keep source hashes and any changed host paths in new evidence; never use resampling as a substitute for cross-template registration. Extraction performs no new denoising or final inclusion.

## S12

**Scalar tables and HTML links.** The Python exporter can read an existing verified archive on either host once the archive contract, paths and relative report assets are valid. It reads previously computed values rather than running FreeSurfer/XCP-D again. A Linux archive must first have a genuinely implemented and validated archival transition; manually setting the Mac relocation status string is not validation.

```sh
: "${ADNI_ARCHIVE_ROOT:?Set the actual verified archive root mounted on this host}"
python 04_workflow/lab.py export-results --archive-root "$ADNI_ARCHIVE_ROOT" --status "$HOME/adni-metrics-status.json"
```

For lightweight repeated scans, the step's explicit `--watch` loop is portable Python. Installing launchd timers on Mac or a reviewed Linux service is a separate deployment task. Preserve one row per pair/run, NA, source/units dictionaries and pending final inclusion.

## Cross-host comparison

Use a new output/work directory per host with the same repository revision, bundled source hashes, container digests, profile, seed and thread counts. Work caches and absolute-path execution receipts are host-bound; this guide does not migrate an active Mac calculation to Linux or repair old Nipype paths.

Start with the [synthetic reference](../07_reproducibility/README.md#a-offline-example-step-by-step), then complete the real public imaging example on each host before comparing its outputs. Use the existing [comparison command and scope](../07_reproducibility/README.md#c-compare-two-peoples-results). Bit-identical compressed files are not promised: assess identity, settings, grid/order/missingness and decoded numerical differences separately. Record CPU architecture, image IDs/digests and effective threads; engineering tolerances are not scientific equivalence criteria. Final registration/segmentation review and cohort inclusion remain research decisions.

## Sources and scope

- [Docker Desktop Mac installation](https://docs.docker.com/desktop/setup/install/mac-install/) and [VM/emulation backends](https://docs.docker.com/desktop/features/vmm/).
- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Docker WSL2 integration](https://docs.docker.com/desktop/features/wsl/) and [Linux-filesystem bind-mount guidance](https://docs.docker.com/desktop/features/wsl/best-practices/).
- [fMRIPrep 25.2.7 usage](https://fmriprep.org/en/25.2.7/usage.html) and [XCP-D 26.2.0 usage](https://xcp-d.readthedocs.io/en/26.2.0/usage.html).
- Repository evidence: `run.py`/`publish_pairs.py` in 7.B, `queue_service.py`, S10 `pipeline.py`/`offload_completed.py`, the pinned upstream stage scripts, and `.github/workflows/tests.yml`.

These links and implementation boundaries were reviewed on 2026-11-06. Source/CI checks establish software contracts and synthetic behavior. This documentation does not establish a new full Linux/Mac imaging baseline or port the missing operational adapters.
