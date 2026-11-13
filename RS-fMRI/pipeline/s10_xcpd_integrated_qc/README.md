# Step 10 — S8 metrics, XCP-D and integrated imaging QC

For new fixed-seed Docker runs, use `pipeline_seeded.py` and `03_config/xcpd_linc.seeded.example.json` with a new root. It preserves the 36P/LINC scientific profile and uses seed 1123 plus OMP1. The seeded launcher rejects legacy Slurm exports. See the [seed contract](../../06_docs/seed_reproducibility.md); original commands below remain available for historical workers.

## Execution

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config /ABSOLUTE/PATH/xcpd.local.json preflight
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config /ABSOLUTE/PATH/xcpd.local.json dry-run
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Checks the configured completed-pair inputs and prints the XCP-D plan. The separately selected `pilot` or `watch` commands below launch real postprocessing.

**Results:** Preflight/plan evidence first; actual runs add denoised BOLD, ROI/FC, native reports and QC tables under the external runtime.

### Run a pilot, then choose whether to watch

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json pilot
```

The pilot performs real XCP-D processing and checks its outputs. After reviewing that pilot, the following optional persistent worker handles newly completed pairs. Use one owner per runtime; do not start a duplicate pilot/watch beside an active worker.

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json watch
```

### Collect or recover an existing attempt

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json collect
```

`collect` refreshes QC tables. A researcher reviews the images and edits `visual_review.tsv`. Choose `retry-failed` to start a new failed-case attempt, or `revalidate` to check existing outputs without repeating the image calculation; these are distinct actions rather than a block to run blindly in sequence.

### Finalize reviewed cohort imaging QC

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config /ABSOLUTE/PATH/xcpd.local.json finalize \
  --cohort-complete --mriqc-flags /ABSOLUTE/PATH/current-cohort-flags.tsv
```

Run only after cohort completion and the required reviews. The watch loop never invokes finalization. `slurm` exports an array script without submitting `sbatch`; CIFTI/Apptainer execution requires separate validation.

### Archive validated output on the configured macOS volume

```sh
python pipeline/s10_xcpd_integrated_qc/offload_completed.py \
  --root /ABSOLUTE/PATH/ADNI_DATA/pair_runtime \
  --settings /ABSOLUTE/PATH/offload.local.json --once
```

This separate command **copies and verifies data, then reclaims the local copies**. Fill in the actual UUID, runtime and validated config_id in the [example settings](../../03_config/offload.example.json) first. The current offloader uses macOS volume checks; Linux needs the adapter described below.

## Purpose

This workflow implements S8 → XCP-D → quantitative QC → validated external archiving from the referenced ADNI preprocessing task. Python and Docker handle repeated processing without LLM/API calls. Finalization remains deferred until the cohort and human review are ready. Installing the code does not switch active services or start new calculations.

## Input

- External JSON: copy [xcpd_linc.example.json](../../03_config/xcpd_linc.example.json) and set root/license/templateflow. `repo=null` selects this repository's integrated protocol source directory; an unreviewed checkout cannot replace it.
- `<root>/results/<PTID>/EPI_YYYYMMDD_MT1_YYYYMMDD/{fmriprep,mriqc,pair_metadata.json}`: the published, completed-pair layout from the referenced task. fMRIPrep inputs must include functional/anatomical images, masks/references/transforms, confounds JSON/TSV, HTML reports and sessionwise FreeSurfer logs.
- `pair_metadata.json`: subject/PTID/pair_id, actual epi_date/mt1_date and image IDs, execution_session_label, `delivery_status=processing_complete_QC_pending`, and the actual mriqc/fmriprep start times, runner hashes and images under `execution_identity`.
- `<root>/runs/<subject>/logs/*_{mriqc,fmriprep}_sub-*_ses-*/run.json`: evidence of successful execution, unchanged inputs and matching published identity. Copying directories without execution records does not establish completion.
- An adapter from flat upstream Slurm derivatives to this pair layout and the S6/S7 queue scheduler are outside this consolidation. The existing task's queue continues as a separate operational runner. Step 7.A volume outputs without FreeSurfer cannot be passed directly to S10.

## Processing

The configuration pins XCP-D 26.2.0 by image digest: linc/nifti, MNI152NLin6Asym/res-2, 36P/GSR, FD 0.3 mm, at least 240 seconds, 4S256 (256 ROIs), 0.01–0.08 Hz, 6 mm smoothing, dummy scans 0, despiking and LINC/ABCC QC. Compare configuration details with the actual xcp_d.toml. This is separate from Step 8.A's 300-second criterion; neither check replaces the other.

