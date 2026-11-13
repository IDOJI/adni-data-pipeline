# Per-run scalar metrics and report browser

## Integrated execution

```sh
python 04_workflow/lab.py export-results \
  --archive-root /ABS/PATH/archive \
  --status /ABS/PATH/runtime/metrics-status.json
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Reads already calculated values from verified archives and exports one scalar row per pair/run plus links to native HTML reports.

**Results:** Each pair/run receives `results/metrics.csv`, `metrics.tsv`, a units/source dictionary, `export_manifest.json` and `index.html`.

The integrated entry point checks the pinned source environment and rejects archive/status paths inside the source repository. This is the one-shot export; optional Step 11 is not required.

### Optional persistent scan

```sh
python 04_workflow/lab.py export-results \
  --archive-root /ABS/PATH/archive \
  --status /ABS/PATH/runtime/metrics-status.json --watch
```

`--watch` repeatedly scans for newly verified archives. It does not launch MRIQC, fMRIPrep or XCP-D. Keep private per-machine service arguments and logs outside the repository.

### Print the export plan

```sh
python 04_workflow/lab.py plan \
  --config /ABS/PATH/generated/pipeline.yaml \
  --archive-root /ABS/PATH/archive \
  --metrics-status /ABS/PATH/runtime/metrics-status.json
```

This only prints the Step-12 command; it does not export or start a watcher. An installed local service can invoke the direct step entry point documented below.

## Purpose

Collect previously calculated structural/functional scalar values into a one-row dataset per image pair/run, and provide a browser entry point for the existing native reports.

## Contract and order

Run after S10 validation and verified archival/local cleanup. This additive export leaves the original archive manifest and all images untouched. Input is an explicit archive root containing participant/scan-date-pair folders, `pair_metadata.json`, FreeSurfer stats, S8 rows and the latest XCP-D execution records. No clinical selection table is required.

Each pair receives `results/index.html` with relative links to the native MRIQC, fMRIPrep, XCP-D participant and executive-summary HTML reports. Original report directories remain in place to preserve their image/assets paths.

`metrics.csv` and `metrics.tsv` each contain exactly one row for the selected participant, T1/EPI image pair and functional run. Structural columns derive from the paired T1, not the EPI acquisition date. Multiple configurations/runs receive separate subdirectories, never a merged ambiguous row.

- `fs__...`: FreeSurfer aseg/wmparc region volumes, cortical atlas surface area, volume and thickness, hemispheric summary measures and other numeric stats. Units are recorded in the dictionary. Both hemispheres and available cortical parcellations remain distinct.
- `s8__...` and `xcpd_qc__...`: existing quantitative QC values and processing states.
- `xcpd__<space>__<atlas>__reho/alff/coverage__<region>`: existing XCP-D regional scalar results. ReHo/ALFF values are read directly; this exporter does not recalculate images or alter denoising.
- Time series and FC matrices remain in their original files and are not flattened into this scalar summary.

`metrics_dictionary.csv` maps every column to its source file and available unit; `export_manifest.json` records source/output hashes, code identity, run IDs and row/column counts. Nonfinite/missing numeric values remain NA. Export success does not establish scientific inclusion, segmentation validity or visual-QC approval; existing coverage warnings remain visible.

## Direct step execution

```sh
python pipeline/s12_metrics_summary/run.py --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json
# Recheck completed archives every 120 seconds without model/API calls:
python pipeline/s12_metrics_summary/run.py --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json --watch
```

Unverified/in-progress archives wait. Unchanged exports are skipped. Modified generated files are preserved and reported as errors rather than overwritten. An existing nonempty results folder without this export's manifest is not adopted automatically.

## Validation

Synthetic tests check one-row output, known volume/thickness/ReHo values, NA preservation, native-report links, idempotence, human-edit preservation and rejection of unvalidated XCP-D success. Real-data validation belongs in private runtime records, never this public source tree.

## Dependencies

Python 3.11+ and pandas from [requirements.txt](../../requirements.txt). Inputs must retain the original report assets and FreeSurfer/S8/XCP-D files in the archived pair. No image pipeline is rerun and no external service is contacted.

## macOS and Linux

The exporter and explicit Python `--watch` scan loop can read existing valid archives on both hosts. Set the actual mounted archive path and keep relative HTML/assets intact. Linux archival must first implement and validate the S10 volume/copy transition; copying a Mac receipt or setting its status by hand is not a verified archive.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s12) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.


For a managed runtime with a source-review skip policy, `04_workflow/source_review_metrics.py` checks exact pair exclusions before delegating to this unchanged exporter. Skipped historical archives keep their existing tables and reports; no metric extraction or report regeneration is performed for them. The wrapper retains the original exporter file and its cache fingerprint, and records `skipped_source_review` in the external watcher status. Use the existing source-review JSON/HTML report for exclusion reasons.
