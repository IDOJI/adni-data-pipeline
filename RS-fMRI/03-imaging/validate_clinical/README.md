# Stage 9.A — Clinical validation

**What:** Check diagnoses near each actual scan date, demographic consistency and diagnostic ties.

**Output:** `clinical_validation.tsv`, demographic/source-row audits and `artifact.json`.

## Run

From `RS-fMRI/`, after [setup](../../docs/installation.md). Point `--included` and `--scan-links` at the tables from the same reviewed S10 finalization. In the example they are available under `DATA/review/`. Set `--dxsum` and `--ptdemog` to the original tables for the chosen data freeze. `--max-dx-days 28 --dx-direction nearest` defines the study's matching rule.

Use matching `final_included_runs.tsv` and `clinical_scan_links.tsv` from [S10](../xcpd_integrated_qc/README.md).

```sh
python pipeline/s9a_validate_clinical/run.py \
  --included "$DATA/review/final_included_runs.tsv" --scan-links "$DATA/review/clinical_scan_links.tsv" \
  --dxsum "$DATA/LONI_download/clindata/DXSUM.csv" \
  --ptdemog "$DATA/LONI_download/clindata/PTDEMOG.csv" \
  --max-dx-days 28 --dx-direction nearest --output-dir "$RESULTS/qc/step9a"
```

Nearest-date ties and missing evidence remain explicit. A dementia label alone is not confirmed AD etiology.

## Evidence and limits

Sources: [ADNI imaging–diagnosis answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2401); [ADNI diagnosis-code answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=1756); [ADNI dementia-etiology answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=209). The [Stage 9.A evidence record](../../docs/stage_evidence.md#stage-9-a) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.

Image IDs use the same numeric LONI identifier rule as Step 3.B. One optional I/i prefix and leading zeros are normalized. Malformed or conflicting IDs and reuse across runs are reported for review.
