# Versions and validation scope

| Component | Initial pin or baseline | Status |
|---|---|---|
| Original protocol baseline | `e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3` | 76 files imported byte-identically as ordinary source on 2026-11-06; original 153-commit history indexed and bundled separately |
| Wrapper | 0.5.0, 2026-11-01 | Source QC, sex filling/TEAM exclusion, 9.B inclusion validation, configuration handoff and tests |
| Motion-duration | Existing local_mac checker | Initially imported byte-identically; source hash recorded separately |
| Example MRIQC | 24.0.2 | Actual installation, execution and digest require environment-specific verification |
| Example fMRIPrep | 25.2.7 | Actual installation, execution and digest require environment-specific verification |
| Full cohort | Not executed | Scientific inclusion/exclusion decisions remain incomplete |

The upstream commit's example environment differs from the wrapper test environment. Read the upstream lock together with `06_docs/validation.md`. The historical fMRIPrep→XCP-D project's 240-second rule is not the setting for the separate 300-second checker.

XCP-D: 26.2.0, with the LINC image digest pinned in `xcpd_linc.example.json`. Keep the 7.A aCompCor and S10 36P/GSR profiles separate. New actual-data calculations were not part of consolidation validation.

Optional atlas source commits are locked in `02_custom/s11_atlas_bold/sources.lock.json`. TemplateFlow payloads are materialized explicitly and verified independently of Git pointers. See the Step 11 README for supported types and exact-space restrictions.
