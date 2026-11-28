# Stage 7.C — Record ANTs registration iterations

This command **starts fMRIPrep** through the same seeded [7.B backend](../sessionwise_preprocessing/README.md). Choose it at the fMRIPrep launch step if you want a per-iteration trace. A batch already running the logger owns its own attempt.

`--runner` names the repository's 7.B program. After the `--` separator, `--config` identifies the verified pair and `--subject` takes the bare label from that YAML. The command reads that label directly. Complete [MRIQC](../mriqc/README.md) first.

```sh
SUB=$(python -c 'import sys,yaml; case, = yaml.safe_load(open(sys.argv[1]))["runs"]; print(case["subject"])' "$CFG") &&
python 02-bids/bids_identity/guarded_runner_seeded.py check --config "$CFG" &&
python 03-imaging/ants_iteration_logging/run.py \
  --runner 03-imaging/sessionwise_preprocessing/run_seeded.py -- \
  --config "$CFG" run --stage fmriprep --subject "$SUB"
```

The fMRIPrep attempt under `$CASE/logs/` contains `ants_logging.json` with the effective Docker command, and `ants_iterations/` with stdout, stderr, iteration tables and progress records. Verbose ANTs logging records progress during registration. Interpret the scientific flags using the [7.B fMRIPrep option table](../sessionwise_preprocessing/README.md#what-the-fmriprep-options-do). Use the [7.B completion checks](../sessionwise_preprocessing/README.md#run-fmriprep) before moving on to motion QC.

## Evidence and limits

Sources: [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4). The [Stage 7.C evidence record](../../docs/stage_evidence.md#stage-7-c) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. This stage is operational instrumentation; no paper is claimed to validate its logs/timing as an imaging-quality measure.
