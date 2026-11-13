from pathlib import Path
import sys

import nibabel as nib
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import image_tools as images


def save(path, data, affine=None):
    nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.float32), np.eye(4) if affine is None else affine), path)
    return path


def test_stream_counts_nonfinite_and_known_temporal_variance(tmp_path):
    data = np.zeros((3, 3, 3, 4), dtype=np.float32)
    data[0, 0, 0] = [1, 2, 3, 4]
    data[1, 1, 1] = [1, np.nan, np.inf, -np.inf]
    mask = np.zeros((3, 3, 3)); mask[0, 0, 0] = 1
    report, mean = images.stream_stats(save(tmp_path / "SYNTHETIC.nii.gz", data), save(tmp_path / "mask.nii.gz", mask))
    assert report["nonfinite_value_count"] == 3
    assert report["brain_mask"]["nonfinite_value_count"] == 0
    assert report["brain_mask"]["sample_temporal_variance"]["median"] == pytest.approx(5 / 3)
    assert float(mean.dataobj[0, 0, 0]) == 2.5


def test_stream_rejects_mask_grid_mismatch(tmp_path):
    data = save(tmp_path / "data.nii.gz", np.ones((3, 3, 3, 4)))
    mask = save(tmp_path / "mask.nii.gz", np.ones((3, 3, 3)), np.diag([2., 2., 2., 1.]))
    with pytest.raises(images.QCError, match="grids differ"):
        images.stream_stats(data, mask)


def test_stream_rejects_workspace_over_cap(tmp_path):
    path = save(tmp_path / "data.nii.gz", np.ones((3, 3, 3, 4)))
    with pytest.raises(images.QCError, match="exceeds requested cap"):
        images.stream_stats(path, max_working_mib=0.0001)


def test_mosaic_renders_with_installed_native_libraries(tmp_path):
    data = np.zeros((15, 15, 15), dtype=np.float32)
    data[3:12, 3:12, 3:12] = 1
    path = tmp_path / "SYNTHETIC.png"
    images.plot_mosaic(nib.Nifti1Image(data, np.eye(4)), path, "Synthetic software test")
    assert path.read_bytes().startswith(b"\x89PNG")
