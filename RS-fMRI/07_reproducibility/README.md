# Copy-and-paste RS-fMRI examples

Run each block in the same terminal, in order. The small offline example produces actual QC tables, ROI means and a one-row metrics report using repository code. A second example includes public **real T1w/resting BOLD image files in this repository** for MRIQC → fMRIPrep → XCP-D. Neither example needs ADNI access or any private participant list.

The public example preserves the current **sessionwise / surface-enabled / SyN-SDC / 36P-LINC** analysis options. It is an explicit one-participant demo, independent of the private rolling queue. These commands do not install services or alter an existing ADNI run.

For host preparation and each stage's Mac/Linux limits, read the [platform guide](../06_docs/platform_execution.md). The standalone public example does not install the Mac queue or a Linux archival service.

## 0. Install the example environment

Use Python **3.11+**, Git, and a new source directory. Python 3.11.16 was tested. Run the following from any directory; the data/results live outside the source checkout.

```sh
git clone --branch main https://github.com/IDOJI/adni-data-pipeline.git "$HOME/adni-repro-source"
cd "$HOME/adni-repro-source/RS-fMRI"
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Use Python 3.11 or newer"'
python3 -m venv "$HOME/.venvs/adni-rsfmri-repro"
source "$HOME/.venvs/adni-rsfmri-repro/bin/activate"
python -m pip install -r 07_reproducibility/requirements.lock.txt
python 04_workflow/lab.py doctor
export TOY_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/adni-toy.XXXXXX")/run"
python 07_reproducibility/toy.py init --root "$TOY_ROOT"
```

If using an existing checkout, start with `cd` into its `RS-fMRI/` directory and use the environment commands above. Record `git rev-parse HEAD` and use that **same revision** on the second computer. Core source is versioned by this repository. Optional atlas/SNP submodules still use reviewed pins rather than automatic remote updates.

The dependency file pins the tested example environment, including its Python dependencies. It does not install FSL, ANTs, AFNI or FreeSurfer on the host. The core example needs no Docker; actual imaging execution uses pinned containers. For repository-wide development tests, install `requirements.txt` and pytest separately as described in the [installation guide](../06_docs/installation.md).

## A. Offline example, step by step

Every identity, clinical row, volume and derivative record in this section is **synthetic**. The 4×4×4 phantom is for exact numerical checks, not for anatomical preprocessing. MRIQC/fMRIPrep/XCP-D execution and real archival transfers are **not** simulated into a claim of success: the fixture directory and simulated receipts/reports are explicitly labeled. Source selection, motion/QC, atlas extraction, report generation and scalar parsing use the actual stage implementations.

Each `run` command prints its underlying CLI and writes `outputs/done-<step>.json` only after completion. Each stage is run once. To repeat, create a new `TOY_ROOT` with block 0's last two commands; existing files are preserved.

### 3.A — Source QC, NFQ and identity evidence

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 3a
```

Output: `outputs/3a/image_qc.tsv` and hashed source evidence. The synthetic EPI has source-QC `pass`; that is not a research inclusion decision.

### 5.C — Convert the selected-image handoff into stage inputs

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 5c
```

Output: `outputs/5c/{mriqc_subjects.csv,post_clinica.csv,valid_sessions.tsv,handoff.json}`. Expected: one subject/session. The example maps synthetic `bl` to `ses-M000`; real EPI–T1 pairing remains image/date/hash based.

### 5.D — Check the exact EPI–T1 pair against actual files

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 5d
```

Output: `outputs/5d/` binding tables, summary, hashed receipt and execution plan. Expected: one preprocessing-ready pair, zero analysis-ready pairs. The upstream pairing receipt is a labeled synthetic input fixture, not evidence of real ADNI selection.

### 8 — Extract motion metrics with the original upstream utility

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 8
```

Output: `outputs/8/motion_summary.tsv` and `motion_timeseries.tsv`. Expected: 120 frames, two with FD > 0.5 mm, mean FD ≈ 0.1116666667 mm. The confounds are a known synthetic input, not estimated from phantom images.

