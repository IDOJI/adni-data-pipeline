# 🧬 ADNI Data Pipeline

Contribution and maintenance rules: [Repository instructions.md](<Repository instructions.md>)

A research pipeline for processing and validating ADNI data by modality. **[RS-fMRI](RS-fMRI/README.md)** is implemented; an SNP pipeline is planned as a separate module.

| Area | Status | Guide |
|---|---|---|
| RS-fMRI | Pinned upstream submodule, Custom Steps, integrated execution guide, synthetic validation, XCP-D and integrated imaging QC | [RS-fMRI/README.md](RS-fMRI/README.md) |
| SNP | Planned; no execution code yet | A separate module and protocol will be added |

```text
adni-data-pipeline/
├── README.md
├── .gitmodules
├── LICENSE
└── RS-fMRI/
    ├── 01_upstream/ADNI_fMRI_protocol/  # Pinned upstream commit
    ├── 02_custom/                      # Lab-specific additional steps
    ├── 03_config/                      # Configuration examples and version records
    ├── 04_workflow/                    # Handoff, configuration and command planning
    ├── 05_tests/                       # Synthetic validation
    └── 06_docs/                        # Installation, updates and validation
```

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

See [RS-fMRI/NOTICE.md](RS-fMRI/NOTICE.md) for attribution and added code, and [GPL-3.0](LICENSE) for the license.
