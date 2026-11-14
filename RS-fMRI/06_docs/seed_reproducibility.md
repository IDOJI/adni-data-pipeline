# Fixed-seed execution

New local runs use **master seed 1123**, **OMP1** and the `fixed-seed-v1` profile. fMRIPrep remains **25.2.7**; skull stripping is enabled.

| Stage | Control |
|---|---|
| MRIQC | Python/NumPy/ANTs seed 1123; deterministic enhancement and Atropos initialization |
| fMRIPrep | `--random-seed 1123 --skull-strip-fixed-seed --omp-nthreads 1` |
| XCP-D | `--random-seed 1123 --omp-nthreads 1` |
| R cohort fitting | `set.seed(1123)` and explicit isotree seed support |

Existing internal constants remain fixed: MRIQC QI2 `1191935`, FreeSurfer `1234`, R isotree `123456` and R example selection `1`. Every algorithm need not share the same number. Container numerical thread limits are also fixed to one.

## Run

Use the [local batch runner](local_batch.md) or the seeded stage entry points:

| Task | Entry point / configuration |
|---|---|
| Exact pair | `pipeline/s5d_bids_identity/guarded_runner_seeded.py` |
| Sessionwise MRIQC/fMRIPrep | `pipeline/s7b_sessionwise_preprocessing/run_seeded.py` |
| Volume/aCompCor | `pipeline/s7a_volume_workflow/pipeline_seeded.py` + its `config.seeded.example.json` |
| XCP-D | `pipeline/s10_xcpd_integrated_qc/pipeline_seeded.py` + `03_config/xcpd_linc.seeded.example.json` |

For a standalone preprocessing YAML, include:

```yaml
seed_policy: fixed-seed-v1
random_seed: 1123
work_revision: fixed-seed-v1
resources:
  cpus: 2
  omp_nthreads: 1
  workflow_memory_mb: 4000
  docker_memory: 16g
```

R fitting requires `rrobot` exposing `SHASH_out(..., iso_seed=...)`:

```sh
python 04_workflow/iqm_seeded.py \
  --config /ABS/iqm-cohort.yaml --out-dir /ABS/new-iqm-results --execute
```

**Records:** `<runtime>/seed_policy/` stores the policy and frozen implementation; stage logs/cache signatures store the effective command. A changed seed or implementation requires a new runtime.

The MRIQC adapter accepts only the audited image digest in `04_workflow/seed_policy.py`; its package reports `24.1.0.dev0+gd5b13cb5.d20240826` despite the historical `24.0.2` tag. Historical/Slurm entry points do not automatically enable this profile. Fixed seeds do not guarantee identical floating-point results across machines; use the [comparison commands](../07_reproducibility/README.md#compare-two-runs).