### 8.A — Compute retained duration and non-steady-state sensitivity

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 8a
```

Output: `outputs/8a/paper_motion_summary.tsv` and frame masks. At TR=3 s, FD-only retention is **118×3=354 s**, and retention after the two initial non-steady-state frames is **116×3=348 s**. No image frames are modified.

### 9.A — Validate scan-date clinical linkage

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 9a
```

Output: `outputs/9a/clinical_validation.tsv` and source-row audits. The fixture tests the nearest/28-day rule, a future clinical visit, missing education/APOE, and the distinction between Dementia and confirmed AD etiology.

### 9.B — Preserve metadata eligibility and unresolved final inclusion

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 9b
```

Output: `outputs/9b/inclusion_audit.tsv` and retained/held/excluded tables. Expected: metadata `eligible`, `ANALYSIS_READY=False`. This does not infer visual QC or cohort-wide inclusion.

### 10 — Generate an individual integrated QC report

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 10
```

Output: `fixture_archive/999_S_9999/EPI_20200101_MT1_20200101/qc_report.{json,html}`. This runs the real report writer on an explicitly synthetic derivative fixture. **No XCP-D computation occurs in this block.** See section B for actual XCP-D.

### 11 — Extract analytically known ROI BOLD signals

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 11
```

Output: `outputs/11/{timeseries.tsv,labels.tsv,frames.tsv,roi_coverage.tsv,artifact.json}`. Expected: 120×2 values; ROI 1 is `1…120`, ROI 3 is `10…1200`, without additional denoising or standardization. This demonstrates extraction on an artificial matching grid, not successful anatomical registration. This standalone extraction explicitly records inclusion as `not_checked`.

### 12 — Export one row of volumes, thickness, ReHo/ALFF and report links

```sh
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step 12
export TOY_RESULTS="$TOY_ROOT/fixture_archive/999_S_9999/EPI_20200101_MT1_20200101/results"
ls "$TOY_RESULTS"
```

Output: `metrics.csv`, `metrics.tsv`, `metrics_dictionary.csv`, `export_manifest.json`, and `index.html`. Open the HTML with your preferred browser. Known fixture values: left/right hippocampus **123.4/145.6 mm³**, left superior-frontal thickness **2.1 mm**, ReHo ROI_A **0.2**, ROI_B **NA**. These values are **inputs to test the exporter**, not quantities estimated by FreeSurfer or XCP-D in this example. The native report link target also says “SYNTHETIC FIXTURE ONLY.”

### Check against the committed reference

```sh
python 07_reproducibility/toy.py verify --root "$TOY_ROOT"
cat "$TOY_ROOT/verification.json"
```

Expected: `PASS`. [expected.json](expected.json) is the reviewed, committed semantic baseline. The verifier also checks the complete analytical ROI matrix, original S8 FD and input hashes. Timestamps, absolute paths and gzip metadata are not reference measurements. Passing establishes these integration checks, not an imaging accuracy claim.

### Repeat all steps without model calls

Start with a **new** root. This executes the same ten stages in a plain Python loop.

```sh
export TOY_ROOT_2="$(mktemp -d "${TMPDIR:-/tmp}/adni-toy-repeat.XXXXXX")/run"
python 07_reproducibility/toy.py init --root "$TOY_ROOT_2"
python 07_reproducibility/toy.py run --root "$TOY_ROOT_2" --step all
python 07_reproducibility/toy.py verify --root "$TOY_ROOT_2"
python 07_reproducibility/compare.py "$TOY_ROOT" "$TOY_ROOT_2" \
  --mode synthetic --report "$TOY_ROOT_2/comparison.json"
