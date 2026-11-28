# Data preparation

Obtain ADNI access through s1/s2, then export collection metadata and the corresponding Study Files before deciding which images to process. Follow the [date-based selection guide](date_based_selection.md). Historical Research RDS files or a particular Selection Table are not required inputs.

1. Export T1 and resting-state collection CSVs with Image ID, participant, actual acquisition date and phase. Keep every acquisition and preserve original visit labels as provenance. Do not inner-join modalities on VISCODE or retain only the first image per visit.
2. Run [3.A](../01-selection/source_qc/README.md) on the original QC/NFQ/identity tables and [3.B](../01-selection/image_selection/README.md) on the collection exports. The T1 reference pool is independent of the EPI clinical diagnosis window; QC unknown stays pending.
3. Download the audited candidates, [convert each selected DICOM series with dcm2niix](../02-bids/dcm2niix/README.md). Check conversion records against the selected Image IDs. A converter retaining another scan with the same visit label is not an acceptable substitute.
4. Resolve SliceTiming only with unambiguous source evidence. Run [5.D](../02-bids/bids_identity/README.md) against actual files and independent conversion hash evidence. Launch only through its guarded exact-pair route. Cross-date references, ties, missing files and identity disagreements remain held.
5. After preprocessing, combine imaging QC with separate scan-date clinical checks in 9.A/9.B. A metadata proposal or successful container exit does not establish inclusion.

```text
ADNI_DATA/                         # Outside this Git repository
├── LONI_download/
│   ├── zipped_imaging_data/
│   ├── meta_data/                 # Collection and download metadata
│   ├── sourcedata/                # DICOM
│   └── clindata/                  # Original clinical, QC and NFQ tables
├── 02-bids/rawdata/               # BIDS images and sourcedata/conversion evidence
├── derivatives/{mriqc,fmriprep}/
├── config/                        # Generated actual upstream configuration
├── qc/{step3a,step3b,step4b,step5,step5c,step5d,step8}/
├── jobs/
├── logs/
└── results/
```

Preserve download criteria, data-freeze dates, collection CSVs and source-table versions. Current support matches upstream GO/2/3. Define separate inputs, validation and scope before extending to ADNI4/SNP.

Step 5.C outputs are session-level audit artifacts, not T1 reference approval. Keep sessions, runs and Image IDs linked to the original source-to-NIfTI conversion records. Even matching session names and valid NIfTI files do not establish the correct acquisition pair; 5.D checks date, UID, hashes and headers independently.
