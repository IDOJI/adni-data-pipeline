#!/usr/bin/env python3
"""Run the public SNP teaching workflow and compare its results with a fixed reference."""
from __future__ import annotations

import argparse
import collections
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent
BATCHES = ("a", "b")
STAGES = ("prepare", "pre", "imputation", "post1", "post2", "deduplicate", "harmonize", "merge", "final", "x")
TOOLS = {
    "Darwin": ("https://s3.amazonaws.com/plink1-assets/plink_mac_20260927.zip", "927ecadbefb3e0ceefbe4978d71bf63566e9ea422d6595c2ee23a83ad76eeb62"),
    "Linux": ("https://s3.amazonaws.com/plink1-assets/plink_linux_x86_64_20260927.zip", "ee4d8616dc64c04ed395e81a7bb04f9b3d92e4bf23d12a8b6233b19f7227eccd"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def read_json(path):
    return json.loads(path.read_text())


def external(value):
    path = Path(value).expanduser().resolve()
    if path == REPO or REPO in path.parents or path in REPO.parents:
        raise ValueError("Choose a run directory outside the repository and its ancestors")
    return path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def whitespace(path):
    with path.open() as stream:
        keys = next(stream).split()
        return [dict(zip(keys, line.split())) for line in stream if line.strip()]


def dataset(prefix):
    """Decode SNP-major BED for path-independent, allele-aware genotype comparison."""
    samples = [line.split() for line in Path(str(prefix) + ".fam").read_text().splitlines()]
    variants = [line.split() for line in Path(str(prefix) + ".bim").read_text().splitlines()]
    content = Path(str(prefix) + ".bed").read_bytes()
    width = (len(samples) + 3) // 4
    if content[:3] != b"\x6c\x1b\x01" or len(content) != 3 + width * len(variants):
        raise ValueError(f"Invalid BED: {prefix}")
    ids = [(s[0], s[1], s[4]) for s in samples]
    if len(set((s[0], s[1]) for s in ids)) != len(ids):
        raise ValueError("Duplicate sample IDs")
    records = {}
    for index, variant in enumerate(variants):
        calls = []
        for j in range(len(samples)):
            code = (content[3 + index * width + j // 4] >> (2 * (j % 4))) & 3
            calls.append((2, None, 1, 0)[code])
        if variant[1] in records:
            raise ValueError("Duplicate variant IDs")
        records[variant[1]] = {"chrom": variant[0], "pos": int(variant[3]), "a1": variant[4], "a2": variant[5], "calls": calls}
    return ids, records


def signature(prefix):
    samples, variants = dataset(prefix)
    order = sorted(range(len(samples)), key=lambda i: samples[i])
    canonical = {"samples": [samples[i] for i in order], "variants": [
        [name, row["chrom"], row["pos"], row["a1"], row["a2"], [row["calls"][i] for i in order]]
        for name, row in sorted(variants.items())]}
    return {"samples": len(samples), "variants": len(variants),
            "sha256": digest(json.dumps(canonical, separators=(",", ":")).encode())}


class Demo:
    def __init__(self, run):
        self.run = external(run)
        self.plink = self.run / "tools/plink"
        self.out = None

    def call(self, *args):
        if not self.plink.is_file():
            raise ValueError("Run setup first")
        command = [str(self.plink), "--threads", "1", "--memory", "512", "--seed", "20261106",
                   "--allow-no-sex", "--keep-allele-order", *map(str, args)]
        with (self.out / "commands.log").open("a") as stream:
            stream.write(json.dumps(command) + "\n")
            stream.flush()
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)

    def setup(self, archive=None):
        system = platform.system()
        if system not in TOOLS or (system == "Linux" and platform.machine() not in ("x86_64", "AMD64")):
            raise ValueError("Pinned builds support Linux x86_64 and macOS; Apple Silicon requires Rosetta")
        target = self.run / "tools"
        target.mkdir(parents=True, exist_ok=False)
        url, checksum = TOOLS[system]
        if archive:
            data = Path(archive).read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
        if digest(data) != checksum:
            raise ValueError("PLINK archive checksum differs from the pinned download")
        package = target / "plink.zip"
        package.write_bytes(data)
        with zipfile.ZipFile(package) as archive_file:
            self.plink.write_bytes(archive_file.read("plink"))
        self.plink.chmod(0o755)
        version = subprocess.check_output([str(self.plink), "--version"], text=True).strip()
        if "v1.9.0" not in version or "27 Sep 2026" not in version:
            raise ValueError("Unexpected PLINK release")
        write_json(target / "version.json", {"url": url, "archive_sha256": checksum, "version": version})
        print(version)

    def stage(self, name):
        index = STAGES.index(name)
        if index and not (self.run / STAGES[index - 1] / "complete.json").is_file():
            raise ValueError(f"Complete {STAGES[index - 1]} first")
        self.out = self.run / name
        self.out.mkdir(parents=True, exist_ok=False)
        getattr(self, name)()
        write_json(self.out / "complete.json", {"stage": name, "mode": "synthetic_teaching_workflow"})
        print(f"PASS {name}: {self.out}")

    def prepare(self):
        for name, expected in read_json(HERE / "inputs.sha256.json").items():
            if digest((HERE / "inputs" / name).read_bytes()) != expected:
                raise ValueError("Bundled input checksum mismatch: " + name)
        raw = read_json(HERE / "inputs/genotypes.json")["batches"]
        refs = {}
        for batch, block in raw.items():
            prefix = self.out / batch
            Path(str(prefix) + ".map").write_text("".join(f"{v['chrom']} {v['id']} 0 {v['pos']}\n" for v in block["variants"]))
            lines = []
            for sample, calls in zip(block["samples"], block["calls"]):
                fields = [sample["id"], sample["id"], "0", "0", str(sample["sex"]), "1"]
                for variant, value in zip(block["variants"], calls):
                    refs[variant["id"]] = variant["ref"]
                    fields += ["0", "0"] if value is None else [variant["ref"], variant["ref"]] if value == 0 else [variant["ref"], variant["alt"]] if value == 1 else [variant["alt"], variant["alt"]]
                lines.append(" ".join(fields))
            Path(str(prefix) + ".ped").write_text("\n".join(lines) + "\n")
        (self.out / "ref-alleles.txt").write_text("".join(f"{key} {value}\n" for key, value in sorted(refs.items())))

    def pre(self):
        for batch in BATCHES:
            base = self.out / batch
            self.call("--file", self.run / "prepare" / batch, "--a2-allele", self.run / "prepare/ref-alleles.txt", "2", "1", "--make-bed", "--out", str(base) + ".raw")
            self.call("--bfile", str(base) + ".raw", "--geno", ".05", "--maf", ".01", "--make-bed", "--out", str(base) + ".variants")
            self.call("--bfile", str(base) + ".variants", "--mind", ".01", "--make-bed", "--out", str(base) + ".samples")
            self.call("--bfile", str(base) + ".samples", "--check-sex", "--out", str(base) + ".sex")
            bad = [row for row in whitespace(Path(str(base) + ".sex.sexcheck")) if row["STATUS"] != "OK"]
            remove = Path(str(base) + ".sex.remove")
            remove.write_text("".join(f"{r['FID']} {r['IID']}\n" for r in bad))
            self.call("--bfile", str(base) + ".samples", "--remove", remove, "--make-bed", "--out", str(base) + ".sexpass")
            self.call("--bfile", str(base) + ".sexpass", "--autosome", "--hwe", "1e-6", "--make-bed", "--out", str(base) + ".aut")
            self.call("--bfile", str(base) + ".aut", "--het", "--genome", "full", "unbounded", "nudge", "--min", ".20", "--out", str(base) + ".review")
            self.call("--bfile", str(base) + ".aut", "--recode", "vcf-iid", "--output-chr", "chrM", "--out", str(base) + ".upload")
            samples, _ = dataset(Path(str(base) + ".sexpass"))
            pheno = Path(str(base) + ".sex.pheno")
            pheno.write_text("".join(f"{s[0]} {s[1]} {s[2]}\n" for s in samples))
            self.call("--bfile", str(base) + ".sexpass", "--chr", "X", "--pheno", pheno, "--test-missing", "--out", str(base) + ".xdiff")
            drop = [r["SNP"] for r in whitespace(Path(str(base) + ".xdiff.missing")) if Decimal(r["P"]) <= Decimal("1e-7")]
            Path(str(base) + ".xdiff.remove").write_text("".join(k + "\n" for k in drop))
            self.call("--bfile", str(base) + ".sexpass", "--chr", "X", "--exclude", str(base) + ".xdiff.remove", "--filter-females", "--hwe", "1e-6", "--write-snplist", "--out", str(base) + ".xfemale")
            self.call("--bfile", str(base) + ".sexpass", "--chr", "X", "--extract", str(base) + ".xfemale.snplist", "--make-bed", "--out", str(base) + ".x")

    def imputation(self):
        shutil.copyfile(HERE / "inputs/imputation-fixture.json", self.out / "fixture.json")
        write_json(self.out / "provenance.json", {"mode": "offline_synthetic_fixture", "topmed_job_submitted": False,
                                                  "ancestry": "One supplied DEMO group; no ancestry inference"})
        print("OFFLINE FIXTURE: no TOPMed job was submitted")

    def post1(self):
        blocks = read_json(self.run / "imputation/fixture.json")["batches"]
        for batch, block in blocks.items():
            observed, _ = dataset(self.run / f"pre/{batch}.aut")
            if {s[1] for s in observed} != {s["id"] for s in block["samples"]}:
                raise ValueError("Pre-QC sample set differs from the fixture handoff")
            counts = collections.Counter(v["id"] for v in block["variants"])
            excluded = {"low_r2": 0, "multiallelic": 0, "duplicate_id": 0}
            retained = []
            for i, variant in enumerate(block["variants"]):
                reason = "low_r2" if Decimal(variant["r2"]) < Decimal(".8") else "multiallelic" if "," in variant["alt"] else "duplicate_id" if counts[variant["id"]] > 1 else None
                if reason:
                    excluded[reason] += 1
                else:
                    retained.append(i)
            write_json(self.out / f"{batch}.excluded.json", excluded)
            for chrom, suffix in (("1", "aut"), ("X", "x")):
                selected = sorted((i for i in retained if block["variants"][i]["chrom"] == chrom), key=lambda i: block["variants"][i]["pos"])
                vcf = self.out / f"{batch}.{suffix}.vcf"
                with vcf.open("w") as stream:
                    stream.write("##fileformat=VCFv4.2\n##source=offline_synthetic_fixture\n##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Synthetic hard call\">\n")
                    stream.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + "\t".join(s["id"] for s in block["samples"]) + "\n")
                    for i in selected:
                        v = block["variants"][i]
                        values = []
                        for sample, row in zip(block["samples"], block["calls"]):
                            value = row[i]
                            values.append(str(value // 2) if chrom == "X" and sample["sex"] == 1 else ("0/0", "0/1", "1/1")[value])
                        stream.write("\t".join([chrom, str(v["pos"]), v["id"], v["ref"], v["alt"], ".", "PASS", ".", "GT", *values]) + "\n")
                self.call("--vcf", vcf, "--double-id", "--make-bed", "--out", self.out / f"{batch}.{suffix}")
            keep = "".join(f"{s['id']} {s['id']}\n" for s in block["samples"])
            (self.out / f"{batch}.DEMO.keep").write_text(keep)

    def restore(self, typed, imputed, output, keep=None):
        if keep:
            for source, suffix in ((typed, "typed"), (imputed, "imputed")):
                self.call("--bfile", source, "--keep", keep, "--make-bed", "--out", str(output) + "." + suffix)
            typed, imputed = Path(str(output) + ".typed"), Path(str(output) + ".imputed")
        _, variants = dataset(typed)
        ids = Path(str(output) + ".typed.ids")
        ids.write_text("".join(name + "\n" for name in sorted(variants)))
        self.call("--bfile", imputed, "--exclude", ids, "--make-bed", "--out", str(output) + ".nontyped")
        self.call("--bfile", typed, "--bmerge", str(output) + ".nontyped", "--make-bed", "--out", str(output) + ".restored")

    def post2(self):
        for batch in BATCHES:
            output = self.out / batch
            self.restore(self.run / f"pre/{batch}.aut", self.run / f"post1/{batch}.aut", output)
            self.call("--bfile", str(output) + ".restored", "--hwe", "1e-6", "--maf", ".01", "--make-bed", "--out", output)

    def deduplicate(self):
        left_samples, left = dataset(self.run / "post2/a")
        right_samples, right = dataset(self.run / "post2/b")
        li = next(i for i, s in enumerate(left_samples) if s[1] == "TOY_SHARED")
        ri = next(i for i, s in enumerate(right_samples) if s[1] == "TOY_SHARED")
        pairs = [(left[k]["calls"][li], right[k]["calls"][ri]) for k in sorted(left.keys() & right.keys())
                 if all(left[k][f] == right[k][f] for f in ("chrom", "pos", "a1", "a2"))]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        discordant = sum(a != b for a, b in pairs)
        coverage = {b: signature(self.run / f"pre/{b}.aut")["variants"] for b in BATCHES}
        if not pairs or Decimal(len(pairs) - discordant) / len(pairs) <= Decimal(".99") or coverage["a"] <= coverage["b"]:
            raise ValueError("Toy duplicate evidence differs from its documented decision")
        write_json(self.out / "concordance.json", {"compared": len(pairs), "discordant": discordant, "kept_batch": "a", "pre_qc_coverage": coverage})
        for batch, samples in (("a", left_samples), ("b", right_samples)):
            keep = self.out / f"{batch}.keep"
            keep.write_text("".join(f"{s[0]} {s[1]}\n" for s in samples if batch == "a" or s[1] != "TOY_SHARED"))
            self.call("--bfile", self.run / f"post2/{batch}", "--keep", keep, "--make-bed", "--freq", "--out", self.out / batch)

    def harmonize(self):
        # The existing helper owns the output directory, so give it a child directory.
        helper = load_module("toy_harmonize", ROOT / "02_custom/harmonize.py")
        helper.audit([(b, self.run / f"deduplicate/{b}") for b in BATCHES], self.out / "audit")

    def merge(self):
        for batch in BATCHES:
            self.call("--bfile", self.run / f"deduplicate/{batch}", "--extract", self.run / "harmonize/audit/keep.snps", "--make-bed", "--out", self.out / batch)
        self.call("--bfile", self.out / "a", "--bmerge", self.out / "b", "--make-bed", "--out", self.out / "adni_demo")

    def final(self):
        self.call("--bfile", self.run / "merge/adni_demo", "--genome", "full", "unbounded", "nudge", "--min", ".20", "--out", self.out / "relatedness")
        pairs = whitespace(self.out / "relatedness.genome")
        clone = [row for row in pairs if {row["IID1"], row["IID2"]} == {"TOY_A003", "TOY_B002"}]
        if len(clone) != 1 or float(clone[0]["PI_HAT"]) < .90:
            raise ValueError("Expected synthetic cryptic duplicate was not detected")
        remove = self.out / "reviewed.remove"
        remove.write_text("TOY_B002 TOY_B002\n")
        self.call("--bfile", self.run / "merge/adni_demo", "--remove", remove, "--make-bed", "--out", self.out / "adni_demo")
        self.call("--bfile", self.out / "adni_demo", "--pca", "3", "--out", self.out / "pca")

    def x(self):
        samples, _ = dataset(self.run / "final/adni_demo")
        keep = self.out / "autosomal.keep"
        keep.write_text("".join(f"{s[0]} {s[1]}\n" for s in samples))
        for batch in BATCHES:
            output = self.out / batch
            # The imputed FAM uses unknown sex, so restore the known sex from the typed FAM first.
            self.call("--bfile", self.run / f"post1/{batch}.x", "--update-sex", self.run / f"pre/{batch}.x.fam", "3", "--make-bed", "--out", str(output) + ".sex")
            batch_keep = self.run / f"deduplicate/{batch}.keep"
            allowed = {tuple(line.split()) for line in batch_keep.read_text().splitlines()}
            current_keep = self.out / f"{batch}.keep"
            current_keep.write_text("".join(f"{s[0]} {s[1]}\n" for s in samples if (s[0], s[1]) in allowed))
            self.restore(self.run / f"pre/{batch}.x", Path(str(output) + ".sex"), output, current_keep)
            self.call("--bfile", str(output) + ".restored", "--filter-females", "--hwe", "1e-6", "--write-snplist", "--out", str(output) + ".female")
            self.call("--bfile", str(output) + ".restored", "--extract", str(output) + ".female.snplist", "--maf", ".01", "--set-hh-missing", "--make-bed", "--freq", "--out", output)
        # Same fixed X variant panel in both batches; validate allele/position matches explicitly.
        _, a = dataset(self.out / "a")
        _, b = dataset(self.out / "b")
        freqs = {batch: {r["SNP"]: Decimal(r["MAF"]) for r in whitespace(self.out / f"{batch}.frq")} for batch in BATCHES}
        shared = [k for k in sorted(a.keys() & b.keys()) if all(a[k][f] == b[k][f] for f in ("chrom", "pos", "a1", "a2"))
                  and abs(freqs["a"][k] - freqs["b"][k]) <= Decimal(".10")]
        (self.out / "shared.ids").write_text("".join(k + "\n" for k in shared))
        for batch in BATCHES:
            self.call("--bfile", self.out / batch, "--extract", self.out / "shared.ids", "--make-bed", "--out", self.out / f"{batch}.shared")
        self.call("--bfile", self.out / "a.shared", "--bmerge", self.out / "b.shared", "--make-bed", "--out", self.out / "adni_demo_x")


def collect(run):
    run = external(run)
    for stage in STAGES:
        if read_json(run / stage / "complete.json").get("stage") != stage:
            raise ValueError("Incomplete stage: " + stage)
    prefixes = [f"pre/{b}.{suffix}" for b in BATCHES for suffix in ("aut", "x")]
    prefixes += [f"{stage}/{b}" for stage in ("post2", "deduplicate") for b in BATCHES]
    prefixes += [f"post1/{b}.aut" for b in BATCHES]
    prefixes += ["merge/adni_demo", "final/adni_demo", "x/adni_demo_x"]
    result = {name: signature(run / name) for name in prefixes}
    aut_samples, _ = dataset(run / "final/adni_demo")
    x_samples, _ = dataset(run / "x/adni_demo_x")
    if aut_samples != x_samples:
        raise ValueError("X and autosomal sample IDs/sex disagree")
    for name in ("post1/a.excluded.json", "post1/b.excluded.json", "deduplicate/concordance.json", "harmonize/audit/keep.snps", "harmonize/audit/audit.tsv", "final/reviewed.remove", "x/shared.ids"):
        result[name] = {"sha256": digest((run / name).read_bytes())}
    # Exclude timestamps and absolute paths; compare PCA numerically with independent sign flips.
    pca = [line.split() for line in (run / "final/pca.eigenvec").read_text().splitlines()]
    result["pca"] = {"samples": [row[:2] for row in pca], "vectors": [[float(v) for v in row[2:]] for row in pca],
                     "values": [float(v) for v in (run / "final/pca.eigenval").read_text().split()]}
    return result


def compare(actual, expected):
    if actual.keys() != expected.keys():
        raise ValueError("Missing or unexpected checkpoints")
    for key in actual.keys() - {"pca"}:
        if actual[key] != expected[key]:
            raise ValueError("Result mismatch: " + key)
    a, e = actual["pca"], expected["pca"]
    if a["samples"] != e["samples"] or len(a["values"]) != len(e["values"]):
        raise ValueError("PCA sample/component mismatch")
    for block in (a, e):
        if len(block["vectors"]) != len(block["samples"]) or any(len(row) != len(block["values"]) for row in block["vectors"]):
            raise ValueError("PCA matrix dimensions disagree")
    for x, y in zip(a["values"], e["values"]):
        if not math.isclose(x, y, rel_tol=1e-5, abs_tol=1e-6):
            raise ValueError("PCA eigenvalue mismatch")
    for j in range(len(a["values"])):
        av, ev = [r[j] for r in a["vectors"]], [r[j] for r in e["vectors"]]
        sign = 1 if sum(x * y for x, y in zip(av, ev)) >= 0 else -1
        if any(not math.isfinite(x) or abs(sign * x - y) > 1e-5 for x, y in zip(av, ev)):
            raise ValueError("PCA eigenvector mismatch")
    stable = {k: actual[k] for k in actual if k != "pca"}
    return {"status": "PASS", "checkpoints": len(actual), "pca": "within_tolerance_with_sign_alignment",
            "genotype_and_decision_digest": digest(json.dumps(stable, sort_keys=True).encode())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", *STAGES, "verify", "compare"))
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--archive", help="Optional local copy of the pinned PLINK ZIP")
    parser.add_argument("--other-run", help="Second run directory for compare")
    parser.add_argument("--report", help="Write a successful comparison report to a new external JSON file")
    args = parser.parse_args()
    try:
        demo = Demo(args.run_dir)
        if args.action == "setup":
            demo.setup(args.archive)
        elif args.action in STAGES:
            demo.stage(args.action)
        else:
            actual = collect(demo.run)
            if args.action == "compare" and not args.other_run:
                raise ValueError("compare requires --other-run")
            expected = collect(args.other_run) if args.action == "compare" else read_json(HERE / "expected.json")
            result = compare(actual, expected)
            if args.report:
                report = external(args.report)
                report.parent.mkdir(parents=True, exist_ok=True)
                with report.open("x") as stream:
                    stream.write(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
