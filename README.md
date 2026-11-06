# 🧬 ADNI Data Pipeline

Contribution and maintenance rules: [Repository instructions.md](<Repository instructions.md>)

A research repository for processing and validating ADNI data by modality, with **[RS-fMRI](RS-fMRI/README.md)** and **[SNP](SNP/README.md)** modules. Each module separates pinned upstream code, project additions and validation records.

| Area | Status | Guide |
|---|---|---|
| RS-fMRI | Pinned upstream submodule, Custom Steps, integrated execution guide, synthetic validation, XCP-D and integrated imaging QC | [RS-fMRI/README.md](RS-fMRI/README.md) |
| SNP | Eissman-based TOPMed r3 workflow, pinned GWAS_QC submodule, command planning and synthetic variant-audit validation; cohort execution requires external resources and review | [SNP/README.md](SNP/README.md) |

```text
adni-data-pipeline/
├── README.md
├── .gitmodules
├── LICENSE
├── RS-fMRI/
│   ├── 01_upstream/ADNI_fMRI_protocol/  # Pinned upstream commit
│   ├── 02_custom/                      # Lab-specific additional steps
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

Try the [copy-and-paste RS-fMRI examples](RS-fMRI/07_reproducibility/README.md): offline reference checks, pinned public T1w/BOLD data, stage commands and numerical comparison.

## 🚀 Getting started

```sh
git clone --recurse-submodules https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python 04_workflow/lab.py doctor
python -m pytest -q
```

Keep research data, private configuration and results outside the repository. Do not publish original ADNI images, clinical tables, SNP data, real participant lists or credentials here. Passing code tests does not establish scientific validity for the full cohort.

For SNP setup, methods and the Mermaid workflow, start with the [SNP README](SNP/README.md). Its source check and tests require only Python and Git; genomic execution requires a validated Linux environment and external reference resources.

See [RS-fMRI/NOTICE.md](RS-fMRI/NOTICE.md) and [SNP/NOTICE.md](SNP/NOTICE.md) for attribution and added code, and [GPL-3.0](LICENSE) for the license.
