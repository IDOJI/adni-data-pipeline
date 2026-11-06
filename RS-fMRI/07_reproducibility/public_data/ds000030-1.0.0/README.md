# Public real MRI sample included in Git

This directory contains **actual T1w and resting-state BOLD NIfTI payloads**, stored as ordinary Git files. An ordinary clone or GitHub source ZIP includes the images. These files are not synthetic phantoms, Git-annex links or Git LFS pointers.

## Source and attribution

- Dataset: **UCLA Consortium for Neuropsychiatric Phenomics LA5c Study**, OpenNeuro **ds000030 1.0.0**.
- Dataset DOI: [10.18112/openneuro.ds000030.v1.0.0](https://doi.org/10.18112/openneuro.ds000030.v1.0.0).
- Fixed source revision: [4070b6eea231517bfeff42527a46d9d166ac4e13](https://github.com/OpenNeuroDatasets/ds000030/tree/4070b6eea231517bfeff42527a46d9d166ac4e13).
- Original publication: Poldrack et al., *A phenome-wide examination of neural and cognitive function*, Scientific Data (2016), [doi:10.1038/sdata.2016.110](https://doi.org/10.1038/sdata.2016.110). Follow the source dataset's `HowToAcknowledge` field when using these data.
- Data license: **CC0 1.0 Universal**, as declared in the unchanged [dataset_description.json](dataset_description.json). See [LICENSE-CC0.txt](LICENSE-CC0.txt). This CC0 data dedication is separate from the source code's GPL-3.0 license.

## Included files

Only one public subject's T1w/rest BOLD and the metadata required by this example are included. All five source files preserve the upstream bytes. This is a subset, not the full study or an ADNI dataset.

| Image | File size | Dimensions |
|---|---:|---|
| [T1w NIfTI](sub-10159/anat/sub-10159_T1w.nii.gz) | 11,637,742 bytes | 176 × 256 × 256 |
| [Rest BOLD NIfTI](sub-10159/func/sub-10159_task-rest_bold.nii.gz) | 24,052,822 bytes | 64 × 64 × 34 × 152; TR 2 s |

Metadata: [dataset description](dataset_description.json), [task-level BOLD JSON](task-rest_bold.json), and [subject BOLD JSON](sub-10159/func/sub-10159_task-rest_bold.json). Total source payload is **35,696,832 bytes**.

[SHA256SUMS](SHA256SUMS) lists hashes of the five original files. The canonical [public_dataset.json](../../public_dataset.json) also records the original URLs, sizes, hashes and Git-annex MD5 evidence. The MRI files were downloaded as actual payloads and verified against those records before inclusion.

## Use

Follow [the step-by-step guide](../../README.md#b1-stage-and-verify-the-included-public-images). Its `public.py fetch` command copies and verifies these bundled files into a new external working directory **without accessing OpenNeuro**. The original bytes in this directory stay unchanged; execution-specific subject/session names and merged BOLD metadata are created only in the external working directory.

An explicit `--source remote` option can re-download the pinned upstream files for independent provenance checks. Missing or modified bundled files cause the default command to fail; there is no silent network fallback. Bundling the raw sample does not establish completed MRIQC/fMRIPrep/XCP-D results or final research inclusion.
