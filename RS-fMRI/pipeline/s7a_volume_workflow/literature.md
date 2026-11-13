> Preserved methods for the volume pilot. Examples use synthetic identifiers; this document does not describe the methods or validation results of the newer 36P/LINC workflow.

# 🟥1️⃣ Literature evidence and scope

- Review date: 2026-10-28
- Purpose: review evidence for Docker preprocessing of BIDS-organized ADNI3/ADNI4 rs-fMRI.
- Conclusion: Wang et al. (2026) directly analyzed ADNI3 and ADNI4 using GRETNA. This implementation adapts fMRIPrep precedents from Rutherford/Leone and official software settings. A fMRIPrep paper with an explicitly documented actual ADNI4 cohort remained unconfirmed within this review.

## 🟩2️⃣ Core literature reviewed

| Reference | Data and publication status | Verified preprocessing and use | Limitations |
| --- | --- | --- | --- |
| Wang, Chen & Qiao, 2026 | Original Medical Image Analysis article; actual ADNI3/ADNI4 analyses | §4.3: 104 ADNI4 participants (59 CN/45 MCI), TR 1.5 seconds, TE 0.03 seconds, 90 nodes and 200 timepoints | GRETNA-based. Interpret the extent of shared preprocessing details for ADNI4 only within the limits below |
| Rutherford et al., 2026, A Pipeline for ADNI Resting-State Functional MRI Processing and Quality Control | ADNI GO/2/3; Research Square and arXiv preprint | Reviewed arXiv v3 (2026-09-04): fMRIPrep 25.2.3, MRIQC 24.0.2. FD 0.5 mm; exclude runs with more than 30% censored frames or less than 5 minutes of retained low-motion data. Includes FreeSurfer surfaces and Euler QC | ADNI4 excluded because Clinica conversion is unsupported. The public example configuration uses fMRIPrep 24.0.0, unlike the updated manuscript. Requiring 5 retained minutes is difficult for 5-minute ADNI4 acquisitions |
| Canal-Garcia et al., 2024, Dynamic multilayer functional connectivity detects preclinical and clinical Alzheimer’s disease | ADNI3; original Cerebral Cortex article | fMRIPrep 20.2.4, discard first 2 volumes, motion/slice-timing correction, 2 mm MNI152, 24-parameter motion nuisance model and WM/CSF noise handling, 0.01 Hz high-pass | Designed for dynamic connectivity. Not direct evidence for this implementation's aCompCor, 0.08 Hz low-pass or 6 mm smoothing |
| Billaud & Yu, 2025, Structure–function coupling using fixel-based analysis and functional magnetic resonance imaging in Alzheimer’s disease and mild cognitive impairment | Original Network Neuroscience article explicitly describing an ADNI3 protocol | fMRIPrep 20.2.5; AFNI slice timing, MCFLIRT, FreeSurfer bbregister with 9 DOF and MNI transformation. Nilearn handling of 6 motion parameters, WM/CSF/global signal, derivatives and cosines; 5 mm smoothing, 0.1 Hz low-pass; exclusion if more than 20% of volumes have relative RMS >0.25 | GSR, 5 mm, 0.1 Hz and RMS criteria differ from this implementation's noGSR, 6 mm, 0.08 Hz and Power FD criteria |
| Arani et al., 2024, Design and validation of the ADNI MR protocol | Original ADNI4 MRI acquisition-protocol article | ADNI4 BOLD: basic TR 1.5 seconds, advanced 0.6 seconds; legacy scanners retain 3 seconds. Duration reduced from 10 minutes in ADNI3 to 5 minutes in ADNI4 | Not a fMRIPrep validation study of an analysis cohort. Supports checking TR/duration in each sidecar and NIfTI rather than assigning them solely by phase |

