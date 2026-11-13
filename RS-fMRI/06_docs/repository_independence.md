# Independent local runtime

The owned repository contains the protocol sources, Custom Steps, controllers, timing observer and CPU quota tool. Docker, the host Python/R installations, source data, TemplateFlow payloads and the FreeSurfer license remain explicit external prerequisites. Removing a separate historical protocol checkout requires a verified handoff; copying source files alone does not migrate an active Python environment or service configuration.

## Execution commands

```sh
cd /ABSOLUTE/PATH/adni-data-pipeline/RS-fMRI
source .venv/bin/activate

# Read-only inspection of a private, prepared handoff plan:
python 04_workflow/independent_repository.py \
  --plan /ABSOLUTE/PATH/runtime/service_handoff/migration/plan.json check

# Deferred cutover: finish the captured cohort, then migrate and remain stopped.
python 04_workflow/independent_repository.py \
  --plan /ABSOLUTE/PATH/runtime/service_handoff/migration/plan.json watch

# Separate operational quota; does not change imaging arguments or thread counts.
python 04_workflow/cpu_budget.py --root /ABSOLUTE/PATH/runtime --cpus 1.5 watch
```

These are administration commands, not another preprocessing stage. They do not launch new imaging calculations. A private plan must identify the captured cohort, expected source hashes, staged replacement hashes, exact service labels, historical scientific configuration and the new repository-owned environment. Do not put participant lists, actual service plans or execution receipts in the public repository.

## Drain and handoff contract

1. Hold only new subject admission. The live verified feeder waits while its source gate has the explicit `admission_held_for_repository_migration` status. Preserve the successful ZIP validation evidence and disable the source-gate timer that could reopen admission. Existing independent workers continue through S6/S7 and S10.
2. Prepare `.venv` inside `RS-fMRI` with the same installed package versions. When copying an existing environment locally, create a fresh interpreter environment first, copy installed packages without links into the old checkout, regenerate console scripts with the new interpreter, and verify imported module paths. Preserve the old environment while calculations run. Keep the installed R library in ignored `.R-library/` and set `R_LIBS_USER` to that directory.
3. Wait for no managed imaging containers, no captured subject-worker locks, verified external archive manifests and S12 export manifests for successful subjects. Terminal failures remain failures with their original caches and receipts preserved; they are not silently relaunched under a different runner identity.
4. At the idle boundary, disable the explicitly captured ADNI services, compare expected source hashes, install reviewed owned-source replacements, bind source paths and regenerate deployment fingerprints. Source changes by another owner hold the migration rather than being overwritten.
5. Repoint all service interpreters to the new `.venv`, all executable Python sources to this repository, and the CPU service to `04_workflow/cpu_budget.py`. Keep every service disabled after the handoff. A later explicit request is required to resume subject admission.
6. Run imports, `lab.py doctor`, the queue source check and the XCP-D compatibility check. On macOS these checks deny reads of the old checkout using a child-process sandbox, without moving or deleting it. Save private verification receipts and report completion only after the checks pass.

## Historical identity and effective source

Existing result configuration IDs depend on historical configuration bytes, including a former source path. Replacing that text inside a historical configuration would change its identity. Instead, the private deployment's `repository_binding` records the historical path, the effective owned protocol path and independently verified S8 source hashes. The compatibility service verifies the original configuration/ID, then redirects executable source reads to the owned repository. Original run records, image IDs, inputs, seeds, images, analysis thresholds and cache signatures are unchanged. Historical path text can remain in immutable provenance without being an active filesystem dependency.

The stale legacy completion code is not loaded once `active_xcpd` is empty. Previously completed legacy subjects are not a new execution scope. Missing or failed inputs still require their original verification/retry gates; the migration does not authorize new pair selection or bypass source QC.

## Validation limits

Synthetic tests cover quota scoping, the admission hold, live-container refusal, archive/S12 readiness, terminal failure preservation, concurrent source changes, service path rebinding and unchanged historical config IDs when the old checkout is absent. These are operational and source checks, not proof of scientific equivalence between different imaging versions. CPU quota changes can increase elapsed runtime without changing scientific options. Never delete the original checkout on the strength of a scheduled handoff or a pending status alone.
