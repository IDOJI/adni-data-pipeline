# 🧠 Functional connectivity and harmonization after atlas selection

Evidence and repository documentation reviewed: **2026-11-02**.

## Recommendation and implementation status

**ComBat is a reasonable first baseline to evaluate for multi-scanner ADNI resting-state FC.** Direct ADNI applications and broader FC validation support this choice. This is a practical recommendation based on selected primary studies, not a systematic count establishing the most frequently used method or a guarantee that ComBat is optimal for this cohort. Harmonization should follow a reviewed study design; a single-batch dataset does not automatically need ComBat.

The intended analysis sequence is:

```text
Reviewed denoised BOLD + a pinned atlas in the correct space
  -> Step 11: ROI time series + labels + coverage + acquisition-frame evidence
  -> Pearson FC for each reviewed run, with an explicit run/visit policy
  -> Fisher-z off-diagonal edges in a fixed atlas/edge order
  -> Cohort-level batch/covariate audit
  -> ComBat baseline, with prespecified alternatives when appropriate
  -> Harmonization evaluation
  -> Group inference, prediction, or graph/network analysis
```

| Component | Current repository status |
|---|---|
| [Step 11 atlas selection and BOLD extraction](../02_custom/s11_atlas_bold/README.md) | Implemented; produces time series and spatial/temporal audits, without computing FC |
| [S10 XCP-D products](../02_custom/s10_xcpd_integrated_qc/README.md) | Separate existing atlas/FC products and validation; their atlas, preprocessing and provenance must be checked before reuse |
| Selected-atlas Step 11 FC adapter | Proposed downstream connection; no runnable adapter or workflow command is introduced by this document |
| Cohort FC harmonization | Proposed design and external software references; no ComBat fitting, package installation or cohort validation has been performed here |
| Step 12 scalar/report export | An independent reporting branch; its position after Step 11 in the README does not make it an FC or harmonization step |

Harmonization is across scans/participants, not across the time points of one BOLD run. Preserve original FC alongside adjusted FC. Do not pool different atlases, ROI orders, templates or denoising profiles as though they were the same features. The existing 7.A aCompCor and S10 36P/GSR branches remain distinct.

## Direct ADNI evidence

### Blujus et al. (2026), Human Brain Mapping

