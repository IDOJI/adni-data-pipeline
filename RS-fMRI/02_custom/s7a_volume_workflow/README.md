# Step 7.A — Docker volume workflow (aCompCor profile)

For new fixed-seed runs, use `pipeline_seeded.py` and `config.seeded.example.json` with separate new output/work/log paths. This retains the volume/aCompCor profile and adds seed 357, OMP1 and fixed skull stripping. See the [seed contract](../../06_docs/seed_reproducibility.md). Original launcher commands below remain the historical compatibility route.

## Execution

```sh
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json dry-run --stage fmriprep --subject 999S9999
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** First prints the Docker command for the separate volume/aCompCor profile. The explicitly selected `run` commands below perform the imaging calculations.

**Results:** External volume-profile derivatives and attempt evidence; `verify` checks the recorded stage output. Keep this profile separate from 7.B/S10.

Run from `RS-fMRI/` with an actual external configuration. Container downloads and processing occur only when the corresponding commands below are explicitly executed.

For metadata finalization of a previously successful XCP-D run, use `finalize-xcpd --stage xcpd` with the same configuration/subject. It checks success, unchanged inputs and execution identity while preserving the original run record. Do not relocate active containers or invent cache identities to bypass checks.

### Execute the selected profile

```sh
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json run --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json verify --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json run --stage xcpd --subject 999S9999
python 02_custom/s7a_volume_workflow/audit_outputs.py --data-root /ABSOLUTE/PATH/ADNI_DATA/volume --subject 999S9999 --session 20200101 --output /ABSOLUTE/PATH/ADNI_DATA/volume-qc/audit.json
```

These are real processing/verification commands. Run the fMRIPrep calculation to completion before verifying it or launching XCP-D; use the same reviewed configuration and subject. The final audit writes its report to the explicit external path.

## Purpose

This consolidates fMRIPrep → XCP-D volume execution, audit, image QC and guarded metadata repair from the former local `adni-rsfmri-pipeline`. It preserves different scientific settings from S10's newer 36P/LINC workflow. Do not run it alongside upstream Step 7 against the same output/cache.

| Setting | This workflow | Main S10 postprocessing |
|---|---|---|
| Standard space | MNI152NLin2009cAsym/res-2 | MNI152NLin6Asym/res-2 |
| Regression | aCompCor, no GSR | 36P, including GSR |
| FD / minimum retained time | 0.5 mm / 240 seconds | 0.3 mm / 240 seconds |
| FreeSurfer reconstruction | Disabled | Completed FreeSurfer outputs required for S8 Euler |
| ROI/FC | Omitted in this profile | 4S256 ROI/FC and coverage validation |

## Input

Requires actual BIDS T1w/rest BOLD data with original metadata, a separate FreeSurfer license and external JSON configuration. Participants in `config.example.json` are synthetic examples. Set all runtime/data paths to actual locations outside the repository. The supported unit is an explicit subject/session, not a generalized multi-run/multi-echo workflow.

## Processing

- Resolve pinned fMRIPrep 25.2.7 and XCP-D 26.2.0 tags to installed immutable digests; execute argv lists without a shell.
- Record read-only input mounts, before/after SHA-256, commands, configuration, runner snapshots, CITATION files and cache identity.
- `repair_xcpd_metadata.py`: conditionally repair only the known missing units, preserving compressed originals, before/after headers and proof of unchanged voxel payloads. Arbitrary header edits are prohibited.
- `audit_outputs.py`: compare confounds/Power FD, censoring, output volumes, settings and reports. `qc_images.py`: check voxel finiteness/temporal variance and render registration mosaics. Image generation does not replace human visual review.

## Output

Derivatives/work/logs under external `paths`, plus independent QC JSON/PNG files. Distinguish execution completion, technical checks and visual/scientific decisions. Detailed historical results for the two actual visits and private configuration remain only in the local archive.

## Validation

The existing synthetic execution, failure recovery, header/voxel invariance, independent audit and image-QC tests were ported to `05_tests/volume_workflow/`. Historical actual-visit records are not presented as new executions during this consolidation. See [full validation scope](../../06_docs/validation.md).

## Dependencies

Python 3.11+, [requirements](../../requirements.txt), Docker and existing image/template caches. Execution targets Linux AMD64; Mac emulation and runtime require environment-specific validation. See [preserved methods](METHODS.md), [literature and scope](literature.md), and the [consolidation and transition guide](../../06_docs/xcpd_consolidation.md).

## macOS and Linux

Use Docker Desktop on Mac and Docker Engine on Linux x86-64, with the same immutable images and host-correct bind paths. Preserve this separate volume/aCompCor profile and its caches; it is not the main surface-enabled 36P-LINC profile. Full Linux imaging execution remains a deployment validation task.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s7a) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
