# ADNI Data Pipeline

Process ADNI resting-state fMRI and SNP data.

| Pipeline | Results | Start here |
|---|---|---|
| RS-fMRI | Preprocessed images, denoised BOLD, QC reports, ROI signals and scalar tables | [Steps and commands](RS-fMRI/README.md) |
| SNP | Variant QC and cohort workflow | [SNP guide](SNP/README.md) |

```text
adni-data-pipeline/
├── RS-fMRI/
│   ├── pipeline/          # All processing stages
│   ├── 03_config/         # Configuration examples
│   ├── 04_workflow/       # Batch runners
│   ├── 05_tests/          # Tests
│   ├── 06_docs/           # Setup and reference
│   ├── 07_reproducibility/ # Runnable examples
│   └── provenance/        # Historical references
└── SNP/
```

New RS-fMRI runs use **seed 1123**, **fMRIPrep 25.2.7** and fixed skull-stripping initialization. Start with [installation](RS-fMRI/06_docs/installation.md) and [date-based image selection](RS-fMRI/06_docs/date_based_selection.md). The selection path is **collection CSVs → source QC (3.A) → EPI/T1 proposals by actual acquisition date (3.B) → BIDS conversion → exact image verification (5.D) → guarded preprocessing → imaging/clinical QC**. Confirmed targets with missing grade evidence can be downloaded for inspection; they remain ineligible for automatic preprocessing. Only confirmed target series enter the manual download list; the private [Image ID comparison](RS-fMRI/pipeline/s3b_image_selection/README.md#optional-private-comparison) explains differences from previous Search/QC lists. Matching VISCODE or session labels alone does not authorize a T1–EPI pair.

New S10 configurations use automatic non-steady-state removal and session-specific Euler QC under an explicit versioned policy; use a fresh runtime. See the [local batch](RS-fMRI/06_docs/local_batch.md) for its single-pair-per-participant handoff contract, or the [public example](RS-fMRI/07_reproducibility/README.md).

After final XCP-D imaging QC and Step 9.B eligibility, [Step 14](RS-fMRI/pipeline/s14_fc_harmonization/README.md) audits the cohort and harmonizes 4S256 resting-state connectivity across reviewed scanners using ComBat. It exports original and adjusted FC, the edge map, selection decisions and model diagnostics.

The optional [tolerance-based thread experiment](RS-fMRI/pipeline/s13_reproducibility/README.md)
compares isolated preprocessing/XCP-D results and measured speed at different
OMP/ITK limits while retaining existing jobs and outputs.
Its optional priority launcher admits the finite experiment before pending
production work when a shared subject slot and memory are available, retaining
the five-subject cap and existing running calculations.

The RS-fMRI skeleton was adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol). Original [GPL license](LICENSE), [citations](RS-fMRI/pipeline/CITATION.cff) and [attribution](RS-fMRI/NOTICE.md) are retained.
