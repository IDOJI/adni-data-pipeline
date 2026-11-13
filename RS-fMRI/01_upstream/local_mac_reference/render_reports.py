#!/usr/bin/env python3
"""Read-only static rendering of selected generated report SVGs."""
from __future__ import annotations

import argparse
import base64
import copy
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as ET

import run as local


def states(root):
    layers = [name for name in ("background-svg", "foreground-svg")
              if any(name in item.get("class", "").split() for item in root.iter())]
    return layers or ["static"]


def complete_embedded_png_dimensions(root):
    """Supply one missing SVG image dimension from its PNG aspect ratio.

    Work only on a copied report tree. Refuse unsupported or ambiguous cases
    rather than silently producing a static report with an empty panel.
    """
    repairs = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "image":
            continue
        missing = [key for key in ("width", "height") if key not in element.attrib]
        if not missing:
            continue
        if len(missing) != 1:
            raise ValueError("An embedded SVG image lacks both width and height")
        href = next((value for key, value in element.attrib.items()
                     if key.rsplit("}", 1)[-1] == "href"), "")
        prefix, separator, payload = href.partition(",")
        if not separator or prefix.lower() != "data:image/png;base64":
            raise ValueError("Missing image dimension requires an embedded base64 PNG")
        try:
            header = base64.b64decode("".join(payload.split())[:32], validate=True)
        except ValueError as exc:
            raise ValueError("Invalid embedded PNG header") from exc
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            raise ValueError("Invalid embedded PNG header")
        png_width, png_height = struct.unpack(">II", header[16:24])
        if not png_width or not png_height:
            raise ValueError("Embedded PNG has an invalid intrinsic size")
        present = "width" if missing[0] == "height" else "height"
        text = element.get(present, "")
        match = re.fullmatch(r"((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(px)?", text)
        if not match:
            raise ValueError(f"Unsupported SVG image {present}: {text!r}")
        size = float(match.group(1))
        if not math.isfinite(size) or size <= 0:
            raise ValueError("SVG image dimensions must be positive and finite")
        derived = size * png_height / png_width if missing[0] == "height" else size * png_width / png_height
        if not math.isfinite(derived) or derived <= 0:
            raise ValueError("Derived SVG image dimension is not positive and finite")
        value = f"{derived:.12g}{match.group(2) or ''}"
        element.set(missing[0], value)
        repairs.append({"attribute": missing[0], "value": value,
                        "intrinsic_png_width": png_width, "intrinsic_png_height": png_height})
    return repairs


def static_tree(root, layer, repairs=None):
    tree = copy.deepcopy(root)
    if layer != "static":
        for parent in tree.iter():
            for child in list(parent):
                classes = child.get("class", "").split()
                is_layer = any(name in classes for name in ("background-svg", "foreground-svg"))
                if is_layer and layer not in classes:
                    parent.remove(child)
                elif is_layer:
                    child.set("style", "opacity:1;visibility:visible;display:inline;animation:none")
                elif child.tag.rsplit("}", 1)[-1] == "style" and (
                    "@keyframes" in (child.text or "") or "foreground-svg" in (child.text or "")
                ):
                    parent.remove(child)
    changes = complete_embedded_png_dimensions(tree)
    if repairs is not None:
        repairs.extend(changes)
    return tree


def selected_fmriprep_report(name):
    """Select functional, surface and anatomical QC report SVGs."""
    return (any(word in name for word in ("coreg", "sdc", "reconall", "norm", "carpetplot"))
            or name.endswith("_dseg.svg")
            or ("_space-MNI" in name and name.endswith("_T1w.svg")))


def render(cfg, stage):
    root = local.runtime(cfg)
    target = root / "qc/report_renders" / stage
    target.mkdir(parents=True, exist_ok=True)
    items = []
    if stage == "mriqc":
        for case in cfg["runs"]:
            folder = root / "derivatives/mriqc" / f"sub-{case['subject']}" / "figures"
            for source in sorted(folder.glob(f"sub-{case['subject']}_ses-{case['session']}*.svg")):
                items.append((source, source.stem, ET.parse(source).getroot()))
    else:
        for case in cfg["runs"]:
            folder = root / "derivatives/fmriprep" / f"sub-{case['subject']}" / "figures"
            for source in sorted(folder.glob(f"sub-{case['subject']}_ses-{case['session']}*.svg")):
                if selected_fmriprep_report(source.name):
                    items.append((source, source.stem, ET.parse(source).getroot()))
    if not items:
        raise ValueError(f"No {stage} source report SVGs found")
    manifest = []
    for source, name, tree in items:
        original = local.sha(source)
        for layer in states(tree):
            destination = target / f"{name}_{layer}.svg"
            repairs = []
            ET.ElementTree(static_tree(tree, layer, repairs)).write(destination, encoding="utf-8", xml_declaration=True)
            manifest.append({"source": str(source.relative_to(root)), "source_sha256": original,
                             "layer": layer, "svg": destination.name, "intrinsic_size_repairs": repairs,
                             "svg_sha256": local.sha(destination), "png": destination.with_suffix('.png').name})
    # The renderer sees only exported report SVGs, not MRI input volumes.
    script = "from pathlib import Path;import subprocess\nfor p in sorted(Path('/review').glob('*.svg')):\n subprocess.run(['rsvg-convert','--width','2000','--output',str(p.with_suffix('.png')),str(p)],check=True)"
    image = local.image_record(cfg["images"]["fmriprep"])
    argv = ["docker", "run", "--rm", "--platform", "linux/amd64", "--cpus", "1", "--memory", "2g",
            "--mount", f"type=bind,src={target},dst=/review", "--entrypoint", "python", image["resolved"], "-c", script]
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (target / "render_console.log").write_text(result.stdout)
    if result.returncode:
        raise ValueError(f"SVG rendering failed; see {target / 'render_console.log'}")
    for item in manifest:
        item["png_sha256"] = local.sha(target / item["png"])
        item["source_unchanged"] = local.sha(root / item["source"]) == item["source_sha256"]
        if not item["source_unchanged"]:
            raise ValueError("Source report changed during rendering")
    local.dump(target / "render_manifest.json", {"time": local.now(), "stage": stage,
               "renderer_image": image, "command": argv, "images": manifest,
               "scope": "Static report display states only; source reports and MRI values unchanged."})
    print(json.dumps({"rendered": len(manifest), "folder": str(target)}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("mriqc", "fmriprep"))
    p.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.yaml"))
    a = p.parse_args()
    render(local.load(a.config), a.stage)


if __name__ == "__main__":
    main()
