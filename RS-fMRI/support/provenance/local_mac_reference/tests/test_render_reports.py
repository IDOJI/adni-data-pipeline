import base64
import io
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import render_reports as renderer


def png_href(width=8, height=4):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def report_image(**attributes):
    root = ET.Element("svg")
    image = ET.SubElement(root, "image", href=png_href(), **attributes)
    return root, image


def test_missing_height_is_derived_on_a_copy_from_the_embedded_image():
    root, original = report_image(width="12")
    repairs = []
    result = renderer.static_tree(root, "static", repairs)
    image = next(x for x in result.iter() if x.tag == "image")
    assert image.get("height") == "6"
    assert original.get("height") is None
    assert repairs == [{"attribute": "height", "value": "6", "intrinsic_png_width": 8, "intrinsic_png_height": 4}]


def test_missing_width_uses_the_intrinsic_ratio_and_preserves_px_unit():
    root, original = report_image(height="5px")
    result = renderer.static_tree(root, "static")
    assert next(x for x in result.iter() if x.tag == "image").get("width") == "10px"
    assert original.get("width") is None


def test_complete_dimensions_are_preserved_without_reading_an_external_image():
    root = ET.Element("svg")
    ET.SubElement(root, "image", width="12", height="9", href="https://example.invalid/image.png")
    repairs = []
    result = renderer.static_tree(root, "static", repairs)
    image = next(x for x in result.iter() if x.tag == "image")
    assert (image.get("width"), image.get("height"), repairs) == ("12", "9", [])


@pytest.mark.parametrize("attributes,match", [
    ({}, "lacks both width and height"),
    ({"width": "100%"}, "Unsupported SVG image width"),
    ({"width": "0"}, "positive and finite"),
])
def test_ambiguous_missing_dimension_fails_instead_of_hiding_a_panel(attributes, match):
    root, _ = report_image(**attributes)
    with pytest.raises(ValueError, match=match):
        renderer.static_tree(root, "static")


def test_missing_dimension_with_non_png_data_is_rejected():
    root = ET.Element("svg")
    ET.SubElement(root, "image", width="10", href="data:image/png;base64,AAAA")
    with pytest.raises(ValueError, match="Invalid embedded PNG header"):
        renderer.static_tree(root, "static")


def test_selected_layer_is_visible_and_other_layer_is_removed_without_mutating_source():
    root = ET.Element("svg")
    bg = ET.SubElement(root, "g", {"class": "background-svg"})
    ET.SubElement(bg, "image", href=png_href(), width="12")
    fg = ET.SubElement(root, "g", {"class": "foreground-svg"})
    ET.SubElement(fg, "image", href=png_href(), width="20")
    result = renderer.static_tree(root, "background-svg")
    groups = [x for x in result if x.tag == "g"]
    assert len(groups) == 1 and groups[0].get("class") == "background-svg"
    assert "opacity:1" in groups[0].get("style")
    assert groups[0][0].get("height") == "6"
    assert len(root) == 2 and bg[0].get("height") is None and fg[0].get("height") is None


def test_selects_actual_anatomical_and_functional_report_names():
    selected = [
        "sub-1_ses-1_space-MNI152NLin6Asym_T1w.svg",
        "sub-1_ses-1_space-MNI152NLin2009cAsym_T1w.svg",
        "sub-1_ses-1_dseg.svg",
        "sub-1_ses-1_desc-reconall_T1w.svg",
        "sub-1_ses-1_task-rest_desc-coreg_bold.svg",
        "sub-1_ses-1_task-rest_desc-sdc_bold.svg",
        "sub-1_ses-1_task-rest_desc-carpetplot_bold.svg",
    ]
    assert all(renderer.selected_fmriprep_report(name) for name in selected)


def test_excludes_unrelated_report_names():
    assert not renderer.selected_fmriprep_report("sub-1_ses-1_task-rest_desc-rois_bold.svg")
    assert not renderer.selected_fmriprep_report("sub-1_ses-1_space-MNI152NLin6Asym_bold.svg")
