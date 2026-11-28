# 3 · 🧠 Run preprocessing, denoising and quality checks

**Bring** the stage 2 binding receipt, your FreeSurfer license and a populated TemplateFlow cache. Use the [pinned Docker images and setup instructions](../../06_docs/installation.md#paths-for-a-manual-run). This local route uses the macOS clone-capable publisher; keep the study on a compatible volume such as APFS and share its location with Docker Desktop. The commands below start real processing.

```sh
python stages/03-imaging/run.py "$STUDY" run
```

The script checks the acquisition settings for each verified pair, runs **MRIQC** to measure image quality, runs **fMRIPrep** to align the scans, then runs **XCP-D** to denoise BOLD and calculate connectivity. It prints the path to `visual_review.tsv` under `03-imaging/postprocessing/`. Each acquisition has its own work and execution logs in `03-imaging/cases/I<image-id>/`. To start from a previous verified selection, add `--binding "/path/to/07.binding-receipt.json"`. If multiple acquisitions share a visit or dated output, review them and pass the chosen keys in a text file with `--pairs "/path/to/epi-keys.txt"`.

**Review the whole cohort.** Once processing is complete, fit the cohort MRIQC quality thresholds using the [seeded R environment](../../06_docs/seed_reproducibility.md). Look at the flags in `03-imaging/cohort-iqms/all_IQMs_with_QC_flags_clean.tsv`. Open the HTML reports listed in `visual_review.tsv`, especially for flagged registrations and brain masks. Record the requested decisions, reviewer and date there. [Visual review fields](../../pipeline/s10_xcpd_integrated_qc/README.md) · [Illustrated MRIQC/fMRIPrep examples and exclusion criteria (Table 3)](https://doi.org/10.3389/fnimg.2022.1073734)

```sh
python stages/03-imaging/run.py "$STUDY" iqms
```

**After review**, finalize imaging QC. If your cohort already has a reviewed MRIQC flags table, skip `iqms` and add `--mriqc-flags "/path/to/flags.tsv"` to this command. Pending reviews remain visible in the final table.

```sh
python stages/03-imaging/run.py "$STUDY" finalize --cohort-complete
```

**Check clinical eligibility.** Put `DXSUM.csv` and `PTDEMOG.csv` in `clindata/`. The script also reads `ADSL.csv`, `DM.csv` and `APOERES.csv` when supplied there. Add `review/confirmed-st-absence.csv` with columns `IMAGE_ID,PTID,MRI_STUDY_DATE,ST_STATUS,EVIDENCE_REF`. A header-only file means the review identified no confirmed slice-timing exclusions. For documented conversion exclusions, add `--conversion-failures "/path/to/failures.csv"`. [Clinical checks](../../pipeline/s9a_validate_clinical/README.md) · [Exclusion records](../../pipeline/s9b_validate_inclusion/README.md)

```sh
python stages/03-imaging/run.py "$STUDY" clinical
```

**Open** the printed final imaging QC table and `03-imaging/inclusion/inclusion_audit.tsv`. The first records imaging decisions. The second links scans to source QC and clinical eligibility. Stage 4 uses both. To apply clinical checks to existing imaging results, add `--final-qc "/path/to/finalizations/run/final_qc_master.tsv" --source-qc "/path/to/step3a" --scan-links "/path/to/audited-scan-links.tsv"`.

[Study setup](../setup.md) · [All stages](../../README.md)
