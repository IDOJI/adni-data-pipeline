# Stage 11 — Atlas BOLD signals

**What:** Extract one mean BOLD time series per ROI from reviewed denoised images.

**Output:** `timeseries.tsv`, `labels.tsv`, `frames.tsv`, `roi_coverage.tsv` and `artifact.json`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Set `--bold` to one reviewed denoised BOLD file and `--mask` to its matching brain mask. Both filenames must retain their BIDS entities. Set `--atlas` to a catalog ID in that template space, `--image-id` to the source EPI Image ID from the inclusion record, and the mapping flags to the directories generated for that run. These are study-specific inputs.

Install the selected atlas source and list matching-space atlases:

```sh
python pipeline/s11_atlas_bold/sources.py install --source CBIG
python pipeline/s11_atlas_bold/run.py list --space MNI152NLin6Asym
```

For one reviewed run, keep its two [adapter outputs](adapters.md) under `$RESULTS/audit/run-001/`. Set `MASK` to the matching brain mask. The command reads the denoised BOLD path and source image ID from that run link.

```sh
LINK_DIR="$RESULTS/audit/run-001/bids-link"
MASK="/absolute/path/to/your/matching_brain_mask.nii.gz"
BOLD=$(python - "$LINK_DIR/artifact.json" <<'PY'
import json, sys
record = json.load(open(sys.argv[1]))
image, = [path for path, digest in record["inputs_sha256"].items()
          if digest == record["summary"]["bold_sha256"] and path.endswith((".nii", ".nii.gz"))
          and "_desc-denoised_" in path]
print(image)
PY
) &&
IMAGE_ID=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["summary"]["image_id"])' "$LINK_DIR/artifact.json") &&
python pipeline/s11_atlas_bold/run.py extract \
  --bold "$BOLD" --mask "$MASK" \
  --atlas cbig_Schaefer2018_400Parcels_7Networks_order_FSLMNI152_2mm \
  --space MNI152NLin6Asym --input-kind denoised \
  --inclusion "$RESULTS/qc/step9b" --image-id "$IMAGE_ID" \
  --frame-map "$RESULTS/audit/run-001/acquisition-map" --run-link "$LINK_DIR" \
  --resample-labels --min-coverage 0.5 --output-dir "$RESULTS/atlas-signals/Schaefer400"
```

Use full BIDS filenames from your actual run. Create frame/run mapping evidence with [adapter commands](adapters.md); censored frames and rewritten session labels require the corresponding mapping. Atlas and BOLD must share a template space; resampling only adjusts the grid. This stage extracts signals, without additional denoising or FC estimation.
