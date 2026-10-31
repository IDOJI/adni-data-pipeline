# Step 9.B — Final inclusion validation

## Purpose

Combine 3.A source quality, corrected 9.A clinical conditions and explicitly confirmed ST absence for each image/run. Fix **nearest diagnoses within 28 days and source-QC pending preservation**. A clinical pass cannot reintroduce a known problem image. No Selection Table/RDS becomes a required input.

## Input

- `--source-qc`: a 3.A `source_qc_v1` artifact directory.
- `--clinical`: a corrected 9.A `clinical_validation_v2` artifact with sex filling and TEAM exclusion. Only nearest/28-day policy is accepted. Regenerate v1 results rather than editing their manifests.
- `--confirmed-st-absence`: a reviewed CSV/TSV containing explicitly confirmed ST absence. Do not substitute an ordinary missing/unverified-ST table.
- Optional `--conversion-failures`: a reviewed conversion-failure table; its omission is recorded.
- Supply reviewed imaging inclusion rows to 9.A first. For S10, use `final_included_runs.tsv` and `clinical_scan_links.tsv`. If `final_qc_status` is present, preserve `exclude` and `pending_review`; only `include` can proceed. Contradictory or negative `final_include` flags cannot be promoted.

ST input supports either schema below. If no confirmed exclusions exist, explicitly provide an empty file with the required header. **Absence from this ledger does not establish usable ST.**

| Schema | Required fields and conditions |
|---|---|
| Explicit reviewed ledger | `IMAGE_ID,PTID,MRI_STUDY_DATE,ST_STATUS,EVIDENCE_REF`; status `confirmed_absent` and a nonempty evidence reference |
| Native Research audit | `EPI_IMAGE_ID,PTID,MRI_STUDY_DATE`, `final_analysis_status=no_slice_timing_any_source`, `final_slice_timing_class=no_slice_timing`, `full_dicom_recheck=TRUE`, `nfq_usable_st=FALSE`, `st_evidence_class=not_found_anywhere` |

Conversion exclusions require `IMAGE_ID,PTID,MRI_STUDY_DATE,MODALITY,SELECTION_ACTION,ERROR_CLASS,ERROR_REASON`; action must be `exclude_before_date_and_image_selection`. Incomplete confirmation or conflicting identities are not silently ignored.

## Processing

- Verify artifact kinds, hash-covered required outputs and clinical policy.
- Compare Image ID, participant, actual scan date and modality; compare UID when supplied. Preserve original run entities and every audit row.
- Classify source-QC blocks, clinical failures, confirmed ST absence and optional conversion failures as `excluded`.
- Hold missing/conflicting identities and pending imaging reviews. Preserve source-QC `pending` when no exclusion or hold applies.
- Classify the remaining QC/clinical passes as `eligible`. Missing sex, education or APOE alone does not exclude a run.

## Output

| File | Content |
|---|---|
| `inclusion_audit.tsv` | Every input run, decision, reasons and original clinical/imaging-QC columns |
| `retained_sessions.tsv` | Both `eligible` and `pending` rows |
| `pending_qc.tsv` | Retained candidates with unverified source quality |
| `excluded_sessions.tsv` | Runs failing known inclusion conditions |
| `held_sessions.tsv` | Identity conflicts or pending imaging review |
| `confirmed_exclusion_evidence.tsv` | Raw ST/conversion evidence and source rows |
| `artifact.json` | Input/output/code hashes, policy and counts |

`INCLUDED_BY_METADATA_POLICY` denotes retention under this step's scope. Keep `ANALYSIS_READY=False` for every result. This step does not establish physical BIDS/DICOM/JSON correspondence, T1 pairing, headers, coverage, motion or visual QC. When imaging-QC columns are absent, explicitly record that a reviewed input remains a precondition.

## Execution

Run from `RS-fMRI/`; write only to a new external output directory.

```sh
python 02_custom/s9b_validate_inclusion/run.py \
  --source-qc /ABSOLUTE/PATH/ADNI_DATA/qc/step3a \
  --clinical /ABSOLUTE/PATH/ADNI_DATA/qc/step9a \
  --confirmed-st-absence /ABSOLUTE/PATH/ADNI_DATA/qc/confirmed-st-absence.csv \
  --conversion-failures /ABSOLUTE/PATH/ADNI_DATA/qc/confirmed-conversion-failures.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9b
```

## Validation

Synthetic tests cover pending preservation, QC/clinical/ST/conversion exclusions, identity conflicts, old or modified artifacts, changed policies, S10 imaging decisions, empty subsets, CLI execution and overwrite protection. Public actual-data documentation contains aggregate counts only; participant-level results remain in external local storage.

## Dependencies

Python 3.11+ standard library and this repository's `02_custom/_shared.py`, with actual 3.A and corrected 9.A artifacts.
