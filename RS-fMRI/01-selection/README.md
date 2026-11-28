# 1 · 🔎 Choose the scans

Find resting scans and a matching picture of the brain’s structure (T1) taken on the same day.

**Prepare.** In [your study folder](../docs/setup.md), put the two scan lists from ADNI in `collections/T1.csv` and `collections/EPI.csv`. Put the ADNI quality tables in `LONI_download/clindata/`.

<details>
<summary>Which columns and quality tables do I need?</summary>

Export the phase, scan date, Image ID, participant ID and description for each scan. Include age at the scan for step 4.

Use `MRIQC.csv`, `MAYO_ADNI3.csv`, `MAYO_GO2.csv`, `DELMRSCANS.csv` and `NFQ.csv`. Check which tables cover your ADNI phases. Here `MRIQC.csv` is a file from ADNI. [ADNI account](setup_account/README.md) · [Source quality checks](source_qc/README.md)

</details>

**Run** from the repository’s `RS-fMRI/` folder.

```sh
python 01-selection/run.py "$STUDY"
```

**Open** `01-selection/images/09.download-candidates.txt` in your study folder. Take those IDs to step 2. Scans listed in `10.download-for-qc-review.csv` still need quality review. Uncertain T1 matches are in `05.pairing-review.csv` beside it.

<details>
<summary>Different filenames or questions about selection?</summary>

Add `--t1 "/path/to/structural.csv" --epi "/path/to/rest.csv"` to the command. [Selection rules](image_selection/README.md) · [Method notes](docs/) · [Example settings](config/)

</details>

**Next → [2 · Download and convert](../02-bids/README.md)**
