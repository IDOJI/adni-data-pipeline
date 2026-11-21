"""Prepare private paths for the single-session README and publish a completed ADNI pair."""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

from seed_policy import load_backend

LAB = Path(__file__).resolve().parents[1]
PAIR = LAB / "pipeline/s5d_bids_identity"
SESSION = LAB / "pipeline/s7b_sessionwise_preprocessing"


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def separate(a, b):
    if a.is_relative_to(b) or b.is_relative_to(a):
        raise ValueError(f"Choose separate, non-overlapping directories: {a} and {b}")


def setup(data, results):
    license_file = data / "license.txt"
    templates = data / "templateflow"
    separate(data, LAB.parent)
    if not license_file.is_file() or not templates.is_dir():
        raise ValueError("Supply license.txt and a resident templateflow/ cache under the data directory")
    if results.exists() or results.is_symlink() or not results.parent.is_dir():
        raise ValueError("Choose a new results directory under an existing writable parent")
    for source in (LAB.parent, data, templates.resolve(), license_file.resolve()):
        separate(results, source)
    for path in (data, results, license_file.resolve(), templates.resolve()):
        if any(char in str(path) for char in ",:"):
            raise ValueError("Use Docker mount paths without commas or colons")
    return license_file, templates


def prepare_adni(data, results, key):
    license_file, templates = setup(data, results)
    receipt = data / "binding/07.binding-receipt.json"
    gate = load_backend(PAIR / "guarded_runner_seeded.py", "manual_gate")
    use_existing_binding = receipt.parent.exists()
    if use_existing_binding:
        receipt = receipt.resolve(strict=True)
    else:
        # Bind from independently generated evidence using the public Stage 5.D schema.
        files = {"images": "candidate-audit.csv", "epi_manifest": "04.epi-analysis-manifest.csv",
                 "pairing_receipt": "pairing-run-manifest.json"}
        inputs = {field: str((data / name).resolve(strict=True)) for field, name in files.items()}
        bids = (data / "bids").resolve(strict=True)
        separate(bids, results)
        fingerprints = (data / "hash-evidence.csv").resolve(strict=True)
        inputs.update(bids_roots=[str(bids)], hash_evidence=[str(fingerprints)],
                      output_dir=str(results / "binding"))
        results.mkdir()
        write(results / "binding.json", inputs)
        gate.binding.run(results / "binding.json")
        receipt = results / "binding/07.binding-receipt.json"
    proof = gate.binding.proof_files(receipt)
    plans = read(Path(proof["outputs"]["plans"]["path"]))
    keys = [plan["epi_key"] for plan in plans if plan["preprocessing_ready"]]
    if key is None:
        if len(keys) != 1:
            raise ValueError(f"Expected one preprocessing-ready pair. Available --epi-key values: {keys}")
        key = keys[0]
    plan = gate.binding.verify_plan(receipt, key)
    if (not re.fullmatch(r"\d{3}_S_\d{4,}", plan["ptid"])
            or plan["subject"] != "ADNI" + plan["ptid"].replace("_", "")):
        raise ValueError("The Step 10 ADNI publisher requires a BIDS subject label matching the source PTID")
    for role in ("epi", "t1"):
        separate(results, Path(plan[role]["BIDS_ROOT"]).resolve())
    batch = read(LAB / "03_config/local_batch.seeded.example.json")
    template = batch["preprocessing_template"]
    template.update(source_templateflow=str(templates), freesurfer_license=str(license_file))
    if use_existing_binding:
        results.mkdir()
    template_path = results / "preprocessing-template.yaml"
    template_path.write_text(yaml.safe_dump(template, sort_keys=False))
    config = gate.prepare(receipt, key, results / "pair", template_path)
    runtime = results / "pair/processing"
    (results / "runs").mkdir()
    (results / "runs" / plan["subject"]).symlink_to(runtime, target_is_directory=True)
    xcpd = read(LAB / "03_config/xcpd_linc.seeded.example.json")
    xcpd.update(root=str(results), license=str(license_file), templateflow=str(runtime / "templateflow"),
                resources=batch["xcpd_resources"])
    write(results / "xcpd.json", xcpd)
    print(config)