- Wang: Yiding Wang, Longyun Chen, Chen Qiao. *Continuous-time causal distribution learning with identifiability for brain dynamic effective connectivity inference*. Medical Image Analysis. 2026;112:104124; published online 2026-05-13. DOI: [10.1016/j.media.2026.104124](https://doi.org/10.1016/j.media.2026.104124). [PubMed](https://pubmed.ncbi.nlm.nih.gov/42134283/), [publisher §4.3](https://www.sciencedirect.com/science/article/pii/S1361841526001933)
- Rutherford: [PubMed](https://pubmed.ncbi.nlm.nih.gov/42926671/), [reviewed v3 PDF](https://arxiv.org/pdf/2602.03278v3), [author code](https://github.com/statMINDlab/ADNI_fMRI_protocol), [example configuration](https://raw.githubusercontent.com/statMINDlab/ADNI_fMRI_protocol/main/config/config_adni.yaml), [final-QC code guide](https://raw.githubusercontent.com/statMINDlab/ADNI_fMRI_protocol/main/s8_final_qc/README.md). DOI: 10.21203/rs.3.rs-11132707/v1
- Canal-Garcia: [article PDF](https://adni.loni.usc.edu/adni-publications/Canal-Garcia_2024_Dynamic%20multilayer%20functiona.pdf). DOI: 10.1093/cercor/bhad542
- Billaud & Yu: [article PDF](https://direct.mit.edu/netn/article-pdf/doi/10.1162/netn_a_00461/2513016/netn_a_00461.pdf). DOI: 10.1162/netn_a_00461
- Arani: [full text](https://alz-journals.onlinelibrary.wiley.com/doi/full/10.1002/alz.14162). DOI: 10.1002/alz.14162

## 🟩2️⃣ Scope of the Wang methods

- The opening of §4.3 refers to ADNI3 EMCI/LMCI and Table 7: GRETNA stabilization, motion correction, normalization, smoothing and 0.01–0.08 Hz filtering, with AAL90 and 187 timepoints.
- The later ADNI4 paragraph and Fig. 9(a) establish an additional actual cohort, but do not transfer ADNI3's 10-minute/TR 3-second/187-timepoint settings to ADNI4. ADNI4 dummy counts, regressors, motion cutoff, smoothing width, SDC and normalization space remain unconfirmed.
- Earlier synthetic experiments and §4.2 Starplus task-fMRI settings are not evidence for ADNI preprocessing. Section 4.3 describes ROI-level data and does not provide a complete BIDS→fMRIPrep reproduction specification.
- Verification: compared indexed publisher text from §4.3 with PubMed metadata. Direct page access returned 403; acquisition of the PDF was not recorded as successful.

## 🟩2️⃣ Verification status of Down and Leone

- Down et al., 2026, *Synergistic and redundant information dynamics are modulated by Alzheimer’s disease and cognitive impairment*: [PubMed](https://pubmed.ncbi.nlm.nih.gov/41757079/), [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12934565/), DOI 10.64898/2026.02.18.706630. bioRxiv preprint. Indexed Methods describe selecting the latest scan per participant from 2,907 ten-minute rs-fMRI scans acquired before 2023-11-22. The acquisition section mentions ADNI3/ADNI4, but actual phase-specific inclusion counts and an ADNI4 scan list were not verified. Do not use it as conclusive evidence of actual ADNI4 processing validation. Its 10-minute/TR 3/0.6-second description does not cover all official ADNI4 5-minute/TR 1.5/0.6-second protocols. PMC-indexed preprocessing text confirms fMRIPrep 23.0.2 and Clinica ADNI-to-BIDS; custom nuisance/filter details remain unverified.
- Leone et al., 2024, *Beyond Focal Lesions: Dynamical Network Effects of White Matter Hyperintensities*: [PubMed](https://pubmed.ncbi.nlm.nih.gov/39624946/), [publisher full text §2.1–2.2](https://onlinelibrary.wiley.com/doi/full/10.1002/hbm.70081), DOI 10.1002/hbm.70081. Analyzed 188 of 363 initial ADNI3 participants. Verified fMRIPrep 21.0.4 → XCP-D, removal of the first 4 timepoints, nonaggressive ICA-AROMA, 6 motion parameters/derivatives and WM/CSF noise handling, AAL90, demeaning/detrending and 0.04–0.07 Hz filtering. This is peer-reviewed evidence for applying fMRIPrep→XCP-D to ADNI3. The reviewed sections do not establish the exact XCP-D version, smoothing or motion cutoff. This implementation's aCompCor and 0.01–0.08 Hz settings differ.

## 🟩2️⃣ Sources of implementation choices

| Implementation choice | Evidence category |
| --- | --- |
| fMRIPrep 25.2.7 Docker | Version update informed by the public ADNI workflow, not an identical reproduction of Rutherford's 25.2.3 execution. Record actual versions/digests and reasons for changes in execution manifests/methods |
| MNI152NLin2009cAsym 2 mm, volumetric-only, fs-no-reconall | Project choice of shared space and processing/storage scope. Differs from Rutherford's full pipeline with surfaces/CIFTI and Euler QC |
| Fieldmap-less SyN SDC | Informed by Rutherford's public code. Verify actual PE/readout metadata and execution logs; review fieldmap inputs separately |
| XCP-D 26.2.0, WM5+CSF5 aCompCor, 12 motion parameters, cosines, noGSR | Postprocessing specification informed by Leone's fMRIPrep→XCP-D structure without replicating ICA-AROMA. Explicitly uses the official XCP-D acompcor model |
| FD >0.5 mm censoring and motion-censored fraction ≤30% | Informed by Rutherford's motion criteria, with the denominator explicitly defined after dummy removal. Retained time changed from 300 to 240 seconds. The independent audit checks both ≤30% censoring and ≥240 seconds in addition to the XCP-D minimum-time argument |
| At least 240 retained seconds | Project criterion accounting for 5-minute ADNI4 acquisitions; explicitly changed from Rutherford's 300-second criterion |
| 0.01–0.08 Hz, Butterworth order parameter 2 and 6 mm smoothing | Project choices; do not describe them as exact shared settings of all reviewed studies |
| Preserve acquisition TR | Handle ADNI3/4 temporal-resolution differences per input; do not reproduce Down's downsampling to TR 3 seconds |

- fMRIPrep provides minimal preprocessing such as motion correction, registration, normalization and confound estimation. Distinguish these outputs from BOLD that has completed final nuisance regression, band-pass filtering and smoothing: [official fMRIPrep documentation](https://fmriprep.org/en/latest/).
- The official ADNI4 FAQ states that routine field maps are not acquired. This does not justify automatically assigning diffusion reverse-PE scans as BOLD fieldmaps: [ADNI MRI FAQ](https://adni.loni.usc.edu/help-faqs/faqs/).

## 🟩2️⃣ Search history and interpretation limits

- Main queries: `ADNI3 fMRIPrep resting state preprocessing 2024 2025`; `ADNI4 resting state fMRI preprocessing fMRIPrep`; `ADNI4 functional connectivity 2025 2026 preprocessing`; verification by title and PMID.
- Source priority: author code, article full text/public institutional PDFs, PubMed and official ADNI MRI Core documentation.
- Excluded example: Baek et al., 2026, DOI 10.1002/hbm.70548 includes ADNI GO/2/3/4 but studies T1w structural images. It is not evidence for ADNI4 rs-fMRI preprocessing.
- Some PMC full-text requests showed reauthentication pages. Distinguish indexed excerpts from accessible full text. Additional XML network access stopped pending approval and was not recorded as successful retrieval.
- Additional query: `"Continuous-time causal distribution learning" "ADNI4"`. Direct cohort confirmation in Wang replaced the initial uncertainty about ADNI4 analysis papers. Technical completion of ADNI4 processing and scientific validity remain separate judgments.


## 🟩2️⃣ Execution versions and official settings

- [fMRIPrep 25.2.7 changelog](https://fmriprep.org/en/25.2.7/changes.html): MCFLIRT motion-parameter reconstruction and BOLD-mask fixes from 25.0.0–25.2.6 informed selection of 25.2.7 for new execution.
- [XCP-D 26.2.0 workflow](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html): explicitly pin linc's 0.01–0.08 Hz and 6 mm settings and change the default FD=0 to 0.5.
- [XCP-D acompcor configuration](https://raw.githubusercontent.com/PennLINC/xcp_d/26.2.0/xcp_d/data/nuisance/acompcor.yml): verified WM5, CSF5, motion12 and cosine components.
- Final source checks supersede initial uncertainty recorded during the search. Do not infer settings beyond the verified sections.
