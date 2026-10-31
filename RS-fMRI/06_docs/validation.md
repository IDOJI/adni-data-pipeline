# Initial implementation validation — 2026-10-31

## Completed scope

- Wrapper tests: **20 passed**. Covers upstream Step-5 TSV normalization, duplicates, missing fields, existence flags, empty lists, output paths, upstream Step-7 parser round-trips and an actual upstream Step-6 launcher dry-run.
- Pinned upstream `utils/tests`: **60 passed, 1 skipped**, run separately from wrapper tests. The skip reflects an upstream environment condition and is not counted as completed wrapper validation.
- Motion checks: synthetic 4D NIfTI/JSON/confounds test the 300-second/30% boundaries, initial-frame sensitivity, missing FD, TR consistency, hashes, original frame indices and overwrite protection.
- Submodule: gitlink, lock and actual HEAD agree; upstream checkout is clean.
- Configuration: external paths generated; upstream configuration unchanged; placeholders/in-repository outputs rejected; changed Step-5.C output hashes block configuration generation.

## Test environment

Python 3.11.16 / NumPy 2.4.6 / pandas 3.1.0 / NiBabel 5.4.2 / PyYAML 6.0.3 / pytest 9.2.0. PATH was configured so the upstream shell's `python` used the same environment.

Initially, pytest collected submodule tests automatically, and the shell used another Python without PyYAML. Wrapper discovery was restricted to `05_tests/`, and upstream tests were rerun separately with the correct PATH to obtain the results above.

```sh
# After activating the RS-fMRI virtual environment
python -m pytest -q
python -m pytest -q 01_upstream/ADNI_fMRI_protocol/utils/tests
python 04_workflow/lab.py doctor
```

## Scope not completed

At initial implementation, this repository had not performed actual ADNI downloads, DICOM conversion, full-cohort MRIQC/fMRIPrep, MRIQC fitting-population/visual QC, clinical mapping extensions, SNP processing or complete Mac-adapter validation. The Step-6 dry-run used synthetic directories/CSVs; it did not run containers or process images.

GitHub Actions is configured for synthetic validation on Python 3.11/3.12. Verify remote CI outcomes separately from local test results.


## 2026-11-01 numbered-layout validation

Paths were standardized as `01_upstream`, `02_custom`, `03_config`, `04_workflow`, `05_tests` and `06_docs`. Wrapper tests reported **23 passed**, covering paths, document links, CI/pytest configuration, private-config exclusions and imported-code hashes. The pinned upstream commit is unchanged; upstream `config/`/`utils/tests` and external ADNI_DATA `config/` retain their original names.


## 2026-11-01 Research QC and clinical validation

Implemented source Study Files QC/NFQ audit 3.A, the selected-BOLD source gate in 5.C and run-level actual-date/clinical validation 9.A. Wrapper tests reported **57 passed**, covering the actual upstream Step-6 dry-run/Step-7 parser, native CLIs, source hashes, failure blocking, pending preservation, ties, repeated visits, demographic missingness and identity conflicts.

These results validate upstream input contracts with synthetic CSV/NIfTI fixtures. They are not results of processing all Research CSV/RDS sources or actual images in the new repository. Source-QC and clinical passes do not establish complete research inclusion. See `research_validation_rules.md` for ported and unported scope.

## 2026-11-01 XCP-D consolidation

Ported 7.A Docker volume execution/audit/metadata repair/image QA and S10 S8 collection, 36P/LINC XCP-D, ROI/FC/coverage, integrated imaging QC and validated external archiving. Wrapper tests reported **193 passed, 17 subtests passed**. Original tests were adapted to synthetic participants/external configuration, with additional checks for explicit configuration, pinned upstream, external runtime protection, distinct profiles and the 9.A handoff.

Container reconnection/failure recovery and external-volume disconnection/corruption/interrupted recovery were tested with synthetic files and mocked subprocesses. Actual Docker imaging calculations or external archiving were not rerun during this consolidation. Evidence for the active SB pilot and historical two-visit volume pilot remains in their private runtimes/local archive. Code tests do not establish completion of active workers.

The upstream submodule commit remains pinned. Input-contract differences between 7.A (no FreeSurfer) and S10 (Euler required) are documented. Actual Linux/Slurm/CIFTI processing, flat-derivative-to-pair adapters and automated research-inclusion intersections across source QC/8.A/clinical conditions remain unvalidated or unimplemented.

## 2026-11-01 Sex filling, TEAM exclusion and Step 9.B

Local verification: **226 passed, 17 subtests passed**. Coverage includes raw-row sex filling, TEAM exclusion, artifact-version/hash enforcement, nearest/28-day policy, pending preservation, explicit ST evidence, identity conflicts and S10 decision preservation.

Step 9.A v2 fills missing sex only from consistent eligible same-scope raw visits, excludes TEAM and records source rows. Step 9.B verifies 3.A/9.A artifacts and combines source QC, clinical conditions and confirmed ST/optional conversion exclusions. It fixes nearest/28-day matching, retains source-QC pending and preserves S10 exclusions, review holds and identity conflicts.

Actual Research sources were rerun through 3.A → 9.A → 9.B. Among 16,638 candidate images, 9,582 were eligible, 2,068 pending and 4,988 excluded. The retained 11,650 images (including 2,239 EPI) exactly reproduced the Research retained image set. All 119 additional unresolved-sex images were reconciled; the original one unresolved image remained. All 33 TEAM rows were excluded. Reasons cover 254 source-QC blocks, 4,804 clinical failures, five confirmed ST-absence images and seven conversion failures; these categories overlap and must not be summed.

The actual-data input used explicit per-image metadata-audit labels, not a BIDS inclusion table approved by physical/visual QC. Every result remains ANALYSIS_READY=False. Participant-level outputs and private source paths stay outside this public repository.
