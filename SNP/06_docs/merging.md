# Multi-array integration and final QC

Follow the upstream [Multi-set Merges](https://github.com/VUMC-VMAC/GWAS_QC/blob/5bbabfb54c2fffb86f39810386652daa124ce683/README.md#multi-set-merges) procedure after each batch has completed post-QC part 2. Work within reviewed ancestry groups. The commands below are templates to execute in the validated genomics environment; replace every path and preserve logs.

## 1. Check imputation provenance

Run `04_workflow/snp.py check-jobs` with every configured autosomal batch record, then compare the records with the actual server reports. The check rejects missing batches, repeated batch IDs, non-r3 jobs, non-GRCh38 results, missing software versions and differing server/engine/phasing versions. It checks records, not remote jobs or report contents.

## 2. Resolve repeated participants

Use an external sample mapping to identify cross-array duplicates, including different IDs belonging to the same participant. For every pair, calculate concordance from allele-aligned, jointly nonmissing hard calls at shared loci. Retain the number compared and number discordant; do not count missing/missing as agreement. A concordance threshold is meaningful only with adequate shared coverage.

For pairs with concordance >0.99, normally retain the sample from the chip with more variants in its final pre-imputation dataset. Document exceptions and ties. Hold discordant or insufficiently compared pairs for identity review; do not automatically keep the larger chip. Preserve a reviewed FID/IID keep list per batch. Duplicate resolution is intentionally a scientific review step, not an automatic inference from filenames.

Apply the reviewed keep lists before calculating frequencies. For each batch, normalize its BIM/FRQ output together:

```sh
plink --bfile /ABSOLUTE/PATH/postqc/human610_EUR \
  --keep /ABSOLUTE/PATH/review/human610_EUR.keep \
  --make-bed --freq --out /ABSOLUTE/PATH/audit-inputs/human610_EUR
```

Repeat for every batch. This writes a matched output BIM/FRQ pair and uses the retained samples for allele frequencies. Do not combine a frequency file from one sample set with a BIM from another run.

## 3. Verify reference alleles and audit frequencies

Validate GRCh38 coordinates and biological REF/ALT against the exact FASTA/reference resources used to prepare the uploads. Retain the variant ID mapping through the upstream rsID conversion. Check reference conflicts separately from PLINK's A1/A2 coding. A matching rsID alone does not establish matching coordinates or alleles. Do not silently flip strands to force a merge.

Run [harmonize.py](../02_custom/README.md) on the matched BIM/FRQ prefixes. This selects an intersection across all supplied batches, a deliberately conservative policy that can remove batch-specific variants. It is not the upstream alternative procedure for small batches. If too few loci survive, investigate array, ancestry and reference differences before choosing and documenting another policy.

## 4. Merge compatible sets

Extract the reviewed variant intersection from each batch:

```sh
plink --bfile /ABSOLUTE/PATH/audit-inputs/human610_EUR \
  --extract /ABSOLUTE/PATH/audits/EUR-run-001/keep.snps \
  --keep-allele-order --make-bed \
  --out /ABSOLUTE/PATH/merge-inputs/human610_EUR
```

Repeat for all batches. Write `other-batches.txt` outside the repository with one remaining BED/BIM/FAM prefix per line, excluding the base batch:

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

If PLINK produces `.missnp`, inspect the conflicts and remove the reviewed conflicting loci from **every** batch before retrying with a new output prefix. Record the exclusion list. Check that sample counts equal the sum of deduplicated batch counts and that the resulting variant set matches the reviewed intersection.

## 5. Reassess relatedness and PCs

Upstream's standard multi-set procedure checks merged relatedness at PI_HAT >0.25, then calculates PCs and reviews outliers. Calculate the relatedness evidence in the validated environment:

```sh
plink --bfile /ABSOLUTE/PATH/merged/adni_EUR \
  --genome full unbounded nudge --min 0.20 \
  --out /ABSOLUTE/PATH/final-qc/adni_EUR_relatedness
```

Review pairs, choose exclusions with documented reasons, and write a final keep list. Apply it to a new output prefix. Use upstream `calc_plot_PCs.sh` or `calc_plot_PCs_snprelate.sh` on the resulting data. Pass `-n` to suppress default inclusion generation: the upstream plotting defaults must not silently impose a White-only sample selection.

```sh
# Run from the pinned scripts directory inside the validated container.
bash calc_plot_PCs_snprelate.sh \
  -i /input/final/adni_EUR_reviewed -n
```

Inspect ancestry PCs and color plots by array/batch as well as reviewed ancestry labels. Remove reviewed outliers and recalculate PCs until the final keep set and PC file agree. Preserve counts, decisions, residual relatedness, batch plots and reference/provenance reports with the final data. Record HWE and MAF behavior after any sample exclusions; re-filter if required by the chosen analysis protocol.
