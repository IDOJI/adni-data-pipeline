import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import warnings

import nibabel as nib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "02_custom/s7a_volume_workflow"))
import qc_images


class StreamQCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def image(self, name, data, affine=None):
        path = self.root / name
        nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.float32), np.eye(4) if affine is None else affine), path)
        return path

    def test_nonfinite_counts_and_finite_only_sample_variance(self):
        data = np.zeros((3, 3, 3, 4), dtype=np.float32)
        data[0, 0, 0] = [1, 2, 3, 4]
        data[1, 1, 1] = [1, np.nan, np.inf, -np.inf]
        path = self.image("raw.nii.gz", data)
        mask = np.zeros((3, 3, 3)); mask[0, 0, 0] = 1
        mask_path = self.image("mask.nii.gz", mask)
        stats, mean = qc_images.stream_stats(path, mask_path)
        self.assertEqual(stats["raw_volume_count"], 4)
        self.assertEqual(stats["nonfinite_value_count"], 3)
        self.assertEqual(stats["nan_value_count"], 1)
        self.assertEqual(stats["positive_infinity_value_count"], 1)
        self.assertEqual(stats["negative_infinity_value_count"], 1)
        self.assertAlmostEqual(stats["brain_mask"]["sample_temporal_variance"]["median"], 5 / 3)
        self.assertEqual(stats["brain_mask"]["nonfinite_value_count"], 0)
        self.assertEqual(float(mean.dataobj[0, 0, 0]), 2.5)
        self.assertEqual(stats["streaming"]["maximum_loaded_frames"], 1)
        json.dumps(stats, allow_nan=False)

    def test_workspace_cap_fails_before_streaming(self):
        path = self.image("raw.nii", np.ones((5, 5, 5, 3)))
        with self.assertRaises(qc_images.QCError):
            qc_images.stream_stats(path, max_working_mib=0.0001)

    def test_mask_grid_mismatch_fails(self):
        path = self.image("raw.nii", np.ones((3, 3, 3, 3)))
        mask = self.image("mask.nii", np.ones((3, 3, 3)), np.diag([2, 2, 2, 1]))
        with self.assertRaises(qc_images.QCError):
            qc_images.stream_stats(path, mask)

    def test_output_cannot_overlap_input(self):
        data = self.root / "data"; data.mkdir()
        with self.assertRaises(qc_images.QCError):
            qc_images.validate_paths(data, data / "qc")

    def test_mosaic_renders_small_synthetic_volume(self):
        data = np.zeros((15, 15, 15)); data[3:12, 3:12, 3:12] = 1
        image = nib.Nifti1Image(data.astype(np.float32), np.eye(4))
        path = self.root / "qc.png"
        qc_images.plot_mosaic(image, path, "Synthetic smoke test")
        self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))

    def test_mask_cuts_exclude_neck_and_empty_extremes_in_world_coordinates(self):
        mask = np.zeros((15, 15, 50)); mask[3:12, 3:12, 20:40] = 1
        affine = np.diag([2, 2, 2, 1]); affine[2, 3] = -80
        path = self.image("brain_mask.nii.gz", mask, affine)
        cuts = qc_images.mask_axial_cuts(path)
        self.assertEqual(len(cuts), 7)
        # Occupied world-z range -40..-2; remove 10% from both ends.
        self.assertAlmostEqual(cuts[0], -36.2)
        self.assertAlmostEqual(cuts[-1], -5.8)
        self.assertTrue(all(a < b for a, b in zip(cuts, cuts[1:])))

    def test_discrete_tissues_use_contours_without_canny_edges(self):
        labels = np.zeros((25, 25, 25), dtype=np.float32)
        labels[3:22, 3:22, 3:22] = 1
        labels[5:20, 5:20, 3:22] = 2
        labels[8:17, 8:17, 3:22] = 3
        mask = nib.Nifti1Image((labels > 0).astype(np.float32), np.eye(4))
        segmentation = nib.Nifti1Image(labels, np.eye(4))
        background = nib.Nifti1Image(labels * 30, np.eye(4))
        output = self.root / "discrete_tissues.png"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            qc_images.plot_mosaic(background, output, "Discrete tissue contours",
                                  label_contours=[(segmentation, "gold")],
                                  contours=[(mask, "cyan")], cut_mask=mask)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
        self.assertFalse([w for w in caught if issubclass(w.category, RuntimeWarning)])
        with mock.patch.object(qc_images.plotting, "plot_anat") as draw:
            qc_images.plot_mosaic(background, output, "Contour dispatch",
                                  label_contours=[(segmentation, "gold")], cut_mask=mask)
            display = draw.return_value
            display.add_edges.assert_not_called()
            self.assertEqual(display.add_contours.call_args.kwargs["levels"], [1.5, 2.5])


if __name__ == "__main__":
    unittest.main()
