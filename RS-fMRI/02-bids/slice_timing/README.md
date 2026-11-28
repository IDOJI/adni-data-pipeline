# Stage 4.B — Philips SliceTiming

**What:** Add missing Philips slice timing from matching NFQ records.

**Output:** Updated BIDS JSON sidecars and a slice-timing audit TSV, including the selected metadata row, available UID/date and match basis.

## Run

From `RS-fMRI/`, after [setup](../../support/docs/installation.md). Replace example paths and IDs with your inputs.

For date-based sessions such as `ses-YYYYMMDD`, the NFQ row must match the participant RID, scan date and exact series UID. For the default study layout, preview the proposed changes from your terminal:

```sh
python 02-bids/slice_timing/insert_philips_slicetiming.py --dry-run \
  --bids-dir "$STUDY/02-bids/rawdata" --metadata-csv "$STUDY/LONI_download/clindata/NFQ.csv" \
  --report-tsv "$STUDY/review/philips-slice-timing.tsv"
```

If you use a private YAML, set `paths.clinica_bids_dir` to the converted BIDS tree, `paths.adni_fmri_metadata_csv` to the matching NFQ table and `slice_timing.report_tsv` to your audit filename. Keep the original sidecars. Inspect the dry-run report before applying changes to the working BIDS copy. `SliceTiming` gives per-slice acquisition times; `PhaseEncodingDirection` requires separate evidence for the axis and sign.

```sh
# Preview the proposed changes.
python 02-bids/slice_timing/insert_philips_slicetiming.py \
  --config "$PIPELINE_CONFIG" --dry-run
```

After checking image identity, slice axis and acquisition order, apply the reviewed changes:

```sh
python 02-bids/slice_timing/insert_philips_slicetiming.py \
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
and the slice-timing rationale studied by
[Sladky et al. (2011)](https://doi.org/10.1016/j.neuroimage.2011.06.078).
Physical slice-axis/direction verification remains an implementation requirement,
not a conclusion established by that paper for these ADNI acquisitions.
The preprint has not been peer reviewed; it is a protocol reference, not a
validation of this adapter or a substitute for reviewing the actual acquisition.

## Evidence and limits

Sources: [ADNI NFQ/slice-order answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=1822); [Sladky et al. (2011)](https://doi.org/10.1016/j.neuroimage.2011.06.078); [Rutherford et al. (2026)](https://doi.org/10.21203/rs.3.rs-11132707/v1). The [Stage 4.B evidence record](../../support/docs/stage_evidence.md#stage-4-b) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
