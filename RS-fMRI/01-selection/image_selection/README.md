# Stage 3.B — Date-based image selection

For the [stage 1 walkthrough](../../README.md#select), set your study path and run `python start/01_select.py "$STUDY"` from `RS-fMRI/`.

**What:** Join explicit IDA collection exports to source QC and propose T1 references for each EPI using actual acquisition dates. This is a metadata inventory and review stage.

**Output:** An image registry, all T1 candidates, within-participant EPI/T1 links, one manifest row per distinct EPI Image ID, review records and a hashed receipt. No image processing starts here.

## Inputs and execution

From `RS-fMRI/`, after [setup](../../docs/installation.md):

1. Export reviewed T1 and resting-fMRI collection CSVs and the original Study Files through [Step 2](../../02-bids/download/README.md).
2. Produce [3.A source QC](../source_qc/README.md). Its `artifact.json` must bind the unchanged `image_qc.tsv` used here.
3. Copy [image_selection.example.json](../../config/image_selection.example.json) to an external private configuration and replace every `/ABS` path.
4. Run against a new external output directory:

```sh
python pipeline/s3b_image_selection/run.py --config /ABS/image-selection.json
```

Declare a search scope (`T1` or `EPI`); it is not evidence of series type. Mixed-phase IDA exports work directly: `Image ID`, `Subject ID`, `Study Date`, `Phase`, `Description` and `Imaging Protocol`. A file-level `phase` is only for verified uniform exports: when a Phase column exists each row must agree with that declaration. A blank row phase is held when no declaration is supplied. Visit and archive dates cannot stand in for acquisition dates. Optional `columns` mappings support other schemas. If search scope is omitted every ID must have a classifiable source modality.

Rebuild 3.A first: old artifacts lack original MRIQC series type/description. The collection is joined by Image ID and checked against participant, acquisition date, modality and available UID. Original spine type and both descriptions separate resting BOLD/T1w from non-target and ambiguous rows. The MRIQC spine's MoCoSeries and non-target T1 descriptors (ax/cor/SmartBrain/FLAIR) override quality grades. A Search-only MoCo label without corroboration remains held. Read manufacturer, field and model from dedicated or packed protocol fields; retain independent MRIQC values. Conflicting normalized evidence holds the image; missing model is never manufactured. The `ELIGIBLE` field records absence of a hard source exclusion; only `DOWNLOAD_ELIGIBLE` governs downloading.

## Pairing policy

- Preserve every raw row in the inventory. Keep target and unresolved search candidates visible for pairing; established non-target series do not enter pairing. Neither a T1's clinical diagnosis gap nor the later 28-day clinical rule removes it from the anatomical reference inventory.
- Prefer eligible same-day T1 candidates. Rank by documented QC, Mayo selection and quality grade, retaining all top ties. Unknown quality can remain a candidate but cannot authorize processing.
- If no eligible same-day T1 exists, rank cross-date candidates by documented QC, absolute date gap, Mayo selection and quality grade. Store signed gaps and flag future anatomy, scanner/phase differences and missing evidence.
- `cross_date_candidate_window_days: null` inventories all supplied dates; it does **not** authorize an unlimited pairing interval. A positive integer limits the candidates considered for cross-date review, retaining outside-window rows in the audit. Every cross-date proposal stays held.
- Acceleration is recorded, not used as a quality preference. Image ID ordering only makes reports stable; it never breaks a scientific tie.

All rows remain `PREPROCESSING_READY=False` and `ANALYSIS_READY=False` here. A unique `same_day_proposed` row still needs exact [5.D binding](../../02-bids/bids_identity/README.md), intake and later imaging/clinical checks. ADNI4 and other protocol extensions remain review cases.

## Output contract

| File | Purpose |
|---|---|
| `00.candidate-images.csv` | Normalized image identity, source QC and eligibility evidence |
| `01.pairing-policy.json` | Exact pairing policy used |
| `02.t1-reference-pool.csv` | All T1 candidates with reference eligibility |
| `03.epi-t1-candidates.csv` | All within-participant links, dates, ranks and review flags |
| `04.epi-analysis-manifest.csv` | One row per target or unresolved EPI search candidate, with QC and pairing state |
| `05.pairing-review.csv` | EPI rows requiring pairing/source review |
| `06.summary.json` | Counts and explicit scope limitations |
| `07.run-manifest.json` | Input/output hashes, implementation hashes and policy provenance |
| `08.collection-row-audit.csv` | Original file/row references and visit labels |
| `09.download-candidates.txt` | Union of source-QC-pass targets and targets downloadable for local inspection, after all other holds; never an execution list |
| `10.download-for-qc-review.csv` | Subset of 09 with missing grade evidence, exact identity and no independent hold; includes phase, reasons and source-row references |

`DOWNLOAD_TIER` is `source_qc_pass`, `for_qc_review` or `held`. A positive class requires a matching MRIQC spine. When only a Mayo assessment or a functional NFQ grade is missing, retrieving an image for inspection does not grant it a passing grade. A different phase, known failure, ambiguous identity, undefined grade or scanner conflict remains held. Use the tier or 10 to distinguish these populations before interpreting 09. Rebuild 3.A and 3.B to obtain phase-specific reason codes. See [missing evidence by phase](../../docs/date_based_selection.md#reading-missing-evidence-by-phase).

An optional `confirmed_exclusions` CSV requires `IMAGE_ID`, `PTID`, `MRI_STUDY_DATE`, `MODALITY`, `REASON` and `CONFIRMED`. Use exact identity and explicitly reviewed conversion/slice-timing failures; absence of a sidecar is not sufficient evidence.

The runner verifies source-QC outputs, detects changing inputs, refuses an existing output directory and records hashes for the 5.D handoff. Synthetic tests exercise policy and file contracts. They do not establish real-cohort equivalence, anatomical suitability or successful conversion. See the [design and evidence guide](../../docs/date_based_selection.md) for the distinction between published methods and project policy.

## Optional private comparison

After selection, run the following on the two existing Research Search/QC exports (`image_id,PTID,STUDY_DATE`). The union report includes all raw IDs, even images in neither list. A second report contains only changes with all contributing reasons, QC record references and descriptions. Duplicate IDs, conflicting historical identities and a download file that disagrees with the registry stop the audit. The external receipt binds the compared files. These are stage-matched lists, not a comparison against final clinical or preprocessing cohorts.

```sh
python pipeline/s3b_image_selection/reconcile.py --receipt /ABS/new-step3b/07.run-manifest.json \
  --legacy-t1 /ABS/search_T1_QC_filtered.csv --legacy-epi /ABS/search_EPB_QC_filtered.csv \
  --output-dir /ABS/private/new-comparison
```

## Evidence and limits

Sources: [ADNI VISCODE answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2126); [ADNI EPI–T1 pairing answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=434). The [Stage 3.B evidence record](../../docs/stage_evidence.md#stage-3-b) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
