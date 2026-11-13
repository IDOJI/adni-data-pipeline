# Fixed seeds for new preprocessing runs

Use the `fixed-seed-v1` profile for new local Docker runs. Its master seed is **357**, its numerical worker thread count is **1**, and fMRIPrep remains **25.2.7** at the recorded immutable image digest. Skull stripping is enabled; `--skull-strip-fixed-seed` fixes its stochastic initialization rather than enabling or disabling extraction.

Existing active batches, source locks, cached work and historical results retain their original settings. Installing or pulling this source does not migrate a running service. Use a new runtime root and the seeded entrypoints below. Historical launchers and imported Slurm/Apptainer scripts remain available for compatibility; they do not acquire this profile automatically. The seeded S10 launcher supports Docker and rejects its legacy Slurm export action.

## Seed coverage

| Stage | Fixed control |
|---|---|
| MRIQC | Master/Python/NumPy seed 357; ANTs environment seed 357; enhancement draws reset a local RandomState per invocation; Atropos uses `use_random_seed=False`; existing QI2 seed 1191935 is retained. |
| fMRIPrep 25.2.7 | `--random-seed 357` initializes its deterministic derived ANTs/NumPy seeds; `--skull-strip-fixed-seed` disables random Atropos initialization; `--omp-nthreads 1`. |
| FreeSurfer in the pinned fMRIPrep image | Installed `recon-all` already defaults to `NoRandomness=1` and `RngSeed=1234`. Those defaults are retained. The separate 7.A volume profile disables reconstruction. |
| XCP-D | `--random-seed 357`, ANTs/Python environment controls and `--omp-nthreads 1`; existing denoising, censoring and QC settings are retained. |
| Cohort MRIQC outlier fitting in R | Global `set.seed(357)`; original SHASH/isotree `iso_seed=123456`; original example selection seed 1. The launcher requires an R package exposing `iso_seed`; it refuses the old compatibility fallback. |
| Source identity, clinical joins, motion summaries, ROI means and scalar exports | No stochastic sampling is introduced by these operations. Existing explicit sampling seeds in review tools remain fixed. |

All container stages also set `PYTHONHASHSEED`, `OMP_NUM_THREADS`, `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS` and `NUMEXPR_NUM_THREADS`. Numerical thread limits are 1; independent workflow processes can still run concurrently. This may take longer than a historical OMP2 run. Different internal fixed seeds are intentional: repeatability requires each stochastic operation to receive a stable seed, not every algorithm to share the same number.

The pinned MRIQC image is `nipreps/mriqc@sha256:dabe930dd0d1180c565a42f2c6a34f2b23026d9642db5d110f05b427413b829f`. Its package identifies itself as `24.1.0.dev0+gd5b13cb5.d20240826`, despite the historical tag `24.0.2`. It has no supported random-seed CLI option. The bootstrap checks the complete installed anatomical module hash before adapting its two random sites in the disposable container. It runs as an executable Docker entrypoint, preserving the original application arguments for the logging, batch and recovery adapters. It preserves the source/license header, records original/effective hashes and the effective source, and leaves the image unchanged. Any other image or source hash is rejected pending review.

## New local batch

Copy [local_batch.seeded.example.json](../03_config/local_batch.seeded.example.json) to a private external configuration, replace its paths/fingerprints, and point `xcpd_template` at [xcpd_linc.seeded.example.json](../03_config/xcpd_linc.seeded.example.json). Keep the same master seed and OMP1 for both stages. Existing exact-pair, source-review and intake requirements still apply; see [local batch preparation](local_batch.md).

```sh
# Preparation only: verifies/copies inputs into a new root; does not run imaging.
python 04_workflow/local_batch_seeded.py --config /ABS/private-seeded-batch.json prepare
# Inspect prepared state without launching imaging.
python 04_workflow/local_batch_seeded.py --config /ABS/new-runtime/config/batch.json status
# Actual processing, only after reviewing the prepared batch and environment:
python 04_workflow/local_batch_seeded.py --config /ABS/new-runtime/config/batch.json watch
```

Preparation records the seeded session runner in the new continuation registry and selects the seeded S10 worker. Source locks still protect all executable dependencies. A service for this new batch must invoke `local_batch_seeded.py`; do not replace a busy historical service or change its source lock.

## Standalone routes

For a newly prepared 7.B YAML configuration, explicitly set:

```yaml
seed_policy: fixed-seed-v1
random_seed: 357
work_revision: fixed-seed-v1
resources:
  cpus: 2
  omp_nthreads: 1
  workflow_memory_mb: 4000
  docker_memory: 16g
```

Retain the rest of the reviewed input/output-space/license settings and use a new external `runtime`. Use `02_custom/s5d_bids_identity/guarded_runner_seeded.py` in place of `guarded_runner.py` for new exact-pair preparation and dispatch. Direct 7.B uses `run_seeded.py` with the same intake and action arguments as its original runner:

