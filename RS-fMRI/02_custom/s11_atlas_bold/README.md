# Step 11 — Atlas-based BOLD signal extraction

## Purpose

Select a pinned brain atlas and extract one mean BOLD signal per discrete ROI. Preserve label identity, input-frame indices and source evidence. Audit source labels, resampling losses and brain-mask coverage rather than silently removing empty ROIs. This step does not perform registration, denoising or connectivity estimation.

## Stored atlas library

| Source submodule | Stored content and role |
|---|---|
| [Neuroparc](https://github.com/neurodata/neuroparc) | 141 human label images, including resolution variants of AAL, AICHA, Glasser, Harvard–Oxford, Yeo and other families |
| [CBIG](https://github.com/ThomasYeoLab/CBIG) | 60 original Schaefer volume variants: 100–1000 parcels, 7/17/Kong2022 ordering and 1/2-mm grids; sparse checkout avoids the full multi-GB repository |
| [TemplateFlow archive](https://github.com/templateflow/templateflow) | Pinned archive and two nested template datasets; 51 registered 2-mm atlas variants in MNI152NLin6Asym/MNI152NLin2009cAsym |
| [Nilearn](https://github.com/nilearn/nilearn) | Pinned source reference for [atlas fetchers](https://nilearn.github.io/stable/modules/datasets.html) and maskers; cloning the library alone does not download atlases |

The catalog has **252 file variants, not 252 independent atlas families**. Source commits are in `sources.lock.json`; `catalog.json` records file/label-metadata SHA-256, source identity, expected labels and observed counts. Binary atlas files remain in their upstream submodules or the ignored local `02_atlases/` cache; they are not copied into the parent Git history.

TemplateFlow uses Git-annex pointers. Explicit fetching validates pinned annex sizes/digests and additional SHA-256 values before storing actual NIfTI payloads. A pointer is never accepted as a loaded atlas. The local fetch includes three reference segmentations that are not exposed as atlas choices.

Neuroparc declares the shorter space `MNI152NLin6`. Preserve that identifier: **do not automatically equate it with MNI152NLin6Asym or MNI152NLin2009cAsym**. Choose a verified matching-space CBIG/TemplateFlow entry for those BOLD derivatives. Matching shapes or affines alone do not establish template registration. Source README count discrepancies are recorded and cause extraction QC failure; the library does not repair or relabel source atlases. Neuroparc expected IDs use the observed highest-resolution source variant; TemplateFlow uses a verified LUT/declared parcel count where available and otherwise observed source IDs. This detects additional resampling loss but does not prove preservation relative to every original publication. The expectation basis is recorded per catalog entry.

## Input

- A 4-D volumetric BOLD image and a finite binary brain mask on the same grid, with valid millimetre affines.
- `--atlas`: exact catalog ID. Use `list` to discover choices.
- `--space`: explicit coordinate space, matching both the registered atlas and the BOLD filename space when present. Other standard spaces require a separately registered matching atlas or a validated external transform.
- `--input-kind preprocessed|denoised`: declare the existing processing state. Prefer the intended S10 denoised output for the connected workflow; this tool does not verify that denoising was scientifically adequate.
- Optional `--bold-json`: TR in seconds and spatial metadata. Known NIfTI temporal units and sidecar TR must agree.
- Optional `--sample-mask`: a complete input-frame ledger, either `frame_index,keep` or 8.A's `original_frame_index_zero_based,retain_FD_and_nonsteady`. It must match the current BOLD frame count and order. Do not apply a pre-dummy-removal mask to a shortened derivative.
- For the ADNI workflow, supply `--inclusion` with the 9.B artifact and `--image-id`. The image must be uniquely eligible/pending, EPI, and match actual BIDS run entities. Excluded/held images and metadata-only audit session labels cannot substitute for an actual run mapping.

External catalogs may explicitly register 3-D label atlases with relative paths under their own catalog directory, SHA-256, exact space, expected positive IDs, background zero, `source=external` and a provenance citation. Probability maps, coordinate spheres, surfaces and CIFTI are not supported by this extractor.

## Processing

1. Verify the selected source commit, atlas/label metadata hashes and optional 9.B evidence.
2. Require exact space identity. Grid changes require `--resample-labels` and use nearest-neighbor labels only; no nonlinear or cross-template transformation is inferred.
3. Audit expected/source/BOLD-grid labels, coverage inside the provided brain mask, and approximate masked physical-volume coverage relative to the selected source image. Partial field-of-view cropping cannot be hidden by a full mask of the remaining fragment. Default minimum mask coverage is 0.5 and one voxel; these are explicit configurable QC settings, not universally validated study criteria.
4. Stream one BOLD frame at a time and preserve a fixed ROI voxel set. Any nonfinite included voxel invalidates that ROI's frame rather than silently changing its averaging support.
5. Preserve every expected ROI column. Empty ROIs contain NaN, constant/nonfinite signals fail QC, and losses remain in the audit. Optional `--standardize zscore` is explicit; the default preserves signal units without extra temporal cleaning.

## Output

| File | Meaning |
|---|---|
| `timeseries.tsv` | Retained input frames × expected ROI columns (`roi_<label ID>`), in fixed label order |
| `labels.tsv` | Column, source label ID and source name; uncertain LUT mappings retain numeric names |
| `frames.tsv` | Output row → zero-based input frame and input-relative seconds |
| `roi_coverage.tsv` | Source/grid/masked voxel counts, physical volumes, mask/source-volume coverage and per-ROI failure reasons |
| `atlas_on_bold_grid.nii.gz` | Atlas sampled to the BOLD grid for spatial inspection |
| `artifact.json` | Input/output/code hashes, source pins, TR, processing declaration, QC settings and outcome |

Exit code **2** means artifacts were written but ROI/source QC failed. Exit code **1** means an input/contract error. Code 0 establishes extraction checks only; every artifact remains `analysis_ready=false`, and physical registration/visual QC is not established. Without 9.B evidence, inclusion is explicitly `not_checked`.

## Execution

Run from `RS-fMRI/`. Source installation and payload fetching are explicit network operations; extraction itself never downloads data.

```sh
python 02_custom/s11_atlas_bold/sources.py install
python 02_custom/s11_atlas_bold/sources.py fetch-templateflow
python 02_custom/s11_atlas_bold/sources.py status
python 02_custom/s11_atlas_bold/run.py list --space MNI152NLin6Asym
```

Only selected sources can be installed with repeatable `--source`, for example `--source CBIG`. Do not recursively initialize every TemplateFlow dataset. A full `git clone --recurse-submodules` can fetch unrelated datasets and large histories; use the selective setup above.

```sh
python 02_custom/s11_atlas_bold/run.py extract \
  --bold /ABSOLUTE/PATH/ADNI_DATA/derivatives/sub-ADNI999S9999_ses-M000_task-rest_run-1_space-MNI152NLin6Asym_desc-denoised_bold.nii.gz \
  --mask /ABSOLUTE/PATH/ADNI_DATA/derivatives/sub-ADNI999S9999_ses-M000_task-rest_run-1_space-MNI152NLin6Asym_desc-brain_mask.nii.gz \
  --atlas cbig_Schaefer2018_400Parcels_7Networks_order_FSLMNI152_2mm \
  --space MNI152NLin6Asym --input-kind denoised \
  --inclusion /ABSOLUTE/PATH/ADNI_DATA/qc/step9b --image-id 999999999 \
  --resample-labels --min-coverage 0.5 \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/atlas-signals/run-001/Schaefer400
```

For MNI152NLin2009cAsym, a matching example is `templateflow_tpl-MNI152NLin2009cAsym_res-02_atlas-Schaefer2018_desc-400Parcels7Networks_dseg`. The above subject/image values are synthetic placeholders. Results must use a new external directory; neither inputs nor source atlas files are modified.

## Validation

Synthetic tests cover exact signal means, agreement with Nilearn, label preservation, masked/resampled ROI loss, nonfinite/constant signals, TR units, temporal masks, source hashes, memory caps, inclusion gates and CLI failure auditing. Actual public CBIG/TemplateFlow/Neuroparc atlas geometries are also tested with analytically known synthetic BOLD signals. This does not claim actual ADNI extraction or full-cohort processing.

## Dependencies and citations

Python 3.11+, NumPy, NiBabel and SciPy; Nilearn supplies an independent test reference and remains separately installed from requirements. The checked-out Nilearn submodule is not inserted into the runtime import path. Source software and individual atlas terms/citations remain applicable; parent repository licensing does not replace them. See each source license, the atlas metadata and [source locking guide](../../06_docs/atlas_library.md).

## Original acquisition frames and actual BIDS run evidence

Before extraction, optionally build two independent, hash-bound artifacts. Run these after 9.B and after the chosen denoised derivative exists. They preserve the nearest/28-day and pending policies and do not change imaging QC.

```sh
python 02_custom/s11_atlas_bold/adapters.py frames \
  --raw-bold /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.nii.gz \
  --raw-json /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.json \
  --bold /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin2009cAsym_desc-denoised_bold.nii.gz \
  --bold-json /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin2009cAsym_desc-denoised_bold.json \
  --outliers /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_outliers.tsv \
  --dummy-volumes 4 --output-dir /DATA/audit/run-001/acquisition-map
```

The frame adapter supports XCP-D **compressed denoising outputs**: raw frame count minus the explicit dummy count must equal the outlier-table length, and the number of `denoising=0` rows must equal the current BOLD length. Run entities, sidecar TR and the derivative's exact BIDS `Sources` reference to the outlier table must agree. Other temporal representations, including AFNI zero-filled censored frames, require a separate adapter and are rejected when counts disagree. The adapter does not remove additional frames. It writes `acquisition_frames.tsv` and an artifact binding it to the processed BOLD hash.

```sh
python 02_custom/s11_atlas_bold/adapters.py link-run \
  --inclusion /DATA/qc/step9b --image-id 999999999 \
  --raw-bold /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.nii.gz \
  --raw-json /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.json \
  --bold /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin2009cAsym_desc-denoised_bold.nii.gz \
  --bold-json /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin2009cAsym_desc-denoised_bold.json \
  --preprocessed-json /DATA/fmriprep/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.json \
  --output-dir /DATA/audit/run-001/bids-link
```

`link-run` verifies the raw JSON's SeriesInstanceUID, acquisition date and subject against the unique retained EPI row in 9.B. It checks raw/derivative run entities, TR and the exact declared derivative → preprocessed → raw BIDS Sources chain. The output preserves the original audit session and all inclusion evidence. Only a recognized metadata-audit session alias can be replaced by UID/date-backed actual BIDS entities; other conflicts fail. `pending` remains pending. Missing UID/date or ambiguous Sources are errors. This establishes a metadata and file-hash link, without asserting that transformation payloads or physical registration were independently verified.

Pass `--frame-map /DATA/audit/run-001/acquisition-map --run-link /DATA/audit/run-001/bids-link` to `extract`, alongside `--inclusion` and `--image-id`. The extractor rejects maps for another payload/run or different 9.B evidence. With a frame map, `frames.tsv` adds `raw_frame_index_zero_based`, `raw_nominal_time_seconds` and `raw_interval_from_previous_seconds`. Gaps survive both existing censoring and any explicitly supplied current-input sample mask. The legacy `input_frame_time_seconds` column remains nominal time in the current derivative; it must not be interpreted as original acquisition time after temporal compression. Raw nominal time is frame index × TR; slice-timing reference offsets remain in the source JSON. No continuous sampling or downstream FC validity is inferred.

## Investigating low coverage without changing QC

```sh
python 02_custom/s11_atlas_bold/diagnose_coverage.py \
  --extraction /DATA/atlas-signals/run-001/Schaefer400 \
  --mask /DATA/derivatives/BIDS_space-MNI152NLin2009cAsym_desc-brain_mask.nii.gz \
  --boldref /DATA/derivatives/BIDS_space-MNI152NLin2009cAsym_boldref.nii.gz \
  --t1w /DATA/derivatives/BIDS_space-MNI152NLin2009cAsym_desc-preproc_T1w.nii.gz \
  --gm-probability /DATA/derivatives/BIDS_space-MNI152NLin2009cAsym_label-GM_probseg.nii.gz \
  --anatomical-mask /DATA/derivatives/BIDS_space-MNI152NLin2009cAsym_desc-brain_mask.nii.gz \
  --output-dir /DATA/audit/run-001/coverage-diagnostics
```

Replace `BIDS` with the actual matching subject/session entities; EPI and anatomical masks are separate files. Inputs must be finite 3-D images on the same explicit standard-space grid. The EPI mask must be the one used by extraction. `coverage_diagnostics.tsv` preserves each existing ROI QC outcome and compares included/excluded EPI-reference medians, GM probability, T1 intensity and anatomical-mask support. It does not expand masks, drop ROIs, introduce a new cutoff or establish a unique cause. Reference attenuation in excluded tissue supports joint dropout/mask review; distortion, atrophy and local registration can still contribute. Default coverage 0.5, minimum one voxel and `analysis_ready=false` remain unchanged.

## macOS and Linux

The source manager and Python extraction CLI use the same pinned atlas/label hashes, spaces, coverage settings and run/frame evidence on both hosts. Fetch only selected sources explicitly, use host-correct external paths and preserve raw/denoised input declarations. This step does not need a new imaging container to read existing derivatives.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s11) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
