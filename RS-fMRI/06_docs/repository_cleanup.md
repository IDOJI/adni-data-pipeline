# Standalone checkout retirement

`adni-data-pipeline` is the single maintained repository. It contains both RS-fMRI and SNP; only the RS-fMRI source layout was involved in this cleanup.

## Why two pipeline names appeared

The sibling `adni-rsfmri-pipeline` was a symbolic link created during the 2026-11-01 consolidation. It pointed to `adni-data-pipeline/RS-fMRI/pipeline/s7a_volume_workflow`, not a separate copy or Git repository. The compatibility link was removed on 2026-11-13. Use [Custom Step 7.A](../pipeline/s7a_volume_workflow/README.md) directly when that distinct aCompCor volume profile is required.

The standalone `ADNI_fMRI_protocol` checkout was the original statMIND source plus local installation tools and environments. It is no longer required by the integrated runtime. Its local directory was removed after source comparison, a complete verified backup, and checks with both retired paths inaccessible. The original remote repository was not changed.

## Preserved content

| Content | Location and verification |
|---|---|
| 76 protocol source, configuration, documentation and attribution files | `pipeline/`; each matched the original file byte for byte at retirement |
| Five original notebooks | Existing `provenance/notebook_sources/` exports retain code without recorded outputs; original/export hashes remain in `03_config/protocol_notebooks.json` |
| Local Mac helpers, historical tests and integration probe | 31 Python/R/shell files plus one compatibility JSON in `provenance/local_mac_reference/`; original/export hashes and adaptations in `03_config/local_mac_reference.json` |
| Historical standalone S10 | Four source/test files in `provenance/s10_local_reference/`; original/export hashes in `03_config/s10_local_reference.json` preserve local changes made after the initial import |
| Current execution and postprocessing | Existing Custom Steps 7.A, 7.B, 8.A and 10 retain their reviewed adaptations and source provenance |
| Exact original files, private configuration, results, environments and Git metadata | Complete private backup outside this repository; every regular file, directory mode and symbolic-link target was checked against the original inventory |
| Original Git history | Complete verified local Git bundle restores all 154 reachable commits and every reference from the standalone checkout; the existing public history index covers the 153-commit imported main history |

Private participant data, original notebook outputs, machine configuration and installed packages were not added to public source. Synthetic examples replace participant/scan/image examples in the additional reference export. No scientific settings, active runner files, caches or result identities were changed.

The final coverage audit accounted for all 83 original Python/R/shell source files in the protocol and local additions, with no missing file. All five original notebook hashes also matched the existing export manifest.

## Runtime verification

The previous independent-runtime handoff completed on 2026-11-08 (Asia/Seoul). At retirement, services pointed to the repository-owned Python and sources. Python/R imports, protocol doctor, queue source validation and XCP-D compatibility checks were repeated while operating-system access to the retired paths was denied. Running-process and container-mount inspection found no dependency on either retired path. Four already-disabled service definitions were corrected to use the integrated deployment or updated relocation checks; their historical settings were backed up and no service was started.

The existing source/synthetic test suite passed 499 tests and 17 subtests from an isolated copy of the current working tree, with one existing Nilearn deprecation warning. Reference exports were checked for Python syntax, source/export hashes and private identifiers. These checks verify source preservation and runtime independence; they do not rerun imaging or establish scientific inclusion decisions.

The private retirement record, complete inventory, backup digest, original Git bundle and command-check results are stored together under the local `backups/sources/adni-protocol-retirement-20261113/` directory outside this repository. The backup is for restoration and is not an active second pipeline.
