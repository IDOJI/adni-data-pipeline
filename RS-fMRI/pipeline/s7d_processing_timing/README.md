# Processing times: MRIQC, fMRIPrep and XCP-D

## 1. Check automatic recording without running the pipeline

```sh
cd /ABSOLUTE/PATH/adni-data-pipeline/RS-fMRI
python - <<'CHECK'
import ast
from pathlib import Path
checks = {
    'pipeline/s7b_sessionwise_preprocessing/run.py': 'run_stage',
    'pipeline/s10_xcpd_integrated_qc/pipeline.py': 'run_one',
}
missing = []
for name, function in checks.items():
    tree = ast.parse(Path(name).read_text())
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == function)
    calls = {n.func.id for n in ast.walk(node)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    absent = {'add_timing', 'refresh_safely'} - calls
    if absent:
        missing.append(f'{name}: missing {", ".join(sorted(absent))}')
if missing:
    raise SystemExit('Automatic completion hooks are absent:\n' + '\n'.join(missing))
print('Both runners contain automatic timing hooks; no jobs were executed.')
CHECK
```

This command reads Python source with `ast.parse`. It does not import a runner, read research inputs, call Docker, collect existing timings or install/start a service. It checks that the completion functions call both the timing writer and report refresher; it is a static check, not execution validation.

The timing-enabled repository version writes times automatically when **you later run** 7.B/S10. No additional timing watcher is required for those new runners. A checkout can retain older deployment-bound runner files to preserve active jobs: the presence of Step 7.D alone does not add completion hooks to those files. If this check fails, use a separate clean checkout with the timing hooks for future work, or explicitly use the legacy collector below. Preserve existing runners, their source hashes and work caches until a reviewed handoff; do not overwrite them just to pass this check.

To obtain the timing-enabled source in a **new, separate directory**:

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git "$HOME/adni-timing-source"
cd "$HOME/adni-timing-source/RS-fMRI"
```

Use a directory that does not already exist, prepare the Python environment using the [installation guide](../../06_docs/installation.md), and repeat the static check there. This leaves the old working directory available for its existing deployments.

## 2. Commands for later imaging execution

### MRIQC and fMRIPrep

```sh
export PREPROC_CONFIG="/ABSOLUTE/PATH/preprocessing.local.yaml"
export ADNI_SUBJECT="ADNI999S9999"
python pipeline/s7b_sessionwise_preprocessing/run.py \
  --config "$PREPROC_CONFIG" run --stage mriqc --subject "$ADNI_SUBJECT"
python pipeline/s7b_sessionwise_preprocessing/run.py \
  --config "$PREPROC_CONFIG" run --stage fmriprep --subject "$ADNI_SUBJECT"
```

These commands **launch real calculations when you execute them**. Run from `RS-fMRI/` in the installed environment, replace the synthetic subject/config examples, and complete the [7.B preparation and intake](../s7b_sessionwise_preprocessing/README.md) first. Each prepared case is selected from the YAML `runs` list. Successful and failed exits write a `timing` object into that attempt's `run.json`, then call `refresh_safely` to update timing reports. A missing completion timestamp stays missing.

### XCP-D

```sh
export XCPD_CONFIG="/ABSOLUTE/PATH/xcpd.local.json"
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config "$XCPD_CONFIG" pilot
```

This is the real first-candidate XCP-D run, not a timing-only command. Follow the [S10 input/publication contract](../s10_xcpd_integrated_qc/README.md): completing standalone 7.B commands alone does not create the published EPI–T1 pair layout needed here. The S10 JSON `root` must be the corresponding shared pair runtime. Keep preprocessing receipts under that root's `runs/<subject>/logs/` so a single report can cover all three stages. Independent, unrelated roots produce independent reports; the collector does not guess how to join them.

S10 saves the container interval after `wait_container` returns, before output validation, and refreshes it again after the final status/finish is saved. A container that has exited while validation is still pending can have a measured duration without being marked fully completed. Export failures warn without changing imaging success/failure or retry decisions.

For a reviewed ongoing XCP-D workload, `watch` is a separate explicit choice:

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline.py \
  --config "$XCPD_CONFIG" watch
```

This starts a persistent XCP-D processing loop when you run it. It is different from the timing-only watcher in section 4. Do not start a second processing owner beside an existing one.

## 3. Exact record locations

Let `R7` mean the resolved `runtime` value in the 7.B YAML, and `R10` mean the `root` value in the S10 JSON. These are external data directories, not the source checkout.

| Stage | Original execution record | Recorded values |
|---|---|---|
| MRIQC | `<R7>/logs/<timestamp>_mriqc_sub-<subject>_ses-<session>/run.json` | `started_at`, `execution_started_at`, `container_ended_at`, `ended_at`, `timing.elapsed_seconds` |
| fMRIPrep | `<R7>/logs/<timestamp>_fmriprep_sub-<subject>_ses-<session>/run.json` | The same fields, for the independent fMRIPrep attempt |
| XCP-D | `<source_pair>/s10/<config_id>/runs/<run_key>/attempt-NNN/execution.json` | `started_at`, `container_started_at`, `container_finished_at`, `container_ended_at`, `finished_at`, `timing.elapsed_seconds` |
| Public imaging example | `<PUBLIC_ROOT>/logs/{mriqc,fmriprep,xcpd}_execution.json` | Start/end timestamps and `timing.elapsed_seconds` |

