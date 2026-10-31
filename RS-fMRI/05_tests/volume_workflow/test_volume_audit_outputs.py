"""Behavioral audit tests: temporal alignment, provenance, and explicit incompleteness."""
import csv
import gzip
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "02_custom/s7a_volume_workflow"))
from audit_outputs import Audit, AuditError, column, infer_dummy, motion_duration_gate, nifti_header, sha256, xcpd_output_root


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def save_tsv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(fields)
        writer.writerows(rows)


def save_nifti(path, n=8, tr=1.5, version=1, endian='<', units=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    if version == 1:
        header = bytearray(352)
        struct.pack_into(endian + 'i', header, 0, 348)
        struct.pack_into(endian + '8h', header, 40, 4, 2, 2, 2, n, 1, 1, 1)
        struct.pack_into(endian + '8f', header, 76, 1, 2, 2, 2, tr, 0, 0, 0)
        struct.pack_into(endian + 'h', header, 70, 16)
        struct.pack_into(endian + 'h', header, 72, 32)
        struct.pack_into(endian + 'f', header, 108, 352)
        header[123] = units
        header[344:348] = b'n+1\x00'
    else:
        header = bytearray(544)
        struct.pack_into(endian + 'i', header, 0, 540)
        header[4:12] = b'n+2\x00\r\n\x1a\n'
        struct.pack_into(endian + '8q', header, 16, 4, 2, 2, 2, n, 1, 1, 1)
        struct.pack_into(endian + '8d', header, 104, 1, 2, 2, 2, tr, 0, 0, 0)
        struct.pack_into(endian + 'i', header, 500, units)
    with gzip.open(path, 'wb') as f:
        f.write(header)
        f.write(bytes(2 * 2 * 2 * n * 4))


def make_fixture(root):
    case = Path('sub-test/ses-one')
    base = 'sub-test_ses-one_task-rest'
    raw = root / 'bids' / case / 'func' / f'{base}_bold.nii.gz'
    save_nifti(raw)
    save_json(raw.with_name(f'{base}_bold.json'), {'RepetitionTime': 1.5})
    t1 = root / 'bids' / case / 'anat/sub-test_ses-one_T1w.nii.gz'
    save_nifti(t1, n=1)
    save_json(t1.with_name('sub-test_ses-one_T1w.json'), {})
    files = [{'path': str(p.relative_to(root / 'bids')), 'bytes': p.stat().st_size,
              'sha256': sha256(p), 'phase': 'ADNI4'} for p in (root / 'bids').rglob('*') if p.is_file()]
    save_json(root / 'logs/staging_manifest.json', {'files': files})
    froot = root / 'derivatives/fmriprep'
    func = froot / case / 'func'
    preproc = func / f'{base}_space-MNI152NLin2009cAsym_res-2_desc-preproc_bold.nii.gz'
    save_nifti(preproc)
    save_json(preproc.with_name(preproc.name[:-7] + '.json'), {'RepetitionTime': 1.5})
    fields = ['rot_x', 'rot_y', 'rot_z', 'trans_x', 'trans_y', 'trans_z', 'framewise_displacement',
              'non_steady_state_outlier00', 'non_steady_state_outlier01']
    translations = [0, .05, .2, .8, .8, 1.4, 1.4, 1.4]
    fds = [0, .05, .15, .6, 0, .6, 0, 0]
    rows = [[0, 0, 0, t, 0, 0, fd if i else 'n/a', int(i == 0), int(i == 1)]
            for i, (t, fd) in enumerate(zip(translations, fds))]
    extra = [key + '_derivative1' for key in ['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z']]
    extra += [f'{t}_comp_cor_{i:02d}' for t in ['w', 'c'] for i in range(5)] + ['cosine00']
    fields += extra
    rows = [row + [float(i * (j + 1)) / 100 for j in range(len(extra))] for i, row in enumerate(rows)]
    save_tsv(func / f'{base}_desc-confounds_timeseries.tsv', fields, rows)
    fig = froot / 'sub-test/figures' / f'{base}_desc-summary_bold.html'
    fig.parent.mkdir(parents=True)
    fig.write_text('<ul><li>Susceptibility distortion correction: fieldmap-less (SyN)</li></ul>')
    xroot = root / 'derivatives/xcp_d'
    xfunc = xroot / case / 'func'
    flags = [0, 1, 0, 1, 0, 0]
    # --output-layout bids does not append a parameter hash (26.2.0 source).
    mask_cols = ['framewise_displacement', 'censor_between', 'denoising']
    save_tsv(xfunc / f'{base}_outliers.tsv', mask_cols, [[flag, 0, flag] for flag in flags])
    save_tsv(xfunc / f'{base}_motion.tsv', ['framewise_displacement'], [[fd] for fd in fds[2:]])
    design_fields = [key for key in fields if key not in ['framewise_displacement',
                     'non_steady_state_outlier00', 'non_steady_state_outlier01']]
    save_tsv(xfunc / f'{base}_design.tsv', design_fields,
             [[row[fields.index(key)] for key in design_fields] for row in rows[2:]])
    for desc in ['denoised', 'denoisedSmoothed']:
        p = xfunc / f'{base}_space-MNI152NLin2009cAsym_res-2_desc-{desc}_bold.nii.gz'
        save_nifti(p, n=4)
        meta = {'SoftwareFilters': {'Bandpass filter': {'High-pass cutoff (Hz)': .01,
                'Low-pass cutoff (Hz)': .08, 'Filter order': 2}}}
        if desc == 'denoisedSmoothed':
            meta['FWHM'] = 6
        save_json(p.with_name(p.name[:-7] + '.json'), meta)
    save_tsv(xfunc / f'{base}_space-MNI152NLin2009cAsym_desc-linc_qc.tsv',
             ['num_censored_volumes', 'num_retained_volumes', 'num_dummy_volumes',
              'mean_fd', 'mean_fd_post_censoring'], [[2, 4, 2, .225, .0375]])
    for stage, out in [('fmriprep', froot), ('xcpd', xroot)]:
        save_json(out / 'dataset_description.json', {'GeneratedBy': [{'Name': stage, 'Version': 'test'}]})
        (out / 'sub-test.html').write_text('<html>Report</html>')
        log = root / f'logs/20261028_{stage}'
        save_json(log / 'run.json', {'stage': stage, 'run': {'subject': 'test', 'session': 'one'},
                  'started_at': '2026-10-28T10:00:00+00:00', 'status': 'execution_completed_qc_required',
                  'exit_code': 0, 'input_unchanged': True})
        save_json(log / 'input_before.json', {'raw': {'sha256': 'example'}})
        save_json(log / 'input_after.json', {'raw': {'sha256': 'example'}})


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def audit(self, stage='all'):
        return Audit(self.root, 'test', 'one', stage=stage).run()

    def test_recorded_visit_output_is_used_instead_of_default_dataset(self):
        original = self.root / 'derivatives/xcp_d'
        isolated = self.root / 'derivatives/xcp_d_visit'
        original.rename(isolated)
        path = self.root / 'logs/20261028_xcpd/run.json'
        data = json.loads(path.read_text())
        data['config'] = {'paths': {'bids': str(self.root / 'bids'), 'xcpd_output': str(isolated)}}
        save_json(path, data)
        result = self.audit()
        self.assertTrue(result['technical_checks_passed'], result)
        self.assertEqual(result['xcpd_output_root'], str(isolated.resolve()))

    def test_recorded_host_path_maps_to_container_runtime(self):
        path = self.root / 'logs/20261028_xcpd/run.json'
        data = json.loads(path.read_text())
        data['config'] = {'paths': {'bids': '/host/runtime/bids',
                                    'xcpd_output': '/host/runtime/derivatives/xcp_d_visit'}}
        save_json(path, data)
        self.assertEqual(xcpd_output_root(self.root, 'test', 'one'),
                         self.root.resolve() / 'derivatives/xcp_d_visit')

    def test_recorded_output_outside_runtime_is_rejected(self):
        path = self.root / 'logs/20261028_xcpd/run.json'
        data = json.loads(path.read_text())
        data['config'] = {'paths': {'bids': '/host/runtime/bids', 'xcpd_output': '/other/data'}}
        save_json(path, data)
        with self.assertRaises(AuditError):
            xcpd_output_root(self.root, 'test', 'one')

    def test_temporal_alignment_and_duration_are_separate(self):
        result = self.audit()
        self.assertTrue(result['technical_checks_passed'], result)
        x = result['xcpd']
        self.assertEqual(x['dummy_volumes'], 2)
        self.assertEqual(x['retained_original_indices_zero_based'], [2, 4, 6, 7])
        self.assertEqual(x['retained_seconds'], 6)
        self.assertFalse(x['meets_duration_criterion'])
        self.assertFalse(x['passes_automated_motion_duration_gate'])
        self.assertEqual(x['censored_fraction_denominator_volumes'], 6)
        self.assertEqual(x['analysis_inclusion'], 'excluded_by_prospective_motion_duration_gate')
        self.assertEqual(result['scientific_qc'], 'not_assessed')

    def test_off_by_one_mask_is_detected(self):
        p = next(self.root.rglob('*outliers.tsv'))
        p.write_text(p.read_text().rsplit('\n', 2)[0] + '\n')
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:mask_rows_after_dummy_removal' and not c['passed']
                            for c in result['checks']))

    def test_inverted_mask_is_detected(self):
        p = next(self.root.rglob('*outliers.tsv'))
        save_tsv(p, ['framewise_displacement', 'censor_between', 'denoising'],
                 [[1-x, 0, 1-x] for x in [0, 1, 0, 1, 0, 0]])
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:FD_mask_matches_unfiltered_50mm_FD' and not c['passed']
                            for c in result['checks']))

    def test_raw_mutation_is_detected(self):
        p = next((self.root / 'bids').rglob('*bold.json'))
        save_json(p, {'RepetitionTime': 1.5, 'unexpected': True})
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'].startswith('staging_hash:') and not c['passed'] for c in result['checks']))

    def test_incomplete_xcpd_does_not_pass(self):
        next(self.root.rglob('*desc-denoisedSmoothed_bold.nii.gz')).unlink()
        self.assertFalse(self.audit()['technical_checks_passed'])
        self.assertTrue(self.audit(stage='fmriprep')['technical_checks_passed'])

    def test_latest_failed_execution_overrides_existing_outputs(self):
        save_json(self.root / 'logs/later/run.json', {'stage': 'xcpd',
                  'run': {'subject': 'test', 'session': 'one'}, 'started_at': '2026-10-28T11:00:00+00:00',
                  'status': 'failed', 'exit_code': 1, 'input_unchanged': True})
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])

    def test_html_snippet_is_not_a_subject_report(self):
        (self.root / 'derivatives/fmriprep/sub-test.html').unlink()
        self.assertFalse(self.audit(stage='fmriprep')['technical_checks_passed'])

    def test_real_session_report_layout_is_accepted(self):
        for name in ('fmriprep', 'xcp_d'):
            root = self.root / 'derivatives' / name
            report = root / 'sub-test/ses-one/sub-test_ses-one.html'
            (root / 'sub-test.html').rename(report)
        self.assertTrue(self.audit()['technical_checks_passed'])

    def test_citation_and_other_subject_or_session_cannot_replace_report(self):
        root = self.root / 'derivatives/xcp_d'
        (root / 'sub-test.html').unlink()
        for relative in ('sub-test/logs/CITATION.html', 'sub-test2.html',
                         'sub-test/ses-other/sub-test_ses-other.html',
                         'sub-test/ses-other/sub-test.html', 'sub-test_ses-one2.html'):
            p = root / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('<html>Not the selected report</html>')
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:assembled_html_report' and not c['passed']
                            for c in result['checks']))

    def test_multiverse_hashed_names_and_columns_are_unambiguous(self):
        root = self.root / 'derivatives/xcp_d'
        for p in list(root.rglob('*.tsv')):
            with p.open() as f:
                rows = list(csv.reader(f, delimiter='\t'))
            save_tsv(p, [name + '_hash-abc123' for name in rows[0]], rows[1:])
        for p in list((root / 'sub-test/ses-one/func').iterdir()):
            # Hash is a BIDS entity, and therefore sits before the final suffix.
            stem, suffix = p.name.rsplit('_', 1)
            p.rename(p.with_name(stem + '_hash-abc123_' + suffix))
        (root / 'sub-test.html').rename(root / 'sub-test_hash-abc123.html')
        self.assertTrue(self.audit()['technical_checks_passed'])

    def test_motion_dummy_rows_must_be_removed_in_pinned_xcpd(self):
        p = next(self.root.rglob('*motion.tsv'))
        save_tsv(p, ['framewise_displacement'], [[v] for v in [0, .05, .15, .6, 0, .6, 0, 0]])
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:motion_FD_alignment' and not c['passed']
                            for c in result['checks']))

    def test_missing_smoothed_filter_metadata_does_not_crash_or_pass(self):
        p = next(self.root.rglob('*desc-denoisedSmoothed_bold.json'))
        save_json(p, {'FWHM': 6, 'SoftwareFilters': None})
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertNotIn('error', result)
        self.assertTrue(any(c['name'].startswith('xcpd:denoisedSmoothed_bandpass_') and not c['passed']
                            for c in result['checks']))

    def test_ambiguous_QC_parameter_columns_cannot_silently_override(self):
        p = next(self.root.rglob('*qc.tsv'))
        with p.open() as f:
            rows = list(csv.reader(f, delimiter='\t'))
        save_tsv(p, rows[0] + ['mean_fd_hash-other'], [row + ['.225'] for row in rows[1:]])
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:QC_unique_base_columns' and not c['passed']
                            for c in result['checks']))

    def test_nifti2_big_endian_milliseconds(self):
        p = self.root / 'nifti2.nii.gz'
        save_nifti(p, version=2, endian='>', tr=1500, units=18)
        result = nifti_header(p)
        self.assertEqual(result['shape'], [2, 2, 2, 8])
        self.assertEqual(result['tr_seconds'], 1.5)

    def test_truncated_header_rejected(self):
        p = self.root / 'broken.nii.gz'
        with gzip.open(p, 'wb') as f:
            f.write(b'\x00' * 200)
        with self.assertRaises(AuditError):
            nifti_header(p)

    def test_noncontiguous_nss_matches_auto_semantics(self):
        r = infer_dummy(['non_steady_state_outlier00'],
                        [{'non_steady_state_outlier00': x} for x in ['1', '0', '1', '0']])
        self.assertEqual(r['auto_dummy_volumes'], 3)
        self.assertFalse(r['flags_are_contiguous_initial_block'])

    def test_ambiguous_hashed_columns_rejected(self):
        with self.assertRaises(AuditError):
            column(['framewise_displacement_hash-abc', 'framewise_displacement_hash-def'],
                   'framewise_displacement')

    def test_sdc_none_does_not_satisfy_syn_protocol(self):
        p = next(self.root.rglob('*desc-summary_bold.html'))
        p.write_text('<li>Susceptibility distortion correction: None</li>')
        self.assertFalse(self.audit(stage='fmriprep')['technical_checks_passed'])
        self.assertTrue(Audit(self.root, 'test', 'one', stage='fmriprep', expected_sdc='none').run()['technical_checks_passed'])

    def test_sdc_anat_accepted_but_requested_syn_not_accepted(self):
        p = next(self.root.rglob('*desc-summary_bold.html'))
        p.write_text('<li>Susceptibility distortion correction: ANAT</li>')
        self.assertTrue(self.audit(stage='fmriprep')['technical_checks_passed'])
        p.write_text('<li>Susceptibility distortion correction: SyN requested but not applied</li>')
        self.assertFalse(self.audit(stage='fmriprep')['technical_checks_passed'])

    def test_missing_wm_component_is_not_treated_as_rank_removal(self):
        p = next(self.root.rglob('*design.tsv'))
        with p.open() as f:
            all_rows = list(csv.reader(f, delimiter='\t'))
        col = all_rows[0].index('w_comp_cor_04')
        new_rows = [row[:col] + row[col+1:] for row in all_rows]
        save_tsv(p, new_rows[0], new_rows[1:])
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:design_exact_acompcor_selection' and not c['passed']
                            for c in result['checks']))

    def test_unintended_gsr_is_detected(self):
        p = next(self.root.rglob('*design.tsv'))
        with p.open() as f:
            all_rows = list(csv.reader(f, delimiter='\t'))
        save_tsv(p, all_rows[0] + ['global_signal_hash-abc123'], [row + ['0'] for row in all_rows[1:]])
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:design_no_global_signal_regression' and not c['passed']
                            for c in result['checks']))

    def test_design_row_shift_is_detected_even_with_correct_length(self):
        p = next(self.root.rglob('*design.tsv'))
        with p.open() as f:
            all_rows = list(csv.reader(f, delimiter='\t'))
        save_tsv(p, all_rows[0], all_rows[2:] + all_rows[1:2])
        result = self.audit()
        self.assertFalse(result['technical_checks_passed'])
        self.assertTrue(any(c['name'] == 'xcpd:design_matches_source_after_dummy_removal' and not c['passed']
                            for c in result['checks']))

    def test_exactly_thirty_percent_censored_satisfies_gate(self):
        gate = motion_duration_gate(300, 90, 1.5)
        self.assertEqual(gate['censored_fraction'], .30)
        self.assertTrue(gate['passes_automated_motion_duration_gate'])
        self.assertTrue(gate['visual_approval_required'])
        self.assertEqual(gate['analysis_inclusion'], 'pending_visual_and_scientific_review')

    def test_above_thirty_percent_is_excluded_despite_sufficient_duration(self):
        gate = motion_duration_gate(300, 91, 1.5)
        self.assertTrue(gate['meets_duration_criterion'])
        self.assertFalse(gate['meets_motion_fraction_criterion'])
        self.assertFalse(gate['passes_automated_motion_duration_gate'])

    def test_exactly_240_seconds_satisfies_gate(self):
        gate = motion_duration_gate(200, 40, 1.5)
        self.assertEqual(gate['retained_seconds'], 240)
        self.assertTrue(gate['passes_automated_motion_duration_gate'])

    def test_below_240_seconds_is_excluded_despite_low_censor_fraction(self):
        gate = motion_duration_gate(200, 41, 1.5)
        self.assertTrue(gate['meets_motion_fraction_criterion'])
        self.assertFalse(gate['meets_duration_criterion'])
        self.assertFalse(gate['passes_automated_motion_duration_gate'])

    def test_empty_post_dummy_run_has_no_defined_fraction_and_fails_gate(self):
        gate = motion_duration_gate(0, 0, 1.5)
        self.assertIsNone(gate['censored_fraction'])
        self.assertFalse(gate['passes_automated_motion_duration_gate'])

    def test_invalid_gate_parameter_is_rejected(self):
        with self.assertRaises(AuditError):
            motion_duration_gate(200, 0, 1.5, maximum_censored_fraction=1.1)
        with self.assertRaises(AuditError):
            motion_duration_gate(200, 201, 1.5)


if __name__ == '__main__':
    unittest.main()
