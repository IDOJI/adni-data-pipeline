# Updating repository-owned protocol sources

```sh
git pull --ff-only
cd RS-fMRI
python 04_workflow/lab.py doctor
python -m pytest -q
```

Use this normal update sequence after source integration, from a clean checkout or after explicitly preserving local changes. The core protocol is ordinary source in this repository; no ADNI protocol submodule update is needed. SNP and optional atlas sources keep separate reviewed gitlinks.

## Migration from an initialized protocol submodule

```sh
git status --short --ignore-submodules
git fetch --no-recurse-submodules origin main
git log -1 --oneline origin/main
```

These commands inspect and fetch without replacing working files or updating submodules. Do not deinitialize, delete or overwrite a source tree used by active jobs. Preserve uncommitted changes and original Git history first. Review local changes separately from the published migration.

The unified layout places all active stages in `pipeline/` and historical references in `provenance/`. It changes source paths. Freeze the previous revision outside the maintained checkout before updating a live installation, then verify any operational rebinding at an idle boundary without changing scientific settings or cache identities. A fresh clone is the simplest separate validation installation. See the [live-installation contract](source_integration.md#existing-live-installations).

## Review a protocol change

```sh
git switch -c feature/protocol-change
git diff -- RS-fMRI/pipeline
```

Edit ordinary source files and review/stage/commit them in this repository. Doctor rejects uncommitted protocol content but accepts the reviewed parent version, reporting its differences from the original import. Run meaningful compatibility and scientific validation appropriate to the change. Do not replace original import hashes to hide edits; provenance records the current parent revision/content separately.

For a later original-repository update, fetch it in a separate checkout, compare source changes, and port reviewed changes onto a test branch while preserving local improvements and attribution. Installation does not automatically follow the original remote branch.

## One-time migration from the initial unnumbered layout

The historical `RS-fMRI/upstream/ADNI_fMRI_protocol` path predates integration. Preserve its changes and Git history before using a current checkout or reviewed migration. Do not run the former deinit/update recipe against an active runtime.

Optional atlas pins follow the [atlas review process](atlas_library.md).
