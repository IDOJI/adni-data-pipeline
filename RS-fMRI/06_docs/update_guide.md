# Update the pipeline

For a clean checkout that is not bound to active jobs:

```sh
git pull --ff-only
cd RS-fMRI
python 04_workflow/lab.py doctor
python -m pytest -q
```

The maintained code is in `pipeline/`; no original-protocol submodule update is needed. Review optional atlas changes through the [atlas guide](atlas_library.md).

For active batches, retain the frozen source/configuration and validate a separate checkout first. Source relocation must preserve scientific settings and cache identity at an idle handoff; see the [live-installation contract](source_integration.md#existing-live-installations).

To modify a stage, edit its code, update its concise README and run the relevant tests. Port later changes from the original project through a reviewed branch while preserving attribution; do not automatically follow its remote branch.
