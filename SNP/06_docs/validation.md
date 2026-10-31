# Validation record

Checked on November 1, 2026.

| Check | Result | Scope |
|---|---|---|
| SNP source doctor | Passed | Parent gitlink, submodule URL/path, clean checkout and locked hashes |
| SNP synthetic suite | 11 tests passed | Configuration collisions, command handoffs, TOPMed record consistency, variant intersection and malformed inputs |
| Upstream shell checks | Passed | Bash syntax and `-h` interfaces for the three autosomal QC scripts |
| Example command plan | Generated | Four example batches; no QC commands executed |
| RS-fMRI source doctor | Passed | Existing imaging source pin remains unchanged |
| RS-fMRI regression suite | 262 tests and 17 subtests passed | Existing synthetic imaging and workflow checks, including the atlas module |
| Documentation checks | Passed | Local Markdown links, code fences and Git whitespace checks |

The SNP suite ran with Python 3.14.7 and Python 3.11.16. RS-fMRI regression tests used a separate temporary Python 3.11.16 environment with the existing `RS-fMRI/requirements.txt`; no imaging implementation or upstream files were changed.

These checks do not validate a genomics container, actual reference resources, TOPMed execution, the paper's heterozygosity criterion, biological REF/ALT assignments, duplicate participant identity or final cohort selection. X-chromosome handling and continuous dosage output are not validated by this suite. See [methods and differences](methods.md) before preparing a real run.

Re-run from `SNP/`:

```sh
python3 04_workflow/snp.py doctor
python3 -m unittest discover -s 05_tests -v
python3 04_workflow/snp.py plan --config 03_config/pipeline.example.json
```
