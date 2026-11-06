#!/usr/bin/env python3
"""Check pinned source, plan commands or execute one configured upstream QC stage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
UPSTREAM = ROOT / "01_upstream/GWAS_QC"
LOCK = ROOT / "03_config/upstream.lock.json"


def git(*args, cwd=REPO):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def doctor():
    lock = json.loads(LOCK.read_text())
    if not (UPSTREAM / ".git").is_file():
        raise ValueError("Initialize the submodule with git submodule update --init --recursive")
    if git("rev-parse", "HEAD", cwd=UPSTREAM) != lock["commit"]:
        raise ValueError("Upstream HEAD differs from the lock")
    fields = git("ls-files", "--stage", "--", lock["path"]).split()
    if fields[:2] != ["160000", lock["commit"]]:
        raise ValueError("Parent gitlink differs from the lock")
    if git("status", "--porcelain", "--untracked-files=all", cwd=UPSTREAM):
        raise ValueError("Upstream has local changes")
    for key, expected in (("path", lock["path"]), ("url", lock["repository"])):
        actual = git("config", "-f", str(REPO / ".gitmodules"), f"submodule.{lock['path']}.{key}")
        if actual != expected:
            raise ValueError(f"Unexpected submodule {key}")
    for name, expected in lock["sha256"].items():
        if sha256(UPSTREAM / name) != expected:
            raise ValueError(f"Upstream file differs from lock: {name}")
    return {"source_pin": "pass", "commit": lock["commit"],
            "cohort_validation": "not_performed", "container_validation": "not_performed"}


def external(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("Use absolute external paths")
    path = Path(value).resolve()
    if path == REPO or REPO in path.parents or path in REPO.parents:
        raise ValueError("Data and outputs must be outside the repository and its ancestors")
    if any(c in str(path) for c in ":,\n\r"):
        raise ValueError("Container bind paths cannot contain colons, commas or newlines")
    return path


def relative(value):
    # Upstream shell scripts contain unquoted expansions. Keep in-container paths simple.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError("Relative paths must use letters, digits, underscores, dots, slashes or hyphens")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Expected a relative path without '..'")
    return value


def read_config(path):
    config = json.loads(Path(path).read_text())
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported config schema_version")
    for key in ("data_root", "reference_root", "container"):
        external(config[key])
    if config["runtime"] not in ("apptainer", "singularity"):
        raise ValueError("runtime must be apptainer or singularity")
    if type(config["memory_mb"]) is not int or config["memory_mb"] < 1:
        raise ValueError("memory_mb must be a positive integer")
    for value in config["references"].values():
        relative(value)
    seen = set()
    outputs = set()
    raw_inputs = {batch["input_bfile"] for batch in config["batches"]}
    if not config["batches"]:
        raise ValueError("At least one batch is required")
    for batch in config["batches"]:
        label = batch["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or label in seen:
            raise ValueError("Batch IDs must be unique simple labels")
        seen.add(label)
        if batch["input_build"] not in ("b34", "b35", "b36", "b37", "b38"):
            raise ValueError(f"Unsupported input build for {label}")
        for key in ("input_bfile", "sex_file", "preimputation_stem", "imputation_dir", "postimputation_stem"):
            relative(batch[key])
        for key in ("preimputation_stem", "postimputation_stem"):
            stem = batch[key]
            if stem in outputs or stem in raw_inputs:
                raise ValueError("QC output stems must be unique and distinct from raw input prefixes")
            outputs.add(stem)
        if batch.get("cleaned_genotypes"):
            relative(batch["cleaned_genotypes"])
        subsets = set()
        for subset in batch["ancestry_subsets"]:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", subset["label"]) or subset["label"] in subsets:
                raise ValueError("Ancestry labels must be unique simple labels within each batch")
            subsets.add(subset["label"])
            relative(subset["keep_file"])
    return config


def container_command(config, script, args):
    return [config["runtime"], "exec", "--contain",
            "--bind", f"{UPSTREAM}:/scripts/GWAS_QC:ro",
            "--bind", f"{external(config['data_root'])}:/input",
            "--bind", f"{external(config['reference_root'])}:/ref:ro",
            "--pwd", "/scripts/GWAS_QC", str(external(config["container"])),
            "/bin/bash", script, *args]


def plan(config):
    """Render only stages for which path handoffs are explicit; never guess output suffixes."""
    stages = []
    refs = config["references"]
    memory = str(config["memory_mb"])
    for batch in config["batches"]:
        inp = lambda key: "/input/" + batch[key]
        common = ["-m", memory, "-c"]
        commands = [
            ("preimputation", "gwas_qc_preimputation.sh",
             ["-i", inp("input_bfile"), "-o", inp("preimputation_stem"),
              "-f", inp("sex_file"), "-R", "/ref/" + refs["topmed_sites_stem"],
              "-b", batch["input_build"], *common]),
            ("postimputation1", "gwas_qc_postimputation_part1.sh",
             ["-i", inp("imputation_dir") + "/", "-o", inp("postimputation_stem"),
              "-f", inp("sex_file"), "-w", "/ref/" + refs["snpweights_stem"],
              "-s", "/ref/" + refs["rsid_stem"], *common]),
        ]
        if batch.get("cleaned_genotypes"):
            for subset in batch["ancestry_subsets"]:
                commands.append(("postimputation2:" + subset["label"], "gwas_qc_postimputation_part2.sh",
                                 ["-i", inp("postimputation_stem") + "_IDs_sex",
                                  "-g", inp("cleaned_genotypes"),
                                  "-r", "/input/" + subset["keep_file"], "-l", subset["label"],
                                  "-s", "/ref/" + refs["rsid_stem"], "-p", *common]))
        for stage, script, args in commands:
            argv = container_command(config, script, args)
            stages.append({"batch": batch["id"], "stage": stage, "argv": argv,
                           "command": shlex.join(argv)})
    return {"status": "command_plan_only", "executed": False, "stages": stages,
            "gates": ["Validate the container, references and known upstream differences before execution.",
                      "Review pre-imputation counts, sex, relatedness and heterozygosity before TOPMed upload.",
                      "Complete TOPMed separately and record the actual job environment for every batch.",
                      "Set cleaned_genotypes from the reviewed log and ancestry_subsets from part 1 before part 2.",
                      "Follow 06_docs/merging.md for duplicate resolution, allele checks, merge and final QC.",
                      "X chromosome requires its separate workflow in 06_docs/chromosome_x.md."]}


def check_jobs(paths, expected_batches):
    records = [json.loads(Path(path).read_text()) for path in paths]
    batches = [r["batch_id"] for r in records]
    if len(batches) != len(set(batches)) or set(batches) != set(expected_batches):
        raise ValueError("Supply exactly one autosomal job record for each configured batch")
    signatures = set()
    keys = ("panel", "genome_build", "server_version", "phasing", "imputation_engine")
    for record in records:
        for key in (*keys, "job_id", "completed_at", "report_sha256"):
            value = record.get(key)
            if not isinstance(value, str) or not value.strip() or value.lower() in ("unknown", "replace", "null"):
                raise ValueError(f"Record the actual {key} for {record['batch_id']}")
        if record["panel"] != "r3" or record["genome_build"] != "GRCh38":
            raise ValueError("This adaptation requires TOPMed r3 and GRCh38 in every batch")
        if not re.fullmatch(r"[0-9a-f]{64}", record["report_sha256"]):
            raise ValueError("report_sha256 must be the SHA-256 of the saved server report")
        signatures.add(tuple(record[k] for k in keys))
    if len(signatures) != 1:
        raise ValueError("Imputation environments differ; do not merge these jobs")
    return {"job_environment_consistency": "pass", "batches": len(records),
            "server_evidence_independently_verified": False}


def run_stage(config, batch_id, stage, log_path):
    matches = [entry for entry in plan(config)["stages"] if entry["batch"] == batch_id and entry["stage"] == stage]
    if len(matches) != 1:
        raise ValueError("Stage is unavailable; check batch ID and the cleaned_genotypes/ancestry_subsets handoffs")
    batch = next(b for b in config["batches"] if b["id"] == batch_id)
    data, refs = external(config["data_root"]), external(config["reference_root"])
    required = [external(config["container"])]
    if stage == "preimputation":
        prefixes = [data / batch["input_bfile"]]
        required += [data / batch["sex_file"], refs / (config["references"]["topmed_sites_stem"] + ".txt.gz")]
        output = data / batch["preimputation_stem"]
    elif stage == "postimputation1":
        prefixes = []
        required += [data / batch["sex_file"], refs / config["references"]["snpweights_stem"],
                     refs / (config["references"]["snpweights_stem"] + "_snp.txt")]
        required += [data / batch["imputation_dir"] / f"chr{i}.dose.vcf.gz" for i in range(1, 23)]
        required += [refs / (config["references"]["rsid_stem"] + f"_chr{i}.txt") for i in range(1, 23)]
        output = data / batch["postimputation_stem"]
    else:
        label = stage.partition(":")[2]
        subset = next(s for s in batch["ancestry_subsets"] if s["label"] == label)
        prefixes = [data / batch["cleaned_genotypes"], data / (batch["postimputation_stem"] + "_IDs_sex")]
        required += [data / subset["keep_file"], data / (batch["postimputation_stem"] + "_IDs_sex.log"),
                     refs / (config["references"]["rsid_stem"] + ".txt")]
        output = data / (batch["postimputation_stem"] + "_IDs_sex_" + label)
    required += [Path(str(prefix) + suffix) for prefix in prefixes for suffix in (".bed", ".bim", ".fam")]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("Missing stage inputs: " + ", ".join(missing))
    if not shutil.which(config["runtime"]):
        raise ValueError("Container runtime is not installed: " + config["runtime"])
    external(str(output))
    if any(output.parent.glob(output.name + "*")):
        raise ValueError("Stage output prefix already exists; use a fresh prefix")
    log = external(log_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the log before starting; an earlier run's log is never overwritten.
    with log.open("x") as stream:
        output.parent.mkdir(parents=True, exist_ok=True)
        stream.write(json.dumps({"batch": batch_id, "stage": stage, "argv": matches[0]["argv"]}) + "\n")
        stream.flush()
        subprocess.run(matches[0]["argv"], stdout=stream, stderr=subprocess.STDOUT, check=True)
    return {"status": "process_completed", "batch": batch_id, "stage": stage, "log": str(log),
            "qc_review": "required"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("doctor", help="Check the gitlink, clean source and locked file hashes")
    cmd = sub.add_parser("plan", help="Print container commands without executing them")
    cmd.add_argument("--config", required=True)
    cmd = sub.add_parser("check-jobs", help="Check recorded autosomal TOPMed environments before merging")
    cmd.add_argument("--config", required=True)
    cmd.add_argument("--records", nargs="+", required=True)
    cmd = sub.add_parser("run-stage", help="Execute one configured upstream QC stage and save its log")
    cmd.add_argument("--config", required=True)
    cmd.add_argument("--batch", required=True)
    cmd.add_argument("--stage", required=True, help="preimputation, postimputation1 or postimputation2:LABEL")
    cmd.add_argument("--log", required=True)
    args = parser.parse_args()
    try:
        source = doctor()
        if args.action == "doctor":
            result = source
        else:
            config = read_config(args.config)
            if args.action == "plan":
                result = plan(config)
            elif args.action == "run-stage":
                result = run_stage(config, args.batch, args.stage, args.log)
            else:
                result = check_jobs(args.records, [b["id"] for b in config["batches"]])
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
