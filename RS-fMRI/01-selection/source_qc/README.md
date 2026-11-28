# Stage 3.A — Source QC

**What:** Check image IDs, dates, UIDs, deletion records and source QC/NFQ grades. Missing evidence stays pending.

**Output:** `image_qc.tsv`, source audits and `artifact.json` in the output directory.

The image table also retains the original MRIQC series type, description, manufacturer, field strength and model for the Search comparison. Rebuild older 3.A artifacts before 3.B. A uniquely matched NFQ row with no OVERALLQC column, a blank grade, an unrecognized supplied value and no unique match have distinct reason codes. None is a documented pass.

## Run

From `RS-fMRI/`, after [setup](../../support/docs/installation.md). `--mriqc-table` is the original ADNI Study File. Set the remaining file arguments to the matching study phase, deletion log and NFQ download for your data freeze. In `--nfq GO2_3=...`, the text before `=` labels the source; the filename after it is the table to read.

```sh
python 01-selection/source_qc/run.py \
  --mriqc-table "$DATA/LONI_download/clindata/MRIQC.csv" \
  --adni3-qc "$DATA/LONI_download/clindata/MAYO_ADNI3.csv" \
  --go2-qc "$DATA/LONI_download/clindata/MAYO_GO2.csv" \
  --deleted-scans "$DATA/LONI_download/clindata/DELMRSCANS.csv" \
  --nfq GO2_3="$DATA/LONI_download/clindata/NFQ.csv" \
  --output-dir "$RESULTS/qc/step3a"
```

`MRIQC.csv` here is an ADNI Study File, not MRIQC software output. Use original column names and a new output directory.

## Evidence and limits

Sources: [ADNI repeated T1 and grade answers](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=89); [ADNI chosen-series answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=454); [ADNI NFQ/slice-order answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=1822); [ADNI4 ARC quality answer](https://adni.loni.usc.edu/support/experts-knowledge-base/question/?QID=2541). The [Stage 3.A evidence record](../../support/docs/stage_evidence.md#stage-3-a) identifies the relevant answer/section and separates direct evidence from project policy and engineering controls. These references do not certify the current configuration or any individual image as analysis-ready.
