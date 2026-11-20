#!/usr/bin/env python3
"""Give one finite S13 experiment admission priority without stopping containers.

The existing shared admission gate serializes all legacy leases. Holding that
gate prevents NEW production admissions, while already running calculations keep
their existing subject leases and finish naturally. The experiment reserves at
most one subject and retains the authorized five-subject cap.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time


def capacity_reasons(subject, active, memory_mb, total_bytes, limit=5):
    if limit != 5:
        raise ValueError("The shared subject limit must remain five")
    reasons = []
    if subject in active:
        reasons.append("The selected subject already has a live reservation")
    if len(active) >= limit:
        reasons.append("All five shared subject slots are occupied")
    # Existing deployments declare a 4 GB workflow estimate per active subject.
    # Do not assume a free subject slot also implies sufficient memory. Unknown
    # deployments must supply a larger estimate via the recorded priority policy.
    estimated = sum(active.values()) * 10**6 + memory_mb * 10**6 + 2**30
    if estimated > total_bytes:
        reasons.append("Waiting for memory while current calculations finish")
    return reasons


def observed_memory_mb(item):
    command = item.get("Config", {}).get("Cmd", []) or []
    for flag, scale in (("--mem-mb", 1), ("--mem_mb", 1), ("--mem", 1), ("--mem-gb", 1000)):
        if flag in command:
            try:
                value = float(command[command.index(flag) + 1]) * scale
                if math.isfinite(value) and value > 0:
                    return max(4000, value)
            except (ValueError, IndexError):
                pass
    # A reservation between stages still has the existing 4 GB workflow budget.
    return 4000


def active_subjects(slots):
    names = slots.running_subjects()
    names |= slots.live_reservations(slots.HERE / "compute_slots")
    result = {subject: 4000 for subject in names}
    ids = subprocess.check_output(["docker", "ps", "-q"], text=True, timeout=25).split()
    if ids:
        items = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True, timeout=25))
        for item in items:
            match = re.search(r"ADNI[0-9]+S[0-9]+(?![0-9])", item["Name"])
            if match is None or match.group() not in names:
                raise ValueError("Unaccounted running container; cannot guarantee shared capacity: " + item["Name"])
            subject = match.group()
            result[subject] = max(result[subject], observed_memory_mb(item))
    return result


@contextlib.contextmanager
def admission_priority(slots, holder):
    """Release the existing gate on success, exception or normal interruption."""
    with (slots.HERE / "compute_slots/admission.lock").open("a") as gate:
        fcntl.flock(gate, fcntl.LOCK_EX)
        holder["gate_held"] = True
        try:
            yield
        finally:
            holder["gate_held"] = False
            fcntl.flock(gate, fcntl.LOCK_UN)


def install(base, root, existing_estimate_mb=4000):
    """Adapt scheduling/reporting only; keep the frozen scientific source intact."""
    original_module, original_report = base.module, base.report
    plan = base.verified_plan(root)
    slots = original_module("04_workflow/compute_slots.py")
    slots.configure(plan["shared_compute_root"])
    holder = {"gate_held": False}

    def prerequisites(current):
        settings = base.read(slots.HERE / "settings.json")
        limit = settings.get("global_compute_limit", settings.get("target_concurrency"))
        if limit != 5:
            raise ValueError("The shared subject limit changed; hold for review")
        # Deliberately do not block on pending production queue entries.
        return []

    @contextlib.contextmanager
    def lease(subject, stage, poll=5):
        if not holder["gate_held"]:
            raise ValueError("Priority reservation requires the shared admission gate")
        directory = slots.HERE / "compute_slots"
        held = None
        try:
            while held is None:
                prerequisites(plan)
                active = active_subjects(slots)
                active = {key: max(value, existing_estimate_mb) for key, value in active.items()}
                info = json.loads(subprocess.check_output(["docker", "info", "--format", "{{json .}}"], text=True, timeout=25))
                reasons = capacity_reasons(subject, active, plan["workflow_memory_mb"], info["MemTotal"])
                if base.shutil.disk_usage(root).free < plan["min_free_gib"] * 2**30:
                    reasons.append("Experiment volume is below the frozen free-space floor")
                if not reasons:
                    candidate = (directory / (subject + ".lock")).open("a+")
                    try:
                        fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        candidate.close()
                    else:
                        held = candidate
                        held.seek(0)
                        held.truncate()
                        json.dump({"pid": os.getpid(), "subject": subject,
                                   "stage": "reproducibility_priority", "acquired_at": time.time()}, held)
                        held.flush()
                if held is None:
                    base.save(root / "status.json", {"at": base.now(), "status": "waiting_for_priority_slot",
                              "active_subjects": sorted(active), "reasons": reasons,
                              "pending_production_queue_is_not_a_blocker": True, "LLM_calls": 0})
                    time.sleep(poll)
            yield
        finally:
            if held is not None:
                fcntl.flock(held, fcntl.LOCK_UN)
                held.close()

    def adapted_module(relative):
        if relative != "04_workflow/compute_slots.py":
            return original_module(relative)
        slots.lease = lease
        return slots

    def adapted_report(path, current):
        result = original_report(path, current)
        for row in result["cases"]:
            if row["status"] not in ("PASS", "FAIL_TOLERANCE", "CONFOUNDED_LOAD"):
                row["technical_status"] = row["status"]
                continue
            case = next(c for c in current["cases"] if c["id"] == row["case"])
            references = base.trial_paths(path, current, case, 1)
            trials = base.trial_paths(path, current, case, row["threads"])
            if row["threads"] == 1:
                pairs = list(base.itertools.combinations(references, 2))
            else:
                pairs = list(base.itertools.product(references, trials))
            verdicts = [base.read(path / "comparisons" / f"{a.name}--{b.name}.json")["technical_status"] for a, b in pairs]
            row["technical_status"] = "PASS" if verdicts and all(v == "PASS" for v in verdicts) else "FAIL_TOLERANCE"
            row["observed_speedup_uncontrolled"] = row.pop("speedup", None)
            ref_records = [base.read(p / "trial.json") for p in references]
            trial_records = [base.read(p / "trial.json") for p in trials]
            clean_refs = [r for r in ref_records if r.get("isolated") is True]
            clean_trials = [r for r in trial_records if r.get("isolated") is True]
            if len(clean_refs) >= 2 and len(clean_trials) >= 2:
                elapsed = lambda r: sum(r["executions"][s]["wall_seconds"] for s in ("fmriprep", "xcpd"))
                row["speedup"] = statistics.median(map(elapsed, clean_refs)) / statistics.median(map(elapsed, clean_trials))
                row["timing_status"] = "isolated_repeats"
            else:
                row["speedup"] = None
                row["timing_status"] = "insufficient_isolated_repeats"
        passing = [t for t in current["threads"] if t != 1 and all(r.get("technical_status") == "PASS" for r in result["cases"] if r["threads"] == t)]
        timed = [t for t in passing if all(r.get("speedup") is not None and r["speedup"] > 1 for r in result["cases"] if r["threads"] == t)]
        result.update(admission_policy="experiment_before_pending_production", highest_tested_passing_threads=max(passing, default=None),
                      fastest_tested_passing_threads=max(timed, key=lambda t: statistics.geometric_mean(r["speedup"] for r in result["cases"] if r["threads"] == t), default=None))
        base.save(path / "report.json", result)
        import html
        page = ["<!doctype html><meta charset='utf-8'><title>Thread reproducibility</title><h1>Priority thread experiment</h1>",
                "<p>Current production calculations continue. New production admissions wait for this finite experiment. Shared limit: five subjects. Numerical tolerance and timing validity are separate.</p>",
                "<table><tr><th>Case</th><th>Threads</th><th>Tolerance</th><th>Timing</th><th>Controlled speedup</th></tr>"]
        for row in result["cases"]:
            page.append("<tr>" + "".join("<td>" + html.escape(str(row.get(key, "PENDING"))) + "</td>" for key in ("case", "threads", "technical_status", "timing_status", "speedup")) + "</tr>")
        page.append("</table><p>Scientific equivalence remains unestablished.</p>")
        (path / "report.html").write_text("\n".join(page))
        return result

    base.module, base.idle_reasons, base.report = adapted_module, prerequisites, adapted_report
    return plan, slots, holder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True, help="The recorded, frozen S13 run.py")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--existing-memory-mb", type=int, default=4000)
    args = parser.parse_args()
    if args.existing_memory_mb < 4000:
        parser.error("Existing-subject memory estimate must be at least 4000 MB")
    if args.execute and args.report_only:
        parser.error("Choose either execution or reporting")
    sys.path.insert(0, str(args.runner.resolve().parent))
    spec = importlib.util.spec_from_file_location("priority_frozen_s13", args.runner.resolve())
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    root = args.root.resolve()
    if args.report_only:
        plan, _, _ = install(base, root, args.existing_memory_mb)
        print(json.dumps(base.report(root, plan), indent=2, allow_nan=False))
        return
    if not args.execute:
        plan = base.verified_plan(root)
        print(json.dumps({"status": "plan_only", "admission": "next_available_subject_slot", "global_limit": 5,
                          "existing_memory_estimate_mb": args.existing_memory_mb, "threads": plan["threads"],
                          "imaging_started": False}))
        return
    plan, slots, holder = install(base, root, args.existing_memory_mb)
    # Do not start a second experiment manager if the old one still owns its lock.
    priority_lock = (root / "priority_controller.lock").open("a")
    fcntl.flock(priority_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with (root / "controller.lock").open("a") as probe:
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(probe, fcntl.LOCK_UN)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    base.save(root / "priority_scheduler.json", {"pid": os.getpid(), "at": base.now(), "source": str(Path(__file__).resolve()),
              "sha256": script_hash, "frozen_scientific_runner": str(args.runner.resolve()), "global_limit": 5,
              "existing_memory_estimate_mb": args.existing_memory_mb, "current_containers_stopped": False,
              "policy": "experiment_before_pending_production", "LLM_calls": 0})
    base.save(root / "status.json", {"at": base.now(), "status": "waiting_for_admission_gate", "LLM_calls": 0})
    with admission_priority(slots, holder):
        base.run(root, execute=True, wait_idle=True)


if __name__ == "__main__":
    main()
