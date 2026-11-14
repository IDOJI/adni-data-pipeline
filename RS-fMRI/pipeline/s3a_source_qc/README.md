# Stage 3.A — Source QC

**What:** Check image IDs, dates, UIDs, deletion records and source QC/NFQ grades. Missing evidence stays pending.

**Output:** `image_qc.tsv`, source audits and `artifact.json` in the output directory.

## Run

From `RS-fMRI/`, after [setup](../../06_docs/installation.md). Replace example paths and IDs with your inputs.

```sh
python pipeline/s3a_source_qc/run.py \
  --mriqc-table "$DATA/LONI_download/clindata/MRIQC.csv" \
  --adni3-qc "$DATA/LONI_download/clindata/MAYO_ADNI3.csv" \
  --go2-qc "$DATA/LONI_download/clindata/MAYO_GO2.csv" \
  --deleted-scans "$DATA/LONI_download/clindata/DELMRSCANS.csv" \
  --nfq GO2_3="$DATA/LONI_download/clindata/NFQ.csv" \
  --output-dir "$DATA/qc/step3a"
```

`MRIQC.csv` here is an ADNI Study File, not MRIQC software output. Use original column names and a new output directory.