1. Verify S6/S7 completion evidence, reuse motion/Euler functions from integrated protocol S8 and collect MRIQC IQMs.
2. Block individual motion failures, missing required metrics and explicit exclusions. When only cohort Euler/MRIQC decisions are pending, `allow_deferred_cohort_candidates=true` permits provisional XCP-D candidates without marking them as passed.
3. Verify the actual PyBIDS selection across subject/session/task/run/acq/dir/echo/rec. An absent run entity is selected as null; no run-01 is invented.
4. Preserve read-only inputs and hashes, expand only after the first pilot validates, and retain failed attempts, partial results and Docker reconnection support. Validate BOLD/ROI/FC/coverage, motion/censor/LINC QC, HTML, ALFF/ReHo and actual execution settings.
5. Preserve human review fields, decisions and revisions. `collect/watch` never finalizes. Imaging QC is finalized only through a separate command after cohort completion, current MRIQC flags and required human review.

## Output

`<root>/postprocessing/<config_id>/` contains `final_qc_master.tsv`, `pending_review.tsv`, `visual_review.tsv`, counts/distributions/reports, pilot/status records and configuration. Validated attempts remain under each pair's `s10/<config_id>/runs/`.

`clinical_scan_links.tsv` exports actual epi_image_id/epi_date and run identity for Step 9.A. Pass the link table from the same directory as `finalizations/<timestamp>/final_included_runs.tsv`. `ANALYSIS_READY=False` remains set: S10 finalization covers **imaging QC only**. Combining source QC from 3.A, study-specific 8.A criteria and clinical validation from 9.A is a separate research inclusion decision.

`archive_ready.json` establishes archival readiness, not research inclusion. The offloader verifies config_id, evidence hashes, actual volume UUID and copied data before reclaiming local space.

## Validation

`05_tests/test_xcpd_integrated.py`, `test_xcpd_offload.py` and `test_xcpd_consolidation.py` cover inputs, missing/failed outputs, null BIDS selection, actual settings/ROI/censoring consistency, reconnection, the pilot gate, human review preservation, external-volume disconnection/corruption/recovery and the 9.A handoff. Determine the active pilot's success only from its existing runtime evidence. See [validation scope](../../06_docs/validation.md).

## Dependencies

