# Stage 2 — Download

**What:** Export collection metadata and ADNI Study Files, review image candidates, then download the required T1w/resting-fMRI acquisitions.

**Output:** Image archives, collection CSVs, metadata and clinical/QC/NFQ CSVs.

## Run

1. Sign in to [LONI IDA](https://ida.loni.usc.edu/login.jsp) with approved ADNI access.
2. Export reviewed T1w and resting-fMRI collection CSVs with Image IDs, participant identifiers and actual acquisition dates. Record search phase, search criteria and data-freeze date. Retain available UID/scanner fields and visit labels.
3. Download matching Study Files, including clinical, MRI QC, NFQ and deletion records. Run [3.A source QC](../s3a_source_qc/README.md), then [3.B date-based selection](../s3b_image_selection/README.md) before reducing the imaging candidates.
4. Review the 3.B inventory and download the required images through IDA. Its `09.download-candidates.txt` lists positively identified target acquisitions with matching source identity; `10.download-for-qc-review.csv` identifies the subset available for inspection of missing QC. Download manually and retain the original filenames.
5. Store archives, exports and source-table versions outside the repository, following the [data layout](../../06_docs/data_preparation.md). Continue with [direct conversion](../s4_dcm2niix/README.md). A separate [DICOM inventory](../s3_organize/README.md) is optional.

Preserve every candidate EPI and the available T1 reference pool in the metadata audit. Do not restrict T1 downloads to the same VISCODE or prune the T1 reference inventory using the later clinical 28-day rule. Same-day proposals, cross-date review cases and unresolved ties are distinct states; no pairing proposal itself approves processing. See the [selection design](../../06_docs/date_based_selection.md).

This is a manual portal step; no downloader is included. If images are already downloaded, the same metadata workflow can reconcile their identities without downloading them again.

## Evidence and limits

Sources: [ADNI FAQ answers](https://adni.loni.usc.edu/help-faqs/faqs/); [Arani et al. (2024)](https://doi.org/10.1002/alz.14162). The [Stage 2 evidence record](../../06_docs/stage_evidence.md#stage-2) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
