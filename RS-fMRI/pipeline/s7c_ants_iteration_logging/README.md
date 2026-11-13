# Step 7.C — Live ANTs iteration logging

## Execution

```sh
python pipeline/s7c_ants_iteration_logging/run.py \
  --runner pipeline/s7b_sessionwise_preprocessing/run.py -- \
  --config /ABS/PATH/private.yaml run --stage fmriprep --subject ADNI999S9999
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Starts a configured backend's new fMRIPrep run through the existing ANTs logging wrapper; it preserves computational settings and cache identity.

**Results:** fMRIPrep outputs plus wrapper metadata and raw/parsed iteration logs in the configured external attempt directory.

`04_workflow/queue_service.py` uses this launcher automatically for subsequent MRIQC and fMRIPrep stage launches. Existing live controllers require a verified controller-only handoff to load a changed dispatch function. Use the deferred activation procedure below; it waits for existing containers and workers to finish before a graceful idle-controller restart. Never restart active containers or terminate their host clients to enable logging.

## Purpose and execution order

Instrumentation around **7.B (or a verified frozen runner) → MRIQC/fMRIPrep Docker execution → ordinary completion, S8/S10 validation, verified archival and S12**. This is an independent Stage, not a replacement registration pipeline. The queue applies it to future stage launches, including authorized retries; already running containers retain their original commands and mounts.

## Input

An existing 7.B-compatible preprocessing runner, its external private YAML and CLI arguments, installed digest-pinned Docker images and the original runner's console-log handle. No new image pull or participant selection is performed. The selected image must define its original PATH and provide Python plus `antsRegistration`.

## Processing and cache identity

The launcher delegates to the unchanged runner and intercepts only its Docker transport. It mounts a per-attempt immutable copy of the `antsRegistration` logging wrapper, prepends that directory to the original image PATH and mounts a writable iteration-log directory. The wrapper resolves the original executable outside its own directory, retains every computational argument, replaces only verbosity flags with `--verbose 1`, and streams stdout/stderr to both the original caller and separate live files.

The backend's original scientific command, cache signature, input hashes, image digest, random seed, precision, transforms, convergence schedules and thread settings remain intact. `ants_logging.json` records both the base and effective Docker commands and the wrapper SHA-256. Each invocation's `execution.json` records the actual original ANTs executable, computational arguments and effective verbose command. Backend `run.json` and `command.txt` remain the base-command provenance; consult these additional transport/invocation receipts for the logging augmentation. Cached nodes can remain cached and will not generate new iteration logs until ANTs actually runs.

## Output

All artifacts remain outside this repository, under the backend's existing stage-attempt log folder:

```text
logs/<attempt>/
  console.log
  run.json
  ants_logging.json
  ants_logging_code/<sha256>/antsRegistration
  ants_iterations/<UTC-UUID>/
    execution.json
    stdout.log
    stderr.log
    progress.jsonl
    progress.json
```

Raw channels are flushed as they arrive, including carriage-return diagnostic lines. Parsed progress preserves the latest transform stage, resolution level, iteration, metric, convergence field and ANTs-reported elapsed field when available. Fields can be absent for another ANTs output format; raw output remains authoritative. An iteration number is not an overall percent or reliable finish-time prediction. `progress.json` stops advancing after completion; use `execution.json` and backend completion/QC records together.

Existing archival preserves the runtime logs under the pair's `_runtime/logs/`. This step adds no cohort inclusion decision and performs no model/API calls. Detailed output can add logging I/O and storage overhead.

## Validation and limitations

Synthetic tests verify unchanged computational arguments/cache bytes, live progress before exit, independent output channels, original failure propagation and dispatch for both frozen/new runners. A separate installed-image smoke test should compare tiny deterministic direct and wrapped ANTs outputs before deployment. This does not establish full-cohort scientific equivalence or guarantee byte-identical outputs across hardware/thread configurations. This module currently instruments `antsRegistration`; other ANTs tools and already-running registrations are not retrofitted.

## Deferred activation without interrupting active work

`activate_when_idle.py --root /ABS/runtime --service-label com.codex.adni-sb-queue-five --arm --watch` records the original admission policy and applies a temporary admission hold. This hold is represented by a reserve larger than the local disk and is maintenance, not a measured capacity shortage. Existing containers and workers continue unchanged; no new preprocessing subjects enter during the one-time drain. Only when both managed containers and queue workers are absent does it gracefully terminate the idle controller with SIGTERM and start it again. It never sends SIGSTOP/SIGKILL or signals to Docker clients/containers. Once the new controller advertises the logging launcher, it restores the original policy and exits successfully.

The temporary hold can leave slots idle while the slowest preexisting subject finishes. Source installation alone is not activation: inspect external `continuous5/ants_logging_activation.json` for `active` and `admission_restored=true`. A policy conflict is preserved for review rather than overwritten.

## macOS and Linux

The same logging transport operates inside the pinned Linux container on both hosts. Preserve image PATH, registration argv and code hashes; only host bind sources differ. A Mac controller activation or keep-awake service is separate and needs its own Linux implementation.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s7c) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
