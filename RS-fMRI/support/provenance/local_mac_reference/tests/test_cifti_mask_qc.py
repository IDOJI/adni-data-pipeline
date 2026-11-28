import importlib.util
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
source = Path(__file__).parents[1] / 'cifti_mask_qc.py'
if not source.exists():
    source = Path(__file__).with_name('cifti_mask_qc.py')
spec = importlib.util.spec_from_file_location('cifti_mask_qc', source)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_constant_detection_distinguishes_zero_nonzero_and_varying():
    data = np.array([[0, 2, 1], [0, 2, 3], [0, 2, 2]], dtype=np.float32)
    first, constant = tool.constants(data, chunk_size=2)
    assert constant.tolist() == [True, True, False]
    assert first.tolist() == [0, 2, 1]


def test_float64_signal_variation_is_not_rounded_away():
    data = np.array([[0., 1.], [0., 1. + 1e-10]], dtype=np.float64)
    _, constant = tool.constants(data)
    assert constant.tolist() == [True, False]


@pytest.mark.parametrize('bad', [np.nan, np.inf, -np.inf])
def test_nonfinite_time_series_rejected(bad):
    with pytest.raises(ValueError, match='Nonfinite'):
        tool.constants(np.array([[0., 1.], [0., bad]]))


def test_native_and_standard_masks_are_reported_separately():
    native = np.ones(32492, dtype=np.float32)
    template = np.zeros(32492, dtype=np.float32)
    vertices = np.array([1, 2, 3, 4])
    template[vertices] = 1
    native[1], native[2], native[3] = 0., 0.04, 0.5
    result = tool.compare_cortex(vertices, [1, 2, 3], native, template)
    assert result['constant_zero_vertices'] == 3
    assert result['individual_cortex_interpolated_exact_zero'] == 1
    assert result['individual_cortex_interpolated_below_threshold'] == 2
    assert result['all_standard_cortical_vertices_below_threshold'] == 2
    assert result['standard_template_ROI_includes'] == 3


def test_cifti_template_mismatch_rejected():
    with pytest.raises(ValueError, match='template ROI differ'):
        tool.compare_cortex([1, 2], [1], np.ones(32492), np.zeros(32492))


def test_zero_vertex_must_belong_to_cifti_model():
    with pytest.raises(ValueError, match='do not belong'):
        tool.compare_cortex([1, 2], [3], np.ones(32492), np.ones(32492))


def test_empty_zero_set_is_valid_and_not_flagged():
    result = tool.compare_cortex([1, 2], [], np.ones(32492), np.ones(32492))
    assert result['constant_zero_vertices'] == 0
    assert result['individual_cortex_interpolated_max'] is None


def test_nearest_sampling_respects_image_affine():
    data = np.zeros((3, 3, 3), dtype=np.uint8)
    data[1, 2, 1] = 7
    affine = np.diag([2., 2., 2., 1.])
    image = nib.Nifti1Image(data, affine)
    assert tool.sample_nearest(image, [[2., 4., 2.]]).tolist() == [7]
    with pytest.raises(ValueError, match='outside'):
        tool.sample_nearest(image, [[10., 0., 0.]])


def test_output_and_input_trees_must_be_disjoint(tmp_path):
    source = tmp_path / 'source'
    assert not tool.disjoint(source, source / 'results')
    assert not tool.disjoint(source / 'results', source)
    assert tool.disjoint(source, tmp_path / 'other')
