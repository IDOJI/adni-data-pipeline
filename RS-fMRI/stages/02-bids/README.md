# 2 · 📦 Download the images and convert them to BIDS

**📥 Download.** In ADNI IDA, request the Image IDs in `01-selection/images/09.download-candidates.txt` as DICOM. Extract the download so that `$STUDY/LONI_download/sourcedata/` contains the participant folders, with `<participant>/<series>/<date>/I<number>/` underneath. If the download is elsewhere, add `--dicom "/path/to/participant-folders"` to the conversion command.

```sh
python stages/02-bids/run.py "$STUDY" convert
```

**🔍 Check the download.** Open `02-bids/rawdata/sourcedata/conversion/conversion-audit.tsv`. There is one row per selected ID. For each match, the script runs dcm2niix on that ID alone and records the original series UID, the BIDS filename and a SHA-256 fingerprint in `conversion-hashes.csv` beside the audit. Repeat scans on the same date get separate run numbers. Missing, conflicting or split series have a reason in the audit. If you correct the download, use a [fresh output directory](../../pipeline/s4_dcm2niix/README.md). For Philips scans that need slice timing, review the [source-based repair guide](../../pipeline/s4b_slice_timing/README.md) before the next command.

```sh
python stages/02-bids/run.py "$STUDY" bind
```

**✅ Check which pairs can proceed.** Open `02-bids/binding/04.epi-execution-manifest.csv`. Binding checks the actual NIfTI against the recorded fingerprint, the acquisition identity, source QC and the proposed same-day T1 reference. Stage 3 reads the resulting binding receipt.

**Already have BIDS and independent conversion records?** Run `python stages/02-bids/run.py "$STUDY" bind --bids "/path/to/rawdata" --evidence "/path/to/conversion-hashes.csv"`. If the selection receipt is elsewhere, add `--selection "/path/to/07.run-manifest.json"`. [Evidence formats](../../pipeline/s5d_bids_identity/README.md)

[Study setup](../setup.md) · [All stages](../../README.md)
