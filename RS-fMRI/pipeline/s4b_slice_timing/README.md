# Stage 4.B — Philips SliceTiming

**What:** Add missing Philips slice timing from matching NFQ records.

**Output:** Updated BIDS JSON sidecars and a slice-timing audit TSV.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Set the BIDS, NFQ and report paths in `$PIPELINE_CONFIG`.

```sh
# Preview the proposed changes.
python pipeline/s4b_slice_timing/insert_philips_slicetiming.py \
  --config "$PIPELINE_CONFIG" --dry-run
# Apply after checking image identity, slice axis and acquisition order.
python pipeline/s4b_slice_timing/insert_philips_slicetiming.py \
  --config "$PIPELINE_CONFIG"
```

An NFQ match alone does not establish slice-axis/direction correctness; verify against the source acquisition before writing.
