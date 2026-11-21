# Stage 5.C — Processing input lists

**What:** Validate retained Step-5 sessions against source-QC evidence and create processing lists.

**Output:** `mriqc_subjects.csv`, `post_clinica.csv`, `mriqc_sessions.csv`, `valid_sessions.tsv` and `handoff.json`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). `--input` takes the Step 5 heuristics TSV. `--source-qc` takes the whole Step 3.A artifact directory, including its audit and fingerprints. Write to a new `--output-dir` and check the surviving session count in `handoff.json`.

```sh
python pipeline/s5c_validate_handoff/run.py \
  --input "$RESULTS/qc/step5/final_heuristics.tsv" \
  --source-qc "$RESULTS/qc/step3a" \
  --output-dir "$RESULTS/qc/step5c"
```

Use a new output directory. Blocked/pending cases remain audited. For the cluster fMRIPrep launcher, pass `mriqc_sessions.csv` via `--sessions-csv`; the original cluster MRIQC launcher is subject-scoped.
