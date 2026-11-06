#!/usr/bin/env python3
"""Generate the public synthetic fixture. This does not use ADNI or TOPMed data."""
import argparse
import hashlib
import json
from functools import lru_cache
from pathlib import Path


def uniform(key):
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64


def person(sample):
    return "TOY_A003" if sample == "TOY_B002" else sample


def sex(sample):
    if sample.endswith("SHARED"):
        return 2
    if sample.endswith(("LOW", "SEX")):
        return 1
    return 1 if int(person(sample)[-3:]) % 2 else 2


@lru_cache(maxsize=None)
def x_calls(sample):
    order = sorted(range(120), key=lambda i: uniform(person(sample) + f":x:{i}"))
    result = [0] * 120
    for rank, i in enumerate(order):
        result[i] = (2 if rank < 24 else 0) if sex(sample) == 1 else (2 if rank < 6 else 1 if rank < 44 else 0)
    return result


def dose(sample, variant):
    if variant["id"].startswith("xtyped"):
        return x_calls(sample)[int(variant["id"][6:])]
    key = person(sample) + ":" + variant["id"]
    if variant["chrom"] == "X" and sex(sample) == 1:
        return 2 * int(uniform(key + ":0") < .2)
    return sum(uniform(key + ":" + str(i)) < .2 for i in range(2))


def make(output):
    output.mkdir(parents=True, exist_ok=False)
    raw, imputed = {}, {}
    for batch in ("a", "b"):
        samples = [{"id": f"TOY_{batch.upper()}{i:03d}", "sex": sex(f"TOY_{batch.upper()}{i:03d}")} for i in range(1, 31)]
        samples += [{"id": "TOY_SHARED", "sex": 2}, {"id": f"TOY_{batch.upper()}_LOW", "sex": 1},
                    {"id": f"TOY_{batch.upper()}_SEX", "sex": 2}]
        variants = [{"id": f"typed{i:04d}", "chrom": "1", "pos": 10000 + i * 1000, "ref": "A", "alt": "C"}
                    for i in range(1240 if batch == "a" else 1200)]
        variants += [{"id": name, "chrom": "1", "pos": 2000000 + i * 1000, "ref": "A", "alt": "C"}
                     for i, name in enumerate(("toy_missing", "toy_monomorphic", "toy_hwe"))]
        variants += [{"id": f"xtyped{i:03d}", "chrom": "X", "pos": 10000000 + i * 1000, "ref": "A", "alt": "C"} for i in range(120)]
        calls = []
        for index, sample in enumerate(samples):
            row = []
            for j, variant in enumerate(variants):
                value = dose(sample["id"], variant)
                if sample["id"].endswith("LOW") and j < 50:
                    value = None
                if variant["id"] == "toy_missing" and index < 4:
                    value = None
                if variant["id"] == "toy_monomorphic":
                    value = 0
                if variant["id"] == "toy_hwe":
                    value = 1
                row.append(value)
            calls.append(row)
        raw[batch] = {"samples": samples, "variants": variants, "calls": calls}
        kept = [s for s in samples if not s["id"].endswith(("LOW", "SEX"))]
        sites = [dict(v, r2="0.95") for v in variants if v["id"].startswith(("typed", "xtyped")) and not v["id"].startswith("typed12")]
        for i in range(20):
            sites.append({"id": f"novel{i:03d}", "chrom": "1", "pos": 3000000 + i * 1000,
                          "ref": "A", "alt": "G" if batch == "b" and i == 0 else "C", "r2": "0.50" if i == 18 else "0.95"})
        sites.append(dict(sites[-1]))
        sites.append({"id": "toy_multi", "chrom": "1", "pos": 4000000, "ref": "A", "alt": "C,G", "r2": "0.99"})
        sites += [{"id": f"xnovel{i:03d}", "chrom": "X", "pos": 11000000 + i * 1000,
                   "ref": "A", "alt": "C", "r2": "0.95"} for i in range(10)]
        imp_calls = []
        for index, sample in enumerate(kept):
            row = []
            for variant in sites:
                value = dose(sample["id"], variant)
                if variant["id"] == "novel001":
                    value = int(index == 0) if batch == "a" else (2 if index < 5 else 1 if index < 20 else 0)
                if variant["id"] in ("typed0000", "typed0001"):
                    value = (value + 1) % 3
                row.append(value)
            imp_calls.append(row)
        imputed[batch] = {"samples": kept, "variants": sites, "calls": imp_calls}
    for name, batches in (("genotypes.json", raw), ("imputation-fixture.json", imputed)):
        payload = {"source": "Synthetic teaching data; no real participants and no TOPMed execution.", "batches": batches}
        (output / name).write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob("*.json"))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(make(args.output_dir), indent=2))
