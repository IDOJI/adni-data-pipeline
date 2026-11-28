# 1 · 🔎 Choose the scans

Find resting scans and a matching picture of the brain’s structure (T1) taken on the same day.

**Prepare** these files in your study folder.

- `collections/T1.csv` and `collections/EPI.csv` from ADNI IDA. Include phase, scan date, Image ID, participant ID and description. Include age at the scan for step 4.
- `LONI_download/clindata/MRIQC.csv` and the ADNI quality tables that apply to your scans. [Which ADNI tables to use](source_qc/README.md)

**Run.** Replace the two example paths with your code folder and study folder.

```sh
cd "/absolute/path/to/adni-data-pipeline/RS-fMRI"
source .venv/bin/activate
export STUDY="/absolute/path/to/my ADNI study"

python 01-selection/run.py "$STUDY"
```

**Open** `01-selection/images/09.download-candidates.txt` in your study folder. Scans listed in `10.download-for-qc-review.csv` still need quality review. Open `05.pairing-review.csv` for uncertain T1 matches.

**Next → [2 · Download and convert](../02-bids/README.md)**
