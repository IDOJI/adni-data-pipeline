# Repository instructions

- `01_upstream/ADNI_fMRI_protocol` is ordinary editable source. Original baseline/source hashes and the 153-commit history index remain under `03_config/`; changes are reviewed with this repository.
- Upstream s1–s9 remains the main workflow. Do not make a historical Research Selection Table a required input or the authoritative selection source.
- Update execution order and each Custom Step's input/output/validation contract in both the root README and the step README.
- Keep data, raw clinical tables, real participant lists, private configuration, execution results and license files outside the repository. Use synthetic examples only.
- Review original-repository updates on a test branch with local code, provenance, docs and tests. Installation must not automatically follow the original remote branch.
- Distinguish command plans from completed execution, and technical validation from research inclusion decisions. Full MRIQC/fMRIPrep execution requires a separate request and verification of the actual environment.
- Validation: `python -m pytest -q` and `python 04_workflow/lab.py doctor`. Preserve live deployment-bound files, work/cache identities and data. Use an isolated checkout for changes and validation.

- Explicit user authorization on 2026-11-06 permits the two unchanged CC0 OpenNeuro ds000030 1.0.0 NIfTI payloads and their public metadata/provenance under `RS-fMRI/07_reproducibility/public_data/ds000030-1.0.0/`, exactly as listed in `public_dataset.json`. This narrow public-example exception does not permit private ADNI images, clinical data, unrelated participant lists or software license keys.

- Write all repository-owned Markdown explanations, headings, tables and example comments in English. Retain original protocol copyright, GPL and citation files; identify owned-source modifications. Separately pinned SNP/atlas sources require a reviewed update.