For standalone 7.B, automatic summary files normally go to `<R7>/timing/`. When `R7` is `<shared-root>/runs/<subject>` **and** `<shared-root>/continuous5/` exists, `refresh_safely` promotes the report root to `<shared-root>`; reports then go to `<shared-root>/timing/`. S10 normally writes `<R10>/timing/`; the public launcher normally writes `<PUBLIC_ROOT>/timing/`. Use the same shared runtime for a combined MRIQC/fMRIPrep/XCP-D total.

| File under `<report-root>/timing/` | Contents |
|---|---|
| `attempts.display.tsv`, `cases.display.tsv` | Human time strings such as `2시간 45분 7초`, separate from numeric integration files |
| `attempts.tsv` | One row per stage attempt: subject/session, stage, status, start/end, `elapsed_seconds`, `elapsed_hours`, `elapsed_hms`, measurement source |
| `cases.tsv`, `cases.json` | Per-subject/published-pair `mriqc_seconds`, `fmriprep_seconds`, `xcpd_seconds`, preprocessing/postprocessing sums and observed wall span |
| `summary.json` | The same aggregate metrics across all observed attempts, plus completeness/missing/running counts and a separate human `display` object |
| `ledger.json` | Attempt identities retained across collection restarts, archive relocation or temporary unmounts |

In `summary.json`, `preprocessing_seconds` means MRIQC + fMRIPrep and `postprocessing_seconds` means XCP-D. `stage_seconds_sum` sums processing intervals, whereas `observed_wall_seconds` is the elapsed span from the earliest observed stage start to the latest recorded finish, including waiting/gaps and validation. Parallel jobs can make those values very different. `known_stage_seconds_sum` remains available when the final sum is incomplete. A running/missing-time attempt keeps `stage_seconds_sum` null, and `wall_time_complete_for_observed_attempts` does not prove that every planned cohort member was run.

After you have chosen to execute the pipeline, inspect the reports without rerunning imaging:

```sh
export ADNI_RUNTIME_ROOT="/ABSOLUTE/PATH/shared-pair-runtime"
cat "$ADNI_RUNTIME_ROOT/timing/summary.json"
head -n 6 "$ADNI_RUNTIME_ROOT/timing/attempts.display.tsv"
head -n 6 "$ADNI_RUNTIME_ROOT/timing/cases.display.tsv"
```

## 4. Optional legacy/backfill collection, only when you choose it

```sh
python pipeline/s7d_processing_timing/run.py --root "$ADNI_RUNTIME_ROOT"
```

This explicitly reads existing execution receipts and writes summary reports. It does not launch imaging. It is unnecessary for normal completion updates from the timing-enabled runners, but can recover reports after an export warning or summarize legacy receipts. Unlike the source-only check in section 1, this command does access the specified runtime.

To observe legacy runners that lack completion hooks, you may start the timing collector in another terminal before future processing:

```sh
python pipeline/s7d_processing_timing/run.py \
  --root "$ADNI_RUNTIME_ROOT" --watch --interval 30
```

That terminal runs a timing-only loop; Ctrl-C ends it. It does not install a system service. Run only one such watcher per report root. Without either completion hooks or an explicitly started collector, legacy runners do not automatically refresh Step 7.D reports.

If archived receipts are no longer reachable through the runtime's relocation aliases:

```sh
export ADNI_ARCHIVE_ROOT="/ABSOLUTE/PATH/completed-pair-archive"
python pipeline/s7d_processing_timing/run.py \
  --root "$ADNI_RUNTIME_ROOT" --archive-root "$ADNI_ARCHIVE_ROOT"
```

Use the same output directory on subsequent collections. `--output-dir` selects another external report directory for this explicit collector; automatic runner hooks continue to use the default report root described above. All identifiers, execution paths and result rows stay outside Git. The collector reads only known execution/metadata locations and does not scan image payloads. It links pairs using published execution identity or exact selected-input hashes within the same subject/session.

## 5. Separate Docker execution observer and display formats

```sh
# Explicit optional Docker observation, when you choose to run it:
python 04_workflow/processing_timing.py --root "$ADNI_RUNTIME_ROOT" watch
```

This explicitly starts the separate Docker event observer when you choose to run it. It is not the Step 7.D receipt collector and is not required for the timing-enabled completion hooks. Both implementations and synthetic tests are included in this repository. They share only `duration_display.format_duration`; measurements, provenance and report locations remain separate. This documentation does not install or start either observer.

| Implementation | Measurement | Combined time and exclusions |
|---|---|---|
| `04_workflow/processing_time.py` (Step 7.D) | Receipt-based stage intervals; overall observed wall span | Preprocessing = MRIQC + fMRIPrep; postprocessing = XCP-D. Wall span includes waiting and validation. Pause/sleep is not subtracted. |
| `04_workflow/processing_timing.py` (separate observer) | Docker start/die or StartedAt/FinishedAt, subtracting the union of observed pause/sleep intervals | Main combined execution time = fMRIPrep + XCP-D; MRIQC is separate. Queue/inter-attempt holds and delayed driver confirmation are excluded from observed container windows. |

