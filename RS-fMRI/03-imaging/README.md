# 3 · 🧠 Run preprocessing, denoising and quality checks

**Bring** the stage 2 binding receipt, your FreeSurfer license and a populated TemplateFlow cache. Use the [pinned Docker images and setup instructions](../docs/installation.md#paths-for-a-manual-run). This local route uses the macOS clone-capable publisher; keep the study on a compatible volume such as APFS and share its location with Docker Desktop. The commands below start real processing.

```sh
python 03-imaging/run.py "$STUDY" run
```

The script checks the acquisition settings for each verified pair, runs **MRIQC** to measure image quality, runs **fMRIPrep** to align the scans, then runs **XCP-D** to denoise BOLD and calculate connectivity. It prints the path to `visual_review.tsv` under `03-imaging/postprocessing/`. Each acquisition has its own work and execution logs in `03-imaging/cases/I<image-id>/`. To start from a previous verified selection, add `--binding "/path/to/07.binding-receipt.json"`. If multiple acquisitions share a visit or dated output, review them and pass the chosen keys in a text file with `--pairs "/path/to/epi-keys.txt"`.

**Review the whole cohort.** Once processing is complete, fit the cohort MRIQC quality thresholds using the [seeded R environment](../docs/seed_reproducibility.md). Look at the flags in `03-imaging/cohort-iqms/all_IQMs_with_QC_flags_clean.tsv`. Open the HTML reports listed in `visual_review.tsv`, especially for flagged registrations and brain masks. Record the requested decisions, reviewer and date there. [Visual review fields](xcpd_integrated_qc/README.md) · [Illustrated MRIQC/fMRIPrep examples and exclusion criteria (Table 3)](https://doi.org/10.3389/fnimg.2022.1073734)

```sh
python 03-imaging/run.py "$STUDY" iqms
```

**After review**, finalize imaging QC. If your cohort already has a reviewed MRIQC flags table, skip `iqms` and add `--mriqc-flags "/path/to/flags.tsv"` to this command. Pending reviews remain visible in the final table.

```sh
python 03-imaging/run.py "$STUDY" finalize --cohort-complete
```

**Check clinical eligibility.** Put `DXSUM.csv` and `PTDEMOG.csv` in `clindata/`. The script also reads `ADSL.csv`, `DM.csv` and `APOERES.csv` when supplied there. Add `review/confirmed-st-absence.csv` with columns `IMAGE_ID,PTID,MRI_STUDY_DATE,ST_STATUS,EVIDENCE_REF`. A header-only file means the review identified no confirmed slice-timing exclusions. For documented conversion exclusions, add `--conversion-failures "/path/to/failures.csv"`. [Clinical checks](validate_clinical/README.md) · [Exclusion records](validate_inclusion/README.md)

```sh
python 03-imaging/run.py "$STUDY" clinical
```

**Open** the printed final imaging QC table and `03-imaging/inclusion/inclusion_audit.tsv`. The first records imaging decisions. The second links scans to source QC and clinical eligibility. Stage 4 uses both. To apply clinical checks to existing imaging results, add `--final-qc "/path/to/finalizations/run/final_qc_master.tsv" --source-qc "/path/to/step3a" --scan-links "/path/to/audited-scan-links.tsv"`.

[Study setup](../stages/setup.md) · [All stages](../README.md)

## Implementation

- [Ants iteration logging](ants_iteration_logging/README.md)
- [Clinical imaging merge](clinical_imaging_merge/README.md)
- [Final qc](final_qc/README.md)
- [Fmriprep](fmriprep/README.md)
- [Metrics summary](metrics_summary/README.md)
- [Motion duration qc](motion_duration_qc/README.md)
- [Mriqc](mriqc/README.md)
- [Processing timing](processing_timing/README.md)
- [Reproducibility](reproducibility/README.md)
- [Sessionwise preprocessing](sessionwise_preprocessing/README.md)
- [Validate clinical](validate_clinical/README.md)
- [Validate inclusion](validate_inclusion/README.md)
- [Volume workflow](volume_workflow/README.md)
- [Xcpd integrated qc](xcpd_integrated_qc/README.md)
