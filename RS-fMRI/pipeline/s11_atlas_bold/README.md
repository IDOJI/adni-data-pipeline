# Stage 11 — Atlas BOLD signals

**What:** Extract one mean BOLD time series per ROI from reviewed denoised images.

**Output:** `timeseries.tsv`, `labels.tsv`, `frames.tsv`, `roi_coverage.tsv` and `artifact.json`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Install the selected atlas source and list matching-space atlases:

```sh
python pipeline/s11_atlas_bold/sources.py install --source CBIG
python pipeline/s11_atlas_bold/run.py list --space MNI152NLin6Asym
```

Extract with the matching brain mask and reviewed inclusion evidence:

```sh
python pipeline/s11_atlas_bold/run.py extract \
  --bold /ABS/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin6Asym_desc-denoised_bold.nii.gz \
  --mask /ABS/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz \
  --atlas cbig_Schaefer2018_400Parcels_7Networks_order_FSLMNI152_2mm \
  --space MNI152NLin6Asym --input-kind denoised \
  --inclusion "$DATA/qc/step9b" --image-id 999999999 \
  --frame-map /ABS/acquisition-map --run-link /ABS/bids-link \
  --resample-labels --min-coverage 0.5 --output-dir /ABS/atlas-signals/Schaefer400
```

Use full BIDS filenames from your actual run. Create frame/run mapping evidence with [adapter commands](adapters.md); censored frames and rewritten session labels require the corresponding mapping. Atlas and BOLD must share a template space; resampling only adjusts the grid. This stage extracts signals, without additional denoising or FC estimation.

## Evidence and limits

Sources: [Schaefer et al. (2018)](https://doi.org/10.1093/cercor/bhx179); [Mehta et al. (2024)](https://doi.org/10.1162/imag_a_00257). The [Stage 11 evidence record](../../06_docs/stage_evidence.md#stage-11) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
