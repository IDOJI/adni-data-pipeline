"""Synthetic input validation, scientific boundaries and source compatibility."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


workflow = module("workflow", ROOT / "04_workflow/snp.py")
harmonize = module("harmonize", ROOT / "02_custom/harmonize.py")


class SourceAndWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.config = workflow.read_config(ROOT / "03_config/pipeline.example.json")

    def test_source_pin_and_shell_interfaces(self):
        self.assertEqual(workflow.doctor()["source_pin"], "pass")
        for name in ("gwas_qc_preimputation.sh", "gwas_qc_postimputation_part1.sh", "gwas_qc_postimputation_part2.sh"):
            subprocess.run(["bash", "-n", str(workflow.UPSTREAM / name)], check=True)
            result = subprocess.run(["bash", str(workflow.UPSTREAM / name), "-h"],
                                    capture_output=True, text=True, check=True)
            self.assertIn("Usage:", result.stdout)

    def test_plan_preserves_source_and_requires_explicit_part2_handoff(self):
        plan = workflow.plan(self.config)
        self.assertFalse(plan["executed"])
        self.assertEqual(len(plan["stages"]), 8)
        for stage in plan["stages"]:
            self.assertIn(f"{workflow.UPSTREAM}:/scripts/GWAS_QC:ro", stage["argv"])
            self.assertNotIn("-z", stage["argv"])
            self.assertIn("-c", stage["argv"])
        batch = self.config["batches"][0]
        batch["cleaned_genotypes"] = "reviewed/human610_genotyped"
        batch["ancestry_subsets"] = [{"label": "EUR", "keep_file": "reviewed/human610_EUR.keep"}]
        commands = workflow.plan(self.config)["stages"]
        part2 = next(c for c in commands if c["stage"] == "postimputation2:EUR")
        self.assertIn("-p", part2["argv"])
        self.assertIn("/input/reviewed/human610_genotyped", part2["argv"])

    def test_upstream_unquoted_path_and_repository_path_rejected(self):
        for value in ("a b", "../raw/data", "/raw/data", "a;touch-x", "$(cmd)"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                workflow.relative(value)
        with self.assertRaises(ValueError):
            workflow.external(str(ROOT / "private-data"))

    def test_output_collisions_and_raw_input_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            first = self.config["batches"][0]
            second = self.config["batches"][1]
            for conflicting in (first["preimputation_stem"], first["input_bfile"]):
                second["preimputation_stem"] = conflicting
                path.write_text(json.dumps(self.config))
                with self.subTest(conflicting=conflicting), self.assertRaises(ValueError):
                    workflow.read_config(path)

    def records(self, path):
        paths = []
        for batch in self.config["batches"]:
            record = {"batch_id": batch["id"], "job_id": "SYNTHETIC-JOB", "panel": "r3",
                      "genome_build": "GRCh38", "server_version": "synthetic-2.0",
                      "phasing": "Eagle v2.4.1", "imputation_engine": "Minimac4 v4.1.6",
                      "completed_at": "2026-11-01T00:00:00+09:00", "report_sha256": "a" * 64}
            output = path / (batch["id"] + ".json")
            output.write_text(json.dumps(record))
            paths.append(output)
        return paths

    def test_missing_batches_mixed_panels_and_software_changes_rejected(self):
        expected = [b["id"] for b in self.config["batches"]]
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.records(Path(tmp))
            self.assertEqual(workflow.check_jobs(paths, expected)["batches"], 4)
            with self.assertRaises(ValueError):
                workflow.check_jobs(paths[:-1], expected)
            original = json.loads(paths[0].read_text())
            for changes in ({"panel": "r2"}, {"phasing": "Eagle v2.4"}, {"server_version": None},
                            {"genome_build": "GRCh37"}, {"report_sha256": "not-a-checksum"}):
                record = {**original, **changes}
                paths[0].write_text(json.dumps(record))
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    workflow.check_jobs(paths, expected)


class VariantAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def batch(self, label, variants):
        """Records: ID, position, A1, A2, MAF; no real participant data."""
        prefix = self.root / label
        Path(str(prefix) + ".bim").write_text("".join(f"1 {v} 0 {pos} {a1} {a2}\n" for v, pos, a1, a2, maf in variants))
        Path(str(prefix) + ".frq").write_text("CHR SNP A1 A2 MAF NCHROBS\n" + "".join(
            f"1 {v} {a1} {a2} {maf} 200\n" for v, pos, a1, a2, maf in variants))
        return label, str(prefix)

    def test_exact_boundary_and_all_batch_pairwise_maf_range(self):
        batches = [self.batch(label, [("boundary", 10, "A", "C", value),
                                      ("range_fail", 20, "G", "T", other)])
                   for label, value, other in (("a", ".20", ".10"), ("b", ".30", ".18"), ("c", ".25", ".21"))]
        result = harmonize.audit(batches, self.root / "out")
        self.assertEqual(result["counts"]["keep"], 1)
        self.assertEqual(result["counts"]["maf_difference"], 1)
        self.assertEqual((self.root / "out/keep.snps").read_text(), "boundary\n")
        self.assertFalse(result["reference_alleles_verified"])
        self.assertEqual(result["batches"][0]["sha256"][".bim"], harmonize.sha256(batches[0][1] + ".bim"))
        self.assertEqual(list((self.root / "out").glob("harmonize-*")), [])

    def test_swaps_second_alleles_positions_and_absent_variants(self):
        a = [("pass", 1, "A", "C", ".1"), ("swap", 2, "A", "C", ".2"),
             ("a2", 3, "A", "C", ".2"), ("pos", 4, "A", "C", ".2"),
             ("absent", 5, "A", "C", ".2")]
        b = [("pass", 1, "A", "C", ".1"), ("swap", 2, "C", "A", ".2"),
             ("a2", 3, "A", "G", ".2"), ("pos", 40, "A", "C", ".2")]
        result = harmonize.audit([self.batch("a", a), self.batch("b", b)], self.root / "out")
        self.assertEqual(result["counts"], {"keep": 1, "not_shared": 1, "allele_or_position_mismatch": 3, "maf_difference": 0})

    def test_duplicate_variant_and_invalid_frequency_rejected(self):
        base = [("v1", 1, "A", "C", ".1")]
        for label, records in (("duplicate", base + base), ("nan", [("v1", 1, "A", "C", "NaN")]),
                               ("high", [("v1", 1, "A", "C", ".8")])):
            with self.subTest(label=label), self.assertRaises((ValueError, sqlite3.IntegrityError)):
                harmonize.audit([self.batch("base", base), self.batch(label, records)], self.root / label / "out")

    def test_mismatched_frequency_orientation_and_missing_rows_rejected(self):
        base = [("v1", 1, "A", "C", ".1")]
        a = self.batch("a", base)
        b = self.batch("b", base)
        for label, contents in (("wrong", "CHR SNP A1 A2 MAF NCHROBS\n1 v1 C A .1 200\n"),
                                ("missing", "CHR SNP A1 A2 MAF NCHROBS\n")):
            Path(b[1] + ".frq").write_text(contents)
            with self.subTest(label=label), self.assertRaises(ValueError):
                harmonize.audit([a, b], self.root / label)

    def test_empty_intersection_fails_and_existing_results_are_preserved(self):
        a = self.batch("a", [("v1", 1, "A", "C", ".1")])
        b = self.batch("b", [("v2", 2, "A", "C", ".1")])
        output = self.root / "out"
        with self.assertRaises(ValueError):
            harmonize.audit([a, b], output)
        summary = (output / "summary.json").read_text()
        with self.assertRaises(FileExistsError):
            harmonize.audit([a, b], output)
        self.assertEqual((output / "summary.json").read_text(), summary)

    def test_single_batch_and_x_chromosome_are_rejected(self):
        a = self.batch("a", [("v1", 1, "A", "C", ".1")])
        with self.assertRaises(ValueError):
            harmonize.audit([a], self.root / "single")
        b = self.batch("b", [("v1", 1, "A", "C", ".1")])
        Path(b[1] + ".bim").write_text("23 v1 0 1 A C\n")
        with self.assertRaises(ValueError):
            harmonize.audit([a, b], self.root / "x")


if __name__ == "__main__":
    unittest.main()
