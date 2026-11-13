# Step 7.B — Sessionwise MRIQC/fMRIPrep service adapter

For new fixed-seed runs, use `run_seeded.py` with a new runtime and `seed_policy: fixed-seed-v1`, `random_seed: 357`, `resources.omp_nthreads: 1`. Prefer seeded 5.D dispatch when exact-pair evidence is available. See the [seed contract](../../06_docs/seed_reproducibility.md). Original launcher commands below preserve the historical live route.

## Execution

```sh
python 02_custom/s7b_sessionwise_preprocessing/run.py \
  --config /ABSOLUTE/PATH/private.yaml dry-run \
  --stage fmriprep --subject ADNI999S9999
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** First inspects the configured single-case fMRIPrep command. The explicit `run` form below launches the selected case with the sessionwise surface-enabled profile.

**Results:** External work, derivatives and attempt logs for that case. Publishing completed pairs and operating a live queue are separate actions.

### Run one prepared case

```sh
python 02_custom/s7b_sessionwise_preprocessing/run.py \
  --config /ABSOLUTE/PATH/private.yaml run \
  --stage fmriprep --subject ADNI999S9999
```

The `run` command launches real imaging. Use the guarded 5.D entry point when the case was prepared through a binding receipt. An existing live queue chooses this adapter only for new subjects; previously started subjects finish through their recorded runner to preserve cache identity.

### Existing macOS queue deployment

```sh
python 04_workflow/queue_service.py \
  --root /ABSOLUTE/PATH/runtime --deployment /ABSOLUTE/PATH/deployment.json
