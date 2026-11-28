# 🧠 ADNI Data Pipeline

Start with the [four-stage resting-state fMRI guide](RS-fMRI/README.md). It takes you from ADNI collection exports to a table of functional connections adjusted for scanner differences. If you work with genotype data, open the separate [SNP guide](SNP/README.md).

| Stage | What you do | What you get |
|---|---|---|
| [1 · 🔎 Select scans](RS-fMRI/README.md#select) | Check ADNI quality records and match resting scans to same-day T1 images | Image IDs to download and a list of cases to review |
| [2 · 📦 Download and convert](RS-fMRI/README.md#convert) | Download the selected DICOMs from IDA, run dcm2niix once per Image ID and verify each EPI–T1 pair | BIDS images, an ID-to-file audit and a receipt listing verified pairs |
| [3 · 🧠 Process and check quality](RS-fMRI/README.md#process) | Run MRIQC, fMRIPrep and XCP-D, review images and check clinical eligibility | Denoised data, connectivity matrices and final QC tables |
| [4 · 📊 Harmonize connectivity](RS-fMRI/README.md#harmonize) | Audit eligible participants and fit ComBat across reviewed scanners | Original and adjusted connectivity, with the model diagnostics |

### Where to work

- **To run a stage**, use the four numbered scripts in [RS-fMRI/start/](RS-fMRI/start/). The guide shows what to paste into the terminal and which file to open afterward.
- **To understand a method**, open the matching stage in [RS-fMRI/pipeline/](RS-fMRI/pipeline/README.md).
- **To store data**, choose one private study folder outside Git. Each script reads the preceding outputs and writes its own numbered folder there. See the [folder map and setup](RS-fMRI/README.md#setup).

[Installation](RS-fMRI/06_docs/installation.md) · [Practice with public data](RS-fMRI/07_reproducibility/README.md) · [Managed batch runs](RS-fMRI/06_docs/local_batch.md) · [Harmonization papers and software](RS-fMRI/06_docs/fc_harmonization.md)

The RS-fMRI pipeline adapts [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol). See the [GPL license](LICENSE), [citations](RS-fMRI/pipeline/CITATION.cff) and [attribution](RS-fMRI/NOTICE.md).
