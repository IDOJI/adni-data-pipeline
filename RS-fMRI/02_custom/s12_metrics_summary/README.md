# Per-run scalar metrics and report browser

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

## Integrated execution

Run from `RS-fMRI/`. The integrated entry point checks the pinned source environment and rejects archive/status paths inside the source repository:

```sh
python 04_workflow/lab.py export-results --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json
python 04_workflow/lab.py export-results --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json --watch
python 04_workflow/lab.py plan --config /ABS/PATH/generated/upstream.yaml --archive-root /ABS/PATH/archive --metrics-status /ABS/PATH/runtime/metrics-status.json
```

The last command prints an explicit Step-12 plan and does not export or start a watcher. This reporting branch is S10 technical validation → verified archive/local cleanup → S12; optional Step 11 is not required. Private per-machine service arguments, real participant outputs and logs stay outside the repository. An installed local service can continue to invoke the repository-owned step directly.

## Direct step execution

```sh
python 02_custom/s12_metrics_summary/run.py --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json
# Recheck completed archives every 120 seconds without model/API calls:
python 02_custom/s12_metrics_summary/run.py --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics-status.json --watch
```

Unverified/in-progress archives wait. Unchanged exports are skipped. Modified generated files are preserved and reported as errors rather than overwritten. An existing nonempty results folder without this export's manifest is not adopted automatically.

## Validation

Synthetic tests check one-row output, known volume/thickness/ReHo values, NA preservation, native-report links, idempotence, human-edit preservation and rejection of unvalidated XCP-D success. Real-data validation belongs in private runtime records, never this public source tree.

## Dependencies

Python 3.11+ and pandas from [requirements.txt](../../requirements.txt). Inputs must retain the original report assets and FreeSurfer/S8/XCP-D files in the archived pair. No image pipeline is rerun and no external service is contacted.
