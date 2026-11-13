# 🧬 ADNI Data Pipeline

For new RS-fMRI runs, use the [fixed-seed execution guide](RS-fMRI/06_docs/seed_reproducibility.md): master seed 1123, explicit skull-stripping/MRIQC controls and one numerical worker thread. Existing live runs retain their original settings.

Contribution and maintenance rules: [Repository instructions.md](<Repository instructions.md>)

A research repository for processing and validating ADNI data by modality, with **[RS-fMRI](RS-fMRI/README.md)** and **[SNP](SNP/README.md)** modules. RS-fMRI maintains one `pipeline/` tree, adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3), with original attribution and GPL terms retained; SNP and optional atlas libraries retain separate pinned sources.

| Area | Status | Guide |
|---|---|---|
| RS-fMRI | Unified owned pipeline, execution guide, synthetic validation, XCP-D, integrated imaging QC and per-run scalar/report exports | [RS-fMRI/README.md](RS-fMRI/README.md) |
| SNP | Eissman-based TOPMed r3 workflow, pinned GWAS_QC submodule, command planning and synthetic variant-audit validation; cohort execution requires external resources and review | [SNP/README.md](SNP/README.md) |

```text
adni-data-pipeline/
├── README.md
├── .gitmodules
├── LICENSE
├── RS-fMRI/
│   ├── pipeline/                      # All maintained RS-fMRI stages
│   ├── provenance/                    # Historical source references
│   ├── 03_config/                      # Configuration examples and version records
│   ├── 04_workflow/                    # Handoff, configuration and command planning
│   ├── 05_tests/                       # Synthetic validation
│   ├── 06_docs/                        # Installation, updates and validation
│   └── 07_reproducibility/             # Public inputs, executable examples and result comparison
└── SNP/
    ├── 01_upstream/GWAS_QC/             # Pinned upstream commit
    ├── 02_custom/                      # Multi-array variant audit
    ├── 03_config/                      # Batch examples and source lock
    ├── 04_workflow/                    # Source checks and command planning
    ├── 05_tests/                       # Synthetic validation
    └── 06_docs/                        # Methods, installation, merging and X
```

Try the [copy-and-paste RS-fMRI examples](RS-fMRI/07_reproducibility/README.md): offline synthetic reference checks, a pinned public T1w/BOLD sample, stage commands and numerical result comparison.

This is the single maintained ADNI pipeline repository. The former `adni-rsfmri-pipeline` was a compatibility link to Stage 7.A, not a second repository. Use `RS-fMRI/pipeline/s7a_volume_workflow/` directly; see the [legacy-checkout retirement record](RS-fMRI/06_docs/repository_cleanup.md) for source preservation and verification.

Host-specific RS-fMRI setup and stage instructions are in the [macOS/Linux guide](RS-fMRI/06_docs/platform_execution.md). Shared analysis settings, executable local/container routes and missing Linux operational adapters are documented separately.

## 🚀 Getting started

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python 04_workflow/lab.py doctor
python -m pytest -q
```

The [CC0 public MRI sample](RS-fMRI/07_reproducibility/public_data/ds000030-1.0.0/README.md) is included as ordinary Git files, with original source metadata and attribution. This explicitly approved example is separate from private ADNI inputs.

Keep research data, private configuration and results outside the repository. Do not publish original ADNI images, clinical tables, SNP data, real participant lists or credentials here. Passing code tests does not establish scientific validity for the full cohort.

For per-run brain volumes, cortical thickness, ReHo/ALFF and native imaging report links, use [RS-fMRI Stage 12](RS-fMRI/pipeline/s12_metrics_summary/README.md). Its integrated entry point is `python 04_workflow/lab.py export-results` from `RS-fMRI/`; archive and runtime paths stay external.

For SNP setup, methods and the Mermaid workflow, start with the [SNP README](SNP/README.md). Its source check and tests require only Python and Git; genomic execution requires a validated Linux environment and external reference resources.

See [RS-fMRI/NOTICE.md](RS-fMRI/NOTICE.md) and [SNP/NOTICE.md](SNP/NOTICE.md) for attribution and added code, and [GPL-3.0](LICENSE) for the license.

## Local unattended RS-fMRI batches

The [local batch supervisor](RS-fMRI/06_docs/local_batch.md) connects reserved raw handoffs to the existing exact-pair/MRIQC/fMRIPrep/XCP-D workflow, with a host-wide maximum of five subjects, persistent local status, bounded retries and local result retention. It uses native Python/service ownership without model/API polling.
