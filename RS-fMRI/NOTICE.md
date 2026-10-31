# Attribution

- Upstream protocol: statMINDlab/ADNI_fMRI_protocol, commit `e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3`, connected as a submodule. Its copyright, GPL license and citation metadata remain in that repository.
- `02_custom/s8a_motion_duration_qc/run.py` is an initial byte-identical import of the user's pre-existing local `ADNI_fMRI_protocol/local_mac/paper_motion_qc.py`. It implements a separate motion-duration evaluation informed by Rutherford et al., https://arxiv.org/pdf/2602.03278v3. It is not an upstream-authored Step 8 replacement.
- Its tests were adapted from the existing local test suite; all generated image data are synthetic and the test identifiers were replaced with synthetic values.
- Other wrapper, compatibility and documentation code was created for this lab repository on 2026-10-31. Source code is distributed under GPL-3.0, consistent with the upstream license. ADNI images, clinical data and software license keys are not included.

- `02_custom/s3a_source_qc/qc_registry.py` and `nfq_quality.py` adapt the user's Research QC/NFQ matching and decision functions. Hardcoded vault paths, file discovery, historical snapshot naming and legacy launch code were removed. Input schemas and matching rules are explicit; source code hashes are recorded in `03_config/imported_sources.json`.
- `02_custom/s9a_validate_clinical/run.py` is a run/CSV implementation of selected Research clinical validation rules. It preserves date ties and clinical source rows; it does not claim complete equivalence with the original RDS/R module or establish biological AD.

- `02_custom/s7a_volume_workflow/` consolidates the user's former local Docker volume workflow, independent audit, image QA and guarded metadata repair; scientific settings are retained as a separate aCompCor profile. The single-case staging/migration helpers and actual pilot records remain in a private archive.
- `02_custom/s10_xcpd_integrated_qc/` adapts the user's active local S8/XCP-D integrated-QC extension and hash-verified offloader. Private paths/configs/participants were removed; explicit config, pinned upstream, external runtime guards, aggregation lock and clinical scan-link export were added. No active worker or original upstream source was replaced.

- 9.A v2 adapts the Research participant-static PTDEMOG rules with raw-row provenance and TEAM exclusion. 9.B combines independently generated QC/clinical artifacts with explicitly confirmed ST/conversion exclusions; no private subject lists are embedded.