```sh
# Command preview, after preparation and intake:
python 02_custom/s7b_sessionwise_preprocessing/run_seeded.py \
  --config /ABS/preprocessing-seeded.yaml dry-run --stage fmriprep --subject ADNI999S9999
```

For 7.A use [config.seeded.example.json](../02_custom/s7a_volume_workflow/config.seeded.example.json) and `02_custom/s7a_volume_workflow/pipeline_seeded.py`. For S10 use [xcpd_linc.seeded.example.json](../03_config/xcpd_linc.seeded.example.json) and `02_custom/s10_xcpd_integrated_qc/pipeline_seeded.py`. These accept their original command arguments and preserve their distinct aCompCor versus 36P/GSR scientific profiles. Replace `dry-run` with the documented processing action only when ready to calculate.

The [public imaging walkthrough](../07_reproducibility/README.md) now uses this profile automatically. Run `fetch` into a new external root; old comparison identities are rejected instead of reusing historical results under a new seed policy.

## R cohort fitting

Install R dependencies and an `rrobot` build that provides `SHASH_out(..., iso_seed=...)`; capability was checked with version 0.2.0. R `set.seed()` alone does not seed isotree. A local optional package library is searched at `.R-library/seeded` before `.R-library`; neither installed packages nor private cohort configurations are included in Git. The original protocol's dependency instructions still apply on a new machine.

```sh
# Preview only; use a new external output directory and the full reviewed cohort.
python 04_workflow/iqm_seeded.py --config /ABS/iqm-cohort.yaml --out-dir /ABS/new-iqm-results
# Actual R fitting, after dependencies and cohort selection are verified:
python 04_workflow/iqm_seeded.py --config /ABS/iqm-cohort.yaml --out-dir /ABS/new-iqm-results --execute
```

The R launcher fails if explicit isotree seed support is missing. It does not fit population thresholds from a pilot pair. Keep seed 357 for the standard profile; an intentional seed change requires a separate output root and analysis identity.

The launcher resolves configuration/output paths before changing directory and gives the upstream R configuration helper access to the launcher's Python environment. Activating the venv in the calling shell is therefore optional when invoking the venv's Python directly. Existing `R_LIBS_USER` locations are retained after the repository's optional package libraries.

## Evidence and limits

Container launch preparation writes `<runtime>/seed_policy/policy.json`, frozen bootstrap code, original/wrapper source snapshots and command receipts. For 7.A these live under its external `paths.logs`. Actual stage records and cache signatures retain the effective seed-bearing command. Preparation receipts alone are not proof that imaging completed. Changing the seed, seed implementation or a frozen snapshot in an existing root is rejected.

Validation includes command propagation through the real runner builders, session receipt/cache protection, guarded entrypoints and synthetic R fitting. Two disposable containers using the pinned MRIQC image produced identical enhancement arrays for the same seed, even after perturbing global RNG state; changing the seed changed the sampled values. The actual Nipype function and deterministic Atropos setting were checked. This is not a full MRIQC/fMRIPrep/XCP-D cohort rerun or a cross-machine imaging equivalence claim.

Keep inputs, image digests, source revision, templates, settings and hardware/library details in comparisons. Floating-point arithmetic and different architectures can still affect output. Use the numerical comparison tools and visual QC; fixed seeds alone do not guarantee byte-identical whole-pipeline results on every computer. See [fMRIPrep 25.2.7 reproducibility guidance](https://fmriprep.org/en/25.2.7/usage.html) and [ANTs reproducibility guidance](https://github.com/ANTsX/ANTs/wiki/antsRegistration-reproducibility-issues).

## Integration re-audit (2026-11-14)

The first fixed-seed release tested command construction but missed three launcher integration issues. MRIQC's extra bootstrap positional argument broke the original logging/batch/recovery image boundary; the seeded session CLI did not forward an injected logging transport to its underlying runner; and the R launcher depended on shell activation and mishandled relative configuration paths after changing directory. These are corrected without editing legacy deployment-bound runners.

Regression coverage now runs both MRIQC and fMRIPrep through the actual session CLI/direct entry, ANTs logging, local transport and retained-container recovery code, while substituting only external Docker execution. It verifies effective seed settings, unchanged cache identity, command receipts and recovery. A real pinned MRIQC container also successfully ran the bootstrap and logging/batch transport with `--help` (no imaging). Two complete R wrapper runs on 300 synthetic sessions produced identical numeric QC TSVs and example-selection CSVs. These checks supplement, rather than replace, the earlier synthetic algorithm tests. No full participant MRI preprocessing or cross-machine equivalence test was performed.

Use a fresh runtime for this implementation revision; frozen seed implementation hashes intentionally prevent silently changing an existing analysis. Existing automatic batches keep their registered original entrypoint and settings until a separate new batch is prepared.
