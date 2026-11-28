"""Prove that the narrow XCP-D metadata fix cannot change voxel payloads."""
import gzip
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline/s7a_volume_workflow"))
import repair_xcpd_metadata as repair


def image(path, units=10, tr=1.5, endian='<', value=1.0):
    prefix = bytearray(352)
    struct.pack_into(endian + 'i', prefix, 0, 348)
    struct.pack_into(endian + '8h', prefix, 40, 4, 2, 2, 2, 4, 1, 1, 1)
    struct.pack_into(endian + '2h', prefix, 70, 64, 64)
    struct.pack_into(endian + '8f', prefix, 76, 1, 2, 2, 2, tr, 1, 1, 1)
    struct.pack_into(endian + 'f', prefix, 108, 352)
    prefix[123] = units
    struct.pack_into(endian + '2h', prefix, 252, 0, 2)
    struct.pack_into(endian + '12f', prefix, 280, 2, 0, 0, -10, 0, 2, 0, -10, 0, 0, 2, -10)
    prefix[344:348] = b'n+1\0'
    data = bytes(prefix) + struct.pack(endian + '32d', *[value + i / 100 for i in range(32)])
    with gzip.open(path, 'wb') as f:
        f.write(data)


class MetadataRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.xroot = self.root / 'derivatives/xcp_d'
        self.func = self.xroot / 'sub-test/ses-one/func'
        self.func.mkdir(parents=True)
        self.proot = self.root / 'metadata_repairs'
        base = 'sub-test_ses-one_task-rest_space-MNI152NLin2009cAsym_res-2_desc-'
        self.ref = self.func / (base + 'denoised_bold.nii.gz')
        self.target = self.func / (base + 'denoisedSmoothed_bold.nii.gz')
        image(self.ref)
        image(self.target, units=0, value=2.0)
        self.rjson = self.ref.with_name(self.ref.name[:-7] + '.json')
        self.tjson = self.target.with_name(self.target.name[:-7] + '.json')
        self.rjson.write_text(json.dumps({'RepetitionTime': 1.5}))
        self.tjson.write_text(json.dumps({'FWHM': 6}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_repair(self, apply=True):
        return repair.repair_run(self.xroot, 'test', 'one', self.proot, apply=apply)

    def test_actual_failure_units_only_corrects_one_byte_and_preserves_TR(self):
        original = self.target.read_bytes()
        raw_before = gzip.decompress(original)
        ref_before, json_before = self.ref.read_bytes(), self.tjson.read_bytes()
        result = self.run_repair()
        raw_after = gzip.decompress(self.target.read_bytes())
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(result['changed_prefix_byte_offsets'], [123])
        self.assertTrue(result['TR_numeric_value_preserved'])
        self.assertEqual(raw_before[352:], raw_after[352:])
        self.assertEqual(result['before_payload_sha256'], result['after_payload_sha256'])
        self.assertEqual(result['payload_bytes'], 256)
        self.assertEqual(Path(result['original_compressed_backup']).read_bytes(), original)
        self.assertEqual(self.ref.read_bytes(), ref_before)
        self.assertEqual(self.tjson.read_bytes(), json_before)
        self.assertEqual(repair.nifti_prefix(self.target)['units'], 10)
        self.assertEqual(Path(result['record']).parent.joinpath('repair_source.py').read_bytes(), repair.SOURCE_BYTES)
        self.assertEqual(raw_before[252:328], raw_after[252:328])

    def test_default_TR_with_unknown_units_is_restored_big_endian(self):
        image(self.ref, endian='>')
        image(self.target, units=0, tr=1, endian='>', value=2)
        result = self.run_repair()
        self.assertFalse(result['TR_numeric_value_preserved'])
        self.assertEqual(repair.nifti_prefix(self.target)['zooms'][3], 1.5)
        self.assertTrue(set(result['changed_prefix_byte_offsets']) <= {92, 93, 94, 95, 123})

    def test_dry_run_does_not_write_any_file(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.run_repair(apply=False)
        self.assertEqual(result['status'], 'would_repair')
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_second_apply_is_no_op_without_backup_or_recompression(self):
        self.run_repair()
        before = self.target.read_bytes()
        records = list(self.proot.rglob('repair.json'))
        result = self.run_repair()
        self.assertEqual(result['status'], 'already_valid_no_op')
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(list(self.proot.rglob('repair.json')), records)

    def test_conflicting_valid_TR_unknown_nondefault_TR_or_units_rejected(self):
        for units, tr in [(10, 1), (0, 2), (18, 1500), (2, 1.5)]:
            with self.subTest(units=units, tr=tr):
                image(self.target, units=units, tr=tr)
                before = self.target.read_bytes()
                with self.assertRaises(repair.RepairError):
                    self.run_repair()
                self.assertEqual(self.target.read_bytes(), before)

    def test_reference_or_target_JSON_TR_conflict_rejected(self):
        for path in (self.rjson, self.tjson):
            old = path.read_bytes()
            path.write_text(json.dumps({'RepetitionTime': 2.0}))
            with self.assertRaises(repair.RepairError):
                self.run_repair()
            path.write_bytes(old)

    def test_affine_shape_and_spatial_zoom_mismatch_rejected(self):
        original = self.target.read_bytes()
        for offset, format_, value in [(292, 'f', -11), (48, 'h', 5), (80, 'f', 3)]:
            with self.subTest(offset=offset):
                data = bytearray(gzip.decompress(original))
                struct.pack_into('<' + format_, data, offset, value)
                self.target.write_bytes(gzip.compress(data))
                with self.assertRaises(repair.RepairError):
                    self.run_repair()
        self.target.write_bytes(original)

    def test_truncated_payload_cannot_replace_original(self):
        data = gzip.decompress(self.target.read_bytes())[:-8]
        self.target.write_bytes(gzip.compress(data))
        original = self.target.read_bytes()
        with self.assertRaisesRegex(repair.RepairError, 'payload'):
            self.run_repair()
        self.assertEqual(self.target.read_bytes(), original)
        record = json.loads(next(self.proot.rglob('repair.json')).read_text())
        self.assertEqual(record['status'], 'failed')
        self.assertFalse(list(self.func.glob('*.repair.tmp')))

    def test_file_lock_blocks_duplicate_without_removing_existing_lock(self):
        lock = self.target.with_name('.' + self.target.name + '.metadata-repair.lock')
        lock.write_text('other process')
        with self.assertRaisesRegex(repair.RepairError, 'lock exists'):
            self.run_repair()
        self.assertEqual(lock.read_text(), 'other process')

    def test_symlink_target_and_overlapping_provenance_rejected(self):
        elsewhere = self.root / 'outside.nii.gz'
        self.target.rename(elsewhere)
        self.target.symlink_to(elsewhere)
        with self.assertRaisesRegex(repair.RepairError, 'Symlink'):
            self.run_repair()
        self.target.unlink()
        elsewhere.rename(self.target)
        with self.assertRaisesRegex(repair.RepairError, 'separate provenance'):
            repair.repair_run(self.xroot, 'test', 'one', self.func / 'provenance', apply=True)

    def test_failed_atomic_replace_keeps_original_and_backup(self):
        original = self.target.read_bytes()
        real_replace = repair.os.replace
        def replace(source, destination):
            if Path(destination) == self.target:
                raise OSError('simulated replacement failure')
            return real_replace(source, destination)
        with mock.patch.object(repair.os, 'replace', side_effect=replace):
            with self.assertRaises(OSError):
                self.run_repair()
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(next(self.proot.rglob('original_*.nii.gz')).read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
