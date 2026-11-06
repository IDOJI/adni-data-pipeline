# Repository instructions

- This public source repository organizes ADNI pipelines by modality under `RS-fMRI/` and `SNP/`. Read each module's implementation status before describing it as validated.
- Read the relevant modality's `Repository instructions.md` and README before working. The RS-fMRI protocol is ordinary owned source; review its changes in this repository. SNP/atlas submodules remain separately pinned.
- Do not commit original images, clinical tables, genetic data, real participant IDs, private configuration, execution results, license keys or credentials. Use synthetic examples only.
- Do not introduce a Selection Table-centered workflow. Preserve upstream stages, independent Custom Steps and the integrated README.
- Test commands: run `cd RS-fMRI`, then `python -m pytest -q` and `python 04_workflow/lab.py doctor`.
- SNP checks: run `cd SNP`, then `python3 -m unittest discover -s 05_tests -v` and `python3 04_workflow/snp.py doctor`.
- Review owned RS-fMRI source changes with provenance and compatibility tests. SNP/atlas pins still require explicit review; core installation requires no protocol submodule update.

## Codex co-author attribution

- Commits with Codex contributions must include the trailer `Co-authored-by: Codex <codex@openai.com>`.
- `.githooks/commit-msg` adds this trailer in Codex environments, preserves other co-authors and prevents duplicates. Follow the [setup guide](.githooks/README.md).
- In a new clone, check existing hook configuration, then enable it with `git config --local core.hooksPath .githooks`. Set `CODEX_COAUTHOR=1` explicitly in Codex environments without `CODEX_THREAD_ID`.

- Explicit user authorization on 2026-11-06 permits the two unchanged CC0 OpenNeuro ds000030 1.0.0 NIfTI payloads and their public metadata/provenance under `RS-fMRI/07_reproducibility/public_data/ds000030-1.0.0/`, exactly as listed in `public_dataset.json`. This narrow public-example exception does not permit private ADNI images, clinical data, unrelated participant lists or software license keys.

- Write all repository-owned Markdown explanations, headings, tables and example comments in English. Retain original protocol copyright, GPL and citation files; identify owned-source modifications. Separately pinned SNP/atlas sources require a reviewed update.
