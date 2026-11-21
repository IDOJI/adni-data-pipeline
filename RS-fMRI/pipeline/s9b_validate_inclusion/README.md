# Stage 9.B — Eligibility summary

**What:** Combine source QC, clinical validation and confirmed slice-timing/conversion exclusions.

**Output:** `inclusion_audit.tsv`, `retained_sessions.tsv`, `pending_qc.tsv`, `held_sessions.tsv` and `excluded_sessions.tsv`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). `--source-qc` and `--clinical` take the artifact directories from Steps 3.A and 9.A. `--confirmed-st-absence` takes reviewed source-image evidence. If you have a reviewed conversion-failures file, add `--conversion-failures` with its path to the command.

```sh
python pipeline/s9b_validate_inclusion/run.py \
  --source-qc "$RESULTS/qc/step3a" --clinical "$RESULTS/qc/step9a" \
  --confirmed-st-absence "$DATA/review/confirmed-st-absence.csv" \
  --output-dir "$RESULTS/qc/step9b"
```

`--conversion-failures` is optional. Use reviewed exclusion records; absence of a sidecar alone is not confirmed slice-timing failure. Pending imaging/source review remains pending.
