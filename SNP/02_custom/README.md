# Multi-array variant audit

`harmonize.py` provides a conservative replacement for the upstream A1/MAF pre-merge audit. It uses only Python's standard library and a temporary disk-backed SQLite table, so genotype-wide tables do not need to fit in RAM. This temporary database is created under the requested external output directory and removed on completion.

For each ancestry group, supply one PLINK prefix per reviewed batch with matching `.bim` and `.frq` files. Use the same sample set for both files. The helper requires unique variant IDs, autosomal biallelic A/C/G/T SNPs, matching FRQ/BIM allele orientation, finite frequencies and nonzero allele counts.

```sh
python3 02_custom/harmonize.py \
  --batch human610 /ABSOLUTE/PATH/audit-inputs/human610_EUR \
  --batch omniexpress /ABSOLUTE/PATH/audit-inputs/omniexpress_EUR \
  --batch omni25 /ABSOLUTE/PATH/audit-inputs/omni25_EUR \
  --batch gsa_v2 /ABSOLUTE/PATH/audit-inputs/gsa_v2_EUR \
  --output-dir /ABSOLUTE/PATH/audits/EUR-run-001
```

It retains variants shared by every supplied batch with identical ID, chromosome, position, A1 and A2, and a maximum pairwise MAF difference ≤0.10. It rejects allele swaps rather than guessing strand or reference orientation. Frequency comparisons use decimal arithmetic at the precision reported in `.frq`; investigate borderline values using higher-precision source frequencies when needed.

Outputs are `keep.snps`, `audit.tsv` and `summary.json`, including BIM/FRQ SHA-256 hashes. Keep the inputs unchanged while auditing. Decisions are `keep`, `not_shared`, `allele_or_position_mismatch` or `maf_difference`, in that precedence order. Each variant gets one decision; multiple possible failure reasons are not separately counted. An existing output directory is rejected. Empty intersections return an error. Failed runs can leave a partial output directory; use only a successful run with its complete summary and exit status.

This audit does not validate REF against GRCh38, resolve sample duplicates, infer ancestry or merge genotypes. Verify biological reference alleles separately and follow the [merge guide](../06_docs/merging.md). A1/A2 in a BIM file must not be relabelled REF/ALT without evidence.
