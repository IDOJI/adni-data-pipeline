# Evidence by RS-fMRI stage

Reviewed 2026-11-17. Scientific references in this register are restricted to **ADNI official answers** and **research papers**. Software manuals, release notes, repository READMEs and blogs are not used as scientific evidence. The implementation is inspected separately to describe what this repository actually does. Original software attribution and navigation links remain distinct from scientific references.

**Evidence categories:** a direct statement/method from a source; a project adaptation requiring study-specific validation; or an engineering control without a claimed biological validation. A citation supports only the stated method or fact, not every surrounding configuration. All papers below are peer-reviewed except P01, explicitly marked as a preprint. Source access date is the review date; it is not a publication date.

## Stage-to-source mapping

Each stage README links to its entry here. Source IDs resolve to the exact ADNI answer (QID, author/date) or paper (authors/year, title, DOI and relevant location) below.

<a id="stage-1"></a>

### Stage 1 — s1_setup_account

**Evidence and location:** Approved access and account application: A10, named access/download FAQ answers. [A10](#a10).

**Implementation and limits:** Access is an administrative prerequisite, not evidence that a selected scan is analysis-ready. No scientific inclusion cutoff is added here.

<a id="stage-2"></a>

### Stage 2 — s2_download

**Evidence and location:** IDA image/summary linkage: A10 correspondence answer; source protocol varies by phase/scanner: P18 §2.8. [A10](#a10), [P18](#p18).

**Implementation and limits:** Preserving all exported rows, collection hashes and separate T1/EPI inventories is our audit policy; a download or series name does not establish usable source QC.

<a id="stage-3"></a>

### Stage 3 — s3_organize

**Evidence and location:** BIDS describes structured image/metadata organization: P02, data organization. [P02](#p02).

**Implementation and limits:** Inventory, archive-integrity checks and stable Image ID provenance are engineering controls. Directory structure alone does not prove correct pairing.

<a id="stage-3-a"></a>

### Stage 3.A — s3a_source_qc

**Evidence and location:** A05 explains historical T1 grades/repeats; A09 describes recorded chosen-series decisions; A04 identifies GO/2/3 NFQ. [A05](#a05), [A09](#a09), [A04](#a04), [A08](#a08).

**Implementation and limits:** Our pass/pending/blocked combination and exclusion-ledger precedence are explicit safeguards. Grade 3 is not guaranteed suitable for every analysis. ADNI4 ARC evidence (A08) must not be generalized to arbitrary missing-QC files.

<a id="stage-3-b"></a>

### Stage 3.B — s3b_image_selection

**Evidence and location:** A01 distinguishes visit labels from dates. A02 directly discusses acquisition-date T1 choice and possible adjacent-time alternatives. [A01](#a01), [A02](#a02).

**Implementation and limits:** Same-day automatic eligibility, QC → chosen → grade ranking, preserved ties/all EPI, a T1 pool independent of the clinical window, and no cross-date auto-launch are project policies. A02 does not require same-day-only use or specify an acceptable gap. [P18 §§2.6–2.8](#p18) distinguishes ASL and diffusion from task-free BOLD and describes phase/vendor variation. The four-key Search/spine intersection, positive rest evidence, per-row Phase, scanner normalization and the private Image ID change ledger are project rules. Separate retrieval for local inspection from source-QC pass: [A08](#a08) is scoped to ADNI4 ARC, and [A04](#a04) does not make the older NFQ schema universal; see the [checkpoint table](date_based_selection.md#selection-checkpoints-and-their-evidence).

<a id="stage-4"></a>

### Stage 4 — s4_clinica

**Evidence and location:** P03 describes Clinica conversion; P02 describes the BIDS format; P01 Step 4 reports ADNI conversion/selection problems. [P03](#p03), [P02](#p02), [P01](#p01).

**Implementation and limits:** Audit which Image IDs actually survive conversion. The papers do not prove that a current converter retains every proposed scan or implements our preserve-all policy.

<a id="stage-4-b"></a>

### Stage 4.B — s4b_slice_timing

**Evidence and location:** A04 identifies NFQ slice-order evidence; P04 evaluates slice-timing correction; P01 Step 5 requires unambiguous Philips timing. [A04](#a04), [P04](#p04), [P01](#p01).

**Implementation and limits:** Exact series/UID/date conflict checks, nonfinite rejection and no geometry-only tie-breaking are engineering controls. Estimated slice order is not independently verified physical slice timing or source-QC approval.

<a id="stage-5"></a>

### Stage 5 — s5_post_clinica_qc

**Evidence and location:** P01 Step 5/Table 2 provides the inherited acquisition-parameter heuristics; P18 §2.8 establishes protocol variation. [P01](#p01), [P18](#p18).

**Implementation and limits:** These are GO/2/3 protocol heuristics, not universal MRI cutoffs. Existing code requires PercentPhaseFOV >72 whereas Table 2 excludes <72; equality at 72 is a documented boundary mismatch, not exact reproduction. See the parameter table below.

<a id="stage-5-c"></a>

### Stage 5.C — s5c_validate_handoff

**Evidence and location:** A01 and A02 explain why visit/session agreement does not establish contemporaneous anatomy. [A01](#a01), [A02](#a02).

**Implementation and limits:** This is a source-BOLD/session handoff audit. Hashed survivor lists and pending-state handling are engineering controls; they do not authorize a T1. Use 5.D for exact-pair execution.

<a id="stage-5-d"></a>

### Stage 5.D — s5d_bids_identity

**Evidence and location:** A10 describes Image ID correspondence; A02 addresses the anatomical reference; P02 supplies metadata organization. [A10](#a10), [A02](#a02), [P02](#p02).

**Implementation and limits:** Date/UID/hash/header verification, receipt binding and isolated one-EPI/one-T1 staging are project integrity controls. Cross-check scanner evidence against both physical sidecars; [P18 §2.8](#p18) supports recording variability, not mandatory manufacturer/strength holds. No cited source mandates this receipt format or certifies registration quality from hashes.

<a id="stage-6"></a>

### Stage 6 — s6_mriqc

**Evidence and location:** P05 establishes MRIQC; P01 Step 6/Table 3 applies IQMs and robust cohort outlier fitting to ADNI. [P05](#p05), [P01](#p01).

**Implementation and limits:** The original MRIQC classifier study is structural T1w validation. It does not validate this BOLD SHASH fit. Keeping missing/nonfinite decisions pending rather than passed is our safeguard; P01 instead reports excluding missing-IQM sessions.

<a id="stage-7"></a>

### Stage 7 — s7_fmriprep

**Evidence and location:** P06 Methods describes fMRIPrep and image/report validation. [P06](#p06).

**Implementation and limits:** The pinned 25.2.7 image, seed 1123, OMP1 and fresh-runtime rules are implementation choices, not claims established by the 2019 paper. Successful completion does not replace anatomical/functional registration review.

<a id="stage-7-a"></a>

### Stage 7.A — s7a_volume_workflow

**Evidence and location:** P11 supports CompCor; P06 preprocessing and P10 postprocessing provide the method context. [P11](#p11), [P06](#p06), [P10](#p10).

**Implementation and limits:** This alternative volume/aCompCor profile is distinct from S10 36P/GSR. Its FD 0.5 mm, 240 s, 0.01–0.08 Hz, 6 mm and no-despiking choices are recorded adaptations, not the original CompCor protocol.

<a id="stage-7-b"></a>

### Stage 7.B — s7b_sessionwise_preprocessing

**Evidence and location:** P06 supports preprocessing; A02 addresses acquisition-date anatomy. [P06](#p06), [A02](#a02).

**Implementation and limits:** Sessionwise isolated execution is our chosen reference policy. The cited paper does not validate every later command flag or establish superiority over a longitudinal reference. Intake, locks, cache identity and fresh runtimes are engineering controls.

<a id="stage-7-c"></a>

### Stage 7.C — s7c_ants_iteration_logging

**Evidence and location:** P06 provides the registration/preprocessing context. [P06](#p06).

**Implementation and limits:** Operational instrumentation only: iteration logs are not a scientific QC metric or percentage-complete measure. No independent paper is claimed to validate this logger or its output schema.

<a id="stage-7-d"></a>

### Stage 7.D — s7d_processing_timing

**Evidence and location:** P06 and P10 identify the preprocessing/postprocessing methods being timed. [P06](#p06), [P10](#p10).

**Implementation and limits:** Operational accounting only. Duration definitions, retries, wall spans and observer handling are implementation contracts; runtime length is not an imaging-quality criterion. No dedicated scientific validation is claimed.

<a id="stage-8"></a>

### Stage 8 — s8_final_qc

**Evidence and location:** P07 links motion with spurious FC; P19 explains the first-frame FD convention; P08 evaluates reconstruction-specific Euler quality. [P07](#p07), [P19](#p19), [P08](#p08).

**Implementation and limits:** Our sessionwise Euler decisions, equally weighted participant-median site reference, transformed difference threshold 5 and minimum 10 subjects are explicit project choices. Missing/invalid measurements remain pending; anatomical review does not rescue known failures.

<a id="stage-8-a"></a>

### Stage 8.A — s8a_motion_duration_qc

**Evidence and location:** P07 supplies the motion-artifact rationale; P01 Step 8 describes FD 0.5 mm, maximum 30% censoring and 300 s retained duration. [P07](#p07), [P01](#p01).

**Implementation and limits:** This is a separate protocol-comparison report, not the S10 censoring rule. Initial-volume treatment and actual acquisition-frame masks must be reported rather than silently equated with XCP-D outputs.

<a id="stage-9"></a>

### Stage 9 — s9_clinical_imaging_merge

**Evidence and location:** A01/A03 support actual-date nearest clinical linkage; P01 Step 9 describes its 180-day default. [A01](#a01), [A03](#a03), [P01](#p01).

**Implementation and limits:** This inherited score-merge utility is not the final clinical gate. Use 9.A/9.B for the project nearest 28-day policy and preserve source assessment dates and ambiguity.

<a id="stage-9-a"></a>

### Stage 9.A — s9a_validate_clinical

**Evidence and location:** A03 supports a researcher-defined nearest-date window. A06 defines phase-specific diagnostic coding; A07 distinguishes dementia from etiology. [A03](#a03), [A06](#a06), [A07](#a07).

**Implementation and limits:** The 28-day cutoff, tie preservation, past-only option and demographic consensus rules are project choices. Never infer biological AD from a dementia code, or apply ADNI3 coding to a different schema without verification.

<a id="stage-9-b"></a>

### Stage 9.B — s9b_validate_inclusion

**Evidence and location:** A03 and A06 provide clinical context; P01 Steps 6–8 applies cumulative imaging QC; Step 9 links clinical dates and flags unmatched visits rather than dropping them. [A03](#a03), [A06](#a06), [P01](#p01).

**Implementation and limits:** The 9.B clinical eligibility gate is project policy, not an exact reproduction of P01 Step 9. Combining independent receipts, preserving exclusion precedence and confirmed ST/conversion evidence are engineering/policy controls. Metadata eligibility is not completed imaging quality or final scientific inclusion.

<a id="stage-10"></a>

### Stage 10 — s10_xcpd_integrated_qc

**Evidence and location:** P10 §§2.6,2.9–2.14 describes initial-volume removal, denoising/censoring and coverage. P20/P09/P17 evaluate expanded confounds and trade-offs; P16/P21 explain filtering/regression compatibility. [P10](#p10), [P20](#p20), [P09](#p09), [P17](#p17), [P16](#p16), [P21](#p21), [P08](#p08).

**Implementation and limits:** 36P/GSR has empirical support and trade-offs. P10 describes FD 0.3 mm/240 s defaults, not ADNI-specific optimal thresholds. The exact current flags, output-count guard and Euler review policy still require project/cohort validation.

<a id="stage-11"></a>

### Stage 11 — s11_atlas_bold

**Evidence and location:** P12 establishes the Schaefer atlas used in this stage example; P10 §2.14 describes ROI averaging/coverage. [P12](#p12), [P10](#p10).

**Implementation and limits:** Schaefer 400/7 networks is an example, distinct from the S10 default 4S256 composite. Template identity, label resampling and acquisition-frame linkage are implementation controls; 50% coverage is not a universal anatomical-validity threshold.

<a id="stage-12"></a>

### Stage 12 — s12_metrics_summary

**Evidence and location:** P22 describes anatomical segmentation/volumetry; P15 describes cortical thickness; P13 defines ReHo; P14 describes ALFF; P10 describes derivative production. [P22](#p22), [P15](#p15), [P13](#p13), [P14](#p14), [P10](#p10).

**Implementation and limits:** This stage exports already calculated archive values and their provenance; it does not compute those methods again. A populated scalar or report link is not proof of biological validity. Retain NA and source units.

<a id="stage-14"></a>

### Stage 14 — s14_fc_harmonization

Yu et al. evaluated ComBat on multisite FC. Blujus et al. used upper-triangle Fisher-z features in ADNI. This implementation uses a reviewed site/scanner batch, 4S256 connectomes and one acquisition per participant. Batch size, coverage and visit rules belong to this analysis design. [Yu et al.](https://doi.org/10.1002/hbm.24241) · [Blujus et al.](https://doi.org/10.1002/hbm.70622) · [Alternatives and implementation repositories](fc_harmonization.md).

## Parameter and policy traceability

| Current decision | Source-supported point | Exact status in this project |
|---|---|---|
| Acquisition date, not VISCODE equality | A01/A02 | Direct rationale. Same-day-only automatic execution is stricter than A02, which allows considering adjacent-time anatomy. |
| QC → chosen → grade; keep all top ties | A05/A09 describe grading/chosen evidence | The combined ranking and tie policy are ours. Neither source prescribes Image-ID sorting or an acceleration preference. |
| Cross-date review window = null | No source establishes a universally safe maximum gap | Inventory only; never unrestricted execution. Future anatomy and prediction-time availability require study review. |
| EPI clinical nearest 28 days | A03 supports a researcher-defined window; P01 Step 9 uses 180 days | 28 days is a project policy. It is not a T1 reference-pool cutoff. |
| Stage 5 TR 0.5–1.0 or 2.9–3.1 s; depth 155–180 mm; total duration ≥ 300 s; no BODY/Q-Body | P01 Table 2 | Inherited GO/2/3 heuristics. P18 §2.8 shows why automatic application to ADNI4 is inappropriate. |
| Stage 5 PercentPhaseFOV > 72 | P01 Table 2 excludes < 72 | Existing implementation differs exactly at 72; this reference update records that discrepancy without changing selection behavior. |
| Stage 6 robust transformed IQM tails beyond ±4 | P01 Step 6 | A preprint-specific cohort method, not an externally established universal MRIQC threshold. Actual fitting population and uncertainty remain relevant. |
| Stage 8.A FD > 0.5 mm, ≤30% censored, ≥300 s retained | P01 Step 8 | Protocol-comparison rule. S10 settings differ. |
| S10 FD 0.3 mm and ≥240 s after censoring | P10 §2.13 final published paper | Published XCP-D defaults adopted here; not evidence of optimality for ADNI. Do not cite the older preprint's duration default. |
| S10 dummy_scans=auto | P10 §2.6 | Published optional method. Enabling it, rejecting insufficient removal and checking output counts are project safeguards. |
| S10 36P/GSR; filtering 0.01–0.08 Hz; smoothing 6 mm | P09/P10/P16/P17 | Model/method evidence, with potential signal and degrees-of-freedom trade-offs. Validate QC–FC, distance dependence, retained data and group effects. |
| Euler per session; participant-balanced site median; threshold 5; minimum 10 subjects | P08 supports Euler as a quality indicator | This exact aggregation/cutoff/reference-size combination is a project adaptation. No cited paper validates minimum 10 as universal. |
| ROI coverage ≥0.5 | P10 §2.14 | Software-method threshold adopted here; not proof of registration quality or suitability of every parcel. |
| Version/digest, seed 1123, OMP1, hashes, receipts, logs, retries | No scientific source prescribes these exact values/formats | Engineering/reproducibility controls, tested as code contracts. They do not establish cohort validity. |

## ADNI official answers

<a id="a01"></a>

**A01 — [ADNI VISCODE answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2126).** Monica E. (2025-02-27), QID 2126. Response paragraphs on scheduled VISCODE2 versus elapsed time; use actual EXAMDATE for time intervals.

<a id="a02"></a>

**A02 — [ADNI EPI–T1 pairing answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=434).** ADNI MRI Core (2015-02-20), QID 434. Response on raw fMRI, acquisition-date T1/T2 selection, possible adjacent-time anatomy after QC failure, and researcher choice of acceleration. No maximum gap is specified.

<a id="a03"></a>

**A03 — [ADNI imaging–diagnosis answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2401).** Danielle (2026-02-09), QID 2401. Response on nearest diagnosis within a researcher-defined time window when MRI and clinical dates differ.

<a id="a04"></a>

**A04 — [ADNI NFQ/slice-order answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=1822).** Mayo ADIR lab ADNI team (2024-03-06), QID 1822. Response identifying the GO/2/3 NFQ deliverable as a source of estimated slice order; not an ADNI4 timing or quality approval.

<a id="a05"></a>

**A05 — [ADNI repeated T1 and grade answers](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=89).** Bret Borowski (2013-10-24 and 2013-10-29), QID 89. Responses on repeated ADNI1 T1 acquisitions and grades 1 excellent/very good, 2 good, 3 fair/poor, 4 unusable. Historical T1 grading is not a universal functional-analysis acceptance rule.

<a id="a06"></a>

**A06 — [ADNI diagnosis-code answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=1756).** Adam Diaz (2023-09-19), QID 1756. Response distinguishes ADNI3 DIAGNOSIS (1 CN, 2 MCI, 3 Dementia) from legacy GO/2 DXCHANGE recoding. Apply only to the corresponding source schema.

<a id="a07"></a>

**A07 — [ADNI dementia-etiology answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=209).** Jessie, IDA (2014-03-19), QID 209. Response directs AD-versus-other-dementia determination to Diagnostic Summary. It does not validate a current all-phase etiological algorithm.

<a id="a08"></a>

**A08 — [ADNI4 ARC quality answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2541).** ADNI MRI Core (2026-08-20), QID 2541. Response states that ADNI4 ARC Builder displays series passing QC and marked chosen. This is specific to that interface/scope; missing evidence elsewhere is not a pass.

<a id="a09"></a>

**A09 — [ADNI chosen-series answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=454).** ADNI MRI Core (2015-04-07), QID 454. Response describes QC selection among repeated MPRAGE scans, including a first-acquired choice if equally good. Consume the recorded chosen flag; do not manufacture it from Image ID order.

<a id="a10"></a>

**A10 — [ADNI FAQ answers](https://adni.loni.usc.edu/help-faqs/faqs/).** ADNI official FAQ; named respondent/date not displayed. Relevant questions: “How do I download data?”, “How do I get the clinical data?”, image-to-numeric-summary correspondence, and fMRI timing/default slice order. These answers cover approved access, Image ID linkage, and DICOM/NFQ timing evidence.

## Research papers

<a id="p01"></a>

**P01 — [Rutherford et al. (2026)](https://doi.org/10.21203/rs.3.rs-11132707/v1).** A Pipeline for ADNI Resting-State Functional MRI Processing and Quality Control. Research Square, version 1, 2026-10-06. PREPRINT, not peer reviewed. [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC13692585/). Locations: Methods Steps 1–9, Tables 2–3, Results. Version-specific protocol evidence, not a universal ADNI standard.

<a id="p02"></a>

**P02 — [Gorgolewski et al. (2016)](https://doi.org/10.1038/sdata.2016.44).** The brain imaging data structure, a format for organizing and describing outputs of neuroimaging experiments. Scientific Data 3, 160044. Metadata requirements, conversion walkthrough Step 5 (validation), and Discussion. Peer-reviewed; the original paper describes BIDS 1.0, not all current specification details.

<a id="p03"></a>

**P03 — [Routier et al. (2021)](https://doi.org/10.3389/fninf.2021.689675).** Clinica: An Open-Source Software Platform for Reproducible Clinical Neuroscience Studies. Frontiers in Neuroinformatics 15, 689675. “Clinica Utilities” → “Conversion of Neuroimaging Datasets Into a BIDS Hierarchy” → “Conversion of the ADNI Dataset to BIDS”. Peer-reviewed; does not establish the behavior of every later converter release.

<a id="p04"></a>

**P04 — [Sladky et al. (2011)](https://doi.org/10.1016/j.neuroimage.2011.06.078).** Slice-timing effects and their correction in functional MRI. NeuroImage 58, 588–594. Methods → “Slice-timing correction approaches”, simulations and Discussion. Peer-reviewed; not a validation of ADNI NFQ matching or this metadata repair.

<a id="p05"></a>

**P05 — [Esteban et al. (2017)](https://doi.org/10.1371/journal.pone.0184661).** MRIQC: Advancing the automatic prediction of image quality in MRI from unseen sites. PLOS ONE 12, e0184661. IQMs, visual quality labels and held-out-site evaluation. Peer-reviewed; the classifier evaluation concerns structural T1w data, not this BOLD SHASH threshold policy.

<a id="p06"></a>

**P06 — [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4).** fMRIPrep: a robust preprocessing pipeline for functional MRI. Nature Methods 16, 111–116 (online 2018-12-10). Methods → “The fMRIPrep workflow”; Table 1 and Supplementary Note 3; visual-assessment validation. Peer-reviewed; supports the method, not a later exact version, seed or thread count.

<a id="p07"></a>

**P07 — [Power et al. (2012)](https://doi.org/10.1016/j.neuroimage.2011.10.018).** Spurious but systematic correlations in functional connectivity MRI networks arise from subject motion. NeuroImage 59, 2142–2154. FD/DVARS definitions, motion-related FC artifacts and censoring analyses. Peer-reviewed.

<a id="p08"></a>

**P08 — [Rosen et al. (2018)](https://doi.org/10.1016/j.neuroimage.2017.12.059).** Quantitative assessment of structural image quality. NeuroImage 169, 407–418. Methods on quantitative quality measures; Figure 5, Tables 3–4 and Limitations compare Euler with manual structural-image quality assessment. Hemisphere averaging is distinct from averaging separate visits. Peer-reviewed; does not validate this site-reference minimum or participant-median algorithm.

<a id="p09"></a>

**P09 — [Ciric et al. (2017)](https://doi.org/10.1016/j.neuroimage.2017.03.020).** Benchmarking of participant-level confound regression strategies for the control of motion artifact in studies of functional connectivity. NeuroImage 154, 174–187. Compared models and QC–FC/distance-dependence results. Peer-reviewed; not a proof of one universally optimal model.

<a id="p10"></a>

**P10 — [Mehta et al. (2024)](https://doi.org/10.1162/imag_a_00257).** XCP-D: A robust pipeline for the post-processing of fMRI data. Imaging Neuroscience 2, 1–26. Peer-reviewed final article, not the 2023 preprint. Sections 2.6 (initial volumes), 2.7 (despiking), 2.9–2.13 (denoising/filtering/censoring), 2.14 (parcellation/coverage), and functional derivatives. [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC12288603/).

<a id="p11"></a>

**P11 — [Behzadi et al. (2007)](https://doi.org/10.1016/j.neuroimage.2007.04.042).** A component based noise correction method (CompCor) for BOLD and perfusion based fMRI. NeuroImage 37, 90–101. Theory → “CompCor Algorithm”; Data Analysis → “Anatomical Definition of Noise ROI” and “Determination of Principal Components”. Peer-reviewed; does not prescribe the whole current 7.A configuration.

<a id="p12"></a>

**P12 — [Schaefer et al. (2018)](https://doi.org/10.1093/cercor/bhx179).** Local-Global Parcellation of the Human Cerebral Cortex from Intrinsic Functional Connectivity MRI. Cerebral Cortex 28, 3095–3114. Materials and Methods on cohort parcellation/network assignments, pp. 3100–3101; Figure 4. Peer-reviewed; the 400-parcel example is a project selection.

<a id="p13"></a>

**P13 — [Zang et al. (2004)](https://doi.org/10.1016/j.neuroimage.2003.12.030).** Regional homogeneity approach to fMRI data analysis. NeuroImage 22, 394–400. Materials and methods → “Regional homogeneity”, pp. 395–396, Equation 1 (local time-series concordance). Peer-reviewed.

<a id="p14"></a>

**P14 — [Zang et al. (2007)](https://doi.org/10.1016/j.braindev.2006.07.002).** Altered baseline brain activity in children with ADHD revealed by resting-state functional MRI. Brain and Development 29, 83–91. Section 2.5 “ALFF analysis” and Figure 1, pp. 85–86. Peer-reviewed; the empirical population is not ADNI.

<a id="p15"></a>

**P15 — [Fischl and Dale (2000)](https://doi.org/10.1073/pnas.200033797).** Measuring the thickness of the human cerebral cortex from magnetic resonance images. PNAS 97, 11050–11055. Surface-based cortical thickness estimation and validation. Peer-reviewed; does not establish accuracy of each new reconstruction.

<a id="p16"></a>

**P16 — [Hallquist et al. (2013)](https://doi.org/10.1016/j.neuroimage.2013.05.116).** The nuisance of nuisance regression: Spectral misspecification in a common approach to resting-state fMRI preprocessing reintroduces noise and obscures functional connectivity. NeuroImage 82, 208–225. Sections 3.1.3–3.1.4 and 3.3 analyze filtering/regression ordering. Peer-reviewed.

<a id="p17"></a>

**P17 — [Parkes et al. (2018)](https://doi.org/10.1016/j.neuroimage.2017.12.073).** An evaluation of the efficacy, reliability, and sensitivity of motion correction strategies for resting-state functional MRI. NeuroImage 171, 415–436. Abstract verified: comparative denoising evaluation and trade-offs. Full-text subsection locations were not independently verified. Peer-reviewed.

<a id="p18"></a>

**P18 — [Arani et al. (2024)](https://doi.org/10.1002/alz.14162).** Design and validation of the ADNI MR protocol. Alzheimer’s & Dementia (2024-08-08 online). Sections 2.6–2.8 and Table 1: separate ASL, diffusion and BOLD acquisitions; phase/scanner-dependent fMRI protocols, including ADNI4 changes. Peer-reviewed. [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC11497751/).

<a id="p19"></a>

**P19 — [Power et al. (2014)](https://doi.org/10.1016/j.neuroimage.2013.08.048).** Methods to detect, characterize, and remove motion artifact in resting state fMRI. NeuroImage 84, 320–341. Methods on QC/FD, Table 2 and Discussion. Peer-reviewed. First-frame FD=0 is a convention; later missing FD cannot be treated as measured zero.

<a id="p20"></a>

**P20 — [Satterthwaite et al. (2013)](https://doi.org/10.1016/j.neuroimage.2012.08.052).** An improved framework for confound regression and filtering for control of motion artifact in the preprocessing of resting-state functional connectivity data. NeuroImage 64, 240–256. Expanded confound models, Figures 8–9 and Discussion. Peer-reviewed; supports the model family, not universal ADNI cutoffs.

<a id="p21"></a>

**P21 — [Lindquist et al. (2019)](https://doi.org/10.1002/hbm.24528).** Modular preprocessing pipelines can reintroduce artifacts into fMRI data. Human Brain Mapping 40, 2358–2376. Sections 2.1–2.4 and empirical demonstrations in Section 3. Peer-reviewed; explains projection/order effects, without certifying every software implementation.

<a id="p22"></a>

**P22 — [Fischl et al. (2002)](https://pubmed.ncbi.nlm.nih.gov/11832223/).** Whole brain segmentation: automated labeling of neuroanatomical structures in the human brain. Neuron 33, 341–355. DOI: 10.1016/S0896-6273(02)00569-X. Abstract verified: automated anatomical labeling and comparison with manual measurements. Peer-reviewed; motivates segmentation-derived volumes, not the validity of every exported FreeSurfer result.
