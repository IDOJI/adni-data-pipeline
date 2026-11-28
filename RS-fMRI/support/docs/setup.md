# 🗂️ Set up your study folder

You need two folders. The repository holds the **code**. A separate private folder holds **your data and results**.

### Open the code folder

Follow [installation](installation.md) once. It leaves your terminal in `adni-data-pipeline/RS-fMRI`. If you are starting a new terminal, open it in that same folder.

### Choose a home for your data

Replace the quoted path with your private study folder. Keep the quotes if the name contains spaces.

```sh
source .venv/bin/activate
export STUDY="/absolute/path/to/my ADNI study"
mkdir -p "$STUDY/collections" "$STUDY/LONI_download/clindata" "$STUDY/review"
```

Use this terminal for all four steps. Each command reads `$STUDY` and saves its results there. In a new terminal, activate the environment and set `STUDY` again.

**Start → [1 · Choose the scans](../../01-selection/README.md)**

<details>
<summary>Where does each file go?</summary>

| Inside your study folder | Contents |
|---|---|
| `collections/` | Scan lists exported from ADNI |
| `LONI_download/clindata/` | ADNI quality and clinical tables |
| `LONI_download/sourcedata/` | Unzipped DICOM images, starting with the participant folders |
| `review/` | Reviewed exclusions, scanner labels and external conversion records |
| `license.txt` and `templateflow/` | FreeSurfer license and downloaded templates for step 3 |

The scripts create `01-selection/`, `02-bids/`, `03-imaging/` and `04-harmonization/` here as you run them. These contain your study’s results. The folders with the same names **in the repository** hold the scripts.

</details>