```

Expected: `PASS` for the nine selected result tables and the reference measurements. The tool fails if a value, identity/order, missing-value pattern or required product differs.

## B. Actual MRIQC → fMRIPrep → XCP-D on public brain images

### B1. Stage and verify the included public images

[OpenNeuro ds000030 1.0.0](https://doi.org/10.18112/openneuro.ds000030.v1.0.0), CC0, contains the public UCLA CNP data described by [Poldrack et al.](https://www.nature.com/articles/sdata2016110). The selected public subject is `sub-10159`. [public_dataset.json](public_dataset.json) pins the source Git commit, exact bytes and SHA-256 of **every** downloaded file. The five source files, including both actual NIfTI payloads, are included as ordinary Git files under [public_data/ds000030-1.0.0](public_data/ds000030-1.0.0/README.md). A normal clone includes the images; no Git LFS or separate OpenNeuro download is required. Source attribution and the separate CC0 data license are included beside the images. NIfTI sizes were also checked against the tag's Git-annex MD5 records.

```sh
export PUBLIC_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/adni-public.XXXXXX")/run"
python 07_reproducibility/public.py fetch --root "$PUBLIC_ROOT"
```

Included source payload: **35,696,832 bytes** total; T1w is 176×256×256 and BOLD is 64×64×34×152, TR=2 s. The public BOLD header declares slice axis k; its JSON has 34 SliceTiming entries. The default `fetch` command verifies and copies the included files into the new external working directory without network access. Missing or changed bundled files cause an error, with no automatic download fallback. It checks the slice-axis/count and TR correspondence; it does not independently establish the scanner acquisition order without source DICOM.

The NIfTI bytes are preserved. Subject/session filenames become `sub-toy001/ses-M000` so the **sessionwise** profile has an explicit session. `ses-M000` is only an execution wrapper, **not** ADNI VISCODE, a date, or a clinical pairing claim. Inherited BOLD JSON metadata are merged explicitly. Verified source copies, mapping and hashes remain under the external `download/` and `input_manifest.json`; the committed sample is unchanged. For an independent upstream re-download, use `--source remote` with a new root. That explicit option verifies the same pinned hashes and stops on disagreement.

### B2. Prepare Docker and the FreeSurfer license

Docker Engine/Desktop must already be installed and running. Obtain your own [FreeSurfer license](https://surfer.nmr.mgh.harvard.edu/registration.html), save it locally, and set `FS_LICENSE` to its actual location. The example below assumes you saved it as `$HOME/freesurfer/license.txt`.

```sh
export FS_LICENSE="$HOME/freesurfer/license.txt"
test -f "$FS_LICENSE"
docker info --format '{{.OSType}}'
python 07_reproducibility/public.py pull --root "$PUBLIC_ROOT" --execute
```

This block downloads container images: they and later TemplateFlow/atlas downloads can total **several GB**. MRIQC, fMRIPrep and XCP-D use immutable digests and `linux/amd64`. Apple Silicon therefore uses emulation; an AMD64 Linux machine avoids that architecture mismatch. No Docker Desktop settings are changed. MRIQC's historical tag was 24.0.2; inspect the actual image version/GeneratedBy record rather than treating that tag as proof of a stable release. fMRIPrep is 25.2.7 and XCP-D is 26.2.0.

### B3. MRIQC, stage 6

```sh
python 07_reproducibility/public.py mriqc --root "$PUBLIC_ROOT" --execute
```

Output: `derivatives/mriqc/` native IQMs/HTML, `logs/mriqc.log`, execution evidence and image digest. A one-participant example cannot establish representative-cohort MRIQC outlier thresholds.

### B4. fMRIPrep, stage 7 / sessionwise profile

```sh
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" \
  --license "$FS_LICENSE" --ants-verbose --execute
```

Output: `derivatives/fmriprep/` volumes, surfaces/CIFTI, confounds, FreeSurfer stats and participant HTML. Work files are under `work/fmriprep/`. Stage 7.C's existing ANTs verbose wrapper records iterations under `logs/fmriprep/ants_iterations/`; the effective Docker argv and wrapper hash are recorded too.

This is a real anatomical preprocessing task and can take many hours. It is **not** part of the quick offline check, and a zero exit code does not substitute for registration/segmentation review. The launcher refuses a second recorded execution in the same root; create a new root for an independent rerun. It leaves failed outputs/cache intact for inspection.

### B5. S8 motion and 8.A duration from actual confounds

```sh
python 07_reproducibility/public.py motion --root "$PUBLIC_ROOT" --execute
```

Output: `qc/8/` and `qc/8a/`. S8's FD criterion is **0.5 mm**, while the independent paper duration check is **300 s**. XCP-D below censors at **0.3 mm** with a **240 s** minimum; these are different decisions. Inspect the actual retained duration rather than assuming the public sample passes every criterion.

### B6. XCP-D 36P/LINC, stage 10

```sh
python 07_reproducibility/public.py xcpd --root "$PUBLIC_ROOT" \
  --license "$FS_LICENSE" --execute
