# 4 · 📊 Harmonize functional connectivity

**Bring** the final imaging and clinical results plus `review/scanners.tsv`. This tab-separated file identifies the physical scanner for each EPI image and records where you verified it. Use the [scanner table example](../../pipeline/s14_fc_harmonization/README.md#prepare-private-inputs). The model adjusts the **4S256 connectivity edges** across scanners and retains age, sex and diagnosis as covariates. This profile uses one eligible scan per person.

```sh
python stages/04-harmonization/run.py "$STUDY" audit
```

**Open** `04-harmonization/audit/decisions.tsv` and `batch_design.tsv`. Check who was selected and whether scanner groups cover comparable ages and diagnoses. This profile requires at least two batches and at least five selected participants per batch. When the audit passes and you have reviewed the design, run the fit.

```sh
python stages/04-harmonization/run.py "$STUDY" fit
```

**Open** `04-harmonization/fit/fc.npz` for original and adjusted connectivity, `edges.tsv` for ROI pairs, and `diagnostics.json` for before/after checks. **Already at this stage?** Supply the paths to your existing results. Use the same overrides for `fit`. For a revised analysis, use `--output "/path/to/new-result"` to keep both versions. [Method, papers and implementations](../../06_docs/fc_harmonization.md)

```sh
python stages/04-harmonization/run.py "$STUDY" audit \
  --final-qc "/path/to/finalizations/run/final_qc_master.tsv" \
  --inclusion "/path/to/step9b" --scanners "/path/to/scanners.tsv"
```

[Study setup](../setup.md) · [All stages](../../README.md)
