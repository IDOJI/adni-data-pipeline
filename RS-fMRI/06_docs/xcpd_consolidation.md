# XCP-D consolidation and operational transition

## Canonical code locations

| Original implementation | Consolidated location | Treatment |
|---|---|---|
| Volume execution/recovery/audit/image QA in adni-rsfmri-pipeline | pipeline/s7a_volume_workflow | Preserve as a separate aCompCor profile |
| Tests, METHODS and literature in that directory | 05_tests/volume_workflow and 7.A documentation | Replace examples with synthetic IDs/external paths |
| Local S10 from the referenced task | pipeline/s10_xcpd_integrated_qc | Newer 36P/LINC postprocessing and integrated imaging QC |
| Validated external offloader in continuous5 | S10/offload_completed.py | Separate code from runtime settings; retain config_id/hash gates |
| Actual configuration, participant execution results, validation logs and single-case staging/migration | Private local source archive | Excluded from public source; preserved for restoration |

Original code hashes and port destinations are recorded in `03_config/imported_sources.json`. Existing fMRIPrep/XCP-D images are not moved or recalculated. Historical completion of the two-visit pilot and the active SB pilot's progress refer to different executions.

## Relationship to active workers

At consolidation, the existing XCP-D worker uses S10 code in the separate local ADNI_fMRI_protocol checkout, while the offload worker uses its runtime's frozen offloader. They retain source, config_id, cache and containers for reproducibility of active attempts. Installing the new repository does not restart services or force new settings on the next participant.

The consolidated workflow resolves `repo=null` to the repository-owned integrated protocol source and requires explicit external configuration. The path change also changes config_id; do not treat the old worker's configuration/cache as identical. To transition to a new study runtime, complete existing attempts and preserve evidence, then validate preflight → dry-run → pilot with a new root/configuration. Do not start a second watch on a root still managed by the original worker.

On 2026-11-01, the former adni-rsfmri-pipeline path became a compatibility symlink to 7.A after all original files were archived locally and hash-verified. That redundant link was retired on 2026-11-13; use `RS-fMRI/pipeline/s7a_volume_workflow/` directly. Actual source configuration and dedicated staging/migration locations remain in private migration records, not the public repository. See the [retirement record](repository_cleanup.md).

## Execution order and research decisions

Upstream 1–7 → S8/8.A metrics/review and S10 pre-QC → provisional XCP-D candidates → collect/human review → cohort-based S10 imaging-QC finalization → S9/9.A clinical validation → study-specific source/imaging/clinical inclusion checks.

S10 can start independently for pairs completed by S7. S9 clinical linkage can also run separately; revalidate 9.A against the selected runs if the S10 final imaging list changes. Step numbers identify roles rather than requiring strictly numerical execution.

Select both files in the 9.A handoff example from the same S10 finalization directory:

```sh
python pipeline/s9a_validate_clinical/run.py \
  --included /ABSOLUTE/PATH/finalization/final_included_runs.tsv \
  --scan-links /ABSOLUTE/PATH/finalization/clinical_scan_links.tsv \
  --dxsum /ABSOLUTE/PATH/DXSUM.csv --ptdemog /ABSOLUTE/PATH/PTDEMOG.csv \
  --output-dir /ABSOLUTE/PATH/clinical/run-001
```

## Scope not yet generalized

The live S6/S7 queue, raw-zip staging, flat-derivative-to-published-pair adapters, automatic intersections of source QC/8.A/clinical criteria for an actual cohort, and real Slurm/CIFTI execution require separate work. Do not bypass pair-receipt contracts or fabricate metadata to label previous calculations successful. Step 7.A (no FreeSurfer) and S10 (Euler required) are not directly compatible profiles.

## Subsequent live deployment

The [live-service handoff](live_service_handoff.md) adds an explicit compatibility deployment for the existing SB queue. It retains historical scientific configuration and active-job ownership while routing new subjects to integrated sessionwise preprocessing and subsequent XCP-D runs to S10. The earlier consolidation-only boundary above describes the initial import, not this later operational transition.
