# 2 · 📦 Download and convert

Turn each selected scan into a file the analysis tools can read. BIDS is the folder and naming format those tools use.

**Download** the Image IDs from step 1 as DICOM in ADNI IDA. Unzip them under `$STUDY/LONI_download/sourcedata/<participant>/<series>/<date>/I<number>/`.

**Convert** one Image ID at a time with dcm2niix.

Use the same study folder you used in step 1.

```sh
cd "/absolute/path/to/adni-data-pipeline/RS-fMRI"
source .venv/bin/activate
export STUDY="/absolute/path/to/my ADNI study"

python 02-bids/run.py "$STUDY" convert
```

**Check** `02-bids/rawdata/sourcedata/conversion/conversion-audit.tsv` in your study folder. Find each ID and its new filename. A missing or held scan has a reason in the same row.

**Verify the pairs.** This checks the Image ID, series UID and file fingerprint and matches the resting scan to its T1. [Philips scans with missing slice timing](slice_timing/README.md)

```sh
python 02-bids/run.py "$STUDY" bind
```

**Open** `02-bids/binding/04.epi-execution-manifest.csv`. Only pairs marked ready can go to step 3.

**Next → [3 · Process and check](../03-imaging/README.md)**
