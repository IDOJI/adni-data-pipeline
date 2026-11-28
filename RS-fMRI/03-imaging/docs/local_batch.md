# Local batch: MRIQC → fMRIPrep → XCP-D

**Input:** A verified raw-data handoff (`_handoff/batch_manifest.json`, `participants.tsv`, four hashed EPI/T1w NIfTI/JSON files per pair), source-review evidence, Docker images, TemplateFlow cache and a FreeSurfer license.

**Output:** Per-case derivatives/logs, published pair results, XCP-D/QC outputs and `status.html` under a new external runtime. Final clinical/research inclusion remains a separate step.

For new collection exports, start with [3.B date-based selection](../../01-selection/image_selection/README.md) and [5.D exact BIDS binding](../../02-bids/bids_identity/README.md). This controller accepts **one pair per participant per runtime**; it is not an adapter for the complete EPI inventory and does not consume the 3.B CSV directly. Preserve all proposed EPI rows and use separate 5.D guarded runtimes per EPI when a participant has multiple acquisitions. Never collapse them by VISCODE or replace an existing participant entry with a later pair.

## Run

From `RS-fMRI/` after [setup](../../support/docs/installation.md):

```sh
mkdir -p /ABS/private-config
cp config/local_batch.seeded.example.json /ABS/private-config/batch.json
cp config/xcpd_linc.seeded.example.json /ABS/private-config/xcpd.json
```

Edit the copies: set the handoff/source-review paths and fingerprints, fresh `root`, shared compute settings, image/license/template paths, and `xcpd_template=/ABS/private-config/xcpd.json`. Keep seed **1123** and `omp_nthreads=1` in both stages.

The current XCP-D template requires `qc_policy_version=sessionwise-euler-nss-v1`, automatic non-steady-state removal and explicit Euler reference settings. The default minimum of 10 independent reference participants is a project safeguard, not a universal published cutoff. Existing frozen runtimes are not migrated in place; missing/old policy versions reject before creating a new S10 runtime.

```sh
# Verify inputs and prepare the new runtime; no imaging yet.
python workflow/local_batch_seeded.py --config /ABS/private-config/batch.json prepare
# Read preparation status.
python workflow/local_batch_seeded.py --config /ABS/new-runtime/config/batch.json status
# Start MRIQC, fMRIPrep and XCP-D processing.
python workflow/local_batch_seeded.py --config /ABS/new-runtime/config/batch.json watch
```

Use the actual `root` value in place of `/ABS/new-runtime`. Open `<root>/status.html` for progress and hold reasons.

| Location under root | Result |
|---|---|
| `cases/<subject>/` | BIDS, derivatives, work and attempt logs |
| `results/<PTID>/<pair>/` | Published preprocessing, XCP-D and QC reports |
| `control/jobs/`, `control/events.jsonl` | Per-case state and failure/hold records |

The controller permits at most five subjects, subject to available memory/disk reserves. Run one controller per runtime. This integrated publisher is macOS-specific; [Linux requires operational adapters](../../support/docs/platform_execution.md). Existing batches retain their frozen source/configuration; seed 1123 runs need a fresh runtime.
