# Materialized public atlas cache

TemplateFlow's actual 2-mm label NIfTI payloads are stored here by the explicit `sources.py fetch-templateflow` command. The cache is ignored by the parent repository. Filename, pinned dataset commit, byte size, annex digest and SHA-256 are recorded in `templateflow_payloads.json`.

Neuroparc/CBIG images remain tracked in their source submodules. Do not copy private ADNI images, time series or extraction outputs into this directory.
