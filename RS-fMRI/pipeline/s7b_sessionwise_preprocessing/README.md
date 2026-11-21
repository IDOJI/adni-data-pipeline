# Stage 7.B — Sessionwise preprocessing

Use this route for surface-enabled ADNI processing after [5.D intake](../s5d_bids_identity/README.md) and [6 · MRIQC](../s6_mriqc/README.md). fMRIPrep performs sessionwise anatomical reconstruction, motion and SyN distortion correction, and alignment to the output spaces. It produces preprocessed volumes, confounds, FreeSurfer surfaces and 91k CIFTI.

### Run fMRIPrep

`--config "$CFG"` selects the pair prepared in 5.D. Keep `--stage fmriprep`. Preview the command first:

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py dry-run --stage fmriprep --config "$CFG"
```

For standard logging, run the block below. To record ANTs iterations, choose the [7.C launch command](../s7c_ants_iteration_logging/README.md) instead. Launch fMRIPrep once per attempt.

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py run --stage fmriprep --config "$CFG"
```

Check the native HTML report, `*_desc-preproc_bold.nii.gz` and `*_desc-confounds_timeseries.tsv` in `$CASE/derivatives/fmriprep/`. The latest fMRIPrep attempt under `$CASE/logs/` records the Docker command, source, exit code and input checks in `run.json`. Look for `execution_completed_QC_required`, `exit_code: 0` and `input_unchanged: true`. Then inspect [8 · motion and Euler values](../s8_final_qc/README.md) and [8.A · retained duration](../s8a_motion_duration_qc/README.md).

### Publish the completed pair

For the manual 5.D route, `--root` is the results folder containing `pair/verified-config.yaml`. Run this after MRIQC and fMRIPrep succeed. The [publisher](publish_pairs.py) verifies both runs and their inputs, then writes `results/<PTID>/<scan-date-pair>/pair_metadata.json` and both derivative trees under that root. This is a local copy on the results drive. It requires macOS and a filesystem supporting symbolic links. Keep the original work folders and logs for [10 · XCP-D](../s10_xcpd_integrated_qc/README.md). The [managed batch](../../06_docs/local_batch.md) publishes its own pairs.

```sh
python pipeline/s7b_sessionwise_preprocessing/publish_pairs.py --root "$RESULTS"
```

### Standalone configuration

If you already maintain a standalone seeded YAML, set `source_bids`, `source_manifest`, `source_phase_evidence`, `source_templateflow`, `freesurfer_license` and a fresh `runtime` in your private copy. `runs` must match the actual subject/session, PTID, EPI image ID and study phase. Supply `images`, `output_spaces` and the [seeded resource settings](../../06_docs/seed_reproducibility.md). The input manifest and phase-evidence files must match the source. Run preparation and intake once:

```sh
export STANDALONE_CFG="$DATA/config/preprocessing-seeded.yaml"
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py --config "$STANDALONE_CFG" prepare &&
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py --config "$STANDALONE_CFG" intake
```

For the [standalone runner](run_seeded.py), `--subject` takes the bare `runs[].subject` label. The example below reads it from a single-case YAML. Review the intake decision before executing these commands. Run the second stage once MRIQC succeeds.

```sh
SUB=$(python -c 'import sys,yaml; case, = yaml.safe_load(open(sys.argv[1]))["runs"]; print(case["subject"])' "$STANDALONE_CFG") &&
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py --config "$STANDALONE_CFG" \
  run --stage mriqc --subject "$SUB"
```

```sh
python pipeline/s7b_sessionwise_preprocessing/run_seeded.py --config "$STANDALONE_CFG" \
  run --stage fmriprep --subject "$SUB"
```

The manual publisher above expects the verified 5.D layout.
