# Stage 7.A — Volume-only fMRIPrep and XCP-D

Use this profile for a BIDS session with T1w and resting BOLD. fMRIPrep produces MNI152NLin2009cAsym 2 mm volumes and confounds and skips FreeSurfer reconstruction. XCP-D uses aCompCor without global signal regression, FD 0.5 mm and a 240-second minimum.

### Configure your session

Set [your input and results paths](../../06_docs/installation.md#paths-for-a-manual-run). The example expects `$DATA/bids/dataset_description.json`, one `sub-*/ses-*/` folder with `func/*_task-rest*_bold.nii.gz` and its BIDS metadata, and a T1w under the session or subject `anat/` folder. Verify acquisition metadata for SyN correction.

| Field in the [seeded example](config.seeded.example.json) | What to set in your private copy |
|---|---|
| `paths.bids` | Root containing `dataset_description.json` |
| `fs_license`, `paths.templateflow` | Your FreeSurfer license and a writable copy of the template cache |
| `paths.fmriprep_output`, `paths.xcpd_output` | Separate derivative directories |
| `paths.fmriprep_work`, `paths.xcpd_work`, `paths.logs` | Separate work caches and run logs under your results folder |
| `runs` | Selected BIDS labels without `sub-` and `ses-` |

This block fills those fields from your two paths. It selects the only session automatically. For a dataset with several sessions, first set `BIDS_SESSION` to the intended folder relative to the BIDS root (in the form `sub-label/ses-label`). Keep the seed, images, output space and denoising settings for reproducibility.

```sh
python - <<'PY'
import json, os, shutil
from pathlib import Path
data, out = Path(os.environ["DATA"]), Path(os.environ["RESULTS"])
bids = data / "bids"
sessions = sorted(p for p in bids.glob("sub-*/ses-*") if p.is_dir())
if os.environ.get("BIDS_SESSION"):
    sessions = [p for p in sessions if str(p.relative_to(bids)) == os.environ["BIDS_SESSION"]]
if len(sessions) != 1:
    raise SystemExit("Export BIDS_SESSION with one existing sub-label/ses-label and retry.")
session, = sessions
cfg = json.loads(Path("pipeline/s7a_volume_workflow/config.seeded.example.json").read_text())
cfg["runs"] = [{"subject": session.parent.name[4:], "session": session.name[4:]}]
cfg["paths"] = {k: str(out/k) for k in cfg["paths"]}
cfg["paths"]["bids"] = str(bids)
cfg["fs_license"] = str(data/"license.txt")
cache = (data/"templateflow").resolve()
if (out/"templateflow").resolve().is_relative_to(cache):
    raise SystemExit("Choose a results directory outside the input TemplateFlow cache.")
shutil.copytree(cache, out/"templateflow")
with (out/"volume.json").open("x") as f:
    json.dump(cfg, f, indent=2)
PY
```

### Run fMRIPrep

The [volume runner](pipeline_seeded.py) reads the selected labels from your configuration. Repeat this block when returning in a new terminal. A successful preview prints the Docker arguments. If you see `ERROR`, correct the indicated input before continuing.

```sh
export VOL="$RESULTS/volume.json"
SUB=$(python -c 'import json,sys; run, = json.load(open(sys.argv[1]))["runs"]; print(run["subject"])' "$VOL") &&
SES=$(python -c 'import json,sys; run, = json.load(open(sys.argv[1]))["runs"]; print(run["session"])' "$VOL") &&
python pipeline/s7a_volume_workflow/pipeline_seeded.py --config "$VOL" dry-run \
  --stage fmriprep --subject "$SUB" --session "$SES"
```

```sh
python pipeline/s7a_volume_workflow/pipeline_seeded.py --config "$VOL" run \
  --stage fmriprep --subject "$SUB" --session "$SES"
```

```sh
python pipeline/s7a_volume_workflow/pipeline_seeded.py --config "$VOL" verify \
  --stage fmriprep --subject "$SUB" --session "$SES"
```

Continue when `verify` prints `structural_checks_passed_visual_and_scientific_qc_required`. Inspect the HTML report, preprocessed BOLD and confounds under `$RESULTS/fmriprep_output/`.

### Run XCP-D

Use the same labels and config after fMRIPrep passes verification. Even the XCP-D preview reads the fMRIPrep output for that session. This profile skips parcellation, ReHo and ALFF.

```sh
python pipeline/s7a_volume_workflow/pipeline_seeded.py --config "$VOL" dry-run \
  --stage xcpd --subject "$SUB" --session "$SES"
```

```sh
python pipeline/s7a_volume_workflow/pipeline_seeded.py --config "$VOL" run \
  --stage xcpd --subject "$SUB" --session "$SES"
```

```sh
python pipeline/s7a_volume_workflow/pipeline_seeded.py --config "$VOL" verify \
  --stage xcpd --subject "$SUB" --session "$SES"
```

Look for the same successful verification status, then review the denoised BOLD and report under `$RESULTS/xcpd_output/`. Attempt records and command lines are in `$RESULTS/logs/`. The separate [output audit](audit_outputs.py) expects a staged archive layout with `bids/`, `derivatives/` and a staging manifest; use its `--help` for that layout.
