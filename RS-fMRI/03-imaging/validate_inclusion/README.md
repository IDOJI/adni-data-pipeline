# Stage 9.B — Eligibility summary

**What:** Combine source QC, clinical validation and confirmed slice-timing/conversion exclusions.

**Output:** `inclusion_audit.tsv`, `retained_sessions.tsv`, `pending_qc.tsv`, `held_sessions.tsv` and `excluded_sessions.tsv`.

## Run

From `RS-fMRI/`, after [setup](../../support/docs/installation.md). `--source-qc` and `--clinical` take the artifact directories from Steps 3.A and 9.A. `--confirmed-st-absence` takes reviewed source-image evidence. If you have a reviewed conversion-failures file, add `--conversion-failures` with its path to the command.

```sh
python 03-imaging/validate_inclusion/run.py \
  --source-qc "$RESULTS/qc/step3a" --clinical "$RESULTS/qc/step9a" \
  --confirmed-st-absence "$DATA/review/confirmed-st-absence.csv" \
  --output-dir "$RESULTS/qc/step9b"
```

`--conversion-failures` is optional. Use reviewed exclusion records; absence of a sidecar alone is not confirmed slice-timing failure. Pending imaging/source review remains pending.

## Evidence and limits

Sources: [ADNI imaging–diagnosis answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2401); [ADNI diagnosis-code answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=1756); [Rutherford et al. (2026)](https://doi.org/10.21203/rs.3.rs-11132707/v1). The [Stage 9.B evidence record](../../support/docs/stage_evidence.md#stage-9-b) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.

Image IDs use the same numeric LONI identifier rule as Step 3.B. One optional I/i prefix and leading zeros are normalized. Malformed or conflicting IDs and reuse across runs are reported for review.
