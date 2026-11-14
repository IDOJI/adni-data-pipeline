# Stage 7.A — Alternative volume profile

**What:** Run volume-only fMRIPrep and aCompCor XCP-D without FreeSurfer reconstruction.

**Output:** Volume derivatives, denoised BOLD and an output audit in the configured external directories.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Copy [config.seeded.example.json](config.seeded.example.json), fill in private input/output/license paths and use new output/work/log directories.

```sh
python pipeline/s7a_volume_workflow/pipeline_seeded.py \
  --config /ABS/volume-seeded.json dry-run --stage fmriprep --subject 999S9999
python pipeline/s7a_volume_workflow/pipeline_seeded.py \
  --config /ABS/volume-seeded.json run --stage fmriprep --subject 999S9999
python pipeline/s7a_volume_workflow/pipeline_seeded.py \
  --config /ABS/volume-seeded.json verify --stage fmriprep --subject 999S9999
python pipeline/s7a_volume_workflow/pipeline_seeded.py \
  --config /ABS/volume-seeded.json run --stage xcpd --subject 999S9999
python pipeline/s7a_volume_workflow/audit_outputs.py \
  --data-root /ABS/volume-results --subject 999S9999 --session 20200101 \
  --output /ABS/volume-qc/audit.json
```

This profile uses MNI2009c, aCompCor/no GSR and FD 0.5. It is separate from the surface-enabled 7.B → S10 36P/GSR workflow.
