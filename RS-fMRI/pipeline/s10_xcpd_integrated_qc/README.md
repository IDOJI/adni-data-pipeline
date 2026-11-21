# Stage 10 — XCP-D denoising and imaging QC

Start with a [published 7.B pair](../s7b_sessionwise_preprocessing/README.md#publish-the-completed-pair) under `$RESULTS/results/`, or a completed pair delivered by the [batch runner](../../06_docs/local_batch.md). XCP-D checks preprocessed BOLD, confounds, MRIQC measures, FreeSurfer evidence and the successful execution receipts.

### Configure the input

For the [manual layout](../../06_docs/installation.md#paths-for-a-manual-run), set `root` to the directory **containing** `results/` and `runs/`. `license` points to the FreeSurfer license file and `templateflow` to the prepared cache. This block creates a private copy of the [seeded XCP-D profile](../../03_config/xcpd_linc.seeded.example.json) with those paths and the local-batch resource settings. If the batch or an earlier manual setup already created the JSON, use that file as `XCFG` and skip creation.

```sh
export XCFG="$RESULTS/xcpd.json"
python - <<'PY'
import json, os
from pathlib import Path
out = Path(os.environ["RESULTS"])
cfg = json.loads(Path("03_config/xcpd_linc.seeded.example.json").read_text())
batch = json.loads(Path("03_config/local_batch.seeded.example.json").read_text())
cfg.update(root=str(out), license=str(Path(os.environ["DATA"])/"license.txt"),
           templateflow=str(Path(os.environ["CASE"])/"templateflow"), resources=batch["xcpd_resources"])
with Path(os.environ["XCFG"]).open("x") as f:
    json.dump(cfg, f, indent=2)
PY
```

### Preview, run and check

**Preflight.** The [seeded XCP-D runner](pipeline_seeded.py) checks local paths and the installed XCP-D version. The dry run then checks the pair and writes the proposed Docker command in `postprocessing/<config_id>/dry_run.json`. Expect one candidate for one eligible run. For zero candidates, review `s10/<config_id>/pre_qc.json` in the published pair and the controller's `events.jsonl` if present.

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" preflight &&
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" dry-run
```

**Denoise one candidate.** The seeded LINC profile uses 36 nuisance regressors including global signal, 0.01–0.08 Hz filtering, 6 mm smoothing, FD 0.3 mm and a 240-second minimum. It produces denoised BOLD, 4S256Parcels time series and connectivity, ReHo and ALFF. Run once with one processing owner for this root.

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" pilot
```

**Collect and verify.** Read `final_qc_master.tsv` under `postprocessing/<config_id>/` and the pair's `qc_report.html`. The latest attempt under `s10/<config_id>/runs/<run>/attempt-*/` contains the evidence. For a successful denoised result, check `status: success`, `exit_code: 0` and `input_unchanged: true` in `execution.json`, plus `functional_outputs_valid: true` in `output_validation.json`. The validated images are under `derivatives/` in that attempt. Held scans and scans skipped for insufficient duration have separate outcomes.

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" collect
```

For an ongoing cohort, `watch` processes future published pairs after the pilot. After the **whole cohort** and visual review are complete, set `--mriqc-flags` to the reviewed cohort table, then run:

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" finalize \
  --cohort-complete --mriqc-flags "$DATA/review/cohort-mriqc-flags.tsv"
```

Pass the matching `final_included_runs.tsv` and `clinical_scan_links.tsv` from the same `finalizations/<timestamp>/` to [9.A · clinical validation](../s9a_validate_clinical/README.md).
