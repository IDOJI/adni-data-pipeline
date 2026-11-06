# Array merging

Work within each reviewed ancestry group after post-QC part 2 and the [TOPMed record check](installation.md#record-topmed-jobs). The commands below are templates for the genomics environment. The upstream reference is [Multi-set Merges](https://github.com/VUMC-VMAC/GWAS_QC/blob/5bbabfb54c2fffb86f39810386652daa124ce683/README.md#multi-set-merges).

For commands with attached inputs and expected results, use [toy Steps 6–11](../07_toy/README.md#6-resolve-duplicate-participants).

## 1. Resolve duplicate participants

Identify repeated participants across arrays using the sample mapping, including participants with different IDs. Calculate concordance at allele-aligned, jointly nonmissing shared loci; save the number compared and number discordant.

For concordance >0.99, normally retain the sample from the chip with more variants in the final pre-imputation dataset. Review discordant pairs, insufficient overlap, ties and exceptions. Apply a reviewed FID/IID keep list to each batch before calculating frequencies:

```sh
plink --bfile /ABSOLUTE/PATH/postqc/human610_EUR \
  --keep /ABSOLUTE/PATH/review/human610_EUR.keep \
  --make-bed --freq --out /ABSOLUTE/PATH/audit-inputs/human610_EUR
```

Repeat for every batch. Use the resulting matched BIM/FRQ pair for the next step.

## 2. Check variant compatibility

Verify GRCh38 coordinates and biological REF/ALT against the preparation references, preserving the mapping through rsID conversion. Then run the [BIM/FRQ helper](../02_custom/README.md) to select shared variants with matching coordinates and alleles and MAF difference ≤0.10.

The helper selects an intersection across batches and rejects allele swaps. Investigate substantial variant loss before proceeding; a different merge policy requires a documented decision.

## 3. Merge with PLINK

Extract the selected variants from each batch:

```sh
plink --bfile /ABSOLUTE/PATH/audit-inputs/human610_EUR \
  --extract /ABSOLUTE/PATH/audits/EUR-run-001/keep.snps \
  --keep-allele-order --make-bed \
  --out /ABSOLUTE/PATH/merge-inputs/human610_EUR
```

List the other batches in `other-batches.txt`, one PLINK prefix per line, excluding the base batch:

```text
/ABSOLUTE/PATH/merge-inputs/omniexpress_EUR
/ABSOLUTE/PATH/merge-inputs/omni25_EUR
/ABSOLUTE/PATH/merge-inputs/gsa_v2_EUR
```

```sh
plink --bfile /ABSOLUTE/PATH/merge-inputs/human610_EUR \
  --merge-list /ABSOLUTE/PATH/merge-inputs/other-batches.txt \
  --keep-allele-order --make-bed --out /ABSOLUTE/PATH/merged/adni_EUR
```

If PLINK reports `.missnp` conflicts, review and exclude the affected loci from every batch before retrying. Check merged sample counts against the deduplicated inputs and variant counts against the selected intersection.

## 4. Final QC

Calculate relatedness and review pairs with PI_HAT >0.25:

```sh
plink --bfile /ABSOLUTE/PATH/merged/adni_EUR \
  --genome full unbounded nudge --min 0.20 \
  --out /ABSOLUTE/PATH/final-qc/adni_EUR_relatedness
```

Apply reviewed sample exclusions to a new output prefix, then calculate PCs. Inside the container's pinned script directory:

```sh
bash calc_plot_PCs_snprelate.sh \
  -i /input/final/adni_EUR_reviewed -n
```

`-n` suppresses the upstream default inclusion file. Inspect PCs by ancestry and array, remove reviewed outliers, and recalculate until PCs match the final sample set. Retain exclusions, filtering counts, reference checks and batch plots with the final data; reassess HWE and MAF after exclusions as required by the analysis protocol.
