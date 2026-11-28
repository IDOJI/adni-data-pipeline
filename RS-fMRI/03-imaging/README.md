# 3 · 🧠 Process and check

Clean the scans, then decide which are usable. You will stop once to look at the images yourself.

### Run the tools

Start with the verified pairs from step 2. This local run needs Docker, a FreeSurfer license, a populated TemplateFlow cache and a Docker-shared study folder on a compatible Mac volume such as APFS. [Imaging setup](../docs/installation.md#paths-for-a-manual-run)

```sh
python 03-imaging/run.py "$STUDY" run
```

MRIQC measures image quality. fMRIPrep lines up the brain images. XCP-D reduces noise and measures connections between brain regions.

### Review the images

When the whole group has finished, calculate its quality flags. This command uses the [study R environment](docs/seed_reproducibility.md).

```sh
python 03-imaging/run.py "$STUDY" iqms
```

Open `03-imaging/cohort-iqms/all_IQMs_with_QC_flags_clean.tsv` in your study folder. The processing command also prints the path to `visual_review.tsv`. Open the HTML reports listed there. Check whether the brain outlines line up and the masks cover the brain, especially for flagged scans. Record your decision, name and date in the review table. [Examples of poor-quality scans, Table 3](https://doi.org/10.3389/fnimg.2022.1073734) · [Review fields](xcpd_integrated_qc/README.md)

### Save the decisions

After reviewing the whole group, save the imaging decisions.

```sh
python 03-imaging/run.py "$STUDY" finalize --cohort-complete
```

**Prepare the three review files** before running the clinical check.

<details>
<summary>Filenames and required columns</summary>

Put `DXSUM.csv` and `PTDEMOG.csv` in `LONI_download/clindata/`. Supply `review/confirmed-st-absence.csv` with the columns `IMAGE_ID,PTID,MRI_STUDY_DATE,ST_STATUS,EVIDENCE_REF`. Use a header-only file when the review found no confirmed slice-timing exclusions.

</details>

```sh
python 03-imaging/run.py "$STUDY" clinical
```

**Open** the final imaging QC table printed by the script and `03-imaging/inclusion/inclusion_audit.tsv`. Together they tell you which scans can enter step 4.

<details>
<summary>Repeat scans, existing results and other options</summary>

- For an earlier verified selection, add `--binding "/path/to/07.binding-receipt.json"` to `run`. For repeat acquisitions sharing a visit or dated output, review the scans and pass the chosen keys with `--pairs "/path/to/epi-keys.txt"`. Find per-scan logs under `03-imaging/cases/I<image-id>/`.
- If you already reviewed the group’s MRIQC flags, pass `--mriqc-flags "/path/to/flags.tsv"` to `finalize` in place of running `iqms`. Pending reviews remain in the final table.
- The clinical check also reads `ADSL.csv`, `DM.csv` and `APOERES.csv` when available. Add `--conversion-failures "/path/to/failures.csv"` for documented exclusions. To use existing imaging results, supply `--final-qc "/path/to/finalizations/run/final_qc_master.tsv" --source-qc "/path/to/step3a" --scan-links "/path/to/audited-scan-links.tsv"`. [Clinical checks](validate_clinical/README.md) · [Eligibility rules](validate_inclusion/README.md)
- [Methods and code for each tool](../docs/protocol-index.md) · [Example settings](config/)

</details>

**Next → [4 · Adjust for scanner differences](../04-harmonization/README.md)**
