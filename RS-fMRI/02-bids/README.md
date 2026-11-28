# 2 · 📦 Download and convert

Turn each selected scan into a file the analysis tools can read. BIDS is the folder and naming format those tools use.

**Download.** Request the Image IDs from step 1 in ADNI IDA. Choose DICOM. Unzip the download so the participant folders sit directly inside `$STUDY/LONI_download/sourcedata/`.

**Convert** one Image ID at a time with dcm2niix.

```sh
python 02-bids/run.py "$STUDY" convert
```

**Check** `02-bids/rawdata/sourcedata/conversion/conversion-audit.tsv` in your study folder. Find each ID and its new filename. A missing or held scan has a reason in the same row.

**Verify the pairs.** This checks each converted file against its source record and matches the resting scan to its T1.

```sh
python 02-bids/run.py "$STUDY" bind
```

**Open** `02-bids/binding/04.epi-execution-manifest.csv`. Only pairs marked ready can go to step 3.

<details>
<summary>Missing scans, a different download folder, or existing BIDS files?</summary>

- The expected download layout is `<participant>/<series>/<date>/I<number>/`. For another location, add `--dicom "/path/to/participant-folders"` to `convert`.
- Same-day repeats get separate run numbers. The adjacent `conversion-hashes.csv` records a fingerprint of each converted image. After correcting a download, use a [fresh output directory](dcm2niix/README.md). For Philips scans missing slice timing, [review the source timing](slice_timing/README.md) before binding.
- With existing BIDS, run `python 02-bids/run.py "$STUDY" bind --bids "/path/to/rawdata" --evidence "/path/to/conversion-hashes.csv"`. Use `--selection "/path/to/07.run-manifest.json"` for a selection receipt stored elsewhere. [Evidence formats](bids_identity/README.md)

</details>

**Next → [3 · Process and check](../03-imaging/README.md)**
