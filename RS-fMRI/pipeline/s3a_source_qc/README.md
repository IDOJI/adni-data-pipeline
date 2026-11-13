# Step 3.A — Source QC and NFQ evidence validation

## Execution

```sh
python pipeline/s3a_source_qc/run.py \
  --mriqc-table /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MRIQC.csv \
  --adni3-qc /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MAYO_ADNI3.csv \
  --go2-qc /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MAYO_GO2.csv \
  --deleted-scans /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DELMRSCANS.csv \
  --nfq GO2_3=/ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/NFQ.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step3a
```

Run from `RS-fMRI/` in the installed Python environment. Replace every `/ABSOLUTE/PATH`, `/ABS/PATH` or `/external` example with actual external paths. Use a new output directory when the tool requires one; subject IDs and pair keys in examples are placeholders.

**What this does:** Audits source image identity, ADNI quality/NFQ records and deletion evidence before downstream handoff.

**Results:** `image_qc.tsv`, source-row evidence and a hash-bound `artifact.json` in the selected output directory.

Run from `RS-fMRI/` and replace placeholders with actual external file paths.

## Purpose

This independent check after upstream Step 3 adapts source-quality and identity checks from the Research selection workflow. It reads explicitly supplied ADNI Study Files without requiring a historical Selection Table/RDS. Here, `MRIQC` means the ADNI Study Files scan inventory, not IQM output from the MRIQC software.

## Input

Required: `--mriqc-table`, the original MRIQC CSV. Optional: `--adni3-qc`, `--go2-qc`, `--deleted-scans` and repeated `--nfq SOURCE=PATH`. Supported schemas use the original column names from Research's MRIQC, MAYO ADNI3, GO/2, Deleted Scans and NFQ sources. Column names are not guessed; other release schemas require an explicit adapter extension.

MRIQC requires `image_id`, `ParticipantID`, `StudyDate`, `SeriesType`, `SeriesInstanceUID`, `StudyInstanceUID`, `LONIStudy`, `LONISeries`, `SeriesNumber`, `MRIProtocolPhase` and `SeriesTime`. Required columns for each Mayo QC source are specified in `qc_registry.py::normalize`. NFQ uses an ID, UID or complete composite identity together with `OVERALLQC`.

## Processing

- Compare Image ID, PTID/RID, actual date, modality, UID and LONI identifiers. Record conflicts, deletions, quality 4/−1 and study-level holds as blocked states.
- Accept grades 1, 2 and 3. A chosen flag never overrides failure or reduces candidates to a single image.
- For missing GO/2 image IDs, allow only unique LONI series+study+RID+date+modality matches; quarantine multiple targets.
- Match raw NFQ by ID → UID → RID/date/series number/time (within one second). Never override an explicit ID conflict with another matching method.
- Evaluate NFQ quality independently of SliceTiming availability, including NFQ failures when ST is empty.
- Distinguish `blocked`, `pending` and `pass`. EPI requires confirmed base QC and NFQ to `pass`; absent sources or records remain `pending`.

## Output

Outputs include `image_qc.tsv`, source-specific QC registries, raw NFQ row audits and `artifact.json` with input/output/code hashes. Write results only to a new external directory. Original images, tables and the submodule remain unchanged.

## Validation

Synthetic schemas test quality/chosen separation, grades 4/−1, deletion/conflicts, NFQ failure with missing ST, UID mismatch, unique GO/2 matching, pending preservation, overwrite refusal and the 5.C handoff. These checks do not establish full-cohort validation.

## Dependencies

Python 3.11+ standard library. Sources and original code hashes are recorded in `03_config/imported_sources.json`. Reference: [ADNI MRI QC](https://adni.loni.usc.edu/data-samples/adni-data/neuroimaging/mri/mri-quality-control/).

This step supplements upstream image selection and conversion. It audits T1/EPI source records; actual T1-reference/BOLD pairing, NIfTI/JSON consistency and ST axis/direction require separate image-level validation. Auditing ADNI4 NFQ sources does not add Clinica ADNI4 support.

## macOS and Linux

The Python CLI and source-QC rules are shared. Set Study Files/output paths to this host and preserve the source hashes and pending/blocked identity decisions. This step needs neither Docker nor a service manager.

See the [stage-specific host instructions](../../06_docs/platform_execution.md#s3a) for prerequisites, executable routes and validation limits. Shared analysis settings remain in this step's existing configuration; host compatibility is not a new scientific QC pass.
