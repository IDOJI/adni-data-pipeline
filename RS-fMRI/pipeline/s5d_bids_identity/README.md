# Stage 5.D — Verify and prepare one EPI–T1 pair

Start here for an ADNI resting-state EPI and same-day T1w that have passed source review. The binding program checks participant, scan date, image IDs, series UIDs, hashes and headers. It checks the BOLD phase-encoding axis/sign (`PhaseEncodingDirection`) and the acquisition time of each slice (`SliceTiming`) separately.

### 1. Choose the binding receipt

Set [your two paths](../../06_docs/installation.md#paths-for-a-manual-run) first. If you already have a receipt, set `RECEIPT` to that file. Its referenced source files, manifests and validation code must still be accessible at the recorded paths.

```sh
export RECEIPT="$DATA/binding/07.binding-receipt.json"
```

<details>
<summary>Create a receipt if you have the source evidence but no receipt yet</summary>

Change the entries below only if your input layout differs. `images` is the candidate image registry; `epi_manifest` lists proposed EPI/T1 pairs; `pairing_receipt` authenticates those two tables. `hash_evidence` contains independent conversion fingerprints with `SOURCE_PTID`, `STUDY_DATE`, `MODALITY`, `SOURCE_IMAGE_ID` and `NIFTI_SHA256`. `bids_roots` points to the dataset containing the actual NIfTI files and sidecars (use `rawdata` if that is your Clinica output). The JSON copy and binding audits go under `RESULTS`.

```sh
python - <<'PY'
import json, os
from pathlib import Path
data, out = Path(os.environ["DATA"]), Path(os.environ["RESULTS"])
cfg = dict(images=str(data/"candidate-audit.csv"), epi_manifest=str(data/"04.epi-analysis-manifest.csv"),
           pairing_receipt=str(data/"pairing-run-manifest.json"), bids_roots=[str(data/"bids")],
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
