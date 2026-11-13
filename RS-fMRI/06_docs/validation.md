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
python -m pytest -q pipeline/utils/tests
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

## 2026-11-01 Live automation handoff

Local verification: **234 passed, 17 subtests passed**, including eight live-service compatibility tests. These cover legacy/new runner dispatch, the shared five-subject limit, full surface/CIFTI command settings, independently captured container exit receipts, scientific-configuration identity and active-attempt ownership.

The three existing preprocessing, XCP-D and offload services were connected to this repository. All five calculations active at cutover retained their container IDs and start times. Completed-result manifests, scientific configuration and admission settings were unchanged. The replacement services remained running without stderr errors, and the operational automation registry passed validation.

With the actual private template, old and integrated MRIQC/fMRIPrep command arguments and work directories matched exactly. Read-only dispatch verification selected the integrated 7.B adapter for the next previously unstarted subject. No additional imaging calculation was forced while all five shared slots were occupied. Previously started subjects retain their original runner/cache until completion, and the active XCP-D attempt retains its verified completion observer. This verifies continuity and future dispatch; it does not establish completion or scientific inclusion of the active calculations.

See [live_service_handoff.md](live_service_handoff.md) for the deployment boundary and preservation checks. Participant-specific operational evidence remains outside the public repository.
## 2026-11-01 Atlas library and BOLD extraction

Local verification: **262 passed, 17 subtests passed**. A new clone independently installed CBIG/TemplateFlow and verified all 54 cached payloads.

Step 11 registers 252 discrete-label file variants: 141 Neuroparc, 60 original CBIG Schaefer and 51 TemplateFlow atlases. All four source repositories are pinned; both TemplateFlow template datasets are also fixed, and 54 two-mm payloads are materialized locally with pinned annex digests and SHA-256 verification. Three reference segmentations are excluded from the atlas catalog. Nilearn is a source reference, not a claim that all its fetched datasets were cloned.

Synthetic tests verify means, agreement with the installed Nilearn masker, space/grid distinctions, label preservation, mask/reference-volume ROI coverage, missing/nonfinite/constant signals, temporal masks/TR, hashes, memory caps, 9.B inclusion and CLI status. Real public CBIG and TemplateFlow Schaefer-100 geometries and Neuroparc AAL were tested with known synthetic signals: 100/100/116 ROI means agreed within 3.1e-7. This is not actual ADNI signal extraction. Source-space ambiguity and source ROI-count discrepancies remain explicit rather than being silently corrected.

## Atlas acquisition-frame and actual BIDS run adapters

Synthetic regression checks cover compressed XCP-D frame gaps, explicit dummy counts, outlier run/Sources identity, raw/derivative TR, UID/date conflicts, ambiguous Sources, excluded/held images, pending preservation, stale payload maps and descriptive coverage diagnostics without QC rescue. Actual validation uses two existing ADNI3/ADNI4 XCP-D visits outside the public repository. Raw UID/date and the declared BIDS Sources chain connect each actual run to its original 9.B row; the source states remain eligible and pending. The original 400 ROI columns and all time-series values are preserved, with low-coverage counts of 2 and 11 still failing the unchanged 0.5 criterion. Original acquisition gaps are recorded without an additional censor operation. Descriptive anatomical/reference comparisons do not establish a unique biological or processing cause and do not certify physical registration. Private artifacts and real participant identities are not distributed here.


## Integrated source distribution, 2026-11-06

The core gitlink is replaced by 76 ordinary source/attribution files. Doctor checks parent-tracked bytes/modes, licensing and preserved origin/history; it no longer needs an original checkout. Reviewed source edits are accepted independently of the original baseline. See [source integration](source_integration.md) for import exclusions and full local Git-history preservation. Earlier submodule counts above describe the historical distribution.

The migration suite also executes the original utility tests with the selected environment on PATH. The one test that reads the original real-cohort `sample_size_stages.tsv` is explicitly deselected because that output is not redistributed; a new repository test exercises the renderer with an external synthetic manifest. The existing upstream package-layout skip remains documented. Source-only notebook copies are checked for empty outputs and preserved source metadata.

Local migration verification: **335 passed, 17 subtests passed** in the extension suite; original utilities: **59 passed, 1 existing package-layout skip, 1 real-result-manifest test deselected**. A separate ordinary clone passes doctor with all 76 core files and no nested Git metadata or initialized submodules. All imported core bytes/modes match the original baseline. The 153-commit local history bundle was independently restored and passed Git object verification. These are source/compatibility checks; active imaging jobs were not rerun by this migration.

## Processing-time sidecars, 2026-11-06

Local verification: **351 passed, 17 subtests passed**. Sixteen timing tests cover elapsed-time arithmetic, parallel interval unions, timezone conversion, missing/negative timestamps, retries and failure costs, stable prepared/running attempt identity, archive alias deduplication, exact input/published pair linkage, conflicting duplicates, source-receipt preservation and the CLI. The five processing command/cache builder functions remain unchanged. Timing is an operational report; it does not change QC or establish scientific inclusion. See [Step 7.D](../pipeline/s7d_processing_timing/README.md).

## Two timing contracts and shared presentation, 2026-11-07

Local verification: **385 passed, 17 subtests passed**. Timing-specific synthetic checks: **50 passed**, including the imported observer tests and cross-contract checks. Fake clocks/containers verify the difference between receipt wall intervals and pause/sleep-adjusted Docker execution windows, failure/retry cost, raw numeric precision, explicit display units, S12 ownership and ambiguous-pair non-publication. Source AST checks preserve five receipt numeric functions, eight observer numeric/event functions and the extracted formatter logic.

A separate checkout was used. Live-tool execution was blocked during local tests; no imaging calculation, operational reconciliation or service installation/start was performed. These checks do not establish real event delivery or host sleep tracking. Original working files and uncommitted work are outside the integration checkout. See [Step 7.D](../pipeline/s7d_processing_timing/README.md) and the [Docker observer guide](processing_timing.md).
