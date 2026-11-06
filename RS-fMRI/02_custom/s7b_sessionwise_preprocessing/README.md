# Step 7.B — Sessionwise MRIQC/fMRIPrep service adapter

## Purpose

Continue the existing explicit-pair SB preprocessing service with integrated source code. This preserves the original sessionwise FreeSurfer, surface/CIFTI and image settings; it is separate from the surface-disabled 7.A volume profile.

## Input

External private YAML: runtime, source_bids, source_manifest, source_phase_evidence, source_templateflow, images, resources, runs, output_spaces, random_seed and freesurfer_license. Explicit-pair plans, archive members and source hashes remain in the existing private runtime. This is a compatibility adapter, not a new selection-table requirement or pairing inference system.

## Processing

`make_source_manifest.py` validates exact selected BIDS images/sidecars and independent phase evidence. `run.py` reuses pinned upstream Step 5 intake and launches the existing MRIQC/fMRIPrep Docker commands with read-only inputs. It preserves sessionwise anatomy, FreeSurfer reconstruction, requested standard/surface outputs and fsLR 91k. Input hashes, cache signatures, exact commands and original run provenance remain mandatory.

`observe.py` reconnects to existing containers without starting new calculations. Independently captured exit receipts protect auto-removed containers during controller replacement. `publish_pairs.py` publishes completed outputs under actual EPI/T1 dates while preserving internal BIDS paths.

## Output

Existing external bids/derivatives/work/logs and published pair directories. Original run records, failed attempts and caches remain in place. Completed outputs are reused rather than rerun.

## Execution

Run from `RS-fMRI/` with an external configuration. The live queue chooses this adapter only for new subjects; previously started subjects finish through their recorded legacy runner to preserve cache identity.

```sh
python 02_custom/s7b_sessionwise_preprocessing/run.py --config /ABSOLUTE/PATH/private.yaml dry-run --stage fmriprep --subject ADNI999S9999
python 04_workflow/queue_service.py --root /ABSOLUTE/PATH/runtime --deployment /ABSOLUTE/PATH/deployment.json
```

Do not start another controller on a managed runtime. See the [live-service handoff guide](../../06_docs/live_service_handoff.md).

## Validation

Synthetic tests cover legacy/new routing, unchanged surface/CIFTI options, preserved exit receipts, identity conflicts and the shared compute limit. Actual controller cutover separately records container IDs/start times before and after replacement.

## Dependencies

Python 3.11+, repository requirements, installed Docker images/templates, a valid license and pinned upstream. No image pulls or analysis-setting changes are required for a code-path handoff.

## macOS and Linux

The configured single-case `run.py` builds Linux-container argv on either POSIX host after path setup. The completed-pair publisher uses macOS `/bin/cp -cR`, and `queue_service.py` uses `/usr/bin/caffeinate`. Linux needs publisher/controller and service adapters before the complete automatic ADNI chain is available. Do not run Mac-specific publication or queue commands as a Linux deployment recipe.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s7b) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
