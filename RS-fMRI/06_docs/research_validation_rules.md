# Mapping Research rules to Custom Steps

The current baseline is Research's `2026-10-30-preserve-all-v1`. Publish processing rules and source-code hashes only; do not copy original data, RDS files, real participant examples or private paths into the public repository.

| Research rule | Implementation | Current behavior |
|---|---|---|
| Source QC, deletion and decision conflicts | 3.A | Compare source Image ID/date/PTID/UID and audit blocked states |
| Missing GO/2 IDs and NFQ matching | 3.A | Use unique composite identities only; never bypass explicit ID conflicts |
| Separate NFQ quality from ST availability | 3.A | Check failure even with empty ST; ST does not substitute for QC approval |
| Preserve unverified quality | 3.A/5.C | Mark pending separately; retain preprocessing candidates by default, with optional strict mode |
| Prevent known problem images from reentering | 5.C → 6/7/8 | Connect source-QC survivors to configuration/session filters and final valid-sessions |
| Link actual MRI scan dates | 9.A | Hold multiple date/image/phase candidates; never select dates by row order |
| DXSUM date gaps and ties | 9.A | Default 28-day window, nearest/past options and preservation of all nearest raw rows |
| Distinguish Dementia from clinical etiology | 9.A | Code 3 means Dementia; label suspected etiology only for consistent cause codes |
| PTDEMOG, APOE and sex | 9.A v2 | Exclude TEAM, fill missing sex from consistent eligible same-scope visits with raw provenance; no complete-case exclusion |
| Final inclusion conditions | 9.B | Combine QC/clinical/confirmed ST and optional conversion evidence; nearest 28 days and pending preservation |
| Preserve multiple visits and runs | 9.A | One result per input run, exact image/run correspondence and clinical-assessment reuse |
| Compare Search Age and PTDOB | 9.A | Compare explicit scan-link Age with month-based approximate age; flag birth-information conflicts |

## Items requiring separate validation

- Actual BIDS/DICOM/UID file correspondence, NIfTI headers/hashes and SliceTiming axis/direction require physical validation. A 3.A metadata pass does not establish these.
- Actual T1 reference selection, multiple-T1 combinations and cross-date T1 pairing are not resolved by the 5.C source-BOLD gate.
- Step 9.B consumes explicitly supplied confirmed ST/conversion exclusions without embedding private image IDs or discovering historical Selection Tables. QC1 sequence-description exclusions and historical PTDOB snapshots remain separate validation work.
- Upstream Step 6 participant-level execution, IQM fitting-population restrictions, upstream s8 missing-value/input-delimiter handling and complete cognitive-score merging are separate tasks.
- `clinical pass` and `source QC pass` describe only their respective checks. Do not promote `ANALYSIS_READY=False` results to completed scientific eligibility.

## Evidence

- [ADNI Mayo MRI QC](https://adni.loni.usc.edu/data-samples/adni-data/neuroimaging/mri/mri-quality-control/): grades 1–3 accepted, grade 4 failed.
- [ADNI diagnosis definitions](https://adni.loni.usc.edu/quick-start-guide-asset/diagnostic.html): DIAGNOSIS 3 means Dementia.
- Research code sources and versions are recorded in `03_config/imported_sources.json`. Source CSV paths, input/output hashes and actual raw rows are stored only in external per-run artifacts.
