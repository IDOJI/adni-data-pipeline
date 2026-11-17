# Stage 4.B — Philips SliceTiming

**What:** Add missing Philips slice timing from matching NFQ records.

**Output:** Updated BIDS JSON sidecars and a slice-timing audit TSV, including the selected metadata row, available UID/date and match basis.

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

An explicit series-number mismatch is held as `series_number_conflict`; the
script never substitutes another series with a similar TR or slice count.
Available UID/date fields must agree, and repeated acquisition candidates remain
`ambiguous` unless their identity is uniquely resolved. TR and slice count only
validate an identity match. A unique legacy RID/visit/series match remains
supported when NFQ lacks stronger identifiers; its source identity still needs
the manual review above. Nonfinite timing and timing outside the metadata TR
cannot be written. These are owned-source safeguards added after the original
protocol import.

This follows the requirement for unambiguous Philips timing in the
[Rutherford et al. protocol preprint](https://pmc.ncbi.nlm.nih.gov/articles/PMC13692585/)
and the axis/direction semantics in the
[BIDS specification](https://bids-specification.readthedocs.io/en/stable/modality-specific-files/magnetic-resonance-imaging-data.html#timing-parameters).
The preprint has not been peer reviewed; it is a protocol reference, not a
validation of this adapter or a substitute for reviewing the actual acquisition.
