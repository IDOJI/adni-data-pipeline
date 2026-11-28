# Resting-state fMRI

<a id="setup"></a>[Set up your study folder](stages/setup.md), then open the stage you need. Each guide includes inputs, terminal commands and the output to check.

| Stage | What you do |
|---|---|
| <a id="select"></a>[01 · Select scans](01-selection/README.md) | Check source QC and pair each resting scan with a same-day T1. |
| <a id="convert"></a>[02 · Download and convert](02-bids/README.md) | Convert selected DICOMs with dcm2niix and verify each Image ID. |
| <a id="process"></a>[03 · Process and review](03-imaging/README.md) | Run MRIQC, fMRIPrep and XCP-D. Review imaging and clinical eligibility. |
| <a id="harmonize"></a>[04 · Harmonize connectivity](04-harmonization/README.md) | Fit scanner ComBat on eligible XCP-D connectivity matrices. |

<a id="structure"></a><a id="steps-and-commands"></a>[Protocol and configuration index](docs/protocol-index.md) · [Practice with public data](07_reproducibility/README.md) · [Validation](docs/validation.md) · [Attribution](NOTICE.md)

Shared [configuration](config/), [workflow tools](workflow/), [tests](tests/) and [documentation](docs/) support the four stage folders. Earlier numbered paths are compatibility links. The optional [atlas library](pipeline/s11_atlas_bold/README.md) retains its pinned dependencies.
