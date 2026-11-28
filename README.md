# 🧠 ADNI Data Pipeline

Start with the [four-stage resting-state fMRI guide](RS-fMRI/README.md). It takes you from ADNI collection exports to a table of functional connections adjusted for scanner differences. If you work with genotype data, open the separate [SNP guide](SNP/README.md).

| Stage | What you do | What you get |
|---|---|---|
| [1 · 🔎 Select scans](RS-fMRI/stages/01-selection/README.md) | Check ADNI quality records and match resting scans to same-day T1 images | Image IDs to download and a list of cases to review |
| [2 · 📦 Download and convert](RS-fMRI/stages/02-bids/README.md) | Download the selected DICOMs from IDA, run dcm2niix once per Image ID and verify each EPI–T1 pair | BIDS images, an ID-to-file audit and a receipt listing verified pairs |
| [3 · 🧠 Process and check quality](RS-fMRI/stages/03-imaging/README.md) | Run MRIQC, fMRIPrep and XCP-D, review images and check clinical eligibility | Denoised data, connectivity matrices and final QC tables |
| [4 · 📊 Harmonize connectivity](RS-fMRI/stages/04-harmonization/README.md) | Audit eligible participants and fit ComBat across reviewed scanners | Original and adjusted connectivity, with the model diagnostics |

[Set up your study folder](RS-fMRI/stages/setup.md) · [Methods and references](RS-fMRI/06_docs/protocol-index.md) · [Practice data](RS-fMRI/07_reproducibility/README.md)

Adapted from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol). [License](LICENSE) · [Citations](RS-fMRI/pipeline/CITATION.cff) · [Attribution](RS-fMRI/NOTICE.md)
