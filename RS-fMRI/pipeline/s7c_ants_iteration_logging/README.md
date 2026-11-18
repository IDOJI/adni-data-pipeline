# Stage 7.C — ANTs progress logs

**What:** Run the prepared fMRIPrep case while recording registration iterations.

**Output:** `ants_iterations/*/{stdout.log,stderr.log,iterations.tsv,progress.json}` in the attempt log folder.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python pipeline/s7c_ants_iteration_logging/run.py \
  --runner pipeline/s7b_sessionwise_preprocessing/run_seeded.py -- \
  --config /ABS/preprocessing-seeded.yaml run --stage fmriprep --subject ADNI999S9999
```

This launches actual preprocessing. The batch runner already enables this logger. Iteration counts are not a percentage-complete estimate.

## Evidence and limits

Sources: [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4). The [Stage 7.C evidence record](../../06_docs/stage_evidence.md#stage-7-c) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. This stage is operational instrumentation; no paper is claimed to validate its logs/timing as an imaging-quality measure.
