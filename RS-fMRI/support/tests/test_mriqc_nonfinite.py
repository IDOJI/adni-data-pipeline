"""Exercise the real R QC decision/export functions with synthetic cohort rows.

Threshold estimation is replaced with an explicit fixture so these tests isolate
nonfinite inputs and invalid-fit handling without fitting a small fake cohort.
"""
import csv
import io
from pathlib import Path
import shutil
import subprocess

import pytest

LAB = Path(__file__).resolve().parents[2]
R_SOURCE = LAB / "pipeline/s6_mriqc/adni_outlier_pipeline.R"


@pytest.fixture(scope="module")
def rscript():
    binary = shutil.which("Rscript")
    if not binary:
        pytest.skip("Rscript is required for the MRIQC R decision tests")
    available = subprocess.run(
        [binary, "--vanilla", "-e",
         'quit(status=if(all(vapply(c("dplyr","tidyr","purrr"), requireNamespace, logical(1), quietly=TRUE))) 0 else 1)'],
        capture_output=True, text=True,
    )
    if available.returncode:
        pytest.skip("R dplyr/tidyr/purrr are required for the MRIQC decision tests")
    return binary


R_TEST = r'''
suppressPackageStartupMessages(library(dplyr))
suppressPackageStartupMessages(library(tidyr))
suppressPackageStartupMessages(library(purrr))
args <- commandArgs(trailingOnly=TRUE)
needed <- c("prep_rain", "qc_any_outlier", "add_qc_flags", "rename_metrics", "finalize_qc_table")
for (expr in parse(args[[1]])) {
  if (is.call(expr) && identical(expr[[1]], as.name("<-")) &&
      is.symbol(expr[[2]]) && as.character(expr[[2]]) %in% needed) eval(expr)
}
threshold <- switch(args[[2]], finite=4, missing=NA_real_, infinite=Inf)
compute_thresh <- function(x, tail) list(val=threshold, method="fixed_test_threshold")
ids <- c("valid", "inf", "negative_inf", "na", "nan", "failed", "failed_incomplete", "missing_t1")
base <- tibble(participant_id=paste0("synthetic_", ids), ses_id="ses-test")
tables <- list()
groups <- c("bold_upper", "bold_lower", "t1_upper", "t1_lower")
for (group in groups) {
  data <- base %>% mutate(aqi=1, efc=1)
  if (group == "bold_upper") {
    data$aqi <- c(1, Inf, -Inf, NA, NaN, 5, 5, 1)
    data$efc[7] <- NA
  }
  if (startsWith(group, "t1")) data <- data %>% filter(participant_id != "synthetic_missing_t1")
  prep <- prep_rain(data, c("aqi", "efc"), tail="upper")
  tables[[group]] <- rename_metrics(add_qc_flags(prep, group), group, c("participant_id", "ses_id"))
}
joined <- reduce(tables, function(x,y) full_join(x,y,by=c("participant_id","ses_id")))
output <- finalize_qc_table(joined)
write.table(output, stdout(), sep="\t", row.names=FALSE, quote=FALSE, na="NA")
'''


def run_flags(rscript, mode):
    run = subprocess.run([rscript, "--vanilla", "-", str(R_SOURCE), mode],
                         input=R_TEST, capture_output=True, text=True, check=True)
    return {row["sub"].removeprefix("synthetic_"): row
            for row in csv.DictReader(io.StringIO(run.stdout), delimiter="\t")}


def test_nonfinite_metrics_remain_in_export_without_passing(rscript):
    rows = run_flags(rscript, "finite")
    assert len(rows) == 8
    assert rows["valid"]["excluded_any"] == "FALSE"
    assert rows["valid"]["qc_status_any"] == "included"
    assert rows["valid"]["qc_metrics_complete"] == "TRUE"
    for case in ("inf", "negative_inf", "na", "nan", "missing_t1"):
        assert rows[case]["excluded_any"] == "NA"
        assert rows[case]["qc_status_any"] == "missing"
        assert rows[case]["qc_metrics_complete"] == "FALSE"
        assert rows[case]["qc_missing_metrics"]
    for case in ("failed", "failed_incomplete"):
        assert rows[case]["excluded_any"] == "TRUE"
        assert rows[case]["qc_status_any"] == "excluded"
    assert rows["failed_incomplete"]["qc_metrics_complete"] == "FALSE"


@pytest.mark.parametrize("mode", ["missing", "infinite"])
def test_invalid_thresholds_cannot_produce_passing_flags(rscript, mode):
    rows = run_flags(rscript, mode)
    assert len(rows) == 8
    for row in rows.values():
        assert row["excluded_any"] == "NA"
        assert row["qc_status_any"] == "missing"
        assert row["qc_metrics_complete"] == "FALSE"
        assert row["qc_invalid_thresholds"]
