# ▶️ Run a study

Open the [setup and folder map](../stages/setup.md), activate the environment and set `STUDY` once. From the `RS-fMRI/` directory, choose the stage you need.

| Stage | Script | Walkthrough |
|---|---|---|
| 🔎 Select images | [01_select.py](01_select.py) | [Source files and download list](../01-selection/README.md) |
| 📦 Convert and verify | [02_bids.py](02_bids.py) | [Per-ID dcm2niix conversion, file audit and pair checks](../02-bids/README.md) |
| 🧠 Process and review | [03_process.py](03_process.py) | [MRIQC, fMRIPrep, XCP-D and final QC](../03-imaging/README.md) |
| 📊 Harmonize connectivity | [04_harmonize.py](04_harmonize.py) | [Scanner map, audit and ComBat](../04-harmonization/README.md) |

Each script accepts `--help` for alternative input paths. Shared code for the scripts lives in `support/`. Processing methods and their references live in [pipeline/](../pipeline/README.md).