```

Output: `xcpd/derivatives/` denoised BOLD, ReHo/ALFF, 4S256 ROI/FC/coverage, participant HTML and executive summary; `logs/xcpd.log` and `xcpd/output_validation.json`. The launcher uses the **same S10 argument builder and output validator** as the ADNI workflow. The filter selects MNI152NLin6Asym/res-2, rest, and the exact subject/session. It checks actual options, frame/censor counts, geometry, finite values, ROI identities/order, coverage, FC structure and native reports. A validation failure exits unsuccessfully and keeps its diagnostic JSON.

This public demo does **not** fabricate ADNI source QC, NFQ, clinical records, final inclusion, or external-disk relocation. It runs the imaging core explicitly; ADNI-specific metadata gates are exercised with section A's labeled synthetic evidence. It never invokes the private feeder, changes active subjects, or archives/deletes research data.

### B7. Inspect the exact commands and settings

Omit `--execute` to print a command without running a container. The helper may create external work/config directories, but launches no imaging job.

```sh
python 07_reproducibility/public.py mriqc --root "$PUBLIC_ROOT"
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" --license "$FS_LICENSE"
python 07_reproducibility/public.py xcpd --root "$PUBLIC_ROOT" --license "$FS_LICENSE"
cat "$PUBLIC_ROOT/comparison_identity.json"
```

| Component | Fixed analysis/runtime settings |
|---|---|
| fMRIPrep | sessionwise; forced SyN-SDC; ignore fieldmaps; `--use-syn-sdc error`; MNI6 res-2, MNI2009c, fsnative, fsaverage10k, func; CIFTI91k; FreeSurfer enabled; seed357; 4 processes / OMP2 / 6000 MB; Docker8g |
| XCP-D | LINC; volumetric NIfTI; 36P including GSR; no run combination; censored output; FD0.3; min240s; 4S256; dummy0; smoothing6mm; despike; no motion filtering; head50mm; bandpass0.01–0.08Hz/order2; mincoverage0.5; LINC/ABCC QC; seed357; 2 processes / OMP1 / 12000MB; Docker16g |
| Logging | Existing 7.C wrapper adds ANTs verbosity, mounts and PATH; it does not change registration iteration schedules |

`environment.json`, per-stage execution records and `comparison_identity.json` record package/code hashes, source hashes, upstream pin, image digests, seeds, threads and settings. License contents are never recorded. This profile reproduces the current reviewed options; it does not silently switch to an OMP1/fixed-skull-strip variant to claim deterministic output. See the versioned [fMRIPrep usage](https://fmriprep.org/en/25.2.7/usage.html) and [changes](https://fmriprep.org/en/25.2.7/changes.html).

## C. Compare two people's results

First use the **same source revision**, dataset manifest, images, processing profile, seeds and threads. Each person runs section B in a separate root. Copy the other person's public-demo root to a local folder; retain its manifests and derivative layout. The following uses `PUBLIC_ROOT_2` for that second local root; set it to the actual copied directory.

```sh
: "${PUBLIC_ROOT:?Set the first completed public-demo root}"
: "${PUBLIC_ROOT_2:?Set the second completed or copied public-demo root}"
python 07_reproducibility/compare.py "$PUBLIC_ROOT" "$PUBLIC_ROOT_2" \
  --mode public --atol 1e-6 --rtol 1e-5 \
  --report "$PUBLIC_ROOT/comparison.json"
