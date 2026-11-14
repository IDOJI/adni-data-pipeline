# Source and attribution

All maintained stages are in `pipeline/`. The skeleton was adapted and modified from [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3); a separate original checkout is unnecessary.

Original [GPL license](../pipeline/LICENSE), [citation](../pipeline/CITATION.cff) and [NOTICE](../NOTICE.md) are retained.

| Record | Contents |
|---|---|
| [upstream.lock.json](../03_config/upstream.lock.json) | Original URL and import commit |
| [protocol_sources.json](../03_config/protocol_sources.json) | Original 76-file import hashes |
| [protocol_history.json](../03_config/protocol_history.json) | Index of 153 original commits |
| [provenance/](../provenance/README.md) | Historical references and original README |

Private original outputs/full Git history are preserved in local backups, outside the public repository. SNP and optional atlas libraries remain separately pinned.

From `RS-fMRI/`, run `python 04_workflow/lab.py doctor` to check tracked files, attribution and source identity. Edit and commit maintained code in this repository; retain the import hashes as historical records.

## Existing live installations

Keep active batches on their frozen revision, configuration and caches. Before relocating their source, verify an idle handoff and record the new executable binding separately from the analysis identity. Use a new runtime for new seed-1123 analyses. See [updates](update_guide.md) and the [service handoff](live_service_handoff.md).
