# Tolerance-based thread reproducibility

Compare full 7.B preprocessing and S10 XCP-D runs at different **OMP/ITK thread
limits**. Each trial has new BIDS copies, output directories, FreeSurfer output,
TemplateFlow copies and work caches. Existing jobs, queues, results, input files
and the `fixed-seed-v1` production policy are preserved.

This optional stage runs after representative successful 7.B cases are available.
It does not change the production thread count or approve research inclusion.

## Contract

| Item | Requirement |
|---|---|
| Inputs | Successful input-preserving 7.B receipts, their exact-pair configurations/manifests, source XCP-D configuration, installed pinned images and a FreeSurfer license |
| Execution | Original 7.B backend, unchanged S10 argument builder and S10 output validator, existing 7.C logging wrapper; no image download |
| Fixed controls | Inputs, seed, skull-strip seed, scientific options, templates, atlas, CPU budget, memory budget and images |
| Experimental control | `--omp-nthreads`, `OMP_NUM_THREADS` and `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS`; BLAS/NumExpr remain one to avoid nested oversubscription |
| Scheduling | One trial at a time, only after declared production queues are terminal and Docker/shared reservations are idle; use the existing five-subject lease |
| Outputs | Isolated trials, actual Docker identity/mount/start/exit records, per-stage wall time, frozen case-specific tolerance policies, comparisons, `report.json` and `report.html` |
| Validation | Actual zero-exit executions, input preservation, S10 output validation, identical product inventories, coordinate/temporal axes, label order, missingness and exact censor choices |

Use an external volume with room for all final derivatives and one full trial's
scratch. Set `prune_owned_work: true` only to remove **new successful trial
scratch**; original caches and all trial derivatives/logs remain untouched.
Failed trial scratch is always retained. No incomplete trial is automatically
restarted or adopted. Review its evidence and use a new experiment root.
The runtime filesystem device is pinned. If the external volume disappears or
changes, runtime writes fail rather than creating a shadow directory on the host.
Reconnect the original volume and review the retained controller/trial evidence
before resuming the same finite experiment.

## Run

Copy [the example](../../03_config/thread_reproducibility.example.json) outside the
repository and replace its synthetic placeholders. Each source config must
select exactly one visit and match its successful completion receipt.

```sh
python pipeline/s13_reproducibility/run.py init --config /ABS/experiment.json
python pipeline/s13_reproducibility/run.py run --root /ABS/new-experiment
# The command above only reports the plan and blockers. Explicit execution:
python pipeline/s13_reproducibility/run.py run --root /ABS/new-experiment \
  --execute --wait-idle --poll 60
python pipeline/s13_reproducibility/run.py status --root /ABS/new-experiment
python pipeline/s13_reproducibility/run.py report --root /ABS/new-experiment
```

Run the finite experiment in a background process for long datasets. It makes no
model calls and does not create an app automation. Preserve the Python environment
and source hashes until it finishes. A source/configuration change holds the
experiment for review. Docker/image access failures also hold it; they never
justify changing another job. Every image is installed and digest-pinned before
initialization; execution uses `--pull never --network none`.

Use a fixed workflow CPU budget for every condition. For example, with twelve
Docker CPUs, `[1, 2, 4, 8, 12]` is an admissible candidate list, **not a validated
recommendation**. Allocating twelve CPUs with one numerical thread still permits
independent workflow processes to overlap. Do not compare these new timings with
old timings measured under a different CPU budget, workload or cache state.
The runner records interference from other containers and excludes such timings
from its passing/recommended configurations.
The `adni-repro-*` container namespace is separate from production CPU/watchdog
services. The existing shared subject lease still accounts for its one subject.
Docker CPU/memory limits and actual fMRIPrep/XCP-D TOML process/thread settings
are checked against the plan, in addition to the submitted command.

## Tolerances and interpretation

At least three independent one-thread reference runs build a frozen policy before
any candidate run. At least two independent runs are required per candidate.
For each case/product/column, bounds are the larger of the declared engineering
floor and the maximum reference-pair difference multiplied by the declared
factor (default 1.25). Floors and factor must be chosen before candidate results;
they are engineering choices, **not published scientific-equivalence thresholds**.
Three repetitions are an exploratory minimum, not a substitute for the paper's
larger repeated-perturbation design or a confidence guarantee.
Fixed-seed single-thread references may be numerically identical. In that case
the declared engineering floors, rather than an estimated nonzero variability,
determine the limits. An all-failing multithread result under these strict floors
does not establish that multithreading is scientifically unusable.

Numeric products report maximum/mean/99th-percentile absolute differences and
normalized RMSE. Masks/segmentations report label disagreement. TSV text labels,
frame/censor choices and QC volume counts must match exactly. Geometry, TR,
CIFTI axes/brain models and surface topology are checked before comparing values.
FC matrices are compared on the off-diagonal upper triangle, preserving row and
column labels. Matching compressed-file hashes are not required; image values
and their coordinate definitions are compared. High correlation alone never
passes a result. Raw unused CompCor columns are not treated as final endpoints;
the actual XCP-D design, denoised series and connectivity are compared instead.

`highest_tested_passing_threads` is the largest **measured** candidate passing all
declared cases/repeats. `fastest_tested_passing_threads` also requires a speedup in
each case and chooses the highest geometric-mean speedup. Neither interpolates
to untested counts nor modifies production. Missing runs remain `PENDING`, failed
runs remain failures, and interference produces `CONFOUNDED_LOAD`.
All reports retain `scientific_equivalence: not_established`. An unstable baseline
does not establish that a large numerical difference is scientifically harmless;
review downstream endpoints and set a separately justified scientific margin
before adopting a production change. Results on two cases do not certify all ADNI
phases, scanner protocols, computers or downstream scientific conclusions.

## Literature and scope

- Chatelain et al. *A Numerical Variability Approach to Results Stability Tests and
  Its Application to Neuroimaging*. IEEE Transactions on Computers 74(1), 200–209
  (2025), [DOI](https://doi.org/10.1109/TC.2024.3475586),
  [public manuscript](https://arxiv.org/html/2307.01373v2). The manuscript studied
  fMRIPrep 20.2.1 anatomical outputs using numerical perturbations/random seeds,
  thirty samples per subject/condition, and a statistical stability test. This
  stage borrows the calibrated-envelope principle; it does **not** implement that
  test, inject arithmetic noise, reuse its anatomical thresholds for BOLD, or
  claim that the study validated our current XCP-D/thread configurations.
- Salari et al. *Accurate Simulation of Operating System Updates in Neuroimaging
  Using Monte-Carlo Arithmetic* (2021),
  [DOI](https://doi.org/10.1007/978-3-030-87735-4_2). Supports measuring numerical
  variability under controlled environment changes.
- Glatard et al. *Reproducibility of Neuroimaging Analyses across Operating
  Systems* (2015), [DOI](https://doi.org/10.3389/fninf.2015.00012). Includes ADNI-GO
  resting-state data and motivates intermediate-product comparisons.
- Li et al. *Moving beyond processing- and analysis-related variation in
  resting-state functional brain imaging* (2024),
  [DOI](https://doi.org/10.1038/s41562-024-01942-4). Motivates evaluating final
  connectivity, in addition to preprocessing. This is not a thread-count study.
