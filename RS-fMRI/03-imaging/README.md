# 3 · 🧠 Process and check

### Run the tools

Use the verified pairs from step 2. This local route needs Docker, a FreeSurfer license, a populated TemplateFlow cache and a Docker-shared study folder on a compatible Mac volume such as APFS. [Imaging setup](../support/docs/installation.md#paths-for-a-manual-run)

```sh
python 03-imaging/run.py "$STUDY" run
```

MRIQC measures image quality. fMRIPrep lines up the brain images. XCP-D reduces noise and measures connections between brain regions.

### Review the images

When the whole group has finished, calculate its quality flags. This command uses the [study R environment](docs/seed_reproducibility.md).

```sh
python 03-imaging/run.py "$STUDY" iqms
```

Open `03-imaging/cohort-iqms/all_IQMs_with_QC_flags_clean.tsv` for the quality flags. Open the HTML reports listed in `visual_review.tsv`, whose path is printed by `run`. Look for brain outlines that do not line up or masks that miss part of the brain. Record your decision, name and date in the review table. [QC examples](https://doi.org/10.3389/fnimg.2022.1073734)

### Save the decisions

After reviewing the whole group, save the imaging decisions.

```sh
python 03-imaging/run.py "$STUDY" finalize --cohort-complete
```

### Check clinical eligibility

Put `DXSUM.csv` and `PTDEMOG.csv` in `LONI_download/clindata/`. Add `review/confirmed-st-absence.csv` with the columns below. Leave it header-only if the review found no confirmed slice-timing exclusions.

```csv
IMAGE_ID,PTID,MRI_STUDY_DATE,ST_STATUS,EVIDENCE_REF
```

```sh
python 03-imaging/run.py "$STUDY" clinical
```

**Open** the final imaging QC table printed by the script and `03-imaging/inclusion/inclusion_audit.tsv`. Together they tell you which scans can enter step 4.

**Next → [4 · Adjust for scanner differences](../04-harmonization/README.md)**
