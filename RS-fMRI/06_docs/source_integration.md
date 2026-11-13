# Integrated ADNI protocol sources

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r 01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/requirements.txt
python 04_workflow/lab.py doctor
python -m pytest -q
```

A normal clone contains the core protocol. No original-protocol checkout or submodule initialization is required. SNP and optional atlas sources remain separate submodules.

## Ownership and attribution

`01_upstream/ADNI_fMRI_protocol/` is ordinary editable source owned by this repository. The historical path is retained for import, configuration and external work/cache compatibility. Review changes through normal branches and PRs alongside Custom Steps.

The 76 imported source/attribution files are byte-identical to their selected versions at [statMINDlab/ADNI_fMRI_protocol e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3). Original [GPL-3.0](../01_upstream/ADNI_fMRI_protocol/LICENSE), copyright and [CITATION.cff](../01_upstream/ADNI_fMRI_protocol/CITATION.cff) remain intact. The parent [NOTICE](../NOTICE.md) records the import date/scope. Retain attribution and identify subsequent modifications under the license.

## Source and history preservation

- [upstream.lock.json](../03_config/upstream.lock.json) retains the original URL, baseline commit and review date. Its distribution is now `integrated-source`; it is origin metadata rather than a checkout pin.
- [protocol_sources.json](../03_config/protocol_sources.json) records original blobs, modes, sizes and SHA-256 values for all 76 imported files. Keep it as the import reference when editing owned code.
- [protocol_history.json](../03_config/protocol_history.json) indexes all 153 reachable original commits with their original hashes, parents, authors, dates and subjects.
- A verified, complete local Git bundle preserves the entire original object history and exact original commit IDs outside this public source repository. The original repository URL/commit is an additional public history reference.

The complete original history contains participant results. It is **not grafted into this repository's public ancestry**. The source appears as an import here; the history index and local bundle preserve traceability and restoration without republishing those results.

Only executable source/tests, configuration/environment templates, text documentation and attribution are imported. Participant lists, generated CSV/TSV/HTML/SVG results, original output-bearing notebooks, screenshots, upstream CI and local assistant settings are excluded. Five [source-only notebook copies](../01_upstream/notebook_sources/README.md) retain code outside the live protocol directory, with outputs/runtime metadata removed and one participant example made synthetic; [their manifest](../03_config/protocol_notebooks.json) records original and exported hashes. Original text documentation remains verbatim; consult the original pinned GitHub URL for its figures and notebook examples. The full local bundle retains original excluded assets.

The additional historical Mac tools are preserved as [source references](../01_upstream/local_mac_reference/README.md), with all 32 source/test/compatibility files recorded in [their manifest](../03_config/local_mac_reference.json). Four [standalone S10 source/test references](../01_upstream/s10_local_reference/README.md) additionally preserve changes made after the first import. These references are separate from the active integrated runners. The [2026-11-13 cleanup record](repository_cleanup.md) explains the full private backup and retirement of the standalone checkout.

## Doctor and execution identity

Doctor checks parent-tracked ordinary files, actual bytes/modes, the GPL text and attribution, origin/history consistency and step layout. Missing, redirected or uncommitted protocol files fail. Reviewed source changes recorded in this repository are accepted without repinning the original baseline. The report distinguishes that baseline from the current parent revision and computes the actual protocol content identity.

New 7.B/S10 provenance uses this source identity. The integration does not alter scientific configuration/cache construction or rewrite historical receipts/results. A changed runner still requires the normal cache/deployment review. Source checks do not establish scientific inclusion or a full-cohort imaging baseline.

## Existing live installations

Do not deinitialize/delete the source directory, overwrite deployment-bound runners or restart workers while calculations depend on their recorded hashes. Preserve local files, the Git index, original protocol history and live deployment identities before an in-place migration.

An initialized clone may retain its inert old `.git` pointer/object store for recovery and already running legacy workers. New source validation/selection never consults that metadata; fresh clones contain no nested protocol Git metadata. Preserve deployment-bound code as local overlays until a verified idle handoff. This source migration does not perform that service handoff. Omitted original artifacts can remain as ignored local files.

See the [update guide](update_guide.md) and [live-service contract](live_service_handoff.md).
