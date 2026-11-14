# Stage 7.B — Sessionwise preprocessing

**What:** Prepare and process selected T1w/BOLD pairs with MRIQC and surface-enabled fMRIPrep in Docker.

**Output:** `bids/`, `derivatives/{mriqc,fmriprep}/`, `work/`, `logs/` and timing reports under the configured runtime.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

For new batches, use the [batch runner](../../06_docs/local_batch.md), which also publishes completed pairs for S10. For a single pair, use [5.D](../s5d_bids_identity/README.md) when a binding receipt is available.

A standalone private YAML needs `runtime`, `source_bids`, source manifests/phase evidence, `source_templateflow`, image/license paths, `runs`, `output_spaces` and [seed/resource settings](../../06_docs/seed_reproducibility.md).

```sh
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml prepare
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml intake
# Continue only after intake passes.
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml dry-run --stage fmriprep --subject ADNI999S9999
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml run --stage mriqc --subject ADNI999S9999
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml run --stage fmriprep --subject ADNI999S9999
```

Use a new runtime. Direct case commands do not publish the S10 pair layout. The batch publisher/controller uses macOS-specific tools; see [host requirements](../../06_docs/platform_execution.md).
