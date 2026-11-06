# Processing times: MRIQC, fMRIPrep and XCP-D

```sh
: "${ADNI_RUNTIME_ROOT:?Set the existing external pipeline runtime directory}"
python 02_custom/s7d_processing_timing/run.py --root "$ADNI_RUNTIME_ROOT"
cat "$ADNI_RUNTIME_ROOT/timing/summary.json"
```

This records each attempt's start, finish and elapsed wall-clock time, then reports preprocessing (MRIQC + fMRIPrep), postprocessing (XCP-D) and overall observed elapsed time. It backfills existing execution receipts and writes only separate timing reports. No calculation, retry, admission or QC decision is launched or changed.

## Keep the report current

```sh
python 02_custom/s7d_processing_timing/run.py \
  --root "$ADNI_RUNTIME_ROOT" --watch --interval 30
```

Run one watcher per reporting root, or schedule the one-shot command every 30 seconds with the host's service manager. New 7.B and S10 runners also store a `timing` object in their own completion receipts and refresh sidecar reports after completion/failure. The public imaging launcher records the same timestamps. A collector can observe already running legacy workers without replacing their deployment-bound source or rewriting their receipts.

For an archive that is not reachable through the runtime's relocation aliases:

```sh
: "${ADNI_ARCHIVE_ROOT:?Set the existing external completed-pair archive}"
python 02_custom/s7d_processing_timing/run.py \
  --root "$ADNI_RUNTIME_ROOT" --archive-root "$ADNI_ARCHIVE_ROOT"
```

Use the same output directory on subsequent scans. `--output-dir` can select another external report directory. All identifiers, execution paths and result rows remain outside Git.

## Output

| File under `<runtime>/timing/` | Contents |
|---|---|
| `attempts.tsv` | One row per MRIQC/fMRIPrep/XCP-D attempt: status, start/end, seconds, hours, HH:MM:SS and measurement source |
| `cases.tsv`, `cases.json` | Totals per subject/published EPI–T1 pair; unlinked records stay in an explicit session group |
| `summary.json` | Aggregate stage times, known completed work, overall observed wall span, overlapping-work union, pending/missing counts and diagnostics |
| `ledger.json` | Idempotent attempt ledger retained across restarts, relocation or temporary unmounts |

The collector reads only known receipt/metadata locations: `runs/*/logs/*/run.json`, completed-pair `s10/*/runs/*/attempt-*/execution.json`, archived `_runtime/logs/` and public-demo `logs/*_execution.json`. It does not scan image payloads. Pair linkage uses the published execution identity or matching exact selected-input hashes within the same subject/session; an ambiguous visit is not assigned from a participant name alone.

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
