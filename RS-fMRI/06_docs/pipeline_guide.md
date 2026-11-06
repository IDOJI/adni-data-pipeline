# Extending and connecting steps

## Where to add a step

Create only the additional steps needed after an upstream stage: for example, `02_custom/s3a_*` after s3, `02_custom/s5c_*` after s5's 5a/5b, and `02_custom/s7a_*` after s7. Update the execution table in the root RS-fMRI README in the same change.

## Required content for each Custom Step

Start the README with an Execution (or Integrated execution) section containing a complete terminal command block. Explain its action, required working directory, replaceable input paths and expected result location immediately below. Follow with Purpose, Input, Processing, Output, Validation and Dependencies. Label previews, real computation, manual review and optional persistent services explicitly; keep existing section anchors stable. Maintain code, scientific criteria and synthetic tests together. Write results to an external directory disjoint from the input trees.

Independent reporting steps create new outputs only. Steps that alter participants, sessions, images or inclusion tables must check the next upstream stage's actual input options and add adapters and contract tests. Do not assume `prepare-config` resolves every script's hardcoded settings.

## Implemented connections

- 3.A: source QC/NFQ/deletion and identity audits; create a source artifact without historical RDS inputs.
- 5.C: validate upstream final_heuristics.tsv, optionally apply the 3.A source-QC gate and generate Step 6/7 inputs. Clinical selection is separate.
- 7.A: execution, audit and metadata repair for the existing Docker volume aCompCor profile, with scientific settings separate from S10.
- 8.A: reuse existing local motion-duration QC. It does not automatically join upstream final tables; record research inclusion decisions separately for failed/held runs.
- 9.A: validate evidence and exceptions for diagnoses, PTDEMOG and optional APOE/auxiliary sex sources linked to actual scan dates. Exclude TEAM and preserve same-scope participant-static sex-filling evidence.
- 9.B: combine 3.A, corrected 9.A v2 and explicitly confirmed ST absence; fix nearest/28-day matching and retain pending. Optionally apply reviewed conversion failures and preserve S10 imaging decisions.
- S10: S8 collection, 36P/LINC XCP-D, integrated imaging QC and validated archival gates for completed pairs; export actual image dates/IDs to 9.A. See [input and transition boundaries](xcpd_consolidation.md).
- 11: optional pinned atlas library and streaming volumetric ROI extraction after 9.B; exact spaces, labels, brain-mask coverage and frame identities audited. No temporal re-cleaning or FC calculation.
- `04_workflow/lab.py plan`: print commands for known entry points. It is not an orchestration engine for automatic stage execution, scheduler submission or error recovery.

## Unresolved upstream boundaries

Session-restricted MRIQC execution, fitting-population limits, upstream s8 missing-value handling/TSV inputs and a complete Mac adapter remain future work. Step 9.A validates diagnostic mapping, date windows and ties; it does not remerge every cognitive score or replace research inclusion decisions. Passing current code tests does not establish those capabilities.

## Reproducibility and standalone reporting

Use the [public/offline walkthrough](../07_reproducibility/README.md) for copied terminal commands and reviewed reference values. Optional 5.D verifies an explicit pair before dispatch, 7.C adds prospective ANTs iteration logs, and 12 exports existing validated archive scalars/reports after S10. See each step README for its input/output/validation contract. The examples do not install live services or determine cohort inclusion.

## Host-specific stage instructions

The [macOS/Linux guide](platform_execution.md) documents every upstream/custom position using the owned protocol and Custom Steps. Each Custom Step links to its own host section. Preserve the scientific profile and provenance when changing hosts; document and validate service/publication/volume adapters separately from imaging algorithms.

## Processing-time records

[Step 7.D](../02_custom/s7d_processing_timing/README.md) runs alongside 7.B and S10. Keep timing reports outside source/verified pair payloads, count retries explicitly, and distinguish stage-time sums from the elapsed pipeline wall span. An independent collector can record legacy completions without changing active deployment hashes.

The [independent Docker observer](processing_timing.md) is a separate entry point. It shares only the display helper with Step 7.D, preserves raw numeric CSVs, and does not change the receipt/wall-span definition. S12 pair timing files require exporter ownership and an unambiguous single published pair.