Python 3.11+, [requirements](../../requirements.txt), integrated protocol S8, Docker, an existing XCP-D 26.2.0 image and atlas/template caches. See the [official CLI](https://xcp-d.readthedocs.io/en/26.2.0/usage.html), [official mode settings](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html) and [consolidation and transition boundaries](../../06_docs/xcpd_consolidation.md).

## Downstream research inclusion

Pass finalized `final_included_runs.tsv` and `clinical_scan_links.tsv` to 9.A, then pass the corrected v2 artifact to [9.B](../s9b_validate_inclusion/README.md). The gate combines source QC, nearest/28-day clinical conditions and confirmed ST absence while preserving source-QC pending and imaging-review decisions. S10 imaging QC alone does not establish research inclusion.

## Execution resources and terminal worker failures

The compatibility entry point `04_workflow/live_services.py` accepts an optional private deployment `xcpd_execution_override` with a complete `resources` object (`cpus`, `omp_nthreads`, `mem_mb`, `docker_memory`), approval timestamp and reason. Only those execution fields can be overridden. It keeps the historical configuration bytes, analysis parameters and config ID intact, while each new attempt records its historical/effective resources in `execution_environment.json` and its exact effective Docker/XCP-D command in `execution.json`. Existing successful attempts are reused and existing running command records are not rewritten. Do not infer that the original configuration snapshot alone describes overridden attempt resources.

An optional private `xcpd_recovery_priority` subject list orders recovery before other pairs without changing candidate/QC gates. A failed attempt under a different Docker memory limit can receive an immediate resource-revision retry only while the existing maximum attempt count permits it; all failed attempt data remain preserved. Thread count changes may affect floating-point ordering and runtime, so report effective execution resources with provenance.

During Docker waits, the integrated pipeline checks exact config/run container labels, Docker OOM state and the recent log for a terminal `BrokenProcessPool` exception. A confirmed internal terminal failure writes `runtime_failure.json`, stops only that matching failed container and follows ordinary failed-output validation and bounded retry. CPU silence alone is never a stop condition. A live container or fresh scheduler heartbeat does not establish imaging progress. Docker VM memory and its Linux swap are separate from the macOS host's memory/swap; change VM-wide settings only at an authorized idle maintenance boundary.

Synthetic tests cover resource-only command differences, unchanged historical configuration, rejected analysis overrides, terminal failure/healthy-container discrimination, container identity checks and bounded resource-revision retries. These checks establish orchestration behavior, not completion of a real XCP-D retry or research inclusion.

## Individual QC reports and retention of rejected runs

`qc_report.py` writes `qc_report.html` and `qc_report.json` at each completed pair root. Reports identify the subject/pair/configuration, per-run QC and execution statuses, exact measured motion/duration values, applied thresholds and explicit exclusion/skip reasons. Provisional cohort/research inclusion remains pending. A QC rejection is a documented processing decision, not an instruction to delete the subject's files.

`mark_ready` includes these reports in the archival evidence hashes before future S8/XCP-D-complete or QC-rejected pairs are copied. Existing verified offload gates preserve available images, intermediate work and execution records, verify the copy before local cleanup and release the rolling admission position only after completed archival. Failed or integrity-invalid executions do not acquire a false success receipt.

For already archived pairs, run `python pipeline/s10_xcpd_integrated_qc/qc_report.py --archive-root /ABS/archive --config /ABS/private-config.json`. This appends reports and `qc_report_addendum.json` without rewriting the original payload manifest or existing complete reports. The addendum pins report hashes and the original archive-manifest hash. No images are reprocessed or deleted. Synthetic tests cover reason/metric/threshold accuracy, skipped-duration explanations, HTML escaping and preservation of image bytes and completed reports.

## macOS and Linux

The core XCP-D Linux container and validator can use the same scientific configuration on Mac Docker Desktop and Linux Docker Engine. The strict ADNI input layout still needs valid 7.B publication evidence. The external offloader calls macOS `diskutil info -plist`; native Linux needs a mounted-volume/copy-validation adapter before automatic archival and local cleanup. A systemd timer alone is not that port.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s10) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.


The live compatibility service honors the optional [source-review skip policy](../s7b_sessionwise_preprocessing/README.md#automatic-source-review-skips) when listing pairs and immediately before XCP-D dispatch. Skipped pairs retain their original files, QC values and historical receipts; the runtime's separate JSON/HTML exclusion report records why no further automatic computation is admitted. This does not alter the immutable XCP-D analysis configuration or turn routine pending final QC into a source exclusion.

Source exclusions also update the active cohort visual-review table before aggregation: the complete original table and excluded annotations are preserved under the external hub `source_review_excluded/`. Only explicitly excluded known subjects are removed from the active table. Unknown identities remain for the original scope guard, and concurrent manual edits abort the update. Historical per-pair QC files remain unchanged.

## Processing-time records

```sh
export XCPD_CONFIG="/ABSOLUTE/PATH/xcpd.local.json"
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config "$XCPD_CONFIG" pilot
```

This is future real XCP-D execution on the published-pair inputs described above. With the timing-enabled runner, the measured container interval is saved before output validation and refreshed after final completion/failure. The `execution.json` contains `timing.elapsed_seconds`; a finished container with validation pending does not become a completed pipeline. First use [Step 7.D's source-only check](../s7d_processing_timing/README.md#1-check-automatic-recording-without-running-the-pipeline) to detect a legacy copy lacking these hooks.

For JSON `root=R10`, execution records are `<source_pair>/s10/<config_id>/runs/<run_key>/attempt-NNN/execution.json`, normally under `R10/results/`. Reports go to `R10/timing/{attempts.tsv,cases.tsv,summary.json,ledger.json}` (also `cases.json`). Combined preprocessing/postprocessing totals require the corresponding preprocessing receipts under the same shared root. No timing service is required for new completion hooks. See [Step 7.D](../s7d_processing_timing/README.md) for complete paths, total-time definitions and optional legacy collection.

The timing object also exposes `timing.elapsed_display` with explicit hour/minute/second units; numeric `timing.elapsed_seconds` is preserved. Human TSV sidecars are separate from numeric files. See [the measurement contracts](../s7d_processing_timing/README.md#5-separate-docker-execution-observer-and-display-formats).