```

Start this persistent controller only for a verified deployment without another controller owner. It uses Mac-specific integration and is not a Linux service recipe. See the [live-service handoff guide](../../06_docs/live_service_handoff.md).

## Purpose

Continue the existing explicit-pair SB preprocessing service with integrated source code. This preserves the original sessionwise FreeSurfer, surface/CIFTI and image settings; it is separate from the surface-disabled 7.A volume profile.

## Input

External private YAML: runtime, source_bids, source_manifest, source_phase_evidence, source_templateflow, images, resources, runs, output_spaces, random_seed and freesurfer_license. Explicit-pair plans, archive members and source hashes remain in the existing private runtime. This is a compatibility adapter, not a new selection-table requirement or pairing inference system.

## Processing

`make_source_manifest.py` validates exact selected BIDS images/sidecars and independent phase evidence. `run.py` reuses the integrated protocol’s Step 5 intake and launches the existing MRIQC/fMRIPrep Docker commands with read-only inputs. It preserves sessionwise anatomy, FreeSurfer reconstruction, requested standard/surface outputs and fsLR 91k. Input hashes, cache signatures, exact commands and original run provenance remain mandatory.

`observe.py` reconnects to existing containers without starting new calculations. Independently captured exit receipts protect auto-removed containers during controller replacement. `publish_pairs.py` publishes completed outputs under actual EPI/T1 dates while preserving internal BIDS paths.

## Output

Existing external bids/derivatives/work/logs and published pair directories. Original run records, failed attempts and caches remain in place. Completed outputs are reused rather than rerun.

## Validation

Synthetic tests cover legacy/new routing, unchanged surface/CIFTI options, preserved exit receipts, identity conflicts and the shared compute limit. Actual controller cutover separately records container IDs/start times before and after replacement.

## Dependencies

Python 3.11+, repository requirements, installed Docker images/templates, a valid license and the integrated protocol sources. No image pulls or analysis-setting changes are required for a code-path handoff.

## Admission-controller recovery

The live queue catches controller-iteration errors, records a traceback and retries the admission loop without shutting down its active worker pool. Unexpected worker-wrapper errors return the subject to the continuation queue; existing stage records remain authoritative and running containers are observed rather than recreated. The shared five-subject lease and disk-reserve admission policy still apply. A running process alone is not proof of scheduler health: inspect the status timestamp and actual Docker subjects.

## Independent controller heartbeat watchdog

`04_workflow/queue_watchdog.py` checks the external queue status timestamp. A separate local timer can invoke it every minute:

```sh
python 04_workflow/queue_watchdog.py --root /ABS/PATH/runtime --service-label com.codex.adni-sb-queue-five
```

A heartbeat older than 180 seconds causes a `launchctl kickstart -k` of the queue service only. The watchdog never calls Docker or changes scientific settings. It respects `queue_exhausted`, records recovery events and limits successful restarts to three per hour. Fresh `waiting_for_disk_capacity` is healthy and is not bypassed. Before planned controller maintenance, write an external `continuous5/watchdog_maintenance.json` with `until_epoch` set to a future Unix timestamp. The watchdog remains quiet until that deadline.

The source directory alone does not install a timer. Keep the local LaunchAgent definition, archive paths, status and logs outside this public repository. Validate real container identity preservation separately when installing a service on a running batch.

## External archive readiness and verified batch feeding

`04_workflow/source_archive_gate.py --config /ABS/private-source-gate.json` can be scheduled locally every 10,800 seconds. It checks the designated volume UUID, exact expected source size and 60-second file stability. Once size/stability match, it streams every ZIP member to EOF to verify CRC and checks that the frozen queue's required members exist. The checksum pass reads the full archive and may take time; it does not download, extract or alter the source. A matching unchanged validated fingerprint avoids repeating the full pass. This is ZIP integrity validation, not a source SHA-256 comparison or scientific QC.

Only at an idle queue boundary does the gate record and switch the external runtime settings to the validated archive path/size/mtime, retaining a rollback copy. No active calculation is stopped. It starts the verified feeder and existing S8/XCP-D, verified offload and S12 services without forcing restarts. State, configuration, ZIP/data files and LaunchAgents stay outside the source repository.

`04_workflow/verified_batch_feed.py --root /ABS/runtime --deployment /ABS/deployment.json --gate-status /ABS/runtime/continuous5/source-copy-gate/status.json` uses a rolling window of at most five registered subjects that have not yet completed verified external archival. A single completed archival receipt releases one position even when the other four subjects are still computing. It prepares only the available number of unstarted explicit pairs, checks the existing Step 5.D identity/pairing/CRC/header evidence, verifies exact runtime inputs and writes a new immutable continuation registry. Technical failures and unresolved identity gates are retained rather than silently declared completed. Disk reserves and the existing shared total-five compute leases remain enforced.

`04_workflow/rolling.py` launches a singleton worker per newly registered subject, retaining the existing 7.B runners, input hashes, frozen commands, publication layout and per-stage retry limits. Worker state and retry budgets are isolated under `continuous5/rolling/jobs/`, so an older live controller cannot overwrite new subjects. Existing calculations continue with their original container IDs. The old queue controller and its watchdog are retired only after its own registered workers have finished and no stage subprocess remains; other subjects' detached workers are untouched. The rolling manager then merges the subject journals into canonical state/status. External source gates, S8/XCP-D validation, verified copying and S12 remain independent services. No model/API calls are used. Local LaunchAgent startup logs should use a launchd-accessible Library/Logs directory, with an accessible working directory; successful bootstrap alone does not prove process startup.

Synthetic tests verify one-for-one refill, no slot release before completed external cleanup, isolated legacy/new state, independent worker startup while a legacy subject remains active, duplicate-worker locking and deferred retirement of a busy legacy controller. This compatibility path depends on the existing private queue/deployment and reviewed proposal artifacts; it does not introduce a mandatory selection table or change pairing policy.

## Idle runtime relocation

`04_workflow/runtime_relocation.py --config /ABS/private-relocation.json` can perform a one-time local runtime move after a frozen current batch finishes. Suspend the verified feeder and source-copy gate before arming it; keep preprocessing, postprocessing, archival and S12 workers running while the batch drains. The explicit external configuration records the source directory device/inode, separate empty destination, frozen subject list, managed service labels, offloader source, XCP-D configuration ID and read-only post-move check commands.

The watcher requires no managed imaging containers, successful preprocessing states, validated S8/XCP-D archival receipts for every current subject, S12 exports and a normally exited queue controller. It then unloads only idle managed services, acquires runtime worker locks and renames the directory on the same filesystem. Nonempty targets and cross-filesystem moves are refused. The prior absolute runtime location becomes a compatibility symlink; historical configuration bytes, cache paths, execution records, input bindings and archive identities are not rewritten. Queue, feeder and offloader entry points retain the lexical runtime alias while physical-path safety checks still resolve symlinks.

The directory device/inode must survive the move. Interrupted rename-to-alias creation can recover only that exact directory. Configured deployment and Docker bind-mount checks must pass before services are enabled and loaded again; partial service restarts are retried without unloading already resumed calculations. Keep configuration, logs, status, source backups and LaunchAgents outside the public source tree. The tool uses no model/API calls and exits successfully after completing the one-time relocation. Synthetic tests exercise active-work deferral, incomplete-postprocessing deferral, destination collision refusal, identity preservation, crash-window recovery and check-before-resume ordering. Installation and actual completion remain separate operational evidence.

## macOS and Linux

The configured single-case `run.py` builds Linux-container argv on either POSIX host after path setup. The completed-pair publisher uses macOS `/bin/cp -cR`, and `queue_service.py` uses `/usr/bin/caffeinate`. Linux needs publisher/controller and service adapters before the complete automatic ADNI chain is available. Do not run Mac-specific publication or queue commands as a Linux deployment recipe.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s7b) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.


## Bounded failure recovery

`04_workflow/rolling.py` admits at most five eligible subjects, keeps existing worker/container owners, and holds completed deliveries until verified archival. An exhausted execution failure remains recorded with its logs and caches but does not prevent admission of another eligible subject. Explicitly repaired retries receive a finite per-stage budget and optional priority; a queued sixth subject waits for a position. Per-subject locks and the shared compute lease prevent duplicate work and enforce the total-five limit. Controller-only activation must preserve existing subject workers.

The optional `04_workflow/recovery_runner.py` delegates to the frozen backend and original cache command. It raises only the Docker memory ceiling from 8 GiB to 16 GiB and retains workflow memory estimates, CPU/thread counts, image digests, random seeds, scientific flags and the 7.C logging transport. Each attempt writes `execution_environment.json` with base and effective commands, and links its fingerprint from `run.json`. The effective command record is authoritative for the actual execution environment; the base command remains the recorded cache identity. No successful outputs or failed cache signatures are rewritten.

Inputs are a verified continuation route, unchanged pair/configuration/cache evidence and an explicitly authorized retry budget. Outputs are independent attempt logs, execution-environment evidence and a held/completed queue state. Synthetic tests cover admission after failure, preservation of owners/delivery holds, bounded retries, command differences and evidence recording. This execution mechanism does not approve scientific inclusion. A separate [5.D technical-review continuation](../s5d_bids_identity/README.md#explicit-technical-retries-with-pending-source-review) preserves source review flags when an exact previously selected pair is explicitly requested again.


## Automatic source-review skips

The optional `04_workflow/source_review.py` policy reads a private, fingerprinted decision catalog built from the existing EPI manifest, candidate audit and exact selected pairs. Unresolved source/protocol review flags, missing source QC, ambiguous pairing, source ineligibility and failed input verification are automatically skipped. Source warnings remain separate from recoverable execution errors and from routine deferred final imaging QC. No new numerical QC cutoff is introduced.

Execution order is source-review policy → input/pair identity checks → MRIQC/fMRIPrep → S8/XCP-D → verified archival → S12. The policy applies before extraction, at worker stage boundaries, inside guarded continuation and before live postprocessing. A skip cannot be revived by remaining retry budget, old priority or an earlier technical-review exception. Skips do not occupy the rolling window; the next eligible pair can fill a vacancy up to the existing total-five limit. Existing owners for other pairs are preserved.

Outputs are a policy snapshot with source fingerprints and exact pair identities, a decision CSV, and individual JSON/HTML reports under the external runtime's `continuous5/source_review_skips/`. Existing raw files, original selection evidence, execution logs and historical results are retained. A missing or changed pair is skipped; a changed policy fingerprint stops dispatch for inspection. Source-review exclusions for historical completed pairs are recorded separately from their original execution/archival receipts.

Validation uses synthetic cases covering source flags on EPI and T1, missing QC, mismatched/unknown pairs, retained pending-final-QC fields, revoked technical exceptions, worker guards, retry/admission behavior and non-destructive reports. A new selected population requires a newly verified catalog; this policy does not silently extend its scope.


## Automatic execution durations

Run the independent [processing timing observer](../../06_docs/processing_timing.md) alongside S6/S7 and S10. It records actual Docker start/end events, observed pauses and macOS sleep separately, immediately persists each completed attempt, and synchronizes subject totals. Historical driver-only reconstructions are explicitly labeled estimates. Existing execution/cache identities are preserved; no active container restart is required.

## Processing-time records

```sh
export PREPROC_CONFIG="/ABSOLUTE/PATH/preprocessing.local.yaml"
export ADNI_SUBJECT="ADNI999S9999"
python 02_custom/s7b_sessionwise_preprocessing/run.py \
  --config "$PREPROC_CONFIG" run --stage mriqc --subject "$ADNI_SUBJECT"
