# Repository instructions

- `pipeline/` is ordinary editable source adapted and modified from statMINDlab/ADNI_fMRI_protocol. Original baseline/source hashes and the 153-commit history index remain under `config/`; changes are reviewed with this repository.
- The unified `pipeline/` contains all maintained stages, including s1–s12 and interstitial steps. Do not make a historical Research Selection Table a required input or the authoritative selection source.
- Update execution order and each stage's input/output/validation contract in both the root README and the step README.
- Keep data, raw clinical tables, real participant lists, private configuration, execution results and license files outside the repository. Use synthetic examples only.
- Review original-repository updates on a test branch with local code, provenance, docs and tests. Installation must not automatically follow the original remote branch.
- Distinguish command plans from completed execution, and technical validation from research inclusion decisions. Full MRIQC/fMRIPrep execution requires a separate request and verification of the actual environment.
- Validation: `python -m pytest -q` and `python workflow/lab.py doctor`. Preserve live deployment-bound files, work/cache identities and data. Use the primary checkout for routine work and final validation. If a live job requires temporary isolation, integrate the verified changes into the primary checkout and remove the temporary worktree after checking it for unique files.

- Explicit user authorization on 2026-11-06 permits the two unchanged CC0 OpenNeuro ds000030 1.0.0 NIfTI payloads and their public metadata/provenance under `RS-fMRI/07_reproducibility/public_data/ds000030-1.0.0/`, exactly as listed in `public_dataset.json`. This narrow public-example exception does not permit private ADNI images, clinical data, unrelated participant lists or software license keys.

- Write all repository-owned Markdown explanations, headings, tables and example comments in English. Retain original protocol copyright, GPL and citation files; identify owned-source modifications. Separately pinned SNP/atlas sources require a reviewed update.
