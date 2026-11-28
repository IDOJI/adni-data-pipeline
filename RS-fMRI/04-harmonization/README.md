# 4 · 📊 Adjust for scanner differences

Use ComBat to adjust 4S256 connectivity measurements for scanner differences while accounting for age, sex and diagnosis.

**Prepare.** Use the final imaging and eligibility tables from step 3. In `review/scanners.tsv`, record which physical scanner took each resting scan and where you checked that information. [Scanner table example](fc_harmonization/README.md#prepare-private-inputs)

**Check the groups first.**

Use the same study folder you used in step 1.

```sh
cd "/absolute/path/to/adni-data-pipeline/RS-fMRI"
source .venv/bin/activate
export STUDY="/absolute/path/to/my ADNI study"

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

[Back to all four steps](../README.md)
