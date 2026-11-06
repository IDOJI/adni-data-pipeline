# Step 7.C — ANTs iteration logging transport

## Execution

```sh
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" --license "$FS_LICENSE" --ants-verbose --execute
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Starts a new public-example fMRIPrep calculation with the existing ANTs logging wrapper. This is an alternative launch for S7, not a second run after S7 has already completed.

**Results:** fMRIPrep outputs plus `ants_logging.json` and per-invocation raw/parsed iteration logs under the public root.

From `RS-fMRI/`, use the [public-data walkthrough](../../07_reproducibility/README.md#b4-fmriprep-stage-7--sessionwise-profile):

For an existing compatible backend, `run.py --runner /external/backend.py -- <backend arguments>` loads that backend and augments only its Docker calls. The backend must supply a console log file. Keep configuration, inputs and attempt logs outside the repository.

## Purpose and execution order

Add live iteration evidence around a 7.B/frozen fMRIPrep Docker command without changing its scientific arguments or original cache identity. Use after preparing verified inputs, before the next fMRIPrep launch. The public example calls `augment` directly.

## Input and processing

An immutable Docker image digest, an existing Docker preprocessing argv beginning with `docker run`, and an external attempt-log directory. The transport snapshots `antsRegistration`, adds read-only code and writable log mounts, and prepends the wrapper to the image's original PATH. The wrapper preserves ANTs arguments except explicitly setting verbosity to 1. Existing active containers are not changed.

## Output

`ants_logging.json` records base/effective argv, image PATH and wrapper SHA-256. `ants_iterations/<invocation>/` preserves raw stdout/stderr, execution/exit evidence and parsed stage/level/iteration progress. Cached registrations do not produce new iteration logs. This module does not install a queue, timer or controller handoff.

## Validation and dependencies

Python 3.11+, Docker and an installed pinned image. Synthetic transport/stream tests check unchanged computational argv and cache bytes, live raw channels/progress before completion, and preservation of failure exit codes. The transport does not establish registration accuracy or research inclusion.

## macOS and Linux

The same logging transport operates inside the pinned Linux container on both hosts. Preserve image PATH, registration argv and code hashes; only host bind sources differ. A Mac controller activation or keep-awake service is separate and needs its own Linux implementation.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s7c) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
