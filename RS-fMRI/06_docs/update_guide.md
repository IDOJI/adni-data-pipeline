# Updating upstream

For normal updates, run `git pull --ff-only` followed by `git submodule update --init --recursive` from the repository root. These restore the recorded upstream commit. Do not add `--remote` to routine installation commands.

## One-time migration from the initial unnumbered layout

If an existing clone still uses `RS-fMRI/upstream/ADNI_fMRI_protocol`, run the following sequence from the repository root **before updating**. Use `deinit` without `--force` so modified submodules are not forcibly removed. If it refuses, preserve upstream changes first.

```sh
git submodule deinit -- RS-fMRI/upstream/ADNI_fMRI_protocol
git pull --ff-only
git submodule update --init --recursive
cd RS-fMRI
python 04_workflow/lab.py doctor
```

The unnumbered path in this section is a one-time input for cleaning up an older clone. The new path is `RS-fMRI/01_upstream/ADNI_fMRI_protocol`; the submodule identifier and pinned upstream commit remain unchanged. Skip deinit for new or already migrated clones.

To evaluate an upstream update, start a separate branch from a clean repository root.

```sh
git switch -c test/upstream-update
git submodule update --remote --checkout RS-fMRI/01_upstream/ADNI_fMRI_protocol
git diff --submodule=log -- RS-fMRI/01_upstream/ADNI_fMRI_protocol
```

Review the new source commit and input/output changes, then update the commit and review date in `RS-fMRI/03_config/upstream.lock.json` and stage the gitlink. A lock change alone does not establish validation.

```sh
git add RS-fMRI/01_upstream/ADNI_fMRI_protocol RS-fMRI/03_config/upstream.lock.json
cd RS-fMRI
python -m pytest -q
python 04_workflow/lab.py doctor
```

Alongside synthetic compatibility tests, compare conversion, QC, preprocessing and clinical-linkage results on lab validation data in a separate external run. If successful, record actual tools, image digests, changes and validation scope in `03_config/versions.md`, then adopt through PR review.

If validation fails, return to the existing main branch and run `git submodule update --init --recursive` to restore the pinned version. Preserve experimental branches/user changes first; do not use forced checkout or reset.

Reference: [official Git submodule documentation](https://git-scm.com/docs/git-submodule).