python 02_custom/s7b_sessionwise_preprocessing/run.py \
  --config "$PREPROC_CONFIG" run --stage fmriprep --subject "$ADNI_SUBJECT"
```

These are future real-imaging commands for a prepared case. With the timing-enabled runner, each completion/failure calls `add_timing` and `refresh_safely` automatically; no extra timing watcher is required. First use [Step 7.D's source-only check](../s7d_processing_timing/README.md#1-check-automatic-recording-without-running-the-pipeline) to distinguish those runners from preserved legacy copies without hooks.

For YAML `runtime=R7`, original records are `R7/logs/<timestamp>_<stage>_sub-<subject>_ses-<session>/run.json`; `timing.elapsed_seconds` holds the duration. Reports default to `R7/timing/{attempts.tsv,cases.tsv,summary.json,ledger.json}` (also `cases.json`). When `R7=<shared-root>/runs/<subject>` and `<shared-root>/continuous5/` exists, reports go to `<shared-root>/timing/` instead. See [Step 7.D](../s7d_processing_timing/README.md) for combined MRIQC/fMRIPrep/XCP-D totals, manual legacy collection and incomplete values.

The timing object also exposes `timing.elapsed_display` with explicit hour/minute/second units; numeric `timing.elapsed_seconds` is preserved. Human TSV sidecars are separate from numeric files. See [the measurement contracts](../s7d_processing_timing/README.md#5-separate-docker-execution-observer-and-display-formats).
