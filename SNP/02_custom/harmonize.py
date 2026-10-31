#!/usr/bin/env python3
"""Audit PLINK BIM/FRQ pairs before a conservative multi-array intersection merge."""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile

REPO = Path(__file__).resolve().parents[2]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path, columns=None):
    with Path(path).open() as stream:
        if columns is None:
            header = next(stream, "").split()
            if not {"CHR", "SNP", "A1", "A2", "MAF", "NCHROBS"}.issubset(header):
                raise ValueError(f"Invalid PLINK frequency header: {path}")
            columns = header
        for line_number, line in enumerate(stream, 2 if columns[0] == "CHR" else 1):
            values = line.split()
            if not values:
                continue
            if len(values) != len(columns):
                raise ValueError(f"Invalid row at {path}:{line_number}")
            yield dict(zip(columns, values))


def load_batch(db, label, prefix):
    db.execute("CREATE TABLE current (id TEXT PRIMARY KEY, chrom TEXT, pos INTEGER, a1 TEXT, a2 TEXT, maf TEXT)")
    for row in rows(str(prefix) + ".bim", ["chrom", "id", "cm", "pos", "a1", "a2"]):
        if int(row["pos"]) < 1 or row["chrom"] not in {str(i) for i in range(1, 23)}:
            raise ValueError("This helper accepts mapped autosomal variants only")
        if row["a1"] not in "ACGT" or row["a2"] not in "ACGT" or len(row["a1"]) != 1 or len(row["a2"]) != 1 or row["a1"] == row["a2"]:
            raise ValueError("Expected biallelic A/C/G/T SNPs")
        db.execute("INSERT INTO current VALUES (?, ?, ?, ?, ?, NULL)",
                   (row["id"], row["chrom"], int(row["pos"]), row["a1"], row["a2"]))
    for row in rows(str(prefix) + ".frq"):
        maf = Decimal(row["MAF"])
        if not maf.is_finite() or not Decimal(0) <= maf <= Decimal("0.5") or int(row["NCHROBS"]) < 1:
            raise ValueError(f"Invalid frequency for {row['SNP']} in {label}")
        cursor = db.execute("UPDATE current SET maf=? WHERE id=? AND chrom=? AND a1=? AND a2=? AND maf IS NULL",
                            (str(maf), row["SNP"], row["CHR"], row["A1"], row["A2"]))
        if cursor.rowcount != 1:
            raise ValueError(f"Duplicate FRQ row or BIM/FRQ disagreement for {row['SNP']} in {label}")
    if db.execute("SELECT count(*) FROM current WHERE maf IS NULL").fetchone()[0]:
        raise ValueError(f"Missing frequency rows in {label}")
    if not db.execute("SELECT count(*) FROM current").fetchone()[0]:
        raise ValueError(f"Empty variant table in {label}")


def audit(batches, output_dir):
    if len(batches) < 2 or len({label for label, _ in batches}) != len(batches):
        raise ValueError("Supply at least two uniquely labelled batches")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", label) for label, _ in batches):
        raise ValueError("Batch labels must be simple labels")
    output = Path(output_dir).resolve()
    if output == REPO or REPO in output.parents or output in REPO.parents:
        raise ValueError("Write genotype-derived results outside the repository and its ancestors")
    # An existing directory may contain results from an earlier run. Never overwrite it.
    output.mkdir(parents=True, exist_ok=False)
    counts = {"keep": 0, "not_shared": 0, "allele_or_position_mismatch": 0, "maf_difference": 0}
    with tempfile.TemporaryDirectory(prefix="harmonize-", dir=output) as tmp:
        with closing(sqlite3.connect(str(Path(tmp) / "variants.sqlite"))) as db:
            db.execute("CREATE TABLE variants (id TEXT PRIMARY KEY, chrom TEXT, pos INTEGER, a1 TEXT, a2 TEXT, minmaf TEXT, maxmaf TEXT, n INTEGER, mismatch INTEGER)")
            for label, prefix in batches:
                load_batch(db, label, prefix)
                # Decimal comparison preserves the exact 0.10 boundary from the reported FRQ precision.
                db.create_function("dmin", 2, lambda a, b: str(min(Decimal(a), Decimal(b))))
                db.create_function("dmax", 2, lambda a, b: str(max(Decimal(a), Decimal(b))))
                db.execute("""INSERT INTO variants SELECT id, chrom, pos, a1, a2, maf, maf, 1, 0 FROM current WHERE true
                           ON CONFLICT(id) DO UPDATE SET
                           minmaf=dmin(variants.minmaf, excluded.minmaf),
                           maxmaf=dmax(variants.maxmaf, excluded.maxmaf), n=variants.n+1,
                           mismatch=variants.mismatch OR variants.chrom!=excluded.chrom OR variants.pos!=excluded.pos
                           OR variants.a1!=excluded.a1 OR variants.a2!=excluded.a2""")
                db.execute("DROP TABLE current")
                db.commit()
            with (output / "audit.tsv").open("w") as report, (output / "keep.snps").open("w") as keep:
                writer = csv.writer(report, delimiter="\t", lineterminator="\n")
                writer.writerow(["variant_id", "batches_present", "maf_range", "decision"])
                for variant, n, mismatch, low, high in db.execute("SELECT id, n, mismatch, minmaf, maxmaf FROM variants ORDER BY id"):
                    difference = Decimal(high) - Decimal(low)
                    reason = ("not_shared" if n != len(batches) else "allele_or_position_mismatch" if mismatch
                              else "maf_difference" if difference > Decimal("0.10") else "keep")
                    counts[reason] += 1
                    writer.writerow([variant, n, str(difference), reason])
                    if reason == "keep":
                        keep.write(variant + "\n")
    result = {"status": "variant_audit_only", "counts": counts,
              "policy": "shared_autosomal_snps_same_position_A1_A2_maf_range_le_0.10",
              "reference_alleles_verified": False, "sample_duplicates_resolved": False,
              "frequency_precision": "as_reported_in_input_frq",
              "batches": [{"label": label, "prefix": str(prefix),
                           "sha256": {suffix: sha256(str(prefix) + suffix) for suffix in (".bim", ".frq")}}
                          for label, prefix in batches]}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    if counts["keep"] == 0:
        raise ValueError("No variants passed; audit saved, merge must not proceed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", nargs=2, action="append", metavar=("LABEL", "PLINK_PREFIX"), required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.batch, args.output_dir), indent=2))
    except (ValueError, InvalidOperation, OSError, sqlite3.Error) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
