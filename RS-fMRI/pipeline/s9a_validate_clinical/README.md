# Step 9.A — Clinical linkage validation

## Execution

```sh
python pipeline/s9a_validate_clinical/run.py \
  --included /ABSOLUTE/PATH/ADNI_DATA/qc/final/included_reviewed_sessions.tsv \
  --scan-links /ABSOLUTE/PATH/ADNI_DATA/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv \
  --dxsum /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DXSUM.csv \
  --ptdemog /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/PTDEMOG.csv \
  --max-dx-days 28 --dx-direction nearest \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9a
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Links reviewed imaging runs to source clinical rows using actual scan dates and nearest diagnoses within 28 days, retaining ties and demographic evidence.

**Results:** `clinical_validation.tsv`, clinical-pass rows, source-row audits and a hash-bound artifact in the selected output directory.

When APOE/ADSL/DM is not supplied, retain the corresponding unvalidated status. Do not force a single scan date, latest visit, AD-only cohort or complete-case cohort.

Regenerate v1 results instead of editing their manifest. Pass the new v2 artifact to [9.B](../s9b_validate_inclusion/README.md) to combine source QC, clinical conditions and confirmed ST absence. Default nearest/28-day matching is unchanged.

## Purpose

Apply Research's actual-date, diagnostic-tie and raw-evidence preservation rules after the upstream workflow. Preserve Step 8 inclusion rows at run level; do not directly adopt upstream Step 9's label/timing assumptions as analysis diagnoses.

## Input

- `--included`: Step 8 TSV/CSV requiring `sub,ses`; preserve actual BIDS identity columns such as `task,run,acq,echo,dir,rec`.
- `--scan-links`: an fMRI conversion mastersheet or explicit CSV connecting participants/sessions to actual `Image_ID,Scan_Date`. Supports `Subject_ID,VISCODE` or `sub,ses`. Only `bl/mNN` is normalized to Clinica `ses-MNNN`; dates are not inferred from visit codes.
- Multiple runs in a session require exact per-run Image ID mappings. Multiple date/phase/image candidates or reuse of the same ID across runs cause a hold, never automatic first-row selection.
- Supports native `dicom_SeriesInstanceUID` and `SERIES_UID/SeriesInstanceUID`. Different UIDs for one image or conflicts between UID columns also cause a hold.
- `--dxsum`: `PTID` or `RID`, `PHASE,EXAMDATE,DIAGNOSIS`, optional `HAS_QC_ERROR,DXMDUE,DXDDUE`.
- `--ptdemog`: `PTID` or `RID`, `VISDATE`, optional `PHASE,PTGENDER,PTEDUCAT,PTHAND,PTETHCAT,PTRACCAT,PTDOB`. Sex filling uses raw `PHASE,PTGENDER`, not supplied `*_FILLED` values.
- Optional `--apoe`: `PTID/RID,GENOTYPE`; `--adsl`,`--dm`: numeric `SUBJID` or RID and `SEX` (Male/Female or M/F). RDS inputs are unsupported; explicitly export CSV files.

## Processing

- Once the actual scan date is uniquely verified, link **all** nearest eligible DXSUM rows. Hold conflicting diagnoses; allow reuse of one clinical evaluation for multiple images.
- `--max-dx-days 28` is Research's initial policy and can be changed per study. `--dx-direction past` allows only assessments on or before the scan. Record gaps, signed differences, future visits and phase mismatch.
- `1=CN`, `2=MCI`, `3=Dementia`; add suspected AD/other clinical etiology only with consistent `DXMDUE/DXDDUE` evidence. Do not apply later-phase etiology mapping to ADNI1 dementia or infer biological AD.
- Preserve all nearest PTDEMOG ties. Missing/conflicting education, handedness, race, ethnicity, sex or APOE remains unresolved and does not alone exclude a run.
- Exclude `PHASE=TEAM`, QC errors and invalid dates from nearest matching and sex evidence. Fill structurally missing nearest `PTGENDER` only when eligible participant visits provide one consistent known value; preserve education and raw values.
- Keep legacy ADNI1/GO/2/3 gender and ADNI4 sex assigned at birth in separate scopes. Never borrow across scopes or resolve conflicting values automatically. Without PHASE, retain raw evidence but do not fill. Record auxiliary-source disagreements as unresolved.
- Record scan-link Age as a separate source and compare it with month-based PTDOB approximate age and birth-information conflicts. Do not reproduce first-PTDOB selection from historical RDS snapshots.

## Output

`clinical_validation.tsv`: every input run with pass/hold and reasons. `clinically_validated_sessions.tsv`: the subset passing clinical linkage conditions. `clinical_source_rows.tsv`: all linked raw rows and additional participant-level sex evidence with source row numbers and JSON. `clinical_source_eligibility.tsv`: reasons for ignoring TEAM, QC-error rows or invalid dates/diagnoses. `sex_derivation.tsv`: raw values, phase scope, filling method and source rows. `artifact.json`: input/output/code hashes, policy and kind `clinical_validation_v2`.

Keep `ANALYSIS_READY=False` for every result. **A clinical pass does not establish MRI quality, physical-file validity or visual-QC approval.** Use this subset together with upstream and Custom QC decisions when forming research inclusion tables.

## Validation

Synthetic runs cover diagnostic/date ties, conflicting diagnoses, outdated assessments, past-only matching, source QC errors, clinical-visit reuse, multi-run/image identity, PTID/RID conflicts, missing education/APOE, sex conflicts, unchanged inputs and overwrite refusal.

## Dependencies

Python 3.11+ standard library. Official diagnosis definitions: [ADNI DXSUM](https://adni.loni.usc.edu/quick-start-guide-asset/diagnostic.html). Selected clinical rules from Research's `2026-10-30-preserve-all-v1` were adapted to explicit CSV/run inputs; full numerical equivalence with the original RDS/R module is not claimed.

## macOS and Linux

Run the same Python CLI and nearest/28-day, tie and demographics rules on both hosts. Set authorized clinical input paths locally and generate new output evidence. A Linux run does not alter clinical eligibility or fill missing source values.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s9a) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
