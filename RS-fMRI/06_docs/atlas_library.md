# Atlas library and extraction boundaries

The optional Step 11 library pins Neuroparc, CBIG, Nilearn and the TemplateFlow archive as separate Git submodules under `02_custom/s11_atlas_bold/01_sources/`. See the [step contract and commands](../02_custom/s11_atlas_bold/README.md).

| Source | Purpose | Pin and payload policy |
|---|---|---|
| Neuroparc | Standardized human label images and source metadata | Pinned commit; exact source space remains MNI152NLin6 without inferred aliases |
| CBIG | Author-distributed Schaefer volume variants | Pinned commit; sparse checkout only of reviewed MNI parcellations and metadata |
| Nilearn | Fetcher/masker source reference | Pinned commit; runtime installation remains independent |
| TemplateFlow | Exact template identities and associated atlases | Archive commit plus nested MNI6Asym/2009cAsym commits; real data explicitly fetched and checksum verified |

## Reproducible setup

Initialize the core ADNI submodule for ordinary tests. Install optional atlas sources explicitly with `sources.py install`; this uses pinned commits and sparse patterns from `sources.lock.json`, never `--remote`. TemplateFlow installs only the two reviewed nested template datasets. Run `fetch-templateflow` separately to materialize the pinned NIfTI data. Git-annex/LFS pointers are not valid extraction inputs.

Review a source update by changing its pin on a test branch, inspecting licenses, metadata, observed labels and expected labels, rebuilding the catalog to a new path, and rerunning synthetic and actual-atlas tests. Catalog generation never proves scientific registration. Do not replace MNI152NLin6Asym with MNI152NLin2009cAsym based on shape/affine similarity.

## Connection to the existing workflow

S10 already computes configured ROI/FC products internally. Step 11 is a separate explicitly selected atlas extractor; it does not overwrite those outputs or reapply XCP-D cleaning. After imaging-QC review, 9.A and 9.B, select the intended denoised BOLD and its matching-grid mask. Pass 9.B plus the actual image ID/run mapping. Pending source quality is preserved as pending; excluded/held images cannot enter extraction through that gate.

The 7.A volume profile uses MNI152NLin2009cAsym, whereas S10's configured volume space is MNI152NLin6Asym. Select a matching catalog entry for each profile. Volumetric labels are supported; CIFTI/fsLR/fsaverage, probabilistic maps and coordinate spheres require separate validated extractors.

## Evidence

- [Neuroparc repository and atlas metadata](https://github.com/neurodata/neuroparc).
- [CBIG Schaefer distribution](https://github.com/ThomasYeoLab/CBIG/tree/master/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal).
- [Nilearn dataset documentation](https://nilearn.github.io/stable/modules/datasets.html).
- [TemplateFlow client and lazy data loading](https://www.templateflow.org/usage/client/).
- [TemplateFlow MNI6Asym description](https://github.com/templateflow/tpl-MNI152NLin6Asym).

Public validation records aggregate counts only. Private BOLD inputs, participant IDs, time series and execution artifacts stay outside the repository.
