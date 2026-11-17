# Stage 9.A — Clinical validation

**What:** Check diagnoses near each actual scan date, demographic consistency and diagnostic ties.

**Output:** `clinical_validation.tsv`, demographic/source-row audits and `artifact.json`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

Use matching `final_included_runs.tsv` and `clinical_scan_links.tsv` from [S10](../s10_xcpd_integrated_qc/README.md).

```sh
python pipeline/s9a_validate_clinical/run.py \
  --included /ABS/final_included_runs.tsv --scan-links /ABS/clinical_scan_links.tsv \
  --dxsum "$DATA/LONI_download/clindata/DXSUM.csv" \
  --ptdemog "$DATA/LONI_download/clindata/PTDEMOG.csv" \
  --max-dx-days 28 --dx-direction nearest --output-dir "$DATA/qc/step9a"
```

Nearest-date ties and missing evidence remain explicit. A dementia label alone is not confirmed AD etiology.

## Evidence and limits

Sources: [ADNI imaging–diagnosis answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2401); [ADNI diagnosis-code answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=1756); [ADNI dementia-etiology answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=209). The [Stage 9.A evidence record](../../06_docs/stage_evidence.md#stage-9-a) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
