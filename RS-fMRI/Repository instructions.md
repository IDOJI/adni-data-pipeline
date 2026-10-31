# Repository instructions

- `01_upstream/ADNI_fMRI_protocol` is a submodule pinned to a commit. Implement compatibility changes in `02_custom/` or `04_workflow/`.
- Upstream s1–s9 remains the main workflow. Do not make a historical Research Selection Table a required input or the authoritative selection source.
- Update execution order and each Custom Step's input/output/validation contract in both the root README and the step README.
- Keep data, raw clinical tables, real participant lists, private configuration, execution results and license files outside the repository. Use synthetic examples only.
- Review upstream updates on a test branch together with the gitlink, lock, documentation and compatibility tests. Do not use automatic `--remote` updates during installation.
- Distinguish command plans from completed execution, and technical validation from research inclusion decisions. Full MRIQC/fMRIPrep execution requires a separate request and verification of the actual environment.
- Validation: `python -m pytest -q` and `python 04_workflow/lab.py doctor`. Do not modify the existing upstream working copy or data.

- Write all repository-owned Markdown explanations, headings, tables and example comments in English. Keep the pinned upstream submodule unchanged.
