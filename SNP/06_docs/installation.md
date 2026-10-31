# Installation and input preparation

## Local tools

Install Git and Python 3.10+ for this module's standard-library tools. Initialize the recorded gitlinks with `git submodule update --init --recursive`. Do not use `--remote` during installation. Run `python3 04_workflow/snp.py doctor` from `SNP/` to compare the checkout, parent gitlink and file hashes with the lock.

## QC runtime

The [upstream README](https://github.com/VUMC-VMAC/GWAS_QC/blob/5bbabfb54c2fffb86f39810386652daa124ce683/README.md) describes a Linux Singularity image named `CNT_genomic_processing_v3.19.simg`. It is not distributed by that repository. Obtain it through the maintainers or prepare and validate a compatible environment. This module does not download a substitute or claim that an image with the same filename is identical.

Upstream depends on PLINK 1.9 and 2, R and its packages, BCFtools/HTSlib, liftOver, reference-checking scripts, EIGENSOFT and SNPWeights. It also hardcodes paths such as `/SNPweights2.1/inferancestry.py`. macOS Python alone cannot run the genomics workflow. Use Linux/HPC with Apptainer or Singularity after validating the image, script interfaces and known method differences.

The planner binds this repository's pinned checkout read-only at `/scripts/GWAS_QC`, the external data root at `/input`, and the external reference root read-only at `/ref`. This ensures scripts embedded in an older image do not silently replace the source pin. Validate this bind layout against the actual image before using real data. Container bind source paths cannot contain commas or colons; relative paths inside the container must have no spaces or shell metacharacters because upstream contains unquoted shell expansions.

## External resources

Prepare these outside the source repository:

| Resource | Input contract |
|---|---|
| Array genotypes | One BED/BIM/FAM prefix per delivery batch; retain original X data for sex checks |
| Sex metadata | Headerless FID, IID, sex; 1=male, 2=female, 0=unknown; complete mapping to imputed samples |
| TOPMed comparison table | The pinned pre-QC actually reads `topmed_sites_stem.txt.gz`, despite its help text mentioning chromosome-split files |
| Variant-to-rsID mapping | Post-QC part 1 reads `rsid_stem_chrN.txt`; part 2 reads combined `rsid_stem.txt`. Prepare and verify both layouts |
| SNPWeights | `snpweights_stem` and its matching `snpweights_stem_snp.txt` |
| Genomic runtime | Compatible image, SHA-256 and installed tool-version inventory |
| Final ancestry review | Reviewed keep lists, PC plots and sample exclusions |

Set the actual build from each delivery's metadata. The public example's `b37` values are placeholders, not verified ADNI array annotations. Validate allele conventions and reference checks before upload. Do not reuse an old panel's annotation files solely because the script accepts their filenames.

Create separate writable parent directories for each batch's pre-QC and post-QC output stems. Keep raw inputs immutable through filesystem permissions or a separate archive. Supply decrypted TOPMed files as `chr1.dose.vcf.gz` through `chr22.dose.vcf.gz` with matching information files as expected by the pinned code. The planner omits `-z`; handle archive decryption outside command logs and keep passwords outside this repository.

## Validation and updates

Run `python3 -m unittest discover -s 05_tests -v` for synthetic source, configuration, job-environment and variant-audit checks. These do not execute the external genomics tools. Establish a separate container smoke test and reference-validation dataset before a cohort run.

Update the submodule only through explicit source review and compatibility testing. Update the parent gitlink, lock hashes, version notes and tests together. Preserve historical job records; changing the source pin cannot change the provenance of an earlier run.
