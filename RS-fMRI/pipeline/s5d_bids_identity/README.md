# Stage 5.D — Exact EPI–T1 verification

**What:** Check a proposed image pair against Image IDs, UIDs, dates, file hashes and BIDS headers.

**Output:** Binding audit tables, `07.binding-receipt.json` and a separate verified pair runtime.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Create a private binding configuration with the proposed pairs, BIDS/source manifests and independent fingerprints. New collection-driven runs use the [3.B outputs](../s3b_image_selection/README.md):

```json
{
  "images": "/ABS/qc/step3b/00.candidate-images.csv",
  "epi_manifest": "/ABS/qc/step3b/04.epi-analysis-manifest.csv",
  "pairing_receipt": "/ABS/qc/step3b/07.run-manifest.json",
  "bids_roots": ["/ABS/rawdata"],
  "hash_evidence": ["/ABS/conversion/image-hashes.csv"],
  "output_dir": "/ABS/qc/new-binding"
}
```

The independent hash-evidence CSV uses `SOURCE_IMAGE_ID`, `SOURCE_PTID`, `STUDY_DATE`, `MODALITY` (`T1` or `EPI`) and `NIFTI_SHA256`. It must establish the converted file's source identity; hashing an arbitrary BIDS file alone does not establish its origin. Use conversion or independently verified handoff evidence. The runner validates the pairing receipt's input/output hashes; existing supported Research receipts remain readable.

For multiple EPI acquisitions from one participant, prepare a separate guarded runtime per EPI key. The [local batch guide](../../06_docs/local_batch.md) describes its different, one-pair-per-participant handoff contract; it does not directly consume this EPI manifest.

```sh
python pipeline/s5d_bids_identity/binding.py --config /ABS/binding.json
python pipeline/s5d_bids_identity/guarded_runner_seeded.py prepare \
  --receipt /ABS/qc/new-binding/07.binding-receipt.json --epi-key EXACT_EPI_KEY \
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

## Readiness boundary

Binding verifies the exact EPI and proposed T1, including actual dates, unique UIDs, independent NIfTI hashes and BIDS header consistency. It checks source eligibility for both modalities and rejects duplicate EPI image assignments. A BIDS file with the same visit label is not a replacement for a missing proposed Image ID.

The current executable path requires a unique, eligible `same_day_proposed` pair, documented EPI QC, no pairing-review hold and the reviewed GO/2/3 protocol scope. Cross-date candidates, top ties and protocol extensions remain held even if files exist. A 3.B review window does not authorize cross-date execution. See the [date-based selection guide](../../06_docs/date_based_selection.md) for the distinction between inventory, proposal and execution.

`PREPROCESSING_READY` is a technical handoff decision. `ANALYSIS_READY` remains false; anatomical quality, BOLD–T1 registration, denoising, motion/coverage checks and clinical/final inclusion still require their respective stages. Original acquisition dates and source provenance remain unchanged.

## Evidence and limits

Sources: [ADNI FAQ answers](https://adni.loni.usc.edu/help-faqs/faqs/); [ADNI EPI–T1 pairing answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=434); [Gorgolewski et al. (2016)](https://doi.org/10.1038/sdata.2016.44). The [Stage 5.D evidence record](../../06_docs/stage_evidence.md#stage-5-d) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
