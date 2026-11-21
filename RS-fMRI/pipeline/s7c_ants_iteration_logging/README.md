# Stage 7.C — Record ANTs registration iterations

This command **starts fMRIPrep** through the same seeded [7.B backend](../s7b_sessionwise_preprocessing/README.md). Choose it at the fMRIPrep launch step if you want a per-iteration trace. A batch already running the logger owns its own attempt.

`--runner` names the repository's 7.B program. After the `--` separator, `--config` identifies the verified pair and `--subject` takes the bare label from that YAML. The command reads that label directly. Complete [MRIQC](../s6_mriqc/README.md) first.

```sh
SUB=$(python -c 'import sys,yaml; case, = yaml.safe_load(open(sys.argv[1]))["runs"]; print(case["subject"])' "$CFG") &&
python pipeline/s5d_bids_identity/guarded_runner_seeded.py check --config "$CFG" &&
python pipeline/s7c_ants_iteration_logging/run.py \
  --runner pipeline/s7b_sessionwise_preprocessing/run_seeded.py -- \
  --config "$CFG" run --stage fmriprep --subject "$SUB"
```

The fMRIPrep attempt under `$CASE/logs/` contains `ants_logging.json` with the effective Docker command, and `ants_iterations/` with stdout, stderr, iteration tables and progress records. Use the [7.B completion checks](../s7b_sessionwise_preprocessing/README.md#run-fmriprep) before moving on to motion QC.
