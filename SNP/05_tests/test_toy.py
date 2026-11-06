"""Public fixture reproducibility and result-comparison failures."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


toy = module("public_toy", ROOT / "07_toy/run.py")
generator = module("generate_public_toy", ROOT / "07_toy/generate_inputs.py")


class PublicToyTests(unittest.TestCase):
    def test_attached_inputs_are_reproducible_from_generator(self):
        expected = json.loads((ROOT / "07_toy/inputs.sha256.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(generator.make(Path(temp) / "inputs"), expected)
        for name, sha in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / "07_toy/inputs" / name).read_bytes()).hexdigest(), sha)

    def test_bed_decoding_and_changed_genotypes(self):
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp) / "known"
            prefix.with_suffix(".fam").write_text("F A 0 0 1 1\nF B 0 0 2 1\nF C 0 0 1 1\nF D 0 0 2 1\n")
            prefix.with_suffix(".bim").write_text("1 synthetic 0 10 C A\n")
            prefix.with_suffix(".bed").write_bytes(b"\x6c\x1b\x01\xe4")
            _, variants = toy.dataset(prefix)
            self.assertEqual(variants["synthetic"]["calls"], [2, None, 1, 0])
            original = toy.signature(prefix)
            prefix.with_suffix(".bed").write_bytes(b"\x6c\x1b\x01\xe7")
            self.assertNotEqual(original["sha256"], toy.signature(prefix)["sha256"])

    def example(self):
        return {"data": {"sha256": "fixed"}, "pca": {"samples": [["F", "A"], ["F", "B"]],
                "values": [2., 1.], "vectors": [[.6, .8], [.8, -.6]]}}

    def test_pca_sign_reversal_is_allowed(self):
        expected = self.example()
        actual = copy.deepcopy(expected)
        actual["pca"]["vectors"] = [[-.6, .8], [-.8, -.6]]
        self.assertEqual(toy.compare(actual, expected)["status"], "PASS")

    def test_altered_missing_or_nonfinite_results_fail(self):
        expected = self.example()
        changes = []
        altered = copy.deepcopy(expected); altered["data"]["sha256"] = "changed"; changes.append(altered)
        altered = copy.deepcopy(expected); altered["pca"]["vectors"] = [[.6, .8]]; changes.append(altered)
        altered = copy.deepcopy(expected); altered["pca"]["vectors"][0][0] = float("nan"); changes.append(altered)
        altered = copy.deepcopy(expected); altered["pca"]["values"][0] = 3.; changes.append(altered)
        altered = copy.deepcopy(expected); del altered["data"]; changes.append(altered)
        for actual in changes:
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                toy.compare(actual, expected)

    def test_stage_order_and_existing_outputs_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            demo = toy.Demo(temp)
            with self.assertRaises(ValueError):
                demo.stage("post1")
            self.assertFalse((Path(temp) / "post1").exists())
            demo.stage("prepare")
            with self.assertRaises(FileExistsError):
                demo.stage("prepare")


if __name__ == "__main__":
    unittest.main()
