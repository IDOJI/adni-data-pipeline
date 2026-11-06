# Tests

Run from `SNP/`:

```sh
python3 04_workflow/snp.py doctor
python3 -m unittest discover -s 05_tests -v
```

`doctor` checks the submodule URL, gitlink, clean checkout and locked file hashes. The synthetic tests cover configuration paths, command handoffs, job-record consistency and BIM/FRQ comparisons, including allele mismatches and the 0.10 MAF boundary. They also check syntax and help interfaces for the three autosomal QC scripts.

On November 6, 2026, the 17 tests passed with Python 3.14.7. The [public toy walkthrough](../07_toy/README.md) was also executed twice in separate directories with the pinned PLINK 1.9.0 macOS build; all 21 result checkpoints matched. It produced 60 samples with 1,024 autosomal variants and 100 X variants. CI repeats the toy workflow on Linux with Python 3.10 and 3.12.

The toy tests local data handling, including X sample alignment and typed-call restoration. Its offline imputation fixture and supplied ancestry group do not validate TOPMed, SNPWeights or the full upstream container. Cohort data and the paper-specific heterozygosity rule require separate validation.
