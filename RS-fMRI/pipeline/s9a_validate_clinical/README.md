# Stage 9.A — Clinical validation

**What:** Check diagnoses near each actual scan date, demographic consistency and diagnostic ties.

**Output:** `clinical_validation.tsv`, demographic/source-row audits and `artifact.json`.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Point `--included` and `--scan-links` at the tables from the same reviewed S10 finalization. In the example they are available under `DATA/review/`. Set `--dxsum` and `--ptdemog` to the original tables for the chosen data freeze. `--max-dx-days 28 --dx-direction nearest` defines the study's matching rule.

Use matching `final_included_runs.tsv` and `clinical_scan_links.tsv` from [S10](../s10_xcpd_integrated_qc/README.md).

```sh
python pipeline/s9a_validate_clinical/run.py \
  --included "$DATA/review/final_included_runs.tsv" --scan-links "$DATA/review/clinical_scan_links.tsv" \
  --dxsum "$DATA/LONI_download/clindata/DXSUM.csv" \
  --ptdemog "$DATA/LONI_download/clindata/PTDEMOG.csv" \
  --max-dx-days 28 --dx-direction nearest --output-dir "$RESULTS/qc/step9a"
```

Nearest-date ties and missing evidence remain explicit. A dementia label alone is not confirmed AD etiology.
