# Stage 5.C — Processing input lists

**What:** Validate retained Step-5 sessions against source-QC evidence and create processing lists.

**Output:** `mriqc_subjects.csv`, `post_clinica.csv`, `mriqc_sessions.csv`, `valid_sessions.tsv` and `handoff.json`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python pipeline/s5c_validate_handoff/run.py \
  --input "$DATA/qc/step5/final_heuristics.tsv" \
  --source-qc "$DATA/qc/step3a" \
  --output-dir "$DATA/qc/step5c"
```

Use a new output directory. Blocked/pending cases remain audited. For the cluster fMRIPrep launcher, pass `mriqc_sessions.csv` via `--sessions-csv`; the original cluster MRIQC launcher is subject-scoped.