Both measurements are elapsed time, not CPU-core time. Keep their implementation, `duration_source` or `recording_mode`, pause/sleep coverage, and success/failure distinctions with their values. Historical reconstructions are estimates with their quality flags. Missing pause/sleep history cannot establish fully observed active processing time. A successful retry may reuse earlier failed-attempt caches, so the last successful attempt alone is not the full processing cost. Never add the two implementations' overlapping attempt totals together.

The separate observer's human/numeric file contract is:

| External file | Schema and intended reader |
|---|---|
| `<root>/continuous5/timing/processing_times.csv` | Human table, explicit Korean units such as `2시간 45분 7초` |
| `<root>/continuous5/timing/processing_times.raw.csv` | Numeric seconds with the previous machine-readable schema/precision |
| `<root>/continuous5/timing/subjects/<subject>.json` | Human `display`, numeric `summary`, attempts and measurement provenance |
| `<published_pair>/results/processing_time.csv` | Human one-row table, created only after S12 owns `results/export_manifest.json` |
| `<published_pair>/results/processing_time.raw.csv` | Numeric one-row counterpart, with the same S12 ownership condition |
| `<published_pair>/results/processing_time.json` | Both display and numeric summary with the original attempt provenance |

Observer display version 1.1.0 rounds human values to the nearest second, keeps hours above 24, and marks missing/incomplete or QC-skipped results explicitly. It preserves precise numeric fields separately. Code reading the old numeric CSV must use `.raw.csv`, not parse the human table. Existing S12 metrics and its export manifest remain unchanged; the observer does not create an unmanaged results directory before S12.

Step 7.D preserves its existing numeric `attempts.tsv`/`cases.tsv` columns and `elapsed_hms` compatibility field. Its new `attempts.display.tsv`/`cases.display.tsv` use the same explicit-unit formatter as the Docker observer; `summary.json` adds a human `display` object and `measurement_scope=receipt_intervals_and_observed_wall_span`. Display tables reuse metric names for human strings and must not be read as numeric seconds. Rounding is only for display; underlying numeric values are unchanged. `timing.elapsed_display` is additive to new runner receipts. This does not convert one time measurement into the other.

The separate observer's host-sleep tracking uses available macOS kernel sleep/wake information. Other hosts or late observer attachment retain explicit incomplete coverage; source inspection cannot validate event delivery or host support.

A subject-level observer aggregate is assigned to a pair only when that subject has exactly one published pair. Multiple visits stay in the subject aggregate without a misleading single-pair sidecar. See the [observer guide](../../06_docs/processing_timing.md) for its managed-runtime contract.

## Reading the totals

- **Stage seconds sum:** all timed attempts, including failed work and retries. MRIQC + fMRIPrep gives preprocessing time; XCP-D gives postprocessing time. A total with an untimed/running attempt is `null`; `known_stage_seconds_sum` separately sums only the measured completed work.
- **Observed wall seconds:** earliest observed start to latest recorded stage finish, including gaps/queue waiting and runner validation. It excludes work before the first recorded stage and work after the latest recorded finish, such as later archival. A running cohort has no final total yet.
- **Active interval union:** elapsed time covered by at least one measured execution interval. It removes overlap; it is not CPU-hours.

For two jobs running in parallel for one hour, the stage sum is two hours and their active union is one hour. First-start to last-finish may be longer if the pipeline waited between stages. `all_three_stages_observed` describes recorded stage coverage, not completion of every expected run or scientific inclusion.

XCP-D prefers Docker `StartedAt`/`FinishedAt` when available. Other durations use recorded runner execution bounds; older XCP-D records with only `finished_at` include output-validation overhead and are labeled accordingly. Collection time and file modification time never substitute for a missing finish. Invalid, negative or timezone-less timestamps remain missing with a diagnostic. Seconds retain subsecond precision; HH:MM:SS is a display value.

Duplicate copied receipts count once. Conflicting copies are flagged and excluded from duration totals. Atomic writes and a report lock protect concurrent completion/collector updates. An export error warns without changing an imaging result; rerunning collection reconstructs reports from the retained receipts.

## Scope and validation

This step supports the repository's 7.B/S10 pair workflow and public imaging launcher. Original Slurm/Apptainer jobs or the separate 7.A profile need equivalent execution receipts before they can be included; their runtime is not inferred from output files. Timing does not alter scientific settings, cache-signature rules, QC thresholds or research inclusion. A modified runner has a new source hash and still requires the reviewed cache/deployment handoff. Preserve active legacy runners until the existing idle-handoff procedure permits replacement.

Synthetic tests cover parallel intervals, timezone conversion, missing timestamps, retries, start/resume identity, archive aliases, read-only source preservation, exact pair linkage, conflicting duplicates and CLI output. Actual timings are operational observations, separate from imaging/scientific validation.
