# Automatic processing durations

```sh
# Explicitly read existing Docker/receipt state and write timing sidecars:
python 04_workflow/processing_timing.py --root "$ADNI_RUNTIME" once

# Persistent observer; keep this running before subsequent imaging launches:
python 04_workflow/processing_timing.py --root "$ADNI_RUNTIME" watch
```

The `once` command accesses Docker and the specified runtime and writes sidecars; it is not a source-only check. `watch` starts observation only when explicitly run. Neither command installs a service.

The observer reads Docker lifecycle events and existing MRIQC/fMRIPrep/XCP-D execution records. It never starts, pauses, stops or restarts an imaging container and does not modify frozen backend/configuration/cache identities. A terminal event immediately writes a duration record; the subject CSV and published summaries synchronize within the following observation cycle. No model or network service calls are used.

## Relationship to receipt-based Step 7.D

[Step 7.D](../02_custom/s7d_processing_timing/README.md) uses `processing_time.py` for receipt intervals and the overall observed wall span, including queue/inter-attempt gaps and runner validation. This guide describes `processing_timing.py` for container execution windows. They share only `duration_display.format_duration`, which changes presentation without changing numeric values. Do not add overlapping totals together or replace provenance/coverage fields. Step 7.D's preprocessing sum includes MRIQC; this observer's main combined sum is fMRIPrep + XCP-D with MRIQC separate. Neither is CPU-core time.

## Measurement contract

- MRIQC, fMRIPrep and XCP-D are recorded separately. User-facing tables show explicit Korean hour, minute and second units, for example `2시간 45분 7초`; machine-readable raw fields retain seconds without losing precision. Hours do not wrap after 24, missing totals remain incomplete, and displayed values round to the nearest second.
- Actual Docker `StartedAt`/`FinishedAt`, or captured `start`/`die` event timestamps, define each container execution window. Queue admission, time between attempts, post-exit failure holds, and delayed host-runner confirmation are excluded from these windows.
- Captured Docker pause intervals and known macOS kernel sleep/wake intervals are subtracted as a union, without double counting overlap. Coverage is explicitly reported. Late attachment, missing event history and historical logs cannot silently establish complete pause/sleep coverage.
- This is elapsed execution time, not CPU-core time. Image computation, I/O, workflow setup and scheduling inside a running container remain part of its execution.
- Failed execution and successful execution have separate fields. The fMRIPrep-plus-XCP-D total includes their recorded execution attempts; MRIQC has a separate column. A successful retry can reuse cached work produced before a failure, so its last successful attempt alone is not the full cost of processing an input from scratch.
- Incomplete datasets retain a null preprocessing/postprocessing total. Intentional pre-QC skips are identified instead of being reported as successful XCP-D processing.

## Outputs

All outputs are outside the source repository:

```text
$ADNI_RUNTIME/continuous5/timing/
  attempts/<subject>/<stage>/<attempt-token>.json
  subjects/<subject>.json
  processing_times.csv
  processing_times.raw.csv
  observer_state.json
  status.json
  selftests/<container-id>.json
```

`processing_times.csv` is the human-readable table. Starting with recorder 1.1.0, integrations that need the previous numeric schema must read `processing_times.raw.csv` instead. The raw schema and numeric measurement semantics are unchanged.

Subject summaries cover all recorded attempts in their managed scope. Pair sidecars require exactly one published pair per subject; multiple visits stay unassigned and no single-pair timing file is emitted. This prevents a subject total from being presented as one visit's duration.

After the unchanged S12 exporter has established its owned `results/export_manifest.json`, the observer adds `results/processing_time.json`, a human-readable one-row `results/processing_time.csv`, and a numeric `results/processing_time.raw.csv` for that exact published pair. JSON keeps a human-readable `display` object alongside the numeric `summary` and original attempt provenance. It does not pre-create an unmanaged results directory or change the existing metrics/export manifest. Source-review exclusion and final scientific inclusion remain separate decisions.

`recording_mode=automatic_terminal_event` identifies prospective completion capture. `existing_docker_state` identifies measurements recovered from surviving container state. `historical_reconstruction` and its quality field identify later reconstruction from old driver timestamps; these older durations may include observation overhead or unrecorded pauses and must not be represented as fully measured active processing time. Original records are preserved.

## Installation and verification

An installed Python environment with Docker access and an external managed runtime containing `continuous5/settings.json` is required. Writes inside the source repository are rejected. When you choose to observe future processing, run `watch` in a terminal or under a separately configured host service; cloning/importing the source does not start it. Start the observer without restarting active imaging workers. A single observer lock prevents competing writers; reconnects replay available daemon events. Source fingerprints, container IDs, record paths, pause coverage and timing quality remain in each duration record.

Synthetic checks cover immediate terminal persistence, queue/failure-hold exclusion, separate failed attempts, pause/sleep overlap, replay idempotence, historical labeling, late confirmation, unknown-container rejection and S12 ownership. A tiny local self-test container labeled `adni.processing_timing.selftest=true` and named `adni-timing-selftest-*` can validate real event delivery; its records are isolated from participant totals. It requires no neuroimaging inputs and does not validate scientific preprocessing.

macOS kernel sleep tracking is supported when the host exposes `kern.sleeptime` and `kern.waketime`. Other hosts retain Docker event timing and explicitly mark sleep-history coverage as partial. Docker access is required; original clinical/MRI data are not uploaded.
