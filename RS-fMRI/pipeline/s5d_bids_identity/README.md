# Stage 5.D — Verify and prepare one EPI–T1 pair

For the [stage 2 walkthrough](../../README.md#convert), set your study path and run `python start/02_bids.py "$STUDY" bind` from `RS-fMRI/`.

The [direct converter](../s4_dcm2niix/README.md) writes the required conversion fingerprints during stage 2.

Start here for an ADNI resting-state EPI and same-day T1w that have passed source review. The binding program checks participant, scan date, image IDs, series UIDs, hashes and headers. It checks the BOLD phase-encoding axis/sign (`PhaseEncodingDirection`) and the acquisition time of each slice (`SliceTiming`) separately.

### 1. Choose the binding receipt

Set [your two paths](../../06_docs/installation.md#paths-for-a-manual-run) first. If you already have a receipt, set `RECEIPT` to that file. Its referenced source files, manifests and validation code must still be accessible at the recorded paths.

```sh
export RECEIPT="$DATA/binding/07.binding-receipt.json"
```

<details>
<summary>Create a receipt if you have the source evidence but no receipt yet</summary>

Set `STEP3B` to the output directory from a fresh [3.B selection](../s3b_image_selection/README.md). Adjust the BIDS and conversion-evidence paths to your inputs. `images` is the candidate image registry; `epi_manifest` lists proposed EPI/T1 pairs; `pairing_receipt` authenticates those two tables. `hash_evidence` contains independent conversion fingerprints with `SOURCE_PTID`, `STUDY_DATE`, `MODALITY`, `SOURCE_IMAGE_ID` and `NIFTI_SHA256`. `bids_roots` points to the dataset containing the actual NIfTI files and sidecars. The hash evidence must independently link each converted file to its source image. The JSON and binding audits go under `RESULTS`.

```sh
export STEP3B="$DATA/qc/step3b"
python - <<'PY'
import json, os
from pathlib import Path
data, out = Path(os.environ["DATA"]), Path(os.environ["RESULTS"])
selection = Path(os.environ["STEP3B"])
cfg = dict(images=str(selection/"00.candidate-images.csv"),
           epi_manifest=str(selection/"04.epi-analysis-manifest.csv"),
           pairing_receipt=str(selection/"07.run-manifest.json"), bids_roots=[str(data/"rawdata")],
           hash_evidence=[str(data/"hash-evidence.csv")], output_dir=str(out/"binding"))
with (out/"binding.json").open("x") as f:
    json.dump(cfg, f, indent=2)
PY
```

```sh
python pipeline/s5d_bids_identity/binding.py --config "$RESULTS/binding.json" &&
export RECEIPT="$RESULTS/binding/07.binding-receipt.json"
```

</details>

### 2. Prepare a private runtime

The preparation template supplies two host paths, `source_templateflow` and `freesurfer_license`. The published seed, images, output spaces and thread settings come from the [seeded configuration](../../03_config/local_batch.seeded.example.json). Run this block once for the new results folder.

```sh
python - <<'PY'
import json, os, yaml
from pathlib import Path
data, out = Path(os.environ["DATA"]), Path(os.environ["RESULTS"])
cfg = json.loads(Path("03_config/local_batch.seeded.example.json").read_text())["preprocessing_template"]
cfg.update(source_templateflow=str(data/"templateflow"), freesurfer_license=str(data/"license.txt"))
with (out/"preprocessing-template.yaml").open("x") as f:
    yaml.safe_dump(cfg, f)
PY
```

The next block selects the sole eligible `epi_key`. If several are listed, use `export EPI_KEY='your exact listed key'` and rerun this block. The guard revalidates the selection and copies its two compressed images and two JSON sidecars into the isolated workspace.

```sh
PAIR_KEY=$(python - "$RECEIPT" <<'PY'
import json, os, sys
from pathlib import Path
proof = json.loads(Path(sys.argv[1]).read_text())
plans = json.loads(Path(proof["outputs"]["plans"]["path"]).read_text())
keys = [p["epi_key"] for p in plans if p["preprocessing_ready"]]
key = os.environ.get("EPI_KEY")
if key is None and len(keys) == 1:
    key = keys[0]
if key not in keys:
    sys.exit(f"Select one verified EPI_KEY from {keys}")
print(key)
PY
) &&
python pipeline/s5d_bids_identity/guarded_runner_seeded.py prepare \
  --receipt "$RECEIPT" --epi-key "$PAIR_KEY" --runtime "$RESULTS/pair" \
  --template "$RESULTS/preprocessing-template.yaml"
```

### 3. Check intake

`CFG` points to the generated `pair/verified-config.yaml`. The guard rechecks the files; intake evaluates the scan protocol. Continue to [6 · MRIQC](../s6_mriqc/README.md) when `strict_upstream_eligible` is `True`. A held pair has details in `failed_checks`.

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py check --config "$CFG" &&
python pipeline/s5d_bids_identity/guarded_runner_seeded.py intake --config "$CFG" &&
cat "$CASE/results/step5/intake_decisions.tsv"
```

The template uses [seed 1123 and OMP1](../../06_docs/seed_reproducibility.md). Unresolved identity or source-review cases stay held.

## Readiness boundary

Binding verifies the exact EPI and proposed T1, including actual dates, unique UIDs, independent NIfTI hashes and BIDS header consistency. It checks source eligibility for both modalities and rejects duplicate EPI image assignments. A BIDS file with the same visit label is not a replacement for a missing proposed Image ID.

Scan-level source/JSON contradictions and scanner differences across EPI and T1 block execution. Both physical files must report comparable manufacturer and field strength; model is compared when available and otherwise recorded as unknown. Compare normalized vendor names and numeric strengths. A scanner match is not registration QC. Rebuild old 3.B v1 and 5.D receipts before using this path; unversioned Research pairing receipts still require the current physical checks.

The current executable path requires a unique, eligible `same_day_proposed` pair, documented EPI QC, no pairing-review hold and the reviewed GO/2/3 protocol scope. Cross-date candidates, top ties and protocol extensions remain held even if files exist. A 3.B review window does not authorize cross-date execution. See the [date-based selection guide](../../06_docs/date_based_selection.md) for the distinction between inventory, proposal and execution.

`PREPROCESSING_READY` is a technical handoff decision. `ANALYSIS_READY` remains false; anatomical quality, BOLD–T1 registration, denoising, motion/coverage checks and clinical/final inclusion still require their respective stages. Original acquisition dates and source provenance remain unchanged.

Prepare one runtime per EPI key. The [local batch](../../06_docs/local_batch.md) accepts a separately verified handoff with one pair per participant.

## Evidence and limits

Sources: [ADNI FAQ answers](https://adni.loni.usc.edu/help-faqs/faqs/); [ADNI EPI–T1 pairing answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=434); [Gorgolewski et al. (2016)](https://doi.org/10.1038/sdata.2016.44). The [Stage 5.D evidence record](../../06_docs/stage_evidence.md#stage-5-d) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