```

The tool reports **byte-identical**, **exact decoded values**, **within tolerance**, or **fail**, per product. It requires matching input/code/profile identity, verified successful stage receipts and XCP-D validation, matching realized application arguments and relative product lists, image shape/grid/units/TR, table columns and row order, and missing/nonfinite-value locations. Binary segmentation/masks and integer-valued table columns require exact values. It never aligns, reorders time points, fills missing ROIs or recalibrates a threshold to force a pass. Defaults target numerical NIfTI/TSV derivatives; volatile logs, HTML, work files, FreeSurfer binary surfaces and CIFTI are excluded. S12 scalar exports are checked by the offline reference example; whole-surface/CIFTI equivalence needs additional domain-specific checks.

`atol=1e-6, rtol=1e-5` are **engineering comparison defaults**, not scientifically validated equivalence margins. The condition is `abs(left-right) <= atol + rtol*abs(right)`. Use `--atol 0 --rtol 0` for exact decoded values. CPU architecture, threads, upstream defaults, floating-point libraries and stochastic skull stripping can affect actual imaging results; pinned seeds/images alone do not promise byte-identical output on every computer. A mismatch is evidence to inspect, not automatically proof that one person's run is invalid. Input/config mismatch always fails, even when numbers happen to agree.

**Validation status:** the public 35.7MB inputs are bundled as real Git files and were downloaded and hash/header verified; default staging was tested without network access; command construction and synthetic integration/comparison were tested. A fresh full MRIQC/fMRIPrep/XCP-D run of this public subject and a cross-machine imaging baseline have **not** been established by this kit. The committed baseline is section A's analytical/synthetic output only. Share actual public-run outputs/evidence after completing section B to establish a reviewed imaging reference.

## D. Which parts still require real ADNI inputs?

| Stage/profile | Public example coverage | Real ADNI requirements |
|---|---|---|
| 1–2: account/download | Public images bypass ADNI access | Personal ADNI approval, collection/download and usage terms; not an automatic terminal step |
| 3/4/4.B: DICOM organization/Clinica/slice metadata | Public data already are NIfTI; original bytes preserved | Original DICOM, ADNI Study Files and conversion provenance; do not infer acquisition order from phantom data |
| 5.A–B | Synthetic handoff input supplied by `init` | Upstream mastersheet and post-Clinica selection; the demo does not run these R selection scripts |
| 3.A/5.C/5.D | Actual code, synthetic source/selection evidence | Original selected image IDs, QC, pairing proposals and verified file hashes |
| 6/7/7.B scientific profile/7.C | Actual public images and pinned Docker execution | Reviewed ADNI BIDS pairs and live deployment; the toy starts no queue service |
| 7.A alternative volume/aCompCor profile | Separate profile, **not** run by section B | Follow its [own guide](../02_custom/s7a_volume_workflow/README.md); it omits FreeSurfer and uses different space/regressors/FD. Never mix it with the main reference |
| 8/8.A | Synthetic reference and actual-public motion commands | Full MRIQC/Euler/visual/cohort inclusion checks remain separate |
| 9/9.A/9.B | Actual validation code, synthetic clinical rows | Licensed clinical tables; upstream cognitive-score merge is not reproduced by the public subject |
| 10 | Real public XCP-D core; synthetic QC-report example | Source/cohort gates, visual review, explicit final inclusion and verified archival |
| 11 | Exact ROI means from a synthetic matching atlas/grid | Matching-space real atlas and reviewed denoised BOLD; see [atlas guide](../02_custom/s11_atlas_bold/README.md) |
| 12 | Actual exporter on labeled synthetic archive/FreeSurfer/XCP-D records | Actual verified archives for real scalar values and native HTML |

For **existing verified ADNI archives**, stage 12 remains directly executable using your external archive root; no new imaging computation is needed. Set `ADNI_ARCHIVE_ROOT` to the real archive directory before running:

```sh
: "${ADNI_ARCHIVE_ROOT:?Set the directory containing subject/EPI_YYYYMMDD_MT1_YYYYMMDD archives}"
python 02_custom/s12_metrics_summary/run.py \
  --archive-root "$ADNI_ARCHIVE_ROOT" \
  --status "$HOME/adni-s12-export-status.json"
```

For private upstream preparation and cohort operations, use the [complete execution table](../README.md), [lab command planner](../04_workflow/lab.py), [S10 contract](../02_custom/s10_xcpd_integrated_qc/README.md) and reviewed external configurations. Their data-dependent gates and manual research decisions are not replaced by a public toy or represented as completed execution.
