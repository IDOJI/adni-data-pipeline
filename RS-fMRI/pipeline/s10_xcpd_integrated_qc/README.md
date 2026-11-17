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

Profile: XCP-D 26.2.0, 36P/GSR, FD 0.3 mm, minimum 240 s, automatic initial non-steady-state removal, 0.01–0.08 Hz, 6 mm smoothing, seed 1123/OMP1. Use one processing owner per root. Imaging QC finalization is separate from clinical/research inclusion.

## Scientific QC policy and new runtimes

New configurations explicitly identify `qc_policy_version: sessionwise-euler-nss-v1`.
Both maintained examples have new run IDs and pipeline version 1.1.0. Use a new
runtime; do not edit a historical/private configuration in place or attach these
rules to a running calculation. Configurations lacking the new policy are rejected
before runtime creation. Historical results retain their frozen implementation and
configuration identity; this update does not retroactively approve or invalidate them.

The seeded example uses `dummy_scans: auto`. The initial removal count follows
XCP-D's last flagged non-steady-state frame plus one; the input flags must be finite
and binary. The unseeded example retains explicit `dummy_scans: 0` to demonstrate
integer semantics, but a run with detected non-steady-state frames is blocked until
an adequate count or `auto` is selected in a new configuration. Output QC verifies
the actual removed count against the source confounds, then checks motion-mask and
retained-frame counts. A 36P nuisance model does not itself remove these frames.
[XCP-D 26.2.0 workflow documentation](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html)
describes automatic removal and the nuisance models.

Euler QC scores each session's actual reconstruction separately. Conflicting
reconstruction identities or measurements for one session are rejected. Repeated
BOLD runs do not duplicate the anatomical reference. Within each site, participant
medians in square-root-negative-Euler space receive equal weight when estimating
the site median; individual visit decisions are never averaged. The existing
threshold of five above this site reference is retained. Values from zero through
two are valid topologies; nonfinite values and values above two require correction.

`euler_min_reference_subjects` defaults to 10 distinct participants (configurable,
minimum 3). This is a **project safeguard**, not a literature-established universal
sample-size cutoff. Smaller groups remain pending until the reviewer explicitly
records `euler_visual_qc_status=pass`, an anatomical reason, their name and date in
`visual_review.tsv`, in addition to any requested general visual review. An invalid
Euler value cannot be cleared by that small-site review path. Known quantitative or
visual failures remain exclusions. [Rosen et al. (2018)](https://pubmed.ncbi.nlm.nih.gov/29278774/)
supports reconstruction-specific quality assessment; it does not validate a single
universal cutoff or averaging quality decisions across visits.

MRIQC flags are nullable: a missing/nonfinite required metric or unestimable
threshold stays pending, while a known failure still excludes. `qc_metrics_complete`
is checked when supplied by the MRIQC cohort table. Technical success alone remains
insufficient for scientific inclusion.
