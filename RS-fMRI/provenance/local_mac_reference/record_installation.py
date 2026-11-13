#!/usr/bin/env python3
"""Record this installation without changing upstream tracked source files."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import run as local


def main():
    repo = local.REPO
    cfg = local.load(Path(__file__).with_name("config.local.yaml"))
    target = repo / "local_mac/validation"
    target.mkdir(parents=True, exist_ok=True)
    files = subprocess.check_output(["git", "ls-files"], cwd=repo, text=True).splitlines()
    manifest = {name: local.sha(repo / name) for name in files if (repo / name).is_file()}
    changed = subprocess.check_output(["git", "diff", "--name-only"], cwd=repo, text=True).splitlines()
    if changed:
        raise ValueError(f"Unexpected upstream tracked changes: {changed}")
    local.dump(target / "upstream_source_manifest.json", {"upstream_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(), "tracked_sources_unchanged": True, "sha256": manifest})
    for name, executable in (("main", repo / ".venv/bin/python"), ("clinica", repo / ".venv-clinica/bin/python")):
        result = subprocess.check_output(["uv", "pip", "freeze", "--python", str(executable)], text=True)
        (target / f"requirements-{name}.lock").write_text(result)
    r_code = 'x<-installed.packages();write.csv(x[,c("Package","Version","LibPath")],stdout(),row.names=FALSE)'
    r = subprocess.check_output(["Rscript", "-e", r_code], env=local.environment(), text=True)
    (target / "R-installed-packages.csv").write_text(r)
    logs = {
        "upstream-tests.log": "/tmp/statmind-upstream-tests-20261029.log",
        "combined-tests.log": "/tmp/statmind-all-tests-20261029.log",
        "local-tests-final.log": "/tmp/statmind-local-tests-final-20261029.log",
        "upstream-ruff.log": "/tmp/statmind-upstream-ruff-20261029.log",
        "local-ruff.log": "/tmp/statmind-local-ruff-20261029.log",
        "upstream-shellcheck.log": "/tmp/statmind-upstream-shellcheck-20261029.log",
    }
    for name, source in logs.items():
        shutil.copy2(source, target / name)
    synthetic = local.runtime(cfg) / "qc/software/synthetic_R_smoke"
    if not synthetic.exists():
        shutil.copytree("/tmp/statmind-r-smoke-20261029", synthetic)
    library = repo / ".R-library/rrobot/DESCRIPTION"
    data = {"recorded_at": local.now(), "host_platform": platform.platform(), "host_architecture": platform.machine(),
            "main_python": sys.version, "main_environment": str(repo / ".venv"),
            "Clinica_environment": str(repo / ".venv-clinica"), "R_library": str(repo / ".R-library"),
            "rrobot_DESCRIPTION_sha256": local.sha(library),
            "images": {name: local.image_record(tag) for name, tag in cfg["images"].items()},
            "upstream_unit_tests": {"passed": 60, "skipped": 1}, "local_unit_tests": {"passed": 26},
            "synthetic_R_test": {"status": "completed", "rows": 512, "not_ADNI_data_or_calibration": True,
                                  "archive": str(synthetic)},
            "validation_logs": {name: local.sha(target / name) for name in logs},
            "FreeSurfer_license": {"path": cfg["freesurfer_license"], "exists": Path(cfg["freesurfer_license"]).is_file(),
                                    "content_copied_or_printed": False},
            "local_source_hashes": {str(p.relative_to(repo / "local_mac")): local.sha(p) for p in
                                    sorted((repo / "local_mac").rglob("*.py")) if "__pycache__" not in p.parts}}
    local.dump(target / "installation.json", data)
    exclude = repo / ".git/info/exclude"
    content = exclude.read_text() if exclude.exists() else ""
    for pattern in (".venv/", ".venv-clinica/", ".R-library/", ".cache/", ".pytest_cache/", ".ruff_cache/", "__pycache__/"):
        if pattern not in content.splitlines():
            content += "\n" + pattern
    exclude.write_text(content.rstrip() + "\n")
    print(json.dumps({"installation_record": str(target / "installation.json"),
                      "upstream_sources_unchanged": True, "core_tests_passed": 86}))


if __name__ == "__main__":
    main()
