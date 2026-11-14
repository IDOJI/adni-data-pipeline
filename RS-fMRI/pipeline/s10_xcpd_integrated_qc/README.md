# Stage 10 — XCP-D and imaging QC

**What:** Denoise completed 7.B pairs, compute ROI/FC and ReHo/ALFF, and combine quantitative/visual imaging QC.

**Output:** Denoised derivatives and `qc_report.html` per pair; QC tables, `visual_review.tsv` and clinical scan links under `<root>/postprocessing/<config_id>/`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Copy [xcpd_linc.seeded.example.json](../../03_config/xcpd_linc.seeded.example.json) and set the external root, license and TemplateFlow paths. Input pairs must have `fmriprep/`, `mriqc/`, `pair_metadata.json` and their successful execution receipts; the [batch runner](../../06_docs/local_batch.md) publishes this layout.

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config /ABS/xcpd.json preflight
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config /ABS/xcpd.json dry-run
# Process and validate the first candidate.
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config /ABS/xcpd.json pilot
# After the pilot passes, process newly completed pairs continuously.
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config /ABS/xcpd.json watch
```

After cohort completion and visual review, finalize imaging QC:

```sh
python pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py --config /ABS/xcpd.json finalize \
  --cohort-complete --mriqc-flags /ABS/cohort-mriqc-flags.tsv
```

Pass the resulting `finalizations/<timestamp>/final_included_runs.tsv` and matching `clinical_scan_links.tsv` to [9.A](../s9a_validate_clinical/README.md).

Profile: XCP-D 26.2.0, 36P/GSR, FD 0.3 mm, minimum 240 s, 0.01–0.08 Hz, 6 mm smoothing, seed 1123/OMP1. Use one processing owner per root. Imaging QC finalization is separate from clinical/research inclusion.
