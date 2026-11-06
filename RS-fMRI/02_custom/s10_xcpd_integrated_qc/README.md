# Step 10 — S8 metrics, XCP-D and integrated imaging QC

## Purpose

This workflow implements S8 → XCP-D → quantitative QC → validated external archiving from the referenced ADNI preprocessing task. Python and Docker handle repeated processing without LLM/API calls. Finalization remains deferred until the cohort and human review are ready. Installing the code does not switch active services or start new calculations.

## Input

- External JSON: copy [xcpd_linc.example.json](../../03_config/xcpd_linc.example.json) and set root/license/templateflow. `repo=null` selects this repository's pinned upstream submodule; an unreviewed checkout cannot replace it.
- `<root>/results/<PTID>/EPI_YYYYMMDD_MT1_YYYYMMDD/{fmriprep,mriqc,pair_metadata.json}`: the published, completed-pair layout from the referenced task. fMRIPrep inputs must include functional/anatomical images, masks/references/transforms, confounds JSON/TSV, HTML reports and sessionwise FreeSurfer logs.
- `pair_metadata.json`: subject/PTID/pair_id, actual epi_date/mt1_date and image IDs, execution_session_label, `delivery_status=processing_complete_QC_pending`, and the actual mriqc/fmriprep start times, runner hashes and images under `execution_identity`.
- `<root>/runs/<subject>/logs/*_{mriqc,fmriprep}_sub-*_ses-*/run.json`: evidence of successful execution, unchanged inputs and matching published identity. Copying directories without execution records does not establish completion.
- An adapter from flat upstream Slurm derivatives to this pair layout and the S6/S7 queue scheduler are outside this consolidation. The existing task's queue continues as a separate operational runner. Step 7.A volume outputs without FreeSurfer cannot be passed directly to S10.

## Processing

The configuration pins XCP-D 26.2.0 by image digest: linc/nifti, MNI152NLin6Asym/res-2, 36P/GSR, FD 0.3 mm, at least 240 seconds, 4S256 (256 ROIs), 0.01–0.08 Hz, 6 mm smoothing, dummy scans 0, despiking and LINC/ABCC QC. Compare configuration details with the actual xcp_d.toml. This is separate from Step 8.A's 300-second criterion; neither check replaces the other.

1. Verify S6/S7 completion evidence, reuse motion/Euler functions from pinned upstream S8 and collect MRIQC IQMs.
2. Block individual motion failures, missing required metrics and explicit exclusions. When only cohort Euler/MRIQC decisions are pending, `allow_deferred_cohort_candidates=true` permits provisional XCP-D candidates without marking them as passed.
3. Verify the actual PyBIDS selection across subject/session/task/run/acq/dir/echo/rec. An absent run entity is selected as null; no run-01 is invented.
4. Preserve read-only inputs and hashes, expand only after the first pilot validates, and retain failed attempts, partial results and Docker reconnection support. Validate BOLD/ROI/FC/coverage, motion/censor/LINC QC, HTML, ALFF/ReHo and actual execution settings.
5. Preserve human review fields, decisions and revisions. `collect/watch` never finalizes. Imaging QC is finalized only through a separate command after cohort completion, current MRIQC flags and required human review.

## Output

`<root>/postprocessing/<config_id>/` contains `final_qc_master.tsv`, `pending_review.tsv`, `visual_review.tsv`, counts/distributions/reports, pilot/status records and configuration. Validated attempts remain under each pair's `s10/<config_id>/runs/`.

`clinical_scan_links.tsv` exports actual epi_image_id/epi_date and run identity for Step 9.A. Pass the link table from the same directory as `finalizations/<timestamp>/final_included_runs.tsv`. `ANALYSIS_READY=False` remains set: S10 finalization covers **imaging QC only**. Combining source QC from 3.A, study-specific 8.A criteria and clinical validation from 9.A is a separate research inclusion decision.

`archive_ready.json` establishes archival readiness, not research inclusion. The offloader verifies config_id, evidence hashes, actual volume UUID and copied data before reclaiming local space.

## Execution

Run from `RS-fMRI/` with an actual external configuration. Do not start a duplicate pilot/watch against a runtime root already managed by an active worker.

```sh
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json preflight
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json dry-run
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json pilot
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json watch
# Collect separately when needed. A researcher edits visual_review.tsv after reviewing the images.
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json collect
# Retry failures as a new attempt / revalidate without repeating image calculations.
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json retry-failed
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json revalidate
# Run only after the cohort is ready. The watch loop never invokes this command.
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json finalize --cohort-complete --mriqc-flags /ABSOLUTE/PATH/current-cohort-flags.tsv
```

`slurm` exports an array script without submitting `sbatch`. CIFTI/Apptainer execution requires separate validation.

External archiving is a separate command. Fill in the actual UUID, runtime and validated config_id in the [example settings](../../03_config/offload.example.json). **The command below copies and verifies data, then reclaims the local copies.** No actual data relocation is performed as part of this code consolidation.

```sh
python 02_custom/s10_xcpd_integrated_qc/offload_completed.py --root /ABSOLUTE/PATH/ADNI_DATA/pair_runtime --settings /ABSOLUTE/PATH/offload.local.json --once
```

## Validation

`05_tests/test_xcpd_integrated.py`, `test_xcpd_offload.py` and `test_xcpd_consolidation.py` cover inputs, missing/failed outputs, null BIDS selection, actual settings/ROI/censoring consistency, reconnection, the pilot gate, human review preservation, external-volume disconnection/corruption/recovery and the 9.A handoff. Determine the active pilot's success only from its existing runtime evidence. See [validation scope](../../06_docs/validation.md).

## Dependencies

Python 3.11+, [requirements](../../requirements.txt), pinned upstream S8, Docker, an existing XCP-D 26.2.0 image and atlas/template caches. See the [official CLI](https://xcp-d.readthedocs.io/en/26.2.0/usage.html), [official mode settings](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html) and [consolidation and transition boundaries](../../06_docs/xcpd_consolidation.md).

## Downstream research inclusion

Pass finalized `final_included_runs.tsv` and `clinical_scan_links.tsv` to 9.A, then pass the corrected v2 artifact to [9.B](../s9b_validate_inclusion/README.md). The gate combines source QC, nearest/28-day clinical conditions and confirmed ST absence while preserving source-QC pending and imaging-review decisions. S10 imaging QC alone does not establish research inclusion.

## macOS and Linux

The core XCP-D Linux container and validator can use the same scientific configuration on Mac Docker Desktop and Linux Docker Engine. The strict ADNI input layout still needs valid 7.B publication evidence. The external offloader calls macOS `diskutil info -plist`; native Linux needs a mounted-volume/copy-validation adapter before automatic archival and local cleanup. A systemd timer alone is not that port.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s10) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