[The Impact of Denoising Approaches on the Relationship Between Alzheimer's Disease Diagnostic Status and Network Topology Measures](https://doi.org/10.1002/hbm.70622) documents an ADNI application.

| Item | Reported setting |
|---|---|
| Cohort | ADNI-2/3; CN, MCI and AD |
| Atlas/FC | Power 264; Pearson correlation followed by Fisher z |
| Harmonization | R ComBat on unique upper-triangle edges |
| Batch | Manufacturer: GE, Philips, Siemens |
| Preserved covariates | Age, sex, diagnosis, APOE4 carrier status, education |
| Downstream analysis | Reconstructed symmetric matrices, then graph construction |

The paper reports a **34,716 × 156** harmonization input. However, participant counts are **60 CN + 55 MCI + 38 AD = 153**, and manufacturer counts also total 153. Report both counts; the fitted sample size is unresolved.

Scanner-associated edges fell from approximately **1–37% to 0%** under the paper's FDR-controlled tests. This indicates reduced detectable scanner differences, not proof that all confounding disappeared. Its Philips scans were ADNI-2 and GE/Siemens scans ADNI-3, limiting separation of manufacturer and phase effects. [Primary source](https://onlinelibrary.wiley.com/doi/full/10.1002/hbm.70622).

## Additional evidence and its scope

| Study | Data and relevance | Method and interpretation |
|---|---|---|
| [Gao et al. (2023), NeuroImage](https://doi.org/10.1016/j.neuroimage.2023.120277) — Functional alterations in bipartite network of white and grey matters during aging | ADNI-2/3, BLSA and OASIS-3; white–gray matter FC rather than a standard cortical-only connectome | ComBat through neuroCombat R; preserved age/sex; direct ADNI use, with a different feature definition |
| [Yu et al. (2018), Human Brain Mapping](https://doi.org/10.1002/hbm.24241) — Statistical harmonization corrects site effects in functional connectivity measurements from multi-site fMRI data | Four-site FC validation, not an ADNI application | ComBat reduced site effects in connectivity/network measures while retaining age associations; results depend on atlas and connectivity metric |
| [Chen et al. (2022), NeuroImage](https://doi.org/10.1016/j.neuroimage.2022.119198) — Harmonizing functional connectivity reduces scanner effects in community detection | FC and community/network analyses outside the cited ADNI application | FC-ComBat, Block-ComBat and FC-CovBat; supports comparison when community structure is an outcome |
| [Wang et al. (2023), NeuroImage](https://doi.org/10.1016/j.neuroimage.2023.120089) — Comprehensive evaluation of harmonization on functional brain imaging for multisite data-fusion | Evaluation of 11 rs-fMRI harmonization methods | Reported favorable SMA performance; this does not establish SMA as the most widely used ADNI FC method |
| [Zhang et al. (2026), Alzheimer's & Dementia](https://doi.org/10.1002/alz.71891) — Excitation–inhibition imbalance links amyloid pathophysiology to cognition in non-demented individuals | ADNI rs-fMRI-derived regional E/I estimates | ComBat on estimated regional E/I ratios; adjacent evidence, not a direct edgewise FC-harmonization example |

Useful reading order: Blujus for a direct ADNI FC precedent; Yu for FC validation; Chen for community structure; Gao for another ADNI application; Wang for alternatives. Publication venue alone does not establish suitability for the present cohort.

## Connected software repositories

These are verified source/documentation links, **not newly installed dependencies or Git submodules**. The recorded revisions identify the documentation reviewed, not versions already tested with this pipeline. Before implementation, select and lock package versions/commits, check licenses and dependencies, and validate the chosen API.

| Priority/use | Repository | Role and interface |
|---|---|---|
| Baseline, Python | [Jfortin1/neuroCombat](https://github.com/Jfortin1/neuroCombat) | Direct ComBat implementation; `neuroCombat`; features × scans input; categorical and continuous covariate declarations |
| Baseline, R | [Jfortin1/neuroCombat_Rpackage](https://github.com/Jfortin1/neuroCombat_Rpackage) | Implementation cited by Gao; `neuroCombat`; features × scans input; biological design matrix via `mod` |
| Nonlinear effects / learn–apply separation, Python | [rpomponio/neuroHarmonize](https://github.com/rpomponio/neuroHarmonize) | ComBat extensions, optional GAM covariates and `harmonizationLearn`/`harmonizationApply`; scans × features input with a `SITE` covariate |
| Network/community comparison, R | [andy1764/FCHarmony](https://github.com/andy1764/FCHarmony) | `fcComBat`, `blComBat`, `fcCovBat`; FC-specific harmonization and evaluation; CovBat dependency |

Reviewed documentation snapshots:

- neuroCombat: [README at ac82a067412078680973ddf72bd634d51deae735](https://github.com/Jfortin1/neuroCombat/blob/ac82a067412078680973ddf72bd634d51deae735/README.md).
- neuroCombat R: [README at fbec46a61bc92bedb450b0e44addae4ce6afa934](https://github.com/Jfortin1/neuroCombat_Rpackage/blob/fbec46a61bc92bedb450b0e44addae4ce6afa934/README.md).
- neuroHarmonize: [README at 22c550b68e8413f5a64b279afb7e6796185f6a0d](https://github.com/rpomponio/neuroHarmonize/blob/22c550b68e8413f5a64b279afb7e6796185f6a0d/README.md).
- FCHarmony: [README at a31b96b9d7b993e7a68f846155fbbdde5131cd8e](https://github.com/andy1764/FCHarmony/blob/a31b96b9d7b993e7a68f846155fbbdde5131cd8e/README.md).

neuroCombat and neuroHarmonize both provide ComBat. GAM modeling is an optional extension, not a different method automatically enabled by choosing neuroHarmonize. Learn/apply support also does not by itself establish generalization to previously unseen scanners. Its documented holdout constraints require an explicit compatibility check. [neuroHarmonize documentation](https://github.com/rpomponio/neuroHarmonize#applying-pre-trained-models-to-new-data).

Additional comparison sources: [CovBat_Harmonization](https://github.com/andy1764/CovBat_Harmonization), [Wang's 2023 study scripts](https://github.com/Chaogan-Yan/PaperScripts/tree/master/WangYW_2023_NeuroImage), and the [SMA implementation linked by those scripts](https://github.com/hzhoustat/PNAS2018). The study scripts document MATLAB/R/Python components; they are not drop-in replacements for a Python FC adapter.

## Proposed FC handoff from Step 11

The following items are implementation requirements to review before adding executable stages, not new study inclusion cutoffs.

1. **Bind inputs to the actual run.** Read `timeseries.tsv`, `labels.tsv`, `frames.tsv`, `roi_coverage.tsv` and `artifact.json` together. Preserve the atlas ID/hash/space, BOLD hash, preprocessing profile, 9.B evidence and acquisition-frame mapping. Keep pending inclusion pending.
2. **Fix the observation policy.** Prespecify whether one row represents a run, visit or participant, and how multiple runs are combined. Never concatenate visits or duplicate participants without an explicit design. Keep participant identifiers in external metadata so repeated observations and train/test membership can be checked.
3. **Audit signals before FC.** Record finite/constant/missing ROI signals and the exact retained frames. Do not replace missing ROIs or undefined correlations with zero, or silently use a different ROI set in each scan. Coverage flags remain evidence for review; the extractor's configurable 0.5 default is not a universal scientific exclusion threshold.
4. **Compute and identify edges.** For a reviewed Pearson baseline, retain one symmetric correlation matrix per observation and one fixed unique off-diagonal edge map. For 400 ROIs this gives 79,800 edges; for 264, 34,716. Preserve both raw correlations and Fisher-z edge features. Diagonal self-correlations are not harmonization features. Document handling of exact off-diagonal ±1 values before the Fisher transform rather than silently clipping them.
5. **Respect censoring provenance.** Static Pearson FC can use paired retained samples across ROIs without pretending censored gaps are new continuous acquisition time. Preserve original frame gaps and retained duration. Any later temporal filtering, spectral or lag-based method requires its own timing-aware design; do not filter an already compressed series as though it were regularly sampled or repeat upstream denoising by default.
6. **Export auditable products.** Proposed outputs: `fc_r`, `fc_z_edges`, `edge_index.tsv`, `observations.tsv` and an artifact containing input/output hashes, settings, missingness and status. These names describe a future contract, not files already produced by Step 11.

If reusing S10's FC instead, verify the same atlas, ROI order, estimator, retained-sample policy and denoising provenance explicitly. Availability of an FC file alone does not establish equivalence to the selected Step 11 atlas.

## ADNI batch and covariate design

Audit the actual cohort metadata before choosing a batch. Candidate fields include acquisition site, scanner identity, manufacturer/model, field strength, software changes, protocol, phase, TR and multiband status. Tabulate their overlap with age, sex, diagnosis and other target variables. Select a justified batch definition with enough observations and biological overlap to estimate the model; avoid adopting manufacturer solely because one paper used it.

Manufacturer is coarse: scanners at different sites can share a manufacturer, and manufacturer can be coupled to phase/protocol. Conversely, a fine site × scanner × protocol batch can create sparse cells. Document that tradeoff. Do not add redundant batch and phase indicators to a rank-deficient design or claim a model can identify effects perfectly confounded with diagnosis.

| Analysis aim | Covariate plan to review |
|---|---|
| CN/MCI/AD group inference | Consider age, sex, education and other scientifically justified variables. Diagnosis can be preserved when it is the target effect. APOE4 is a study-design choice, not a mandatory universal adjustment. Record missingness and the intended estimand. |
| Disease prediction | Exclude the target diagnosis and unavailable future information from harmonization covariates. Fit harmonization and all learned preprocessing within training folds; apply frozen parameters to compatible validation/test data. Split repeated visits by participant. |
| Nonlinear age associations | Consider ComBat-GAM when justified by age range, support and model diagnostics; assess held-out covariate-range compatibility. |
| Longitudinal change | Prespecify repeated-measures handling. Baseline fitting followed by application is not equivalent to a model of within-subject trajectories. Evaluate a longitudinal method when needed. |

For repeated-measures methodology, see [Beer et al., Longitudinal ComBat (2020)](https://doi.org/10.1016/j.neuroimage.2020.117129). Its ADNI demonstration used cortical thickness, so applicability to FC still requires validation.

Do not fit ComBat separately by diagnosis and then compare those groups as if they shared one harmonization model. For external-site prediction, ordinary within-site cross-validation and transfer to an unseen scanner are different validation problems; define the latter explicitly.

## Harmonization evaluation and acceptance

Start with an unharmonized reference and a prespecified ComBat baseline. Consider FC-CovBat for covariance/community outcomes, ComBat-GAM for justified nonlinear effects, and SMA as a comparative method. Choose comparisons around the scientific outcome rather than a claim of universal superiority.

- **Input integrity:** fixed atlas/edge schema and observation order; finite features; covariate completeness/encoding; batch counts; design rank; repeated participants; package orientation. A transpose error can silently swap edges and scans.
- **Scanner effects:** before/after edge distributions, location/scale differences and residual multivariate site predictability, with evaluation independent of tuning where possible. A nonsignificant site test alone is insufficient evidence of successful harmonization.
- **Biological effects:** prespecified age/diagnosis associations, effect sizes, stability and held-out performance as appropriate. Statistical adjustment should not be judged solely by how much site predictability disappears.
- **Network effects:** compare community assignments and graph metrics before/after adjustment, with a documented policy for negative edges, thresholding and density. These graph choices are separate from fitting ComBat.
- **Matrix properties:** edgewise adjustment need not preserve positive semidefiniteness. If a downstream method requires a valid correlation/covariance matrix, test that requirement and validate any repair separately; symmetry or inverse Fisher transformation alone is insufficient. [Chen et al., limitations](https://pmc.ncbi.nlm.nih.gov/articles/PMC9202339/).
- **Provenance:** save the fitted model, batch mapping, covariate encoding, edge map, training membership, software versions and before/after report outside the public repository. Retain raw FC and any failed or held observations with reasons.

This document does not introduce numeric pass/fail thresholds for those comparisons. Study criteria require explicit scientific justification. Harmonization cannot reconstruct a missing ROI, correct misregistration, recover signal dropout or replace motion/coverage/clinical review. Existing QC settings, the nearest/28-day policy and pending-state preservation remain unchanged.

## Next implementation decisions

Before implementing the selected-atlas FC and harmonization adapters, resolve: observation/run aggregation policy; primary atlas/estimator; cohort and batch definition; inferential versus predictive use; covariates and missingness; repeated visits; software lock; and independent validation outcomes. Then add executable code and meaningful synthetic/real-cohort validation with updated workflow contracts. The present change supplies the English evidence summary, repository connections and integration design only.