def prepare_volume(data, results):
    license_file, templates = setup(data, results)
    bids = (data / "bids").resolve()
    separate(bids, results)
    sessions = sorted(path for path in bids.glob("sub-*/ses-*") if path.is_dir())
    if len(sessions) != 1:
        raise ValueError("Supply a one-session BIDS dataset (one sub-*/ses-* directory)")
    session = sessions[0]
    run = {"subject": session.parent.name.removeprefix("sub-"), "session": session.name.removeprefix("ses-")}
    directory = LAB / "pipeline/s7a_volume_workflow"
    volume = load_backend(directory / "pipeline_seeded.py", "manual_volume")
    config = read(directory / "config.seeded.example.json")
    config["paths"] = {k: str(results / k) for k in config["paths"]}
    config["paths"]["bids"] = str(bids)
    config.update(fs_license=str(license_file), runs=[run])
    volume.check_inputs(config, "fmriprep", run)
    results.mkdir()
    shutil.copytree(templates, results / "templateflow")
    write(results / "volume.json", config)
    print(results / "volume.json")


def publish(results):
    gate = load_backend(PAIR / "guarded_runner_seeded.py", "manual_gate")
    records = load_backend(PAIR / "continuation.py", "manual_continuation")
    publisher = load_backend(SESSION / "publish_pairs.py", "manual_publisher")
    config = results / "pair/verified-config.yaml"
    gate.dispatch(config, "check")
    cfg = yaml.safe_load(config.read_text())
    runtime = results / "pair/processing"
    plan = gate.binding.verify_plan(cfg["binding_receipt"], cfg["epi_key"])
    subject = plan["subject"]
    if (Path(cfg["runtime"]).resolve() != runtime or (results / "runs" / subject).resolve() != runtime):
        raise ValueError("The configured runtime must match this pair's publication source")
    paths = gate.backend().paths_for(cfg, cfg["runs"][0])
    for stage in records.STAGES:
        _, record = records.latest(runtime, subject, stage)
        if not records.completed(record):
            raise ValueError(f"Complete {stage} successfully with unchanged inputs before publishing")
        records.check_record(record, paths, plan, runtime / "bids")
        records.output_evidence(runtime, subject, stage)
    date = plan["date"].replace("-", "")
    pair_id = f"EPI_{date}_MT1_{date}"
    target = results / "results" / plan["ptid"] / pair_id
    case = dict(ptid=plan["ptid"], subject=subject, pair_id=pair_id, target=str(target),
                epi_date=plan["date"], mt1_date=plan["date"], epi_image_id=plan["epi_image_id"],
                mt1_image_id=plan["t1_image_id"], execution_session_label=plan["session"],
                pairing_basis="Verified source images, UIDs, dates and hashes")
    delivery, = publisher.publish(results, [case])
    if delivery["delivery_status"] not in ("processing_complete_QC_pending", "previously_published"):
        raise ValueError(delivery["delivery_status"])
    print(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare-adni", "prepare-volume"):
        prep = commands.add_parser(name)
        prep.add_argument("--data", required=True, type=Path)
        prep.add_argument("--results", required=True, type=Path)
        if name == "prepare-adni":
            prep.add_argument("--epi-key", help="Select a verified pair if the receipt contains several")
    commands.add_parser("publish").add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    results = args.results.expanduser()
    if results.is_symlink():
        parser.error("Choose the original results directory, not a symbolic link")
    results = results.resolve()
    if args.command == "publish":
        publish(results)
    elif args.command == "prepare-adni":
        prepare_adni(args.data.expanduser().resolve(), results, args.epi_key)
    else:
        prepare_volume(args.data.expanduser().resolve(), results)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(str(exc))
