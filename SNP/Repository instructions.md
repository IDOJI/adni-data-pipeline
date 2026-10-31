# Repository instructions

- Preserve `01_upstream/GWAS_QC` as an unmodified, pinned Git submodule. Put adaptations in `02_custom/` and workflow tooling in `04_workflow/`.
- Treat this module as a documented adaptation of Eissman et al. (2024), not an exact historical replication. Keep paper criteria, pinned-code behavior and project decisions distinct.
- Keep genotype data, participant identifiers, reference files, containers, private configuration, server records and results outside this public repository. Use synthetic fixtures only.
- Do not infer an array or genome build from an ADNI phase. Validate each delivered batch, especially ADNI4.
- Command plans do not execute QC, submit TOPMed jobs, resolve identity conflicts or establish scientific inclusion. Preserve manual review gates and report incomplete stages explicitly.
- Record panel and actual server software versions for every job. Do not merge jobs using different imputation environments.
- Keep autosomal and X-chromosome workflows separate. Do not interpret PLINK A1/A2 as validated VCF REF/ALT.
- Write repository-owned documentation and example comments in concise English.
- Validate with `python3 04_workflow/snp.py doctor` and `python3 -m unittest discover -s 05_tests -v` from `SNP/`. Also run the repository's RS-fMRI checks when changing shared files.
