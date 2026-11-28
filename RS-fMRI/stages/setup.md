# 🗂️ Set up your study folder

Complete [installation](../06_docs/installation.md) once. In a terminal, go to this repository's **RS-fMRI** folder and activate its Python environment. Change the *one* study path below to a private folder on your computer. Keep the quotes if its name contains spaces.

```sh
# From the top of the cloned repository
cd RS-fMRI
source .venv/bin/activate
export STUDY="/absolute/path/to/my ADNI study"
mkdir -p "$STUDY/collections" "$STUDY/LONI_download/clindata" "$STUDY/review"
```

Keep using this terminal. In a new terminal, return to this directory, activate the environment and set the same `STUDY` again. The scripts read these locations by default.

```text
Your private study folder/
├── collections/             T1.csv and EPI.csv exported from ADNI
├── LONI_download/
│   ├── clindata/            ADNI Study Files (CSV)
│   └── sourcedata/          Extracted DICOMs, starting with the participant folders
├── review/                  Reviewed exclusions, scanner labels and external conversion evidence
├── license.txt              Your FreeSurfer license (stage 3)
├── templateflow/            Populated local template cache (stage 3)
├── 01-selection/            Created by stage 1
├── 02-bids/                 Created by stage 2
├── 03-imaging/              Created by stage 3
└── 04-harmonization/        Created by stage 4
```

[All stages](../README.md)
