# Stage 3.B — Date-based image selection

**What:** Join explicit IDA collection exports to source QC and propose T1 references for each EPI using actual acquisition dates. This is a metadata inventory and review stage.

**Output:** An image registry, all T1 candidates, within-participant EPI/T1 links, one manifest row per distinct EPI Image ID, review records and a hashed receipt. No image processing starts here.

## Inputs and execution

From `RS-fMRI/`, after [setup](../../06_docs/installation.md):

1. Export reviewed T1 and resting-fMRI collection CSVs and the original Study Files through [Step 2](../s2_download/README.md).
2. Produce [3.A source QC](../s3a_source_qc/README.md). Its `artifact.json` must bind the unchanged `image_qc.tsv` used here.
3. Copy [image_selection.example.json](../../03_config/image_selection.example.json) to an external private configuration and replace every `/ABS` path.
4. Run against a new external output directory:

```sh
python pipeline/s3b_image_selection/run.py --config /ABS/image-selection.json
```

Each collection declares its `path`, `phase` and `modality` (`T1` or `EPI`). The export must identify the participant, Image ID and actual acquisition date. Common headings such as `Subject`, `Image Data ID` and `Acq Date` are recognized. Use `columns` to map a nonstandard heading explicitly; do not map a visit code to `MRI_STUDY_DATE`. If modality is omitted for a mixed export, every image must be classifiable from the source-QC registry. Phase remains an explicit collection declaration.

Optional scanner/UID fields are retained. A UID missing from the export can come from the matched source record. Conflicting participant/date/modality/UID evidence blocks that image; missing quality remains pending. Repeated identical image records share one registry row while every original collection row remains in the audit. Conflicting copies fail instead of selecting the first row.

## Pairing policy

- Preserve every EPI and all supplied T1 candidates, including excluded and unresolved rows. Neither a T1's clinical diagnosis gap nor the later 28-day clinical rule removes it from the anatomical reference inventory.
- Prefer eligible same-day T1 candidates. Rank by documented QC, Mayo selection and quality grade, retaining all top ties. Unknown quality can remain a candidate but cannot authorize processing.
- If no eligible same-day T1 exists, rank cross-date candidates by documented QC, absolute date gap, Mayo selection and quality grade. Store signed gaps and flag future anatomy, scanner/phase differences and missing evidence.
- `cross_date_candidate_window_days: null` inventories all supplied dates; it does **not** authorize an unlimited pairing interval. A positive integer limits the candidates considered for cross-date review, retaining outside-window rows in the audit. Every cross-date proposal stays held.
- Acceleration is recorded, not used as a quality preference. Image ID ordering only makes reports stable; it never breaks a scientific tie.

All rows remain `PREPROCESSING_READY=False` and `ANALYSIS_READY=False` here. A unique `same_day_proposed` row still needs exact [5.D binding](../s5d_bids_identity/README.md), intake and later imaging/clinical checks. ADNI4 and other protocol extensions remain review cases.

## Output contract

| File | Purpose |
|---|---|
| `00.candidate-images.csv` | Normalized image identity, source QC and eligibility evidence |
| `01.pairing-policy.json` | Exact pairing policy used |
| `02.t1-reference-pool.csv` | All T1 candidates with reference eligibility |
| `03.epi-t1-candidates.csv` | All within-participant links, dates, ranks and review flags |
| `04.epi-analysis-manifest.csv` | One row per EPI, including unresolved or excluded images |
| `05.pairing-review.csv` | EPI rows requiring pairing/source review |
| `06.summary.json` | Counts and explicit scope limitations |
| `07.run-manifest.json` | Input/output hashes, implementation hashes and policy provenance |
| `08.collection-row-audit.csv` | Original file/row references and visit labels |
| `09.download-candidates.txt` | Nonblocked Image IDs, including pending QC; a manual download aid |

An optional `confirmed_exclusions` CSV requires `IMAGE_ID`, `PTID`, `MRI_STUDY_DATE`, `MODALITY`, `REASON` and `CONFIRMED`. Use exact identity and explicitly reviewed conversion/slice-timing failures; absence of a sidecar is not sufficient evidence.

The runner verifies source-QC outputs, detects changing inputs, refuses an existing output directory and records hashes for the 5.D handoff. Synthetic tests exercise policy and file contracts. They do not establish real-cohort equivalence, anatomical suitability or successful conversion. See the [design and evidence guide](../../06_docs/date_based_selection.md) for the distinction between published methods and project policy.

## Evidence and limits

Sources: [ADNI VISCODE answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2126); [ADNI EPI–T1 pairing answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=434). The [Stage 3.B evidence record](../../06_docs/stage_evidence.md#stage-3-b) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
