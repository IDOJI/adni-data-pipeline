# Step 14 · Harmonize resting-state functional connectivity across scanners

Use this cohort-level stage for cross-sectional group comparisons after [final imaging QC in Step 10](../s10_xcpd_integrated_qc/README.md) and [clinical eligibility in Step 9.B](../s9b_validate_inclusion/README.md). It fits empirical-Bayes, parametric location-and-scale ComBat using a reviewed site/scanner batch, continuous scan age and categorical sex and diagnosis. It reads the archived XCP-D 4S256Parcels Pearson connectome and coverage file for each included resting-state run. Steps 11–13 are independent branches.

## Prepare private inputs

Copy [the example JSON](../../03_config/fc_harmonization.example.json) outside the repository. Use absolute paths for all inputs and a fresh output directory for each run.

| Field | Input |
|---|---|
| `inclusion_dir` | Step 9.B directory containing the hash-covered `inclusion_audit.tsv` and its `artifact.json` |
| `final_qc` | Step 10 cohort-finalized `postprocessing/<config_id>/finalizations/<timestamp>/final_qc_master.tsv` and its sibling `summary.json` with completed cohort finalization and matching counts |
| `config_id` | Exact archived Step 10 configuration ID shared by the cohort |
| `scanner_map` | Private tab-separated table with the columns below. Preserve leading zeros in site codes. |
| `min_batch_size` | Minimum participants per site/scanner batch after all eligibility and visit checks. The example uses five as a study setting. The model requires at least two per batch. |
| `output_dir` | New analysis directory outside the repository, inputs and pair archives |

The scanner table must have one reviewed record per EPI Image ID. Use scanner logs or validated acquisition metadata to identify a physical scanner or a documented scanner epoch. Record the equipment/protocol evidence in `review_ref`. Use `preprocessing_profile` for the reviewed common fMRIPrep settings, including output space, resolution and processing options. Use the same label only after comparing those settings. The code also compares the published fMRIPrep runner hash and container digest, and reads the XCP-D configuration from each archived pair.

Synthetic scanner TSV example (the last two columns are optional):

```tsv
image_id	ptid	date	site	scanner	review_ref	preprocessing_profile	pair_dir	tie_choice_ref
I901	999_S_9999	2020-01-01	999	scanner-A	review/log-001	surface-seed1123-omp1	/private/synthetic/pair-001	review/tie-001
```

Use `pair_dir` when the completed archive has moved from the master table's `source_pair`. S14 matches participant, Image ID and acquisition date independently of the folder name. It verifies the pair metadata, run/session, attempt, configuration digest and archived hashes for the execution, validation, FC and coverage. A historical metadata-only 9.B export can have artificial session labels. These rows still require an independent match on participant, Image ID and scan date as well as the verified S10 run.

## Run from RS-fMRI

```sh
python -m pip install -r requirements.txt -r pipeline/s14_fc_harmonization/requirements.txt
python 04_workflow/lab.py harmonize-fc --config /private/study/audit.json --audit-only
python 04_workflow/lab.py harmonize-fc --config /private/study/fit.json
```

Set a different `output_dir` in `fit.json`. Review the audit first. The audit can report missing final QC or scanner tables when the 9.B bundle is available. Inspect `artifact.json → summary.status` for `blocked` or `audit_passed`. A blocked fit returns a nonzero exit status. A successful fit returns `fitted`.

## How scans enter the model

1. Require 9.B eligibility, passing source and clinical QC, S10 final inclusion and successful validated XCP-D outputs. Verify the reviewed scanner and age, sex and diagnosis for that acquisition. Missing or conflicting evidence appears in `decisions.tsv`.
2. Check all 256 labels, their order, coverage against the archived threshold, symmetry, unit diagonal and finite correlations. Exact off-diagonal ±1 has no finite Fisher transform. The stage holds that observation and records the reason.
3. Select the earliest eligible acquisition per participant. If distinct eligible acquisitions tie on that date, supply one documented `tie_choice_ref` on the chosen scanner-map row. An unresolved tie holds the participant. An Image ID with multiple ambiguous runs requires upstream resolution.
4. Check at least two batches, the configured batch size, variation in the biological terms, rank of the batch/covariate design, residual degrees of freedom and edge variance. Inspect the age ranges and diagnosis/sex counts per batch. A full-rank design can still have little overlap.
5. Fit one model on the 32,640 unique off-diagonal Fisher-z edges per participant. Diagnosis is included for cross-sectional group inference. Prediction requires a separate within-training-fold design with covariates available at prediction time. Repeated-visit analyses require a longitudinal design.

## Outputs and interpretation

| File | Contents |
|---|---|
| `decisions.tsv`, `cohort.tsv` | All audited EPI decisions and reasons, then the exact participant and row order used for the model |
| `attrition.tsv`, `batch_design.tsv` | Row and distinct participant counts by site, scanner, diagnosis and decision/reason. Counts across strata can include the same participant. Batch design gives selected sex/diagnosis counts and age ranges. Blank scanner means identity was unavailable. |
| `edges.tsv`, `fc.npz` | Zero-based upper-triangle ROI pair order. Arrays have participants × edges dimensions. `raw_r`, `raw_z`, `adjusted_z` and `adjusted_r` preserve the inputs and adjusted values. Mirror edges and set the diagonal to 1 for a symmetric r matrix. Edgewise adjustment can yield a matrix with negative eigenvalues. |
| `model.npz` | Upstream ComBat estimates, including batch levels, estimated location and scale |
| `diagnostics.json`, `edge_coefficients.npz` | Before/after batch and biological coefficients and within-batch residual dispersion. Compare scanner reduction with retention of effects of interest. These descriptive results do not establish scientific acceptance. |
| `artifact.json` | Status, block reasons, source commit, versions, input/output SHA-256 hashes and cohort design |

## Evidence

See the [stage source register](../../06_docs/stage_evidence.md#stage-14) and [method comparison, ADNI applications and software repositories](../../06_docs/fc_harmonization.md). The baseline calls [neuroCombat](https://github.com/Jfortin1/neuroCombat) 0.2.12. Only synthetic data are used to test the model in this repository.
