# Step 5.D — BIDS identity and exact EPI–T1 dispatch

## Execution

```sh
python 02_custom/s5d_bids_identity/binding.py --config /external/binding-config.json
python 02_custom/s5d_bids_identity/guarded_runner.py verify-pair \
  --receipt /external/binding/07.binding-receipt.json --epi-key EXTERNAL_EPI_KEY
python 02_custom/s5d_bids_identity/guarded_runner.py prepare \
  --receipt /external/binding/07.binding-receipt.json --epi-key EXTERNAL_EPI_KEY \
  --runtime /external/NEW_ISOLATED_PAIR --template /external/step7b-template.yaml
python 02_custom/s5d_bids_identity/guarded_runner.py intake --config /external/NEW_ISOLATED_PAIR/verified-config.yaml
python 02_custom/s5d_bids_identity/guarded_runner.py dry-run --stage fmriprep --config /external/NEW_ISOLATED_PAIR/verified-config.yaml
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Checks the proposed EPI–T1 pair against source UIDs, Image IDs, dates and independent file hashes, then prepares an isolated verified input view.

**Results:** Binding/audit tables, `07.binding-receipt.json`, and a separate prepared runtime for dispatch-eligible pairs. The preview does not run fMRIPrep.

`prepare` copies only the verified pair into an isolated source view and delegates the existing 7.B preflight/prepare code. Multiple original runs remain separate EPI keys/runtimes; their original filenames and hashes remain in the provenance. The isolated view may use 7.B's canonical filenames without changing the original BIDS files.

`check`, `intake`, `dry-run` and `run` recheck the receipt, source hashes, exact configured Image IDs and runtime files before calling 7.B. Extra T1 acquisitions are rejected so a session filter cannot silently expand the anatomical template. `run` always uses the strict profile; a technical-extension flag cannot bypass pending pairing evidence.

Full MRIQC/fMRIPrep calculation requires a separate explicit execution request and actual environment verification. This implementation does not start, stop or replace existing controllers, containers, cached subjects or deployment receipts. Use the guarded entry point for newly bound pairs rather than passing their configuration directly to a legacy runner. Completion of this step means file/identity and dispatch-contract validation, not completed preprocessing or research inclusion.

## Purpose and workflow position

This optional adapter follows BIDS conversion and an explicit external EPI–T1 proposal, before Step 7.B execution or an explicitly authorized continuation. It does not replace upstream selection, require a historical Research Selection Table in the main workflow, or change the integrated protocol selection rules. Queue admission requires a separately installed external continuation registry.

## Inputs

An external JSON configuration supplies `images`, `epi_manifest`, `pairing_receipt`, `bids_roots`, `hash_evidence`, `output_dir` and optional output `prefix`. The image registry has `PTID,MRI_STUDY_DATE,MODALITY,IMAGE_ID,SERIES_UID,SEARCH_PHASE,ELIGIBLE,QC_STATUS,EXCLUSION_REASONS`. The external proposal carries each EPI key, proposed T1 ID, tie/review status, metadata-QC status and protocol scope. Its provenance must hash the registry and proposal.

Hash evidence is either a conversion CSV (`SOURCE_PTID,STUDY_DATE,MODALITY,SOURCE_IMAGE_ID,NIFTI_SHA256`) or an extraction JSON list (`ptid,scan_date,modality,image_id,sha256`). Keep real registries, configurations, identifiers and results outside this repository.

## Validation and preservation

- Open only resident local files; do not hydrate cloud placeholders or download data.
- Link an observed JSON `SeriesInstanceUID` to exactly one source registry row. Independently require the Image ID, participant, actual date, modality and NIfTI hash to agree with conversion/extraction evidence. A filename or clinical visit label is not sufficient.
- Validate NIfTI dimensions/geometry, JSON/header TR, phase encoding and slice timing against the declared/header slice axis. These checks do not establish registration, motion, coverage or scientific QC.
- Retain every supplied EPI row. Missing files, unknown/ambiguous UIDs, conflicting copies, pending source QC, ties, cross-date proposals and unsupported protocol extensions remain held.
- Equivalent copies remain in the file audit. Contradictory copies are not hidden by selecting the first good copy.
- Dispatch requires a same-day single T1 proposal, documented source QC, no unresolved review flag and verified files for both images. `ANALYSIS_READY` remains false.

## Outputs

| File | Role |
|---|---|
| `02.image-validation.csv` | All source images and current BIDS identity status |
| `03.file-audit.csv` | Every inspected BIDS copy, hashes and validation reasons |
| `04.epi-execution-manifest.csv` | All EPI rows, verified paths and ready/held status |
| `05.execution-plans.json` | Exact EPI/T1 files for dispatch-eligible pairs only |
| `06.summary.json` | Identity and ready/held counts; scientific inclusion pending |
| `07.binding-receipt.json` | Input/output fingerprints for revalidation at dispatch |

## Dependencies and tests

Python 3.11+, NumPy, NiBabel, PyYAML and the installed 7.B runtime dependencies. Synthetic tests cover UID ambiguity, Image ID/hash/date conflicts, unavailable files, exact-pair isolation, post-validation mutation and refusal to dispatch pending material. Run the repository pytest suite and `04_workflow/lab.py doctor`.

## macOS and Linux

Use host-correct BIDS roots and independent hash evidence in a new external configuration. Binding/guarded single-case delegation remains separate from the Mac-specific 7.B publisher and queue; do not claim the complete Linux dispatch/archive chain from a binding pass.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s5d) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
