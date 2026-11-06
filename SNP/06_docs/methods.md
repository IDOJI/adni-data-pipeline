# Methods

Eissman JM, Archer DB, Mukherjee S, et al. **Sex-specific genetic architecture of late-life memory performance.** *Alzheimer's & Dementia*. 2024;20(2):1250–1267. [doi:10.1002/alz.13507](https://doi.org/10.1002/alz.13507) · [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC10917043/).

Section 2.4 is the methodological reference. It describes four ADNI arrays: Human610-Quad, HumanOmniExpress, Omni 2.5M and Global Screening Array v2. ADNI4 requires additional validation of its delivered array, build and metadata; an ADNI phase label alone does not identify these.

## QC criteria

| Step | Criterion |
|---|---|
| Initial variants | Missingness ≤0.05; MAF ≥0.01 |
| Samples | Missingness ≤0.01; exclude related individuals and sex discrepancies |
| Heterozygosity | Exclude excessive heterozygosity at p <10⁻⁷ |
| HWE | Retain p ≥10⁻⁶ |
| Imputation | TOPMed; GRCh38 |
| Imputed variants | Retain R² ≥0.8; remove duplicate and multiallelic records |
| Typed variants | Restore original calls, then repeat HWE and MAF filtering |
| Duplicate participants | Concordance >0.99; typically retain the better-covered chip |
| Array compatibility | Remove reference-allele conflicts and MAF differences >0.10 |
| Final samples | Reassess cryptic relatedness and ancestry-specific PCA outliers |

The paper's exact code commit and TOPMed release are unspecified in this section. This project uses TOPMed r3 and the source recorded in [versions.md](../03_config/versions.md), so it is an adaptation of the published method.

## Known code differences

- **Heterozygosity:** the pinned `plot_het_check_outliers.R` assigns SD groups, but later assignments overwrite the `6 SD` label used to select exclusions. It also lacks the paper's p-value test. Resolve the exclusion rule before cohort use.
- **Ancestry:** current post-QC uses SNPWeights-derived groups; the paper describes self-reported race/ethnicity together with PCA. Review these assignments before running part 2 separately for each group. Upstream recommends groups with more than ten samples.
- **Relatedness:** upstream uses PI_HAT >0.25 and removes both samples for pairs with PI_HAT ≥0.90. Intentional re-genotyping across arrays is handled separately by the duplicate-sample comparison.
- **Additional filtering:** upstream removes palindromic variants before imputation and applies variant missingness filters after ancestry subsetting.
- **Array comparison:** upstream's `pre_merge_A1_MAF_check.R` matches SNP ID/A1 and uses MAF difference <0.10; its dynamic-column expressions need runtime verification. The [local helper](../02_custom/README.md) requires matching coordinates and both alleles across all batches, with MAF difference ≤0.10. PLINK A1/A2 agreement does not verify biological REF/ALT.
- **Output:** upstream converts imputed VCFs to PLINK BED hard calls. Retain the original VCFs for dosage data; continuous dosage export and dosage-aware typed-call replacement are not implemented here.
