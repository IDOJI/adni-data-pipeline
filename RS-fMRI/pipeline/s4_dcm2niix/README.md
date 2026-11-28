# 📦 Convert selected Image IDs to BIDS

From the [study guide](../../README.md#convert), set `STUDY` and run these commands from `RS-fMRI/`. Install dcm2niix on your PATH. The stage reads the download list and the candidate registry from the same Stage 1 receipt.

```sh
python start/02_bids.py "$STUDY" convert
python start/02_bids.py "$STUDY" bind
```

### What happens to one image?

1. The script looks up the selected ID under `LONI_download/sourcedata/<participant>/<series>/<date>/I<number>/`. Unselected IDs are ignored. Both download tiers can be converted for inspection.
2. It checks the folder identity and the series UID of **every DICOM instance** against the registry. Available DICOM dates, recognizable participant IDs and ADNI IDs in source filenames must agree. It records the original instance hashes and runs dcm2niix once on those staged inputs.
3. One T1w or resting BOLD NIfTI and its JSON go to `sub-ADNI…/ses-YYYYMMDD/anat/` or `func/`. Each modality has its own run numbers, assigned by ascending Image ID across the full selected list for that day. This keeps repeat acquisitions distinct. The image header and geometry come from dcm2niix. The anonymized sidecar retains the verified series UID and Image ID for private linkage.
4. Inspect `rawdata/sourcedata/conversion/conversion-audit.tsv` under `02-bids/`. It has one row per selected ID, including missing inputs and ambiguous outputs. In the same folder, `conversion-hashes.csv` links each converted ID to its BIDS path, NIfTI hash and original JSON hash. The `series/` directory holds per-ID converter logs and the list of source DICOM files with their hashes. A split series is held for review. A nonzero exit reports incomplete coverage; successfully converted files remain available to bind.
5. `bind` reads the recorded fingerprints and checks the images, headers, acquisition identity and Stage 1 pairing policy. Missing phase direction, unverified slice timing or pending source QC can still hold a converted pair. See [pair verification](../s5d_bids_identity/README.md) and [Philips timing review](../s4b_slice_timing/README.md).

For corrected downloads, convert into a fresh directory and use that dataset's evidence automatically:

```sh
python start/02_bids.py "$STUDY" convert --bids "$STUDY/02-bids/revised-rawdata"
python start/02_bids.py "$STUDY" bind --bids "$STUDY/02-bids/revised-rawdata" --binding-dir "$STUDY/02-bids/revised-binding"
```

### Evidence and references

[dcm2niix](https://github.com/rordenlab/dcm2niix) · [BIDS MRI specification](https://bids-specification.readthedocs.io/en/stable/modality-specific-files/magnetic-resonance-imaging-data.html) · [Stage evidence](../../06_docs/stage_evidence.md#stage-4)
