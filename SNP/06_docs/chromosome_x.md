# Chromosome X

Use the pinned upstream [X-chromosome scripts](https://github.com/VUMC-VMAC/GWAS_QC/blob/5bbabfb54c2fffb86f39810386652daa124ce683/README.md#x-chromosome-gwas-qc) separately from autosomes. The local command planner and BIM/FRQ helper cover autosomes only.

For a runnable example, complete toy Steps 0–9, then run from `SNP/`:

```sh
python3 07_toy/run.py x --run-dir "$SNP_TOY_RUN"
python3 07_toy/run.py verify --run-dir "$SNP_TOY_RUN"
```

The toy's X preparation runs in Step 2 and its final X sample set follows autosomal QC. For cohort data:

1. Run `gwas_qc_preimputation_chrX.sh` per batch. It removes samples with unknown sex and excludes variants for differential missingness (p ≤10⁻⁷) and female-only HWE (p <10⁻⁶). Check PAR/non-PAR handling, male ploidy and GRCh38 references.
2. Remove autosomal heterozygosity failures before uploading X to TOPMed r3. Save a separate X job record and report.
3. After final autosomal QC, run `gwas_qc_postimputation_chrX.sh` with typed X genotypes, sex metadata, SNP-name resources, ancestry keep lists and final autosomal prefixes. Keep comma-separated labels and paths in the same order.
4. Review typed-call restoration, HWE, MAF and heterozygous haploid calls. Reconcile the sample sets, then check duplicates and allele compatibility before merging X batches.

Check the script's actual `getopts` interface for `-c`; its README descriptions are inconsistent. X ploidy, PAR and sample handoffs still need separate validation.
