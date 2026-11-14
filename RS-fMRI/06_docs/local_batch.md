# Local batch: MRIQC → fMRIPrep → XCP-D

**Input:** A verified raw-data handoff (`_handoff/batch_manifest.json`, `participants.tsv`, four hashed EPI/T1w NIfTI/JSON files per pair), source-review evidence, Docker images, TemplateFlow cache and a FreeSurfer license.

**Output:** Per-case derivatives/logs, published pair results, XCP-D/QC outputs and `status.html` under a new external runtime. Final clinical/research inclusion remains a separate step.

## Run

From `RS-fMRI/` after [setup](installation.md):

```sh
mkdir -p /ABS/private-config
cp 03_config/local_batch.seeded.example.json /ABS/private-config/batch.json
cp 03_config/xcpd_linc.seeded.example.json /ABS/private-config/xcpd.json
```

Edit the copies: set the handoff/source-review paths and fingerprints, fresh `root`, shared compute settings, image/license/template paths, and `xcpd_template=/ABS/private-config/xcpd.json`. Keep seed **1123** and `omp_nthreads=1` in both stages.

```sh
# Verify inputs and prepare the new runtime; no imaging yet.
python 04_workflow/local_batch_seeded.py --config /ABS/private-config/batch.json prepare
# Read preparation status.
python 04_workflow/local_batch_seeded.py --config /ABS/new-runtime/config/batch.json status
# Start MRIQC, fMRIPrep and XCP-D processing.
python 04_workflow/local_batch_seeded.py --config /ABS/new-runtime/config/batch.json watch
```

Use the actual `root` value in place of `/ABS/new-runtime`. Open `<root>/status.html` for progress and hold reasons.

| Location under root | Result |
|---|---|
| `cases/<subject>/` | BIDS, derivatives, work and attempt logs |
| `results/<PTID>/<pair>/` | Published preprocessing, XCP-D and QC reports |
| `control/jobs/`, `control/events.jsonl` | Per-case state and failure/hold records |

The controller permits at most five subjects, subject to available memory/disk reserves. Run one controller per runtime. This integrated publisher is macOS-specific; [Linux requires operational adapters](platform_execution.md). Existing batches retain their frozen source/configuration; seed 1123 runs need a fresh runtime.
