# Variant compatibility check

`harmonize.py` compares PLINK BIM/FRQ files and writes a variant list for merging. It requires Python's standard library and uses temporary disk storage for the comparison.

Supply at least two uniquely labelled batches from the same ancestry group. Each prefix needs matching `.bim` and `.frq` files from the same samples, with unique IDs, autosomal biallelic A/C/G/T SNPs, finite frequencies and nonzero allele counts.

```sh
python3 02_custom/harmonize.py \
  --batch human610 /ABSOLUTE/PATH/audit-inputs/human610_EUR \
  --batch omniexpress /ABSOLUTE/PATH/audit-inputs/omniexpress_EUR \
  --output-dir /ABSOLUTE/PATH/audits/EUR-run-001
```

Add `--batch` arguments for the remaining arrays. A variant passes when it is present in every batch, its ID, chromosome, position, A1 and A2 match, and its MAF range is ≤0.10. The comparison uses the precision reported in FRQ files; borderline values may need higher-precision frequencies.

Outputs are `keep.snps`, `audit.tsv` and `summary.json` with input checksums. The first applicable decision is recorded: `not_shared`, `allele_or_position_mismatch`, `maf_difference` or `keep`. Existing output directories and empty passing sets return errors; use results only after a successful exit.

REF validation, sample deduplication and the PLINK merge are covered in the [merge guide](../06_docs/merging.md). A1/A2 matching alone does not establish REF/ALT orientation.
