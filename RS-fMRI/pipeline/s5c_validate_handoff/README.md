# Step 5.C — Handoff from upstream Step 5 to Steps 6/7

## Execution

```sh
python pipeline/s5c_validate_handoff/run.py \
  --input /ABSOLUTE/PATH/ADNI_DATA/qc/step5/final_heuristics.tsv \
  --source-qc /ABSOLUTE/PATH/ADNI_DATA/qc/step3a \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step5c
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Validates the sessions already retained by Step 5, checks the supplied 3.A evidence, and writes the CSV/TSV inputs expected by Steps 6 and 7.

**Results:** `mriqc_subjects.csv`, `post_clinica.csv`, `mriqc_sessions.csv`, `valid_sessions.tsv` and `handoff.json`; blocked/pending cases remain audited.

After checking the handoff, generate a new external configuration with `lab.py prepare-config --handoff /ABSOLUTE/PATH/ADNI_DATA/qc/step5c`. Pass its `mriqc_sessions.csv` to upstream Step 7 with `--sessions-csv`. Omitting `--source-qc` selects the separately documented format-only mode.

## Purpose

Upstream writes Step 5 results as TSV, while the Step 6 launcher reads comma-delimited CSV. This step validates and passes on **sessions already retained upstream**. It does not use a historical Research Selection Table or perform new clinical selection.

## Input

- Upstream `final_heuristics.tsv`, requiring `Subject_ID` and `VISCODE`.
- If `NIfTI_exists`, `JSON_exists` or `T1w_exists` are present, each must be true.
- Normalize `bl`, `mNN`, `MNNN` and `ses-MNNN` to Clinica session labels. Do not infer visit codes from screening labels or calendar dates.

## Processing

Validate the entire input first and reject duplicate normalized sessions, invalid IDs, empty inputs and contradictory existence flags. Do not arbitrarily drop sessions or choose a representative run. Multiple runs in a session require an explicit extension.

## Output

| File | Role |
|---|---|
| `mriqc_subjects.csv` | One comma-delimited row per participant for Step 6 |
| `post_clinica.csv` | `Subject_ID,sessions` for Step 7, with space-delimited `M000 M012` |
| `mriqc_sessions.csv` | `Subject_ID,VISCODE` for Step 7 `--sessions-csv` |
| `valid_sessions.tsv` | Retained BIDS `sub,ses` pairs for comparison |
| `handoff.json` | Input/output hashes, scope and unresolved research inclusion status |

**The upstream MRIQC launcher does not pass a session filter.** Other BIDS sessions for a participant may be processed. Check the population used to fit group IQMs separately; this conversion alone does not restrict sessions.

## Validation

Tests verify unchanged source hashes, one-to-one participant/session preservation, round-trip agreement with the upstream Step 7 CSV parser and refusal to overwrite existing results. Completion means format validation, not a new quality pass.

## Dependencies

Python 3.11+ standard library. This step itself does not read MRI images, RDS files or private configuration.


## Applying evidence from Step 3.A

Pass the artifact with `--source-qc /external/qc/step3a` to verify input/output hashes and `Image_ID + Subject_ID + Scan_Date`; supplied UIDs must also match. Exclude failed, conflicting, deleted or identity-unverified sessions from downstream lists and record every decision in `source_qc_audit.tsv`. This gate does not validate the T1 reference image.

Retain `pending` sessions as preprocessing candidates without treating them as research-quality passes. Use `--require-confirmed-qc` to process only confirmed source QC. If all sessions are blocked, preserve the audit files, record `no_surviving_sessions` and return CLI exit code 2. `prepare-config` also rejects that result.

Without 3.A, the existing format-validation mode remains available. `source_qc_audit.tsv`, source-artifact hashes and excluded/pending counts identify whether the gate was applied. Clinical validation is performed separately in 9.A.

## macOS and Linux

Use the same Python CLI and delimiter/session contracts on both hosts. Rebuild path-bearing receipts for the new host. Upstream MRIQC is still subject-scoped; OS choice does not add a missing session filter.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s5c) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
