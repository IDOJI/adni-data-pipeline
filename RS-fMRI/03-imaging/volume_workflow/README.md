# Stage 7.A — Volume-only fMRIPrep and XCP-D

Use this profile for a BIDS session with T1w and resting BOLD. fMRIPrep produces MNI152NLin2009cAsym 2 mm volumes and confounds and skips FreeSurfer reconstruction. XCP-D uses aCompCor without global signal regression, FD 0.5 mm and a 240-second minimum.

### Configure your session

Set [your input and results paths](../../support/docs/installation.md#paths-for-a-manual-run). The example expects `$DATA/bids/dataset_description.json`, one `sub-*/ses-*/` folder with `func/*_task-rest*_bold.nii.gz` and its BIDS metadata, and a T1w under the session or subject `anat/` folder. Verify acquisition metadata for SyN correction.

| Field in the [seeded example](config.seeded.example.json) | What to set in your private copy |
|---|---|
| `paths.bids` | Root containing `dataset_description.json` |
| `fs_license`, `paths.templateflow` | Your FreeSurfer license and a writable copy of the template cache |
| `paths.fmriprep_output`, `paths.xcpd_output` | Separate derivative directories |
| `paths.fmriprep_work`, `paths.xcpd_work`, `paths.logs` | Separate work caches and run logs under your results folder |
| `runs` | Selected BIDS labels without `sub-` and `ses-` |

This block fills those fields from your two paths. It selects the only session automatically. For a dataset with several sessions, first set `BIDS_SESSION` to the intended folder relative to the BIDS root (in the form `sub-label/ses-label`). Keep the seed, images, output space and denoising settings for reproducibility.

```sh
python - <<'PY'
import json, os, shutil
from pathlib import Path
data, out = Path(os.environ["DATA"]), Path(os.environ["RESULTS"])
bids = data / "bids"
sessions = sorted(p for p in bids.glob("sub-*/ses-*") if p.is_dir())
if os.environ.get("BIDS_SESSION"):
    sessions = [p for p in sessions if str(p.relative_to(bids)) == os.environ["BIDS_SESSION"]]
if len(sessions) != 1:
    raise SystemExit("Export BIDS_SESSION with one existing sub-label/ses-label and retry.")
session, = sessions
cfg = json.loads(Path("03-imaging/volume_workflow/config.seeded.example.json").read_text())
cfg["runs"] = [{"subject": session.parent.name[4:], "session": session.name[4:]}]
cfg["paths"] = {k: str(out/k) for k in cfg["paths"]}
cfg["paths"]["bids"] = str(bids)
cfg["fs_license"] = str(data/"license.txt")
cache = (data/"templateflow").resolve()
if (out/"templateflow").resolve().is_relative_to(cache):
    raise SystemExit("Choose a results directory outside the input TemplateFlow cache.")
shutil.copytree(cache, out/"templateflow")
with (out/"volume.json").open("x") as f:
    json.dump(cfg, f, indent=2)
PY
```

### Run fMRIPrep

The [volume runner](pipeline_seeded.py) reads the selected labels from your configuration. Repeat this block when returning in a new terminal. A successful preview prints the Docker arguments. If you see `ERROR`, correct the indicated input before continuing.

```sh
export VOL="$RESULTS/volume.json"
SUB=$(python -c 'import json,sys; run, = json.load(open(sys.argv[1]))["runs"]; print(run["subject"])' "$VOL") &&
SES=$(python -c 'import json,sys; run, = json.load(open(sys.argv[1]))["runs"]; print(run["session"])' "$VOL") &&
python 03-imaging/volume_workflow/pipeline_seeded.py --config "$VOL" dry-run \
  --stage fmriprep --subject "$SUB" --session "$SES"
```

Read the `argv` array in the preview. Below are the fMRIPrep 25.2.7 options after the container image name. The paths and labels come from `volume.json`. The [volume command builder](pipeline.py) sets the anatomical, distortion-correction and output choices for this profile.

#### What the volume fMRIPrep options do

| Option in the preview | What happens to the data |
|---|---|
| `/input /output participant`, `--participant-label`, `--session-label`, `--task-id rest` | Read the BIDS input, select the named participant, visit and resting series, and write derivatives in `fmriprep_output/`. |
| `--subject-anatomical-reference sessionwise` | Uses the visit's anatomical images to make the reference for aligning its functional scans. |
| `--use-syn-sdc error` | Requests anatomy-based distortion correction for field-map-free inputs. Missing information needed for that correction causes an error. With acquired field maps, inspect the report for the method selected. |
| `--output-spaces MNI152NLin2009cAsym:res-2` | Resamples the preprocessed BOLD into this MNI template on its 2 mm grid, so scans have a common coordinate system. |
| `--fs-no-reconall`, `--fs-license-file /license.txt` | Skips cortical surface reconstruction. The runner still supplies the configured license path. Expect volume derivatives here. |
| `--return-all-components` | Saves all estimated CompCor components in the confounds file. The XCP-D aCompCor model below selects the tissue components it uses. |
| `--random-seed 1123`, `--skull-strip-fixed-seed` | Fixes random initialization, including brain extraction. The T1w brain mask and HTML overlay show the estimated boundary. |
| `--output-layout bids`, `-w /work` | Writes derivatives in a BIDS-style tree and intermediate files in the separate fMRIPrep work directory. |

fMRIPrep also estimates head motion, aligns BOLD to the T1w, and uses eligible `SliceTiming` metadata to correct acquisition-time differences between slices. Review the alignment and processing summary in the HTML report. The confounds TSV is an input to the next stage. [fMRIPrep workflow](https://fmriprep.org/en/25.2.7/workflows.html) · [fMRIPrep options](https://fmriprep.org/en/25.2.7/usage.html)

**Start preprocessing** after the preview identifies the intended session.

```sh
python 03-imaging/volume_workflow/pipeline_seeded.py --config "$VOL" run \
  --stage fmriprep --subject "$SUB" --session "$SES"
```

```sh
python 03-imaging/volume_workflow/pipeline_seeded.py --config "$VOL" verify \
  --stage fmriprep --subject "$SUB" --session "$SES"
```

Continue when `verify` prints `structural_checks_passed_visual_and_scientific_qc_required`. Inspect the HTML report, preprocessed BOLD and confounds under `$RESULTS/fmriprep_output/`.

### Run XCP-D

Use the same labels and config after fMRIPrep passes verification. Even the XCP-D preview reads the fMRIPrep output for that session. This profile skips parcellation, ReHo and ALFF.

```sh
python 03-imaging/volume_workflow/pipeline_seeded.py --config "$VOL" dry-run \
  --stage xcpd --subject "$SUB" --session "$SES"
```

#### What the volume XCP-D options do

| XCP-D 26.2.0 option | What happens to the time series or outputs |
|---|---|
| `--mode linc`, `--input-type fmriprep`, `--file-format nifti` | Uses the LINC preset with this profile's explicit settings and reads preprocessed volumes. `--participant-label`, `--session-id` and `--task-id rest` select the same visit and task. |
| `--dummy-scans auto` | Reads fMRIPrep's non-steady-state flags and removes the indicated initial volumes before denoising. |
| `--nuisance-regressors acompcor` | Models noise using white-matter and cerebrospinal-fluid components (five each), head-motion parameters and their derivatives, plus cosine drift terms. This model excludes global signal regression. Inspect the design TSV to see the actual columns. |
| `--despike n`, `--motion-filter-type none`, `--head-radius 50` | Disables the separate despiking step. Uses the unfiltered motion traces to compute framewise displacement (FD), an estimate of how far the head moved between two volumes. A 50 mm radius converts head rotations to displacement. |
| `--fd-thresh 0.5`, `--censor-between 0`, `--output-type censored` | Removes time points with FD above 0.5 mm from the final denoised series. A zero between-frame setting keeps short stretches of otherwise eligible samples. The outlier TSV identifies the removed frames. |
| `--min-time 240` | Requires at least 240 seconds of usable data after initial-volume removal and motion censoring. For a 2-second TR, 120 retained frames meet this threshold. |
| `--lower-bpf 0.01`, `--upper-bpf 0.08`, `--bpf-order 2` | Applies a Butterworth temporal filter with those lower and upper cutoffs in Hz and order parameter 2. This addresses fluctuations over time within a voxel. |
| `--smoothing 6` | Writes an additional spatially smoothed denoised volume. The kernel width is 6 mm full width at half maximum (FWHM). The unsmoothed denoised series is also available. |
| `--combine-runs n`, `--warp-surfaces-native2std n`, `--skip alff reho parcellation` | Keeps runs separate and omits surface warping, low-frequency amplitude maps, local synchrony maps and atlas-based signals or connectivity. The denoised voxel time series is the primary result. |
| `--linc-qc y`, `--abcc-qc n`, `--output-layout bids` | Writes LINC quality metrics and BIDS-style derivatives. ABCC's additional motion and executive-summary reports are disabled. |

**Where to change a value.** In your private `volume.json`, the `postprocessing` fields `fd_threshold_mm`, `minimum_retained_seconds`, `high_pass_hz`, `low_pass_hz` and `smoothing_fwhm_mm` set the corresponding values above. The separate 30% censored-fraction criterion belongs to the [output audit](audit_outputs.py). The runner sets the aCompCor model in code. [XCP-D processing details](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html) · [XCP-D options](https://xcp-d.readthedocs.io/en/26.2.0/usage.html)

**Execution settings for both programs.** The example gives Docker 8 CPUs and 24 GiB. `--nprocs 8 --omp-nthreads 1 --mem-mb 20000` sets the application budgets. Both programs use `--random-seed 1123`, `--fs-license-file`, a stage-specific `-w /work`, `--notrack` and `--stop-on-first-crash`. The output mount switches to `xcpd_output/` for XCP-D. [How to read Docker and runtime options](../../support/docs/installation.md#read-a-docker-preview)

**Start postprocessing** after checking the options in the preview.

```sh
python 03-imaging/volume_workflow/pipeline_seeded.py --config "$VOL" run \
  --stage xcpd --subject "$SUB" --session "$SES"
```

```sh
python 03-imaging/volume_workflow/pipeline_seeded.py --config "$VOL" verify \
  --stage xcpd --subject "$SUB" --session "$SES"
```

Look for the same successful verification status, then review the denoised BOLD and report under `$RESULTS/xcpd_output/`. Attempt records and command lines are in `$RESULTS/logs/`. The separate [output audit](audit_outputs.py) expects a staged archive layout with `bids/`, `derivatives/` and a staging manifest; use its `--help` for that layout.

## Evidence and limits

Sources: [Behzadi et al. (2007)](https://doi.org/10.1016/j.neuroimage.2007.04.042); [Esteban et al. (2019)](https://doi.org/10.1038/s41592-018-0235-4); [Mehta et al. (2024)](https://doi.org/10.1162/imag_a_00257). The [Stage 7.A evidence record](../../support/docs/stage_evidence.md#stage-7-a) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
