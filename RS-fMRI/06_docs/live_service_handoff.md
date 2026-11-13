# Live-service handoff

For a complete removal of the separate historical checkout dependency, use the [independent-runtime handoff](repository_independence.md). It preserves old scientific identities through an explicit effective-source binding and leaves services stopped after the captured cohort drains.

The preprocessing queue, XCP-D controller and offloader can use this repository while existing calculations and results remain in place. The deployment manifest is private and records source hashes, legacy ownership, container identities and the exact historical XCP-D configuration hash.

## Execution boundaries

- `04_workflow/queue_service.py` continues the existing queue/state/retry policy. Previously started subjects use their original runner until completion; newly admitted subjects use `02_custom/s7b_sessionwise_preprocessing`. Shared leases retain the current five-subject limit across preprocessing and XCP-D.
- `04_workflow/live_services.py` is an explicit XCP-D compatibility entry point. It verifies the historical configuration and pinned S8 semantics, preserves the existing config_id/hub, reconnects active attempts through a hash-verified frozen completion observer and uses integrated S10 for subsequent runs. Code deployment is recorded separately from scientific configuration.
- `04_workflow/capture_exits.py` observes existing containers without changing them. Before replacing controllers, attach exit capture so a container exiting with `--rm` cannot lose its completion receipt during the handoff.
- The integrated offloader continues using the existing root/settings and validated archival receipts. It never treats the service transition as scientific QC approval.

## Cutover checks

Back up only controller settings/plists and frozen completion sources. Record active container IDs/start times, scientific settings, source hashes and completed-result manifests. Verify the new code in an isolated workspace, then gate old admission and replace host controllers only at a boundary where their descendants are observers rather than foreground analysis runners. Preserve all Docker containers and external-volume paths.

Activate the existing service labels with new repository entry points and the same private runtime/configuration. Restore the existing admission policy, verify reconnection, confirm unchanged container IDs/start times, and verify that new-subject dispatch selects the integrated adapter. Retain a rollback manifest and the frozen sources required by active jobs.

```sh
python 04_workflow/live_services.py --config /ABSOLUTE/PATH/historical-xcpd.json --deployment /ABSOLUTE/PATH/deployment.json check
python 04_workflow/live_services.py --config /ABSOLUTE/PATH/historical-xcpd.json --deployment /ABSOLUTE/PATH/deployment.json watch
python 02_custom/s10_xcpd_integrated_qc/offload_completed.py --root /ABSOLUTE/PATH/runtime --settings /ABSOLUTE/PATH/offload-settings.json
```

The regular S10 constructor continues to require validated integrated protocol source and a new explicit configuration. Only this verified compatibility entry point preserves a historical configuration identity. It does not authorize changed images, thresholds, atlases, nuisance settings or previously unknown caches. Existing completed attempts and human-review fields are preserved.

## Prospective iteration logging

The queue wraps subsequent stage launches with Custom Step 7.C, including frozen-backend retries. Backend cache identities remain unchanged and the logging transport has separate provenance. For this logging upgrade, use Step 7.C deferred activation: hold only new admission, allow existing containers/workers to finish, gracefully restart the idle controller and restore the original admission policy after the new launcher is advertised. Host `docker run` clients proxy signals; do not terminate active execution trees to enable logging. Check the external activation receipt before reporting the logging transport as active.

## Source integration and active deployments

New deployments validate ordinary parent-tracked source through `protocol_source.py`. Preserve old deployment-bound source files, configuration IDs and cache signatures while jobs run. Keep inert legacy Git metadata and local runner overlays until a verified idle handoff; changing the parent source distribution does not authorize a controller restart or rewriting an existing receipt. See the [integration contract](source_integration.md#existing-live-installations).
