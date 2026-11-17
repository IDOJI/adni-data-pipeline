# Processing stages

All maintained RS-fMRI stages are in this folder.

Every stage README has an evidence section linked to the [stage-by-stage source register](../06_docs/stage_evidence.md). Scientific references are limited to ADNI official answers and research papers; operational controls and project-specific choices are labeled separately.

New ADNI selection follows **2 (collection/Study File metadata) → 3.A (source QC) → 3.B (actual-date EPI/T1 proposals) → 2/3/4 (download/inventory/conversion) → 4.B/5 → 5.D (exact image binding) → guarded 6/7.B → S8/S10 → 9.A/9.B → 11**. [3.B](s3b_image_selection/README.md) keeps all images and does not use VISCODE as a date or identity key. [5.D](s5d_bids_identity/README.md) requires one verified same-day reference before execution. Session lists from 5.C alone do not establish that reference. See the [decision diagram and literature](../06_docs/date_based_selection.md).

Use the [step table](../README.md#steps-and-commands) to choose a stage. Each stage README gives its function, output and commands. Start with [installation](../06_docs/installation.md) or the [local batch runner](../06_docs/local_batch.md).

The skeleton was adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol). Original [GPL license](LICENSE) and [citation](CITATION.cff) are retained.
