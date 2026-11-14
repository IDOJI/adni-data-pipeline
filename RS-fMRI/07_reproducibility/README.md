# Runnable examples

Run from `RS-fMRI/` after [installation](../06_docs/installation.md). Use a new external directory for each run.

## Offline synthetic example

Exercises the actual QC, clinical, ROI-extraction and scalar-export code with synthetic inputs. It does not run MRIQC/fMRIPrep/XCP-D imaging.

```sh
export TOY_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/adni-toy.XXXXXX")/run"
python 07_reproducibility/toy.py init --root "$TOY_ROOT"
python 07_reproducibility/toy.py run --root "$TOY_ROOT" --step all
python 07_reproducibility/toy.py verify --root "$TOY_ROOT"
```

Expected result: `PASS` in `verification.json`, QC tables under `outputs/`, and `results/metrics.csv` plus `index.html` beneath the labeled `fixture_archive/`. To run one step, replace `all` with `3a`, `5c`, `5d`, `8`, `8a`, `9a`, `9b`, `10`, `11` or `12`, in that order. [expected.json](expected.json) defines the reference values.

## Real public-image example

Uses bundled CC0 [OpenNeuro ds000030 1.0.0 data](public_data/ds000030-1.0.0/README.md). Requires Docker and your own FreeSurfer license. Imaging can take hours; this is separate from the offline check.

```sh
export PUBLIC_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/adni-public.XXXXXX")/run"
export FS_LICENSE=/ABS/freesurfer/license.txt
python 07_reproducibility/public.py fetch --root "$PUBLIC_ROOT"
python 07_reproducibility/public.py pull --root "$PUBLIC_ROOT" --execute
python 07_reproducibility/public.py mriqc --root "$PUBLIC_ROOT" --execute
python 07_reproducibility/public.py fmriprep --root "$PUBLIC_ROOT" \
  --license "$FS_LICENSE" --ants-verbose --execute
python 07_reproducibility/public.py motion --root "$PUBLIC_ROOT" --execute
python 07_reproducibility/public.py xcpd --root "$PUBLIC_ROOT" \
  --license "$FS_LICENSE" --execute
```

`fetch` verifies and stages the included images. `pull` downloads pinned containers. Omit `--execute` from a processing command to preview it.

| Location under PUBLIC_ROOT | Result |
|---|---|
| `derivatives/mriqc/` | IQMs and native HTML reports |
| `derivatives/fmriprep/` | Volumes, surfaces/CIFTI, confounds and FreeSurfer outputs |
| `qc/8/`, `qc/8a/` | Motion and retained-duration summaries |
| `xcpd/derivatives/` | Denoised BOLD, ROI/FC, ReHo/ALFF and HTML reports |
| `logs/`, `comparison_identity.json` | Execution records, images, source and settings |

Profile: fMRIPrep 25.2.7, sessionwise anatomy, FreeSurfer/CIFTI, SyN-SDC; XCP-D 26.2.0, 36P/GSR, FD 0.3 mm, minimum 240 s. [Seed 1123 and OMP1](../06_docs/seed_reproducibility.md) apply. The public sample does not supply ADNI clinical/source-QC evidence or final research inclusion.

## Compare two runs

Use the same source revision, inputs, images and settings. Set `PUBLIC_ROOT_2` to a completed second run:

```sh
export PUBLIC_ROOT_2=/ABS/second-public-run
python 07_reproducibility/compare.py "$PUBLIC_ROOT" "$PUBLIC_ROOT_2" \
  --mode public --atol 1e-6 --rtol 1e-5 --report "$PUBLIC_ROOT/comparison.json"
```

The JSON reports exact matches, differences within tolerance or failures for numerical NIfTI/TSV outputs. Use `--mode synthetic` for two toy runs. Tolerances are engineering comparison settings, not validated scientific-equivalence margins; surface/CIFTI equivalence needs separate checks.

The committed reference covers synthetic results. A full public-image and cross-machine imaging baseline has not been established by this example kit.
