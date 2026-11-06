# Versions

| Component | Version or record |
|---|---|
| GWAS_QC | [5bbabfb54c2fffb86f39810386652daa124ce683](https://github.com/VUMC-VMAC/GWAS_QC/tree/5bbabfb54c2fffb86f39810386652daa124ce683); [file hashes](upstream.lock.json) |
| Project panel/build | TOPMed r3; GRCh38 |
| Service documentation | Eagle v2.4.1; Minimac4 v4.1.6, checked November 1, 2026 |
| Upstream container | `CNT_genomic_processing_v3.19.simg`; image and checksum must be supplied |
| Local helpers | Python 3.10+; standard library |
| Public toy | PLINK 1.9.0, September 27, 2026; platform URLs/checksums in [run.py](../07_toy/run.py) |

Service versions above come from the [TOPMed documentation](https://statgen.github.io/tis-v2-docs/imputation/getting-started/). Record actual server, phasing and imputation versions from each completed job, plus the container checksum and installed QC-tool versions.

Install the recorded gitlink with `git submodule update --init --recursive`. For an upstream update, review the changes and update the gitlink, hash lock and compatibility checks together.
