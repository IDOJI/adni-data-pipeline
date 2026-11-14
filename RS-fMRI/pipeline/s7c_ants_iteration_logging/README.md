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
