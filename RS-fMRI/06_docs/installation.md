# Installation and execution environments

For reproducible new local runs, follow the [fixed-seed setup](seed_reproducibility.md). A source checkout does not include Docker, container images, TemplateFlow caches, R packages or a FreeSurfer license. The seeded cohort R launcher requires explicit `iso_seed` support in `rrobot`.

For a small pinned Python environment and public data, follow the [copy-and-paste examples](../07_reproducibility/README.md). The offline route needs no Docker; the real imaging route explicitly downloads/executes pinned containers.

The real CC0 MRI sample is included in a normal clone; `public.py fetch` verifies and stages it without an OpenNeuro download.

## Wrapper and Stages

After a normal clone as shown in the root README, create a Python 3.11+ virtual environment under `RS-fMRI/` and install `requirements.txt`. `doctor` checks ordinary tracked source bytes/modes, origin/history and GPL attribution. See the [integration guide](source_integration.md).

## Upstream environment

Follow upstream `env/env_adni.yml`, `env/env_clinica.yml`, R packages and Apptainer/Slurm setup. This repository's requirements do not replace the Clinica/MRIQC/fMRIPrep execution environments. Container/template downloads can total several GB and are separate from wrapper installation.

Image names in `03_config/lab_config.example.yaml` are examples based on MRIQC 24.0.2 and fMRIPrep 25.2.7 used in local checks. Distinguish them from the upstream commit's 24.0.0 example. Preserve actual image digests and commands in per-run provenance.

## macOS and Linux

Use the [stage-by-stage host guide](platform_execution.md) before moving to a different computer. It provides separate Docker Desktop/Engine setup, common commands and a support matrix. Core Python tools and Linux-container calculations are distinct from Mac-specific service, copy and volume-management adapters.

Stages and configuration tools are tested on Mac. Upstream s4/s6/s7 launchers target Slurm/Apptainer and are not automatically converted to Mac. The existing `local_mac` pilot is an untracked local extension, not part of the original protocol import. Step 7.A adds a separate Docker volume execution/audit profile, and S10 adds completed-pair postprocessing/integrated QC. The full local_mac implementation and S6/S7 queue are not consolidated; a flat-derivative-to-S10-pair adapter is also separate. See [consolidation scope](xcpd_consolidation.md).

## Output locations

`prepare-config` writes only outside the repository. Because s5.A writes `data/` in its working directory, run it from external `ADNI_DATA/qc/step5a/`. The upstream s4 Slurm template contains hardcoded paths, environments and mail directives. Review actual paths, accounts, modality and notification policy in an external lab template before submission.

## Optional atlas library

Step 11 sources and TemplateFlow payloads are installed explicitly using its source manager. Do not recursively clone the whole TemplateFlow archive or full CBIG history as part of ordinary installation. See the [atlas guide](atlas_library.md).

## Scalar tables and report browser

Step 12 uses the wrapper Python environment and pandas from `requirements.txt`; no new imaging container, atlas download or R installation is required. From `RS-fMRI/`, run `python 04_workflow/lab.py export-results --archive-root /ABS/PATH/archive --status /ABS/PATH/runtime/metrics.json`. Add `--watch` to scan every 120 seconds. A local service may invoke this command or the repository-owned `pipeline/s12_metrics_summary/run.py` directly. Configure absolute external archive/status/log paths in a private service definition; creating the source directory alone does not install a service. See [Step 12](../pipeline/s12_metrics_summary/README.md) for inputs, outputs and validation limits.

## Native Linux deployment boundary

Ubuntu CI checks Python/source/synthetic contracts; it does not establish a completed full Linux imaging cohort. The 7.B publisher uses macOS `cp -cR`, the queue uses `caffeinate`, and the S10 offloader uses `diskutil`. Port and validate those operational components before claiming automatic five-subject processing through external archival on Linux. See the [implementation map](platform_execution.md#s7b) and [S10 archival boundary](platform_execution.md#s10).
