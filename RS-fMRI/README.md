# Resting-state fMRI

<a id="setup"></a>[Set up your study folder](stages/setup.md), then open the stage you need. Each guide includes inputs, terminal commands and the output to check.

| Stage | What you do |
|---|---|
| <a id="select"></a>[01 · Select scans](stages/01-selection/README.md) | Check source QC and pair each resting scan with a same-day T1. |
| <a id="convert"></a>[02 · Download and convert](stages/02-bids/README.md) | Convert selected DICOMs with dcm2niix and verify each Image ID. |
| <a id="process"></a>[03 · Process and review](stages/03-imaging/README.md) | Run MRIQC, fMRIPrep and XCP-D. Review imaging and clinical eligibility. |
| <a id="harmonize"></a>[04 · Harmonize connectivity](stages/04-harmonization/README.md) | Fit scanner ComBat on eligible XCP-D connectivity matrices. |

<a id="structure"></a><a id="steps-and-commands"></a>[Protocol and configuration index](06_docs/protocol-index.md) · [Practice with public data](07_reproducibility/README.md) · [Validation](06_docs/validation.md) · [Attribution](NOTICE.md)
