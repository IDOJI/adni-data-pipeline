# Extending and connecting steps

## Where to add a step

Create only the additional steps needed after an upstream stage: for example, `02_custom/s3a_*` after s3, `02_custom/s5c_*` after s5's 5a/5b, and `02_custom/s7a_*` after s7. Update the execution table in the root RS-fMRI README in the same change.

## Required content for each Custom Step

Include Purpose, Input, Processing, Output, Execution, Validation and Dependencies in its README. Maintain code, scientific criteria and synthetic tests together. Write results to an external directory disjoint from the input trees.

Independent reporting steps create new outputs only. Steps that alter participants, sessions, images or inclusion tables must check the next upstream stage's actual input options and add adapters and contract tests. Do not assume `prepare-config` resolves every script's hardcoded settings.

## Implemented connections

- 3.A: source QC/NFQ/deletion and identity audits; create a source artifact without historical RDS inputs.
- 5.C: validate upstream final_heuristics.tsv, optionally apply the 3.A source-QC gate and generate Step 6/7 inputs. Clinical selection is separate.
- 7.A: execution, audit and metadata repair for the existing Docker volume aCompCor profile, with scientific settings separate from S10.
- 8.A: reuse existing local motion-duration QC. It does not automatically join upstream final tables; record research inclusion decisions separately for failed/held runs.
- 9.A: validate evidence and exceptions for diagnoses, PTDEMOG and optional APOE/auxiliary sex sources linked to actual scan dates.
- S10: S8 collection, 36P/LINC XCP-D, integrated imaging QC and validated archival gates for completed pairs; export actual image dates/IDs to 9.A. See [input and transition boundaries](xcpd_consolidation.md).
- `04_workflow/lab.py plan`: print commands for known entry points. It is not an orchestration engine for automatic stage execution, scheduler submission or error recovery.

## Unresolved upstream boundaries

Session-restricted MRIQC execution, fitting-population limits, upstream s8 missing-value handling/TSV inputs and a complete Mac adapter remain future work. Step 9.A validates diagnostic mapping, date windows and ties; it does not remerge every cognitive score or replace research inclusion decisions. Passing current code tests does not establish those capabilities.
