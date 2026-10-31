# Methods and implementation choices

## Scientific reference

Eissman JM, Archer DB, Mukherjee S, et al. **Sex-specific genetic architecture of late-life memory performance.** *Alzheimer's & Dementia*. 2024;20(2):1250–1267. [doi:10.1002/alz.13507](https://doi.org/10.1002/alz.13507). Published online November 20, 2023; accepted September 7, 2023.

Methods 2.4 is the primary reference. The following thresholds also appear in the supplied project brief:

| Operation | Reference criterion |
|---|---|
| Initial variant QC | Missingness ≤0.05; MAF ≥0.01 |
| Sample QC | Missingness ≤0.01; exclude relatedness, sex discrepancies and excessive heterozygosity (p < 10⁻⁷) |
| HWE | Retain p ≥10⁻⁶ |
| Imputation | TOPMed; GRCh38 |
| Imputed variants | Retain R² ≥0.8; remove duplicate and multiallelic records |
| Typed variants | Restore original calls, then repeat HWE and MAF filters |
| Duplicate participants | Concordance >0.99; typically retain the better-covered chip |
| Array compatibility | Remove reference-allele conflicts and MAF differences >0.10 |
| Final samples | Reassess cryptic relatedness and ancestry-specific PCA outliers |

The paper does not specify its exact code commit or panel release here. Using r3 and the current source pin is an adaptation. ADNI4 additionally requires independent validation.

## Known code differences

The reviewed source is [GWAS_QC at 5bbabfb](https://github.com/VUMC-VMAC/GWAS_QC/tree/5bbabfb54c2fffb86f39810386652daa124ce683), not an identified historical paper release. Review these points before executing a cohort:

- **Heterozygosity:** `plot_het_check_outliers.R` labels SD groups and writes samples labelled `6 SD`. Later assignments overwrite that label with lower-SD groups. Its current outlier file cannot establish that extreme samples were excluded, and it does not implement a p-value test. An explicit, validated statistical specification or author clarification is still required. Do not silently equate six SD with p <10⁻⁷.
- **Ancestry:** current post-QC uses SNPWeights-derived groups. The paper describes self-reported race/ethnicity together with PCA. Record this change, review inferred groups and avoid equating genetic ancestry with self-reported categories. Post-QC part 2 runs separately per reviewed group; upstream recommends groups with more than ten samples.
- **Relatedness:** upstream uses PI_HAT >0.25 and treats PI_HAT ≥0.90 as potential identity issues, removing both samples in its standard within-batch procedure. Across arrays, resolve intentional re-genotyping separately using concordance. Do not let within-batch duplicate removal substitute for the cross-array audit.
- **Additional filters:** upstream removes palindromic SNPs before imputation and applies variant missingness filters after ancestry subsetting. Document actual filtering counts, including filters beyond the brief's simplified sequence.
- **Alleles:** upstream's `pre_merge_A1_MAF_check.R` joins on SNP ID and A1, then filters MAF differences with strict `<0.1`. Its `data.table` dynamic-column expressions need runtime verification. Our helper replaces that audit with explicit BIM/FRQ checks and an inclusive ≤0.10 boundary. It also requires matching A2, coordinates and presence in every batch. This is a conservative project policy; PLINK A1/A2 agreement does not verify biological REF/ALT.
- **Hard calls:** post-QC part 1 converts VCFs to BED through PLINK 2. Preserve original imputed VCFs with DS outside the repository. Continuous dosage export and dosage-aware typed-call replacement are not implemented here.

These are execution prerequisites, not evidence that a cohort has passed QC. The command planner deliberately does not launch a run or certify these differences as resolved.

## TOPMed adaptation

The [official documentation](https://statgen.github.io/tis-v2-docs/imputation/getting-started/) checked on November 1, 2026 lists TOPMed r3, Eagle v2.4.1 and Minimac4 v4.1.6. These are documented service versions, not versions observed in a completed job. Save the actual job settings and server-generated software report; a hosted service may change independently of this repository.

Use r3 throughout a combined dataset. Treat the input array build, the GRCh38 upload build, the imputation reference panel, and the local reference SNP/rsID files as separate provenance items. A legacy `freeze5` filename in an upstream example does not establish compatibility with r3. Verify reference origin, build, allele convention and coverage; record checksums.

The service's [data preparation guide](https://statgen.github.io/tis-v2-docs/imputation/data-preparation/) requires chromosome-specific, position-sorted, bgzip-compressed VCFs with GT. GRCh38 uses `chr`-prefixed chromosome names. Confirm the accepted VCF version and sample-count limits when submitting. Save the upload inventory and server QC reports before post-processing.

## Completion evidence

Retain external records for each batch: source delivery and array, original build, file checksums, sample ID mapping, sex metadata, filtering counts, exclusions and reasons, reference provenance, container SHA-256, command lines, tool versions and exit statuses. For each TOPMed job retain the upload checksums, job ID, panel/build, phasing engine, imputation engine, server version, completion date and report checksum.

For integration retain duplicate-sample concordance denominators, coverage comparisons, reviewed keep/remove decisions, REF validation, frequency audit, merged counts, residual relatedness and PCA review. Recalculate PCs after sample exclusions. A genotype merge, a passing source check or a matching job manifest alone does not establish analysis readiness.
