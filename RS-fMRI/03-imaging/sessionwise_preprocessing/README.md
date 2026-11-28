# Stage 7.B — Sessionwise preprocessing

Use this route for surface-enabled ADNI processing after [5.D intake](../../02-bids/bids_identity/README.md) and [6 · MRIQC](../mriqc/README.md). fMRIPrep performs sessionwise anatomical reconstruction, motion and SyN distortion correction, and alignment to the output spaces. It produces preprocessed volumes, confounds, FreeSurfer surfaces and 91k CIFTI.

### Run fMRIPrep

`--config "$CFG"` selects the pair prepared in 5.D. Keep `--stage fmriprep`. Preview the command first:

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py dry-run --stage fmriprep --config "$CFG"
```

Read the preview from left to right. Docker mounts the verified input as `/data` and the derivatives as `/out`. After the image name, `/data /out participant` tells fMRIPrep to process the selected participant. The [option table](#what-the-fmriprep-options-do) explains the arguments that follow. For another pair, use its generated `CFG`.

For standard logging, run the block below. To record ANTs iterations, choose the [7.C launch command](../ants_iteration_logging/README.md) instead. Launch fMRIPrep once per attempt.

```sh
python pipeline/s5d_bids_identity/guarded_runner_seeded.py run --stage fmriprep --config "$CFG"
```

Check the native HTML report, `*_desc-preproc_bold.nii.gz` and `*_desc-confounds_timeseries.tsv` in `$CASE/derivatives/fmriprep/`. The latest fMRIPrep attempt under `$CASE/logs/` records the Docker command, source, exit code and input checks in `run.json`. Look for `execution_completed_QC_required`, `exit_code: 0` and `input_unchanged: true`. Then inspect [8 · motion and Euler values](../final_qc/README.md) and [8.A · retained duration](../motion_duration_qc/README.md).

### What the fMRIPrep options do

| Option in the 7.B preview | What it does to this session |
|---|---|
| `--participant-label`, `--task-id rest`, `--bids-filter-file /config/filter.json` | Select the participant and resting BOLD. The generated filter also limits BOLD and anatomical queries to the verified visit. Check the labels before starting. |
| `--subject-anatomical-reference sessionwise` | Builds this visit's anatomical reference from its T1w input. fMRIPrep aligns the visit's BOLD to that reference. |
| `--ignore fieldmaps`, `--force syn-sdc`, `--use-syn-sdc error` | Excludes acquired field maps, explicitly requests anatomy-based SyN distortion correction and treats an unavailable requested correction as an error. This addresses EPI stretching or compression along the phase-encoding axis. Check the corrected BOLD-to-anatomy alignment in the report. |
| `--output-spaces MNI152NLin6Asym:res-2 MNI152NLin2009cAsym fsnative fsaverage:den-10k func` | Writes the BOLD in the requested coordinate systems. Step 10 reads the 2 mm MNI152NLin6Asym volume. The other requests cover a second MNI template, individual and standard cortical surfaces, and native functional space. `res-2` selects the output grid. |
| `--fs-license-file /license.txt`, `--fs-subjects-dir /fsdir` | Supplies the license and the persistent directory for FreeSurfer reconstruction. The cortical surfaces support surface sampling and the Euler check in Step 8. |
| `--cifti-output 91k` | Also samples BOLD at about 91,000 cortical surface and subcortical volume locations in a CIFTI dense time series (`*.dtseries.nii`). Step 10's published profile uses the NIfTI volume. |
| `--random-seed 1123`, `--skull-strip-fixed-seed` | Fixes the run seed and the initialization used for anatomical brain extraction. Review the extracted brain boundary on the T1w report. |

Head-motion estimation and BOLD-to-anatomy registration are part of the workflow. Slice-timing correction depends on usable `SliceTiming` metadata. Those times describe when each slice was acquired. `PhaseEncodingDirection` identifies an axis and sign used for distortion correction. Check the run report to see which corrections were actually applied. [fMRIPrep 25.2.7 processing details](https://fmriprep.org/en/25.2.7/workflows.html) · [Option reference](https://fmriprep.org/en/25.2.7/usage.html)

**Where the values come from.** The private 5.D YAML supplies `runs`, `output_spaces` and `resources`. The [command builder](run.py) sets the field-map policy and CIFTI request. The [seed policy](../../workflow/seed_policy.py) adds the skull-stripping flag. The published local profile uses `--nprocs 2 --omp-nthreads 1 --mem-mb 4000`. For the meaning of those settings, `-w`, `--notrack`, `--stop-on-first-crash` and the Docker flags, see [execution controls](../../docs/installation.md#read-a-docker-preview).

### Publish the completed pair

For the manual 5.D route, `--root` is the results folder containing `pair/verified-config.yaml`. Run this after MRIQC and fMRIPrep succeed. The [publisher](publish_pairs.py) verifies both runs and their inputs, then writes `results/<PTID>/<scan-date-pair>/pair_metadata.json` and both derivative trees under that root. This is a local copy on the results drive. It requires macOS and a filesystem supporting symbolic links. Keep the original work folders and logs for [10 · XCP-D](../xcpd_integrated_qc/README.md). The [managed batch](../../docs/local_batch.md) publishes its own pairs.

```sh
python pipeline/s7b_sessionwise_preprocessing/publish_pairs.py --root "$RESULTS"
```

### Standalone configuration

If you already maintain a standalone seeded YAML, set `source_bids`, `source_manifest`, `source_phase_evidence`, `source_templateflow`, `freesurfer_license` and a fresh `runtime` in your private copy. `runs` must match the actual subject/session, PTID, EPI image ID and study phase. Supply `images`, `output_spaces` and the [seeded resource settings](../../docs/seed_reproducibility.md). The input manifest and phase-evidence files must match the source. Run preparation and intake once:

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

## Evidence and limits

Sources: [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4); [ADNI EPI–T1 pairing answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=434). The [Stage 7.B evidence record](../../docs/stage_evidence.md#stage-7-b) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
