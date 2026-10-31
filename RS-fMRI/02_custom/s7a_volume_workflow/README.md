# Step 7.A — Docker volume workflow (aCompCor profile)

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

## Execution

Run from `RS-fMRI/` with an actual external configuration. Container downloads and processing occur only when the corresponding commands below are explicitly executed.

```sh
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json dry-run --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json run --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json verify --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json run --stage xcpd --subject 999S9999
python 02_custom/s7a_volume_workflow/audit_outputs.py --data-root /ABSOLUTE/PATH/ADNI_DATA/volume --subject 999S9999 --session 20200101 --output /ABSOLUTE/PATH/ADNI_DATA/volume-qc/audit.json
```

For metadata finalization of a previously successful XCP-D run, use `finalize-xcpd --stage xcpd` with the same configuration/subject. It checks success, unchanged inputs and execution identity while preserving the original run record. Do not relocate active containers or invent cache identities to bypass checks.

## Validation

The existing synthetic execution, failure recovery, header/voxel invariance, independent audit and image-QC tests were ported to `05_tests/volume_workflow/`. Historical actual-visit records are not presented as new executions during this consolidation. See [full validation scope](../../06_docs/validation.md).

## Dependencies

Python 3.11+, [requirements](../../requirements.txt), Docker and existing image/template caches. Execution targets Linux AMD64; Mac emulation and runtime require environment-specific validation. See [preserved methods](METHODS.md), [literature and scope](literature.md), and the [consolidation and transition guide](../../06_docs/xcpd_consolidation.md).
