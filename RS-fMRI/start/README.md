# ▶️ Run a study

Open the [setup and folder map](../README.md#setup), activate the environment and set `STUDY` once. From the `RS-fMRI/` directory, choose the stage you need.

| Stage | Script | Walkthrough |
|---|---|---|
| 🔎 Select images | [01_select.py](01_select.py) | [Source files and download list](../README.md#select) |
| 📦 Convert and verify | [02_bids.py](02_bids.py) | [IDA download, BIDS and pair checks](../README.md#convert) |
| 🧠 Process and review | [03_process.py](03_process.py) | [MRIQC, fMRIPrep, XCP-D and final QC](../README.md#process) |
| 📊 Harmonize connectivity | [04_harmonize.py](04_harmonize.py) | [Scanner map, audit and ComBat](../README.md#harmonize) |

Each script accepts `--help` for alternative input paths. Shared code for the scripts lives in `support/`. Processing methods and their references live in [pipeline/](../pipeline/README.md).
