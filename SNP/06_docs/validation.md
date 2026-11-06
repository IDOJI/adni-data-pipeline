# Tests

Run from `SNP/`:

```sh
python3 04_workflow/snp.py doctor
python3 -m unittest discover -s 05_tests -v
```

`doctor` checks the submodule URL, gitlink, clean checkout and locked file hashes. The synthetic tests cover configuration paths, command handoffs, job-record consistency and BIM/FRQ comparisons, including allele mismatches and the 0.10 MAF boundary. They also check syntax and help interfaces for the three autosomal QC scripts.

The 11 tests passed on November 1, 2026 with Python 3.11.16 and 3.14.7. They test the local helpers; no ADNI cohort processing, genomics container run, TOPMed job or X-chromosome validation was performed.
