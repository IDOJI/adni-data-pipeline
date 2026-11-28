# Stage 5.C — Processing input lists

**What:** Validate retained Step-5 sessions against source-QC evidence and create processing lists.

**Output:** `mriqc_subjects.csv`, `post_clinica.csv`, `mriqc_sessions.csv`, `valid_sessions.tsv` and `handoff.json`.

## Run

From `RS-fMRI/`, after [setup](../../docs/installation.md). `--input` takes the Step 5 heuristics TSV. `--source-qc` takes the whole Step 3.A artifact directory, including its audit and fingerprints. Write to a new `--output-dir` and check the surviving session count in `handoff.json`.

```sh
python pipeline/s5c_validate_handoff/run.py \
  --input "$RESULTS/qc/step5/final_heuristics.tsv" \
  --source-qc "$RESULTS/qc/step3a" \
  --output-dir "$RESULTS/qc/step5c"
```

Use a new output directory. Blocked/pending cases remain audited. For the cluster fMRIPrep launcher, pass `mriqc_sessions.csv` via `--sessions-csv`; the original cluster MRIQC launcher is subject-scoped.

This stage validates selected BOLD at session scope. It does not identify or approve the T1 supplied to fMRIPrep. For new date-based selections, use [3.B](../../01-selection/image_selection/README.md) and then the [5.D guarded route](../bids_identity/README.md). A matching VISCODE/session label may span multiple scan dates and is insufficient for T1 authorization. Legacy cluster commands require separately reviewed exact image inputs.

## Evidence and limits

Sources: [ADNI VISCODE answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2126); [ADNI EPI–T1 pairing answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=434). The [Stage 5.C evidence record](../../docs/stage_evidence.md#stage-5-c) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
