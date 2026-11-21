# Stage 4.B — Philips SliceTiming

**What:** Add missing Philips slice timing from matching NFQ records.

**Output:** Updated BIDS JSON sidecars and a slice-timing audit TSV.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

In the private YAML, set `paths.clinica_bids_dir` to the converted BIDS tree, `paths.adni_fmri_metadata_csv` to the matching NFQ table and `slice_timing.report_tsv` to your audit filename. Keep the original sidecars. Inspect the dry-run report before applying changes to the working BIDS copy. `SliceTiming` gives per-slice acquisition times; `PhaseEncodingDirection` requires separate evidence for the axis and sign.

```sh
# Preview the proposed changes.
python pipeline/s4b_slice_timing/insert_philips_slicetiming.py \
  --config "$PIPELINE_CONFIG" --dry-run
```

After checking image identity, slice axis and acquisition order, apply the reviewed changes:

```sh
python pipeline/s4b_slice_timing/insert_philips_slicetiming.py \
  --config "$PIPELINE_CONFIG"
```

An NFQ match alone does not establish slice-axis/direction correctness; verify against the source acquisition before writing.
