# SNP toy walkthrough

Run the blocks in order from `SNP/`, in the same terminal. Requirements: Python 3.10+, Git, and Linux x86_64 or macOS. Apple Silicon needs Rosetta for the pinned PLINK binary. Setup downloads PLINK 1.9.0 (September 27, 2026) from its [official distribution](https://www.cog-genomics.org/plink/1.9/) and checks the archive checksum.

The attached [genotypes](inputs/genotypes.json) and [imputation fixture](inputs/imputation-fixture.json) are entirely synthetic. The example runs PLINK QC, typed-call restoration, duplicate checks, the repository's variant helper, merging, PCA and X processing. It uses an offline fixture for imputation and one supplied `DEMO` ancestry group. Heterozygosity is reported without applying the unresolved paper-specific exclusion rule. Coordinates and reference alleles are synthetic; this is a local teaching example, not a TOPMed upload dataset.

## 0. Get the code and create a run directory

For a new checkout:

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git adni-snp-demo
cd adni-snp-demo
git submodule update --init -- SNP/01_upstream/GWAS_QC
cd SNP
```

If already in the repository, change into `SNP/`. Then:

```sh
export SNP_TOY_RUN="$(mktemp -d "${TMPDIR:-/tmp}/adni-snp-toy.XXXXXX")"
python3 07_toy/run.py setup --run-dir "$SNP_TOY_RUN"
```

Outputs go to this external directory. To repeat the example, create a new run directory; completed stages are not overwritten.

## 1. Prepare genotype inputs

```sh
python3 07_toy/run.py prepare --run-dir "$SNP_TOY_RUN"
```

Converts the attached JSON into PED/MAP files for two arrays, each with 33 synthetic samples, plus the declared reference-allele list.

## 2. Pre-imputation QC

```sh
python3 07_toy/run.py pre --run-dir "$SNP_TOY_RUN"
```

Applies variant/sample missingness, MAF, sex and HWE checks; writes heterozygosity/relatedness reports and an example VCF. X preparation includes differential missingness and female-only HWE. Each array retains 31 samples, with 1,240 autosomal variants in A and 1,200 in B.

## 3. Load the offline imputation fixture

```sh
python3 07_toy/run.py imputation --run-dir "$SNP_TOY_RUN"
```

Prints `OFFLINE FIXTURE: no TOPMed job was submitted`. For actual data, replace this handoff with the [hosted imputation step](../06_docs/installation.md#record-topmed-jobs).

## 4. Post-imputation part 1

```sh
python3 07_toy/run.py post1 --run-dir "$SNP_TOY_RUN"
```

Filters R² <0.8, multiallelic records and duplicate IDs, then writes BED files and the supplied ancestry keep lists. Each array has 1,218 autosomal imputed variants.

## 5. Restore typed calls and repeat variant QC

```sh
python3 07_toy/run.py post2 --run-dir "$SNP_TOY_RUN"
```

Replaces overlapping imputed calls with pre-QC typed calls and applies HWE/MAF filters. Deliberately altered typed calls in the fixture are restored. Array A has 1,258 variants; B has 1,218.

## 6. Resolve duplicate participants

```sh
python3 07_toy/run.py deduplicate --run-dir "$SNP_TOY_RUN"
```

`TOY_SHARED` has 1,217 comparable calls with no disagreements. Its A copy is retained because A has more typed variants. The concordance report records the denominator and coverage decision.

## 7. Check variants across arrays

```sh
python3 07_toy/run.py harmonize --run-dir "$SNP_TOY_RUN"
```

Runs `02_custom/harmonize.py` on matched BIM/FRQ files. The shared allele/position and MAF checks retain 1,024 variants; `harmonize/audit/audit.tsv` gives the decisions.

## 8. Merge the arrays

```sh
python3 07_toy/run.py merge --run-dir "$SNP_TOY_RUN"
```

Produces `merge/adni_demo.{bed,bim,fam}` with 61 samples and 1,024 variants.

## 9. Final relatedness and PCA

```sh
python3 07_toy/run.py final --run-dir "$SNP_TOY_RUN"
```

PLINK detects the deliberately duplicated `TOY_A003`/`TOY_B002` pair under different IDs. The example's fixed review decision removes `TOY_B002`, leaving 60 samples. The stage calculates three PCs; it does not infer ancestry or automatically select PCA outliers.

## 10. Complete chromosome X

```sh
python3 07_toy/run.py x --run-dir "$SNP_TOY_RUN"
```

Restores typed X calls, applies female-only HWE, MAF and haploid-call handling, checks array allele/frequency agreement, and merges X for the final autosomal sample set: 60 samples and 100 variants.

## 11. Compare with the reference result

```sh
python3 07_toy/run.py verify --run-dir "$SNP_TOY_RUN" \
  --report "$SNP_TOY_RUN/reproducibility.json"
```

Expected: `status: PASS`, with `genotype_and_decision_digest` equal to `b81f225271a6e6eedc927728c6d12911e2b979a775c293a06a968c9076ea3435`. The checker recomputes sample/variant/genotype signatures from BED/BIM/FAM files and checks decision-file hashes against [expected.json](expected.json). PCA eigenvalues use relative tolerance 10⁻⁵ and absolute tolerance 10⁻⁶; eigenvectors allow independent sign flips with absolute tolerance 10⁻⁵. Paths, logs and timestamps are excluded.

Two people using this checkout can compare `genotype_and_decision_digest` in their saved reports. Each should also obtain `PASS`, which checks PCA separately. To compare two complete run directories locally:

```sh
python3 07_toy/run.py compare \
  --run-dir "$SNP_TOY_RUN" --other-run /path/to/another-completed-run
```

The reference was generated from the pinned inputs and PLINK release. [generate_inputs.py](generate_inputs.py) documents how the fixtures were made; [inputs.sha256.json](inputs.sha256.json) fixes their contents. The demo never regenerates its reference results during verification. Re-run the same commit and use a fresh directory when comparing results.
