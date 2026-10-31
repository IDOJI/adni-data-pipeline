# Data preparation

Follow upstream s1/s2 for ADNI access approval, data selection and download. Historical Research RDS files or a particular Selection Table are not required inputs.

```text
ADNI_DATA/                         # Outside this Git repository
├── LONI_download/
│   ├── zipped_imaging_data/
│   ├── meta_data/                 # Collection and download metadata
│   ├── sourcedata/                # DICOM
│   └── clindata/                  # Original clinical, QC and NFQ tables
├── rawdata/                       # Clinica BIDS
├── derivatives/{mriqc,fmriprep}/
├── config/                        # Generated actual upstream configuration
├── qc/{step4b,step5a,step5,step5c,step8}/
├── jobs/
├── logs/
└── results/
```

Preserve download criteria, data-freeze dates, collection CSVs and source-table versions. Current support matches upstream GO/2/3. Define separate inputs, validation and scope before extending to ADNI4/SNP.

Step 5.C outputs are execution handoff artifacts, not a new authoritative selection table. Keep sessions, runs and Image IDs linked to original conversion_info records. File existence and format validation do not establish source-QC approval.
