# Source and runtime versions

| Component | Recorded state |
|---|---|
| GWAS_QC | Commit `5bbabfb54c2fffb86f39810386652daa124ce683`, dated July 20, 2026 |
| Source review | November 1, 2026; [hash lock](upstream.lock.json) |
| Historical paper code | Exact commit unconfirmed |
| Historical TOPMed panel | Release unconfirmed; do not label it R2 as an established fact |
| Project imputation panel | TOPMed r3; GRCh38 |
| Documented service software | Eagle v2.4.1; Minimac4 v4.1.6, per official documentation checked November 1, 2026 |
| Actual service software | Must be recorded from each completed job; no jobs executed here |
| Upstream container | README names `CNT_genomic_processing_v3.19.simg`; image and digest not supplied |
| PLINK, R, BCFtools/HTSlib, EIGENSOFT, SNPWeights | Runtime versions must be captured from the validated environment |
| Local helper runtime | Python 3.10+; standard library only |

The parent gitlink pins source installation. `doctor` checks that gitlink, the clean checkout, `.gitmodules` and locked file hashes; it does not certify external binaries, container contents or scientific criteria. The lock is not a complete runtime environment lock.
