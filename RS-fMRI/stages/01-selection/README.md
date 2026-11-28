# 1 · 🔎 Select the scans

**Bring** the two IDA collection CSVs and the original ADNI source-quality tables. Use `collections/T1.csv` for structural scans and `collections/EPI.csv` for resting-state scans. Include **Phase**, **acquisition date**, **Image ID**, **participant ID** and description in each export. Include **Age at the scan** if you plan to harmonize connectivity. Place `MRIQC.csv`, `MAYO_ADNI3.csv`, `MAYO_GO2.csv`, `DELMRSCANS.csv` and `NFQ.csv` in `LONI_download/clindata/`. The script lists missing optional tables. Check which source files apply to your ADNI phases before using the download list. Here `MRIQC.csv` is a table supplied by ADNI. The MRIQC software runs in stage 3.

```sh
python stages/01-selection/run.py "$STUDY"
```

**Open** `01-selection/images/09.download-candidates.txt` for the IDs to request. The script checks source QC and proposes a structural reference by actual scan date. `05.pairing-review.csv` explains uncertain matches. `10.download-for-qc-review.csv` identifies images that can be retrieved for inspection but still need quality evidence. Different export filenames? Pass their paths, for example `--t1 "/path/to/structural.csv" --epi "/path/to/rest.csv"`. [Selection details](../../pipeline/s3b_image_selection/README.md)

[Study setup](../setup.md) · [All stages](../../README.md)
