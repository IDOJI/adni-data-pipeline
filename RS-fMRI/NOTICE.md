# Attribution

- Upstream protocol: statMINDlab/ADNI_fMRI_protocol, commit `e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3`, connected as a submodule. Its copyright, GPL license and citation metadata remain in that repository.
- `custom/s8a_motion_duration_qc/run.py` is an initial byte-identical import of the user's pre-existing local `ADNI_fMRI_protocol/local_mac/paper_motion_qc.py`. It implements a separate motion-duration evaluation informed by Rutherford et al., https://arxiv.org/pdf/2602.03278v3. It is not an upstream-authored Step 8 replacement.
- Its tests were adapted from the existing local test suite; all generated image data are synthetic and the test identifiers were replaced with synthetic values.
- Other wrapper, compatibility and documentation code was created for this lab repository on 2026-10-31. Source code is distributed under GPL-3.0, consistent with the upstream license. ADNI images, clinical data and software license keys are not included.
