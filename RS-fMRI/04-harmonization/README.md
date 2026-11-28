# 4 · 📊 Adjust for scanner differences

Different scanners can measure the same connection differently. This step uses ComBat to adjust the connection measurements while accounting for age, sex and diagnosis.

**Prepare.** Use the final imaging and eligibility tables from step 3. In `review/scanners.tsv`, record which physical scanner took each resting scan and where you checked that information. [Scanner table example](fc_harmonization/README.md#prepare-private-inputs)

**Check the groups first.**

```sh
python 04-harmonization/run.py "$STUDY" audit
```

Open `04-harmonization/audit/decisions.tsv` to see who was selected. Open `batch_design.tsv` beside it to compare ages and diagnoses across scanners. This analysis uses one scan per person and needs at least two scanner groups, each with five or more selected people.

**Run the adjustment** after the audit passes and you have reviewed the groups.

```sh
python 04-harmonization/run.py "$STUDY" fit
```

**Find the results** in `04-harmonization/fit/` in your study folder.

| File | What it contains |
|---|---|
| `fc.npz` | Original and adjusted connection measurements |
| `edges.tsv` | The two brain regions for each connection |
| `diagnostics.json` | Checks comparing the measurements before and after adjustment |

<details>
<summary>Existing results, model details and references</summary>

For existing XCP-D results with final QC and eligibility records, supply their paths. Use the same paths for `fit`. To keep an earlier analysis, use `--output "/path/to/new-result"`.

```sh
python 04-harmonization/run.py "$STUDY" audit \
  --final-qc "/path/to/finalizations/run/final_qc_master.tsv" \
  --inclusion "/path/to/step9b" --scanners "/path/to/scanners.tsv"
```

This profile adjusts 4S256 connectivity edges. [Model, papers and software](docs/fc_harmonization.md) · [Implementation](fc_harmonization/README.md) · [Example settings](config/)

</details>

[Back to all four steps](../README.md)
