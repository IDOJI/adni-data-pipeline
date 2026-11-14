# Stage 9.B — Eligibility summary

**What:** Combine source QC, clinical validation and confirmed slice-timing/conversion exclusions.

**Output:** `inclusion_audit.tsv`, `retained_sessions.tsv`, `pending_qc.tsv`, `held_sessions.tsv` and `excluded_sessions.tsv`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python pipeline/s9b_validate_inclusion/run.py \
  --source-qc "$DATA/qc/step3a" --clinical "$DATA/qc/step9a" \
  --confirmed-st-absence /ABS/confirmed-st-absence.csv \
  --conversion-failures /ABS/confirmed-conversion-failures.csv \
  --output-dir "$DATA/qc/step9b"
```

`--conversion-failures` is optional. Use reviewed exclusion records; absence of a sidecar alone is not confirmed slice-timing failure. Pending imaging/source review remains pending.
