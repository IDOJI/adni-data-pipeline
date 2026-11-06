# Installation and execution

## Tools

The local helpers require Git and Python 3.10+. Upstream QC runs on Linux with Apptainer or Singularity and depends on PLINK 1.9/2, R, BCFtools/HTSlib, liftOver, EIGENSOFT, SNPWeights and the included reference-checking scripts.

The [upstream README](https://github.com/VUMC-VMAC/GWAS_QC/blob/5bbabfb54c2fffb86f39810386652daa124ce683/README.md) names `CNT_genomic_processing_v3.19.simg`, which is not included in the repository. Obtain the image or prepare a compatible environment, check dependencies such as `/SNPweights2.1/inferancestry.py`, and record the image checksum and tool versions.

The generated commands bind the pinned scripts at `/scripts/GWAS_QC`, data at `/input`, and references at `/ref`. Scripts and references are read-only. Bind source paths cannot contain commas or colons; relative paths must avoid spaces and shell metacharacters because upstream uses unquoted expansions.

## Inputs

| Resource | Format |
|---|---|
| Array genotypes | BED/BIM/FAM prefix per delivery batch; retain X data for sex checks |
| Sex metadata | Headerless FID, IID, sex; 1=male, 2=female, 0=unknown; complete sample mapping |
| TOPMed comparison table | `topmed_sites_stem.txt.gz` as read by the pinned pre-QC script |
| Variant-to-rsID mapping | `rsid_stem_chrN.txt` for part 1 and combined `rsid_stem.txt` for part 2 |
| SNPWeights | `snpweights_stem` and matching `snpweights_stem_snp.txt` |

Check each delivery's build and the reference files' origin, allele convention and coverage. The example configuration's `b37` values are illustrative. A legacy `freeze5` filename does not establish r3 compatibility.

## Run each batch

For an immediately runnable example with public data, use the [toy walkthrough](../07_toy/README.md). The commands below require your actual inputs and the runtime described above. Run from `SNP/`.

### 1. Configure paths

Set these paths once, copy the example, and edit its batch builds, input files and reference/runtime paths:

```sh
export SNP_CONFIG=/ABSOLUTE/PATH/private-snp-config.json
export SNP_LOGS=/ABSOLUTE/PATH/snp-logs
export SNP_BATCH=human610
cp 03_config/pipeline.example.json "$SNP_CONFIG"
python3 04_workflow/snp.py doctor
```

Check the generated commands:

```sh
python3 04_workflow/snp.py plan --config "$SNP_CONFIG"
```

### 2. Run pre-imputation QC

```sh
python3 04_workflow/snp.py run-stage --config "$SNP_CONFIG" \
  --batch "$SNP_BATCH" --stage preimputation \
  --log "$SNP_LOGS/$SNP_BATCH-pre.log"
```

This runs `gwas_qc_preimputation.sh`. Review counts and plots, and set `cleaned_genotypes` in the configuration to its final genotype output.

### 3. Complete hosted imputation

For upload, use sorted, bgzip-compressed chromosome VCFs with GT and GRCh38 `chr` names; see [TOPMed data preparation](https://statgen.github.io/tis-v2-docs/imputation/data-preparation/). For post-QC, provide decrypted `chr1.dose.vcf.gz` through `chr22.dose.vcf.gz` in each batch's imputation directory. The plan omits `-z`; keep decryption passwords outside logs.

This stage requires a TOPMed account and server submission. There is no local command here that substitutes for the service. Save its job settings, reports and original dosage VCFs, then complete the job-record check below before merging.

### 4. Run post-imputation part 1

```sh
python3 04_workflow/snp.py run-stage --config "$SNP_CONFIG" \
  --batch "$SNP_BATCH" --stage postimputation1 \
  --log "$SNP_LOGS/$SNP_BATCH-post1.log"
```

This runs `gwas_qc_postimputation_part1.sh`. Review ancestry assignments and populate `ancestry_subsets` with the resulting keep lists.

### 5. Run post-imputation part 2

For each reviewed ancestry label in the configuration:

```sh
export SNP_ANCESTRY=EUR
python3 04_workflow/snp.py run-stage --config "$SNP_CONFIG" \
  --batch "$SNP_BATCH" --stage "postimputation2:$SNP_ANCESTRY" \
  --log "$SNP_LOGS/$SNP_BATCH-post2-$SNP_ANCESTRY.log"
```

This runs `gwas_qc_postimputation_part2.sh` with `-p` to defer PCA until after merging. Repeat the batch stages for each array. `run-stage` requires the configured inputs and runtime, rejects existing output prefixes/logs, and captures stdout/stderr. A completed process still needs QC review.

## Record TOPMed jobs

Complete one copy of [topmed-job.example.json](../03_config/topmed-job.example.json) per autosomal batch from its server report. Keep the records, reports, upload checksums and private configuration outside the repository.

```sh
python3 04_workflow/snp.py check-jobs \
  --config /ABSOLUTE/PATH/private-snp-config.json \
  --records /ABSOLUTE/PATH/jobs/human610.json \
            /ABSOLUTE/PATH/jobs/omniexpress.json \
            /ABSOLUTE/PATH/jobs/omni25.json \
            /ABSOLUTE/PATH/jobs/gsa_v2.json
```

This checks that every configured batch has a record, all use r3/GRCh38, and recorded server and engine versions agree. Compare records with the original reports before [merging](merging.md).
