# Repository instructions

- This public source repository organizes ADNI pipelines by modality. Current implementation is under `RS-fMRI/`; SNP will be added as a separate module.
- Read the relevant modality's `Repository instructions.md` and README before working. Do not edit the upstream submodule directly.
- Do not commit original images, clinical tables, genetic data, real participant IDs, private configuration, execution results, license keys or credentials. Use synthetic examples only.
- Do not introduce a Selection Table-centered workflow. Preserve upstream stages, independent Custom Steps and the integrated README.
- Test commands: run `cd RS-fMRI`, then `python -m pytest -q` and `python 04_workflow/lab.py doctor`.
- Update upstream pins only after explicit review and compatibility testing. Installation must use the version recorded in the parent gitlink.

## Codex co-author attribution

- Commits with Codex contributions must include the trailer `Co-authored-by: Codex <codex@openai.com>`.
- `.githooks/commit-msg` adds this trailer in Codex environments, preserves other co-authors and prevents duplicates. Follow the [setup guide](.githooks/README.md).
- In a new clone, check existing hook configuration, then enable it with `git config --local core.hooksPath .githooks`. Set `CODEX_COAUTHOR=1` explicitly in Codex environments without `CODEX_THREAD_ID`.

- Write all repository-owned Markdown explanations, headings, tables and example comments in English. Keep the pinned upstream submodule unchanged.
