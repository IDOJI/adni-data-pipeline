# Step 7.C — ANTs iteration logging transport

## Purpose and execution order

Add live iteration evidence around a 7.B/frozen fMRIPrep Docker command without changing its scientific arguments or original cache identity. Use after preparing verified inputs, before the next fMRIPrep launch. The public example calls `augment` directly.

## Input and processing

An immutable Docker image digest, an existing Docker preprocessing argv beginning with `docker run`, and an external attempt-log directory. The transport snapshots `antsRegistration`, adds read-only code and writable log mounts, and prepends the wrapper to the image's original PATH. The wrapper preserves ANTs arguments except explicitly setting verbosity to 1. Existing active containers are not changed.

## Output

`ants_logging.json` records base/effective argv, image PATH and wrapper SHA-256. `ants_iterations/<invocation>/` preserves raw stdout/stderr, execution/exit evidence and parsed stage/level/iteration progress. Cached registrations do not produce new iteration logs. This module does not install a queue, timer or controller handoff.

## Execution

From `RS-fMRI/`, use the [public-data walkthrough](../../07_reproducibility/README.md#b4-fmriprep-stage-7--sessionwise-profile):

```sh
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" --license "$FS_LICENSE" --ants-verbose --execute
```

For an existing compatible backend, `run.py --runner /external/backend.py -- <backend arguments>` loads that backend and augments only its Docker calls. The backend must supply a console log file. Keep configuration, inputs and attempt logs outside the repository.

## Validation and dependencies

Python 3.11+, Docker and an installed pinned image. Synthetic transport/stream tests check unchanged computational argv and cache bytes, live raw channels/progress before completion, and preservation of failure exit codes. The transport does not establish registration accuracy or research inclusion.
