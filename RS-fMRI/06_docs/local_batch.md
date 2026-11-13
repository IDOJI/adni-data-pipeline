# Unattended local handoff batches

For new batches, prefer `04_workflow/local_batch_seeded.py` and `03_config/local_batch.seeded.example.json`; use that entrypoint for `prepare`, `watch` and `status`. It selects seeded MRIQC/fMRIPrep and S10 routes while preserving all admission gates. See the [fixed-seed guide](seed_reproducibility.md). The original launcher described below remains available for existing source-locked batches.

`04_workflow/local_batch.py` prepares and supervises a private reserved input batch without model or API calls. It uses the existing 5.D exact-pair checks, strict 7.B intake, 7.C ANTs logging and S8/S10 XCP-D validation. A native service, rather than a chat heartbeat, owns the work.

## Prepare before launching

Start with `03_config/local_batch.example.json`. Set external paths and the actual fingerprint of an existing source-review catalog. The handoff must contain `_handoff/batch_manifest.json`, `participants.tsv`, and exactly four hashed raw files per participant. Existing candidate/image, EPI-pairing and pairing-receipt artifacts remain authoritative; the supplied batch does not override source-review holds.

```sh
python 04_workflow/local_batch.py --config /ABS/private-batch.json prepare
python 04_workflow/local_batch.py --config /ABS/local-runtime/config/batch.json watch
# Read the persisted state; this does not run or refresh imaging:
python 04_workflow/local_batch.py --config /ABS/local-runtime/config/batch.json status
```

`prepare` requires a new root outside the repository and cloud storage. It copies raw bytes locally, verifies hashes, creates a separate BIDS view, records the addition of `TaskName=rest` to functional JSON only, and preserves original image/JSON files. No slice-axis, Image ID, UID, acquisition date or timing is inferred or changed. The binding gate checks independent canonical Image ID/UID/hash evidence and headers. Every strict intake decision is retained; unresolved cases remain held.

## Native ownership and recovery

Install one local LaunchAgent invoking `watch` in the repository Python environment. Use an accessible working directory and Library/Logs for launchd output; retain private configuration and participant lists outside the source repository. `RunAtLoad` and failure-only `KeepAlive` can resume the same batch after login or a controller crash. A singleton manager lock and per-subject locks prevent duplicate owners. This is a macOS deployment recipe, including the APFS clone publisher; it is not a systemd recipe.

The service admits at most five subjects and obtains the existing host-wide `compute_slots` lease for MRIQC/fMRIPrep and XCP-D. It refills a position after local output validation or a documented hold. Source-review, strict-intake, integrity, exhausted retries and postprocessing holds never become success. Recorded attempts bound retry budgets across controller restarts. Successful stages are reused. A recorded running attempt is observed through its exact retained Docker container, rather than relaunched.

The new preprocessing transport preserves the scientific command and cache identity, adds the existing logging mounts, applies a separately recorded Docker CPU quota, and retains terminal containers for crash recovery. Its actual command is in `local_execution.json`. No successful or failed historic runtime is overwritten. A source-lock mismatch holds future dispatch without stopping active work.

The first successful XCP-D output validation establishes the pipeline's pilot gate. A failed pilot blocks expansion of XCP-D. Native human-review fields and final research inclusion remain pending. Source and imaging QC failures are preserved separately.

## Local results and limits

- `inputs/original/`: unchanged raw handoff and source files.
- `inputs/bids/`, `cases/<subject>/`: verified BIDS views, work/cache, derivatives and attempt logs.
- `runs/<subject>`: local runtime links for the existing publisher/S10 contract.
- `results/<PTID>/EPI_YYYYMMDD_MT1_YYYYMMDD/`: published MRIQC/fMRIPrep, S8/XCP-D output and individual QC evidence.
- `status.json`, `status.html`: machine state and a local browser-readable progress table.
- `control/jobs/`, `control/events.jsonl`: bounded retry and hold records, with `LLM_calls=0`.

No offloader, automatic cache deletion, cloud result upload, clinical merge or final research-inclusion approval runs. New admissions wait when the configured disk reserve is insufficient. The five-subject setting is a maximum, not a guarantee of safe capacity on every host; execution-resource configuration and actual Docker memory must be reviewed separately. Quitting a chat does not stop a native service; shutting down the host stops computation until the existing batch is resumed. Do not unload a busy service as a way to change configuration.
