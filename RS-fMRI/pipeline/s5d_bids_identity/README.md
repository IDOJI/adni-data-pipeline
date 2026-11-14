# Stage 5.D — Exact EPI–T1 verification

**What:** Check a proposed image pair against Image IDs, UIDs, dates, file hashes and BIDS headers.

**Output:** Binding audit tables, `07.binding-receipt.json` and a separate verified pair runtime.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Create a private binding configuration with the proposed pairs, BIDS/source manifests and independent fingerprints. For multiple pairs, use the [local batch guide](../../06_docs/local_batch.md).

```sh
python pipeline/s5d_bids_identity/binding.py --config /ABS/binding.json
python pipeline/s5d_bids_identity/guarded_runner_seeded.py prepare \
  --receipt /ABS/binding/07.binding-receipt.json --epi-key EXACT_EPI_KEY \
  --runtime /ABS/new-pair-runtime --template /ABS/preprocessing-seeded.yaml
python pipeline/s5d_bids_identity/guarded_runner_seeded.py intake \
  --config /ABS/new-pair-runtime/verified-config.yaml
python pipeline/s5d_bids_identity/guarded_runner_seeded.py dry-run \
  --config /ABS/new-pair-runtime/verified-config.yaml --stage fmriprep
```

After intake passes, execute MRIQC, then fMRIPrep:

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py run \
  --config /ABS/new-pair-runtime/verified-config.yaml --stage mriqc
python pipeline/s5d_bids_identity/guarded_runner_seeded.py run \
  --config /ABS/new-pair-runtime/verified-config.yaml --stage fmriprep
```

The template uses [seed 1123 and OMP1](../../06_docs/seed_reproducibility.md). Unresolved identity or source-review cases stay held.
