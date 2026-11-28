import importlib.util
import json
import subprocess
import sys
from pathlib import Path

source = Path(__file__).parents[1] / 'make_source_manifest.py'
if not source.exists():
    source = Path(__file__).with_name('make_source_manifest.py')
spec = importlib.util.spec_from_file_location('make_source_manifest', source)
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)
import nibabel as nib
import numpy as np
import pytest
import yaml


@pytest.fixture
def sample(tmp_path):
    bids = tmp_path / 'bids'
    anat = bids / 'sub-998S9999' / 'ses-20000101' / 'anat'
    func = bids / 'sub-998S9999' / 'ses-20000101' / 'func'
    anat.mkdir(parents=True)
    func.mkdir(parents=True)
    (bids / 'dataset_description.json').write_text(json.dumps({'Name': 'pilot', 'BIDSVersion': '1.9.0'}))
    stem = 'sub-998S9999_ses-20000101'
    t1 = anat / (stem + '_T1w.nii.gz')
    bold = func / (stem + '_task-rest_bold.nii.gz')
    nib.save(nib.Nifti1Image(np.ones((4, 4, 3), dtype=np.float32), np.eye(4)), t1)
    img = nib.Nifti1Image(np.ones((4, 4, 3, 10), dtype=np.float32), np.eye(4))
    img.header.set_xyzt_units('mm', 'sec')
    img.header.set_zooms((1, 1, 1, 1.5))
    nib.save(img, bold)
    (anat / (stem + '_T1w.json')).write_text('{}')
    sidecar = func / (stem + '_task-rest_bold.json')
    sidecar.write_text(json.dumps({'RepetitionTime': 1.5, 'PhaseEncodingDirection': 'j-', 'SliceTiming': [0, 0.5, 1]}))
    proof = tmp_path / 'adni-metadata.csv'
    proof.write_text('phase,participant\nADNI3,998S9999\n')
    evidence = tmp_path / 'phase.json'
    evidence.write_text(json.dumps([{'subject': '998S9999', 'session': '20000101', 'phase': 'ADNI3',
        'matched_row': {'COLPROT': 'ADNI3'}, 'phase_match_basis': 'subject and date',
        'evidence_file': str(proof), 'evidence_file_sha256': manifest.sha(proof),
        'bids_metadata_sha256': manifest.sha(sidecar)}]))
    cfg = {'runtime': str(tmp_path / 'runtime'), 'source_bids': str(bids),
           'source_manifest': str(tmp_path / 'manifest.json'), 'source_phase_evidence': str(evidence),
           'runs': [{'subject': '998S9999', 'session': '20000101', 'phase': 'ADNI3',
                     'ptid': '998_S_9999', 'bold_image_id': 9999999}]}
    return cfg, sidecar, proof, t1, bold


def test_preflight_records_exact_input_hashes_without_writing(sample):
    cfg, _, _, _, _ = sample
    value, visits = manifest.inspect(cfg)
    assert len(value['files']) == 4
    assert visits[0]['BOLD_shape'] == [4, 4, 3, 10]
    assert all(manifest.sha(Path(cfg['source_bids']) / row['path']) == row['sha256'] for row in value['files'])
    assert not Path(cfg['source_manifest']).exists()


def test_duplicate_visit_rejected(sample):
    cfg, *_ = sample
    cfg['runs'].append(dict(cfg['runs'][0]))
    with pytest.raises(ValueError, match='Duplicate'):
        manifest.inspect(cfg)


def test_wrong_phase_evidence_rejected(sample):
    cfg, *_ = sample
    cfg['runs'][0]['phase'] = 'ADNI4'
    with pytest.raises(ValueError, match='phase-evidence'):
        manifest.inspect(cfg)


def test_changed_phase_source_rejected(sample):
    cfg, _, proof, _, _ = sample
    proof.write_text('changed')
    with pytest.raises(ValueError, match='missing or has changed'):
        manifest.inspect(cfg)


def test_inconsistent_tr_rejected(sample):
    cfg, sidecar, *_ = sample
    metadata = json.loads(sidecar.read_text())
    metadata['RepetitionTime'] = 2.0
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='repetition times differ'):
        manifest.inspect(cfg)


def test_missing_slice_timing_rejected(sample):
    cfg, sidecar, *_ = sample
    metadata = json.loads(sidecar.read_text())
    metadata.pop('SliceTiming')
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='SliceTiming'):
        manifest.inspect(cfg)


def test_unrecognized_additional_rest_run_rejected(sample):
    cfg, _, _, _, bold = sample
    extra = bold.with_name(bold.name.replace('_bold', '_run-02_bold'))
    extra.write_bytes(bold.read_bytes())
    with pytest.raises(ValueError, match='multiple'):
        manifest.inspect(cfg)


def test_t2_not_silently_discarded(sample):
    cfg, _, _, t1, _ = sample
    t1.with_name(t1.name.replace('_T1w', '_T2w')).write_bytes(t1.read_bytes())
    with pytest.raises(ValueError, match='T2w'):
        manifest.inspect(cfg)


def test_manifest_cannot_be_written_into_source(sample):
    cfg, *_ = sample
    cfg['source_manifest'] = str(Path(cfg['source_bids']) / 'manifest.json')
    with pytest.raises(ValueError, match='must not overlap'):
        manifest.inspect(cfg)


def test_cli_checks_without_writing_then_writes_once(sample, tmp_path):
    cfg, *_ = sample
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(yaml.safe_dump(cfg))
    script = Path(manifest.__file__)
    check = subprocess.run([sys.executable, str(script), '--config', str(config_path), '--check-only'], capture_output=True, text=True, check=False)
    assert check.returncode == 0 and not Path(cfg['source_manifest']).exists()
    written = subprocess.run([sys.executable, str(script), '--config', str(config_path)], capture_output=True, text=True, check=False)
    assert written.returncode == 0
    original = Path(cfg['source_manifest']).read_bytes()
    assert len(json.loads(original)['files']) == 4
    second = subprocess.run([sys.executable, str(script), '--config', str(config_path)], capture_output=True, text=True, check=False)
    assert second.returncode != 0 and Path(cfg['source_manifest']).read_bytes() == original


def test_evidence_sidecar_hash_must_match_even_when_metadata_are_valid(sample):
    cfg, sidecar, *_ = sample
    metadata = json.loads(sidecar.read_text())
    metadata['TotalReadoutTime'] = 0.03
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='does not match this BOLD JSON'):
        manifest.inspect(cfg)


def test_invalid_phase_encoding_is_rejected(sample):
    cfg, sidecar, *_ = sample
    metadata = json.loads(sidecar.read_text())
    metadata['PhaseEncodingDirection'] = 'PA'
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='PhaseEncodingDirection'):
        manifest.inspect(cfg)
