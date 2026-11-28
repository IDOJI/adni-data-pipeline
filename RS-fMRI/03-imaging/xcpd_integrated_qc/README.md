# Stage 10 — XCP-D denoising and imaging QC

For the [stage 3 walkthrough](../../README.md#process), set your study path and run `python start/03_process.py "$STUDY" run` from `RS-fMRI/`.

Start with a [published 7.B pair](../sessionwise_preprocessing/README.md#publish-the-completed-pair) under `$RESULTS/results/`, or a completed pair delivered by the [batch runner](../docs/local_batch.md). XCP-D checks preprocessed BOLD, confounds, MRIQC measures, FreeSurfer evidence and the successful execution receipts.

### Configure the input

For the [manual layout](../../docs/installation.md#paths-for-a-manual-run), set `root` to the directory **containing** `results/` and `runs/`. `license` points to the FreeSurfer license file and `templateflow` to the prepared cache. This block creates a private copy of the [seeded XCP-D profile](../config/xcpd_linc.seeded.example.json) with those paths and the local-batch resource settings. If the batch or an earlier manual setup already created the JSON, use that file as `XCFG` and skip creation.

```sh
export XCFG="$RESULTS/xcpd.json"
python - <<'PY'
import json, os
from pathlib import Path
out = Path(os.environ["RESULTS"])
cfg = json.loads(Path("config/xcpd_linc.seeded.example.json").read_text())
batch = json.loads(Path("config/local_batch.seeded.example.json").read_text())
cfg.update(root=str(out), license=str(Path(os.environ["DATA"])/"license.txt"),
           templateflow=str(Path(os.environ["CASE"])/"templateflow"), resources=batch["xcpd_resources"])
with Path(os.environ["XCFG"]).open("x") as f:
    json.dump(cfg, f, indent=2)
PY
```

### Preview, run and check

**Preflight.** The [seeded XCP-D runner](pipeline_seeded.py) checks local paths and the installed XCP-D version. The dry run then checks the pair and writes the proposed Docker command in `postprocessing/<config_id>/dry_run.json`. Expect one candidate for one eligible run. For zero candidates, review `s10/<config_id>/pre_qc.json` in the published pair and the controller's `events.jsonl` if present.

```sh
python 03-imaging/xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" preflight &&
python 03-imaging/xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" dry-run
```

Open the `mapping` file named by the dry run. Each candidate has a `bids_filter` showing the selected scan and a `command` listing the exact arguments in order. In that array, `/input /job/derivatives participant` marks the start of XCP-D's arguments. Use the [option table below](#what-the-xcp-d-options-do) to interpret the preview.

**Denoise one candidate.** `pilot` runs the first eligible candidate using your `XCFG`. The primary outputs are denoised BOLD, regional time series and correlations, regional homogeneity (ReHo) and amplitude of low-frequency fluctuations (ALFF). Run once with one processing owner for this root.

```sh
python 03-imaging/xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" pilot
```

**Collect and verify.** Read `final_qc_master.tsv` under `postprocessing/<config_id>/` and the pair's `qc_report.html`. The latest attempt under `s10/<config_id>/runs/<run>/attempt-*/` contains the evidence. For a successful denoised result, check `status: success`, `exit_code: 0` and `input_unchanged: true` in `execution.json`, plus `functional_outputs_valid: true` in `output_validation.json`. The validated images are under `derivatives/` in that attempt. In a successful validation, `actual_configuration_file` in `output_validation.json` points to the XCP-D TOML used to cross-check model, filter and atlas settings. Held scans and scans skipped for insufficient duration have separate outcomes.

```sh
python 03-imaging/xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" collect
```

For an ongoing cohort, `watch` processes future published pairs after the pilot. After the **whole cohort** and visual review are complete, set `--mriqc-flags` to the reviewed cohort table, then run:

```sh
python 03-imaging/xcpd_integrated_qc/pipeline_seeded.py --config "$XCFG" finalize \
  --cohort-complete --mriqc-flags "$DATA/review/cohort-mriqc-flags.tsv"
```

Pass the matching `final_included_runs.tsv` and `clinical_scan_links.tsv` from the same `finalizations/<timestamp>/` to [9.A · clinical validation](../validate_clinical/README.md).

### What the XCP-D options do

The values below are for the **7.B → 10** route. Your private `xcpd.json` holds the input paths and model settings. The [command builder](pipeline.py) reads them and adds fixed choices such as per-run processing. [XCP-D 26.2.0 option reference](https://xcp-d.readthedocs.io/en/26.2.0/usage.html) · [Denoising workflows](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html)

| Select the input | Meaning in this profile |
|---|---|
| `--mode linc`, `--input-type fmriprep`, `--file-format nifti` | Start from LINC defaults, then apply the explicit options below. The input is a preprocessed fMRIPrep BOLD volume. It selects the 2 mm MNI152NLin6Asym NIfTI produced by 7.B. |
| `--participant-label`, `--session-id` (when present), `--task-id rest`, `--bids-filter-file /job/bids_filter.json` | Select the identified participant, visit, task, run and spatial grid. The [container check](container_entry.py) requires exactly the expected BOLD and verifies the atlas before starting XCP-D. |
| `--combine-runs n` | Analyze each run independently. Its censor mask, retained duration and connectivity matrix refer to that run. |

| Denoise the BOLD | Meaning in this profile |
|---|---|
| `--dummy-scans auto` | Removes the leading volumes through the last fMRIPrep non-steady-state flag. XCP-D then censors motion in the remaining time series. |
| `--despike y` | Attenuates large transient intensity spikes in a voxel's time series before nuisance regression. Frame removal is controlled separately by FD. |
| `--nuisance-regressors 36P` | Regresses out 36 terms. The nine base traces are six motion estimates plus mean white-matter, cerebrospinal-fluid and whole-brain signals. Each contributes the original, its temporal derivative, and the square of each. Global signal regression is part of this model. |
| `--motion-filter-type none`, `--head-radius 50` | Uses unfiltered realignment traces for motion estimates. Framewise displacement (FD) estimates movement between successive volumes. A 50 mm radius converts head rotations into millimetres for this calculation. The BOLD band-pass filter below is a separate operation. |
| `--fd-thresh 0.3`, `--censor-between 0`, `--output-type censored` | Marks frames with FD greater than 0.3 mm for removal. Short stretches of low-motion frames remain eligible. The final denoised series contains retained volumes, so its length can be shorter than the input. Check the run's `*_outliers.tsv`. |
| `--min-time 240` | Requires 240 seconds of retained signal. With TR = 2 s, 119 retained volumes give 238 s and the run is skipped. 120 volumes meet the duration requirement. |
| `--lower-bpf 0.01`, `--upper-bpf 0.08`, `--bpf-order 2` | Filters BOLD and nuisance time series along time with a Butterworth band-pass and order parameter 2. The cutoffs are in Hz. XCP-D interpolates censored samples internally for filtering. The final censored output omits them. |
| `--smoothing 6` | Produces an additional denoised image smoothed across neighboring voxels with a 6 mm FWHM kernel. The unsmoothed output preserves more spatial detail. |

| Produce and check the outputs | Meaning in this profile |
|---|---|
| `--atlases 4S256Parcels`, `--min-coverage 0.5` | Averages retained BOLD within each of 256 regions. A region with less than half its extent covered gets missing signal values. The parcel coverage TSV shows which regions are affected. |
| `--output-run-wise-correlations y` | Writes one 256 × 256 Pearson correlation matrix per run from the regional time series. Missing regions can produce missing correlations. |
| `--linc-qc y`, `--abcc-qc y` | Produces LINC QC metrics plus ABCC's additional summary and motion-threshold outputs. The repository collects run-level evidence in `output_validation.json`. |
| `--output-layout bids`, `--report-output-level root` | Organizes derivatives by BIDS entities and puts the XCP-D HTML report at the derivative root. The repository's `qc_report.html` is a separate summary. |

The default profile also produces an ALFF map (strength of slow BOLD fluctuations) and a ReHo map (similarity among neighboring voxel time series). Check the native images, `*_stat-mean_timeseries.tsv`, `*_stat-pearsoncorrelation_relmat.tsv` and `*_stat-coverage_bold.tsv` in the selected attempt.

**Where to change a value.** `fd_threshold`, `min_time`, `dummy_scans`, `lower_bpf`, `upper_bpf`, `bpf_order` and `smoothing` are fields in `$XCFG`. `nuisance_regressors` selects the model. The `global_signal_regression` field records that choice and must agree with 36P. If `bandpass` is false the runner adds `--disable-bandpass-filter`. Start a new analysis directory for a different scientific profile.

**Two different motion decisions.** The repository first screens the whole run using mean FD above 0.5 mm or more than 30% of frames above 0.5 mm, along with its other QC checks. For a run admitted to XCP-D, `--fd-thresh 0.3` then censors individual frames. A 0.4 mm frame counts toward XCP-D censoring while staying below the earlier 0.5 mm cutoff.

**Execution settings.** The manual setup uses the batch resource settings (`--nprocs 2 --omp-nthreads 1 --mem-mb 4000`) with a 16 GiB container limit. `--random-seed 1123` supplies the fixed seed, `--fs-license-file /license.txt` supplies the license, and `--work-dir /job/work` keeps intermediate files with the attempt. `--stop-on-first-crash` and `--notrack` control error handling and telemetry. [Docker and runtime options](../../docs/installation.md#read-a-docker-preview)

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
[Mehta et al. (2024), Sections 2.6 and 2.9](https://doi.org/10.1162/imag_a_00257)
describes optional automatic initial-volume removal and nuisance models. This
paper supports the method, not every setting in software version 26.2.0.

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

## Evidence and limits

Sources: [Mehta et al. (2024)](https://doi.org/10.1162/imag_a_00257); [Ciric et al. (2017)](https://doi.org/10.1016/j.neuroimage.2017.03.020); [Parkes et al. (2018)](https://doi.org/10.1016/j.neuroimage.2017.12.073); [Hallquist et al. (2013)](https://doi.org/10.1016/j.neuroimage.2013.05.116); [Rosen et al. (2018)](https://doi.org/10.1016/j.neuroimage.2017.12.059). The [Stage 10 evidence record](../../docs/stage_evidence.md#stage-10) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
