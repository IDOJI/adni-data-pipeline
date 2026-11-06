"""Native-source provenance, ordinary Git edits and runtime integrity contracts."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_protocol_source', ROOT / '04_workflow/protocol_source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / 'repository'
    root = repo / 'RS-fMRI'
    shutil.copytree(ROOT / '01_upstream/ADNI_fMRI_protocol', root / '01_upstream/ADNI_fMRI_protocol',
                    ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', '.git'))
    (root / '03_config').mkdir()
    for name in ('upstream.lock.json', 'protocol_sources.json', 'protocol_history.json'):
        shutil.copy2(ROOT / '03_config' / name, root / '03_config' / name)
    git(repo, 'init', '-q')
    git(repo, 'add', '-f', '.')
    git(repo, '-c', 'user.name=Test', '-c', 'user.email=synthetic@example.invalid',
        'commit', '-qm', 'Synthetic native-source fixture')
    return repo, root


def test_fresh_native_checkout_needs_no_upstream_git_or_network(checkout):
    repo, root = checkout
    assert not (root / '01_upstream/ADNI_fMRI_protocol/.git').exists()
    result = source.inspect_protocol(root)
    assert result['distribution'] == 'integrated-source'
    assert result['protocol_clean'] and result['protocol_files'] == 76
    assert result['original_history_commits'] == 153
    assert result['repository_commit'] == git(repo, 'rev-parse', 'HEAD').decode().strip()


def test_owned_code_can_change_without_repinning_original_commit(checkout):
    repo, root = checkout
    path = root / '01_upstream/ADNI_fMRI_protocol/s8_final_qc/summarize_motion_from_confounds.py'
    original = source.inspect_protocol(root)
    path.write_text(path.read_text() + '\n# Synthetic reviewed edit.\n')
    with pytest.raises(ValueError, match='uncommitted source'):
        source.inspect_protocol(root)
    git(repo, 'add', str(path))
    with pytest.raises(ValueError, match='uncommitted source'):
        source.inspect_protocol(root)
    git(repo, '-c', 'user.name=Test', '-c', 'user.email=synthetic@example.invalid',
        'commit', '-qm', 'Synthetic reviewed source change')
    changed = source.inspect_protocol(root)
    assert changed['protocol_clean']
    assert changed['protocol_source_sha256'] != original['protocol_source_sha256']
    assert changed['upstream_commit'] == original['upstream_commit']
    assert 's8_final_qc/summarize_motion_from_confounds.py' in changed['modified_from_import']


def test_untracked_source_and_staged_deletion_are_rejected(checkout):
    repo, root = checkout
    protocol = root / '01_upstream/ADNI_fMRI_protocol'
    extra = protocol / 'utils/unreviewed.py'
    extra.write_text('# Synthetic unreviewed module.\n')
    with pytest.raises(ValueError, match='uncommitted source'):
        source.inspect_protocol(root)
    extra.unlink()
    git(repo, 'rm', str(protocol / 'utils/config_tools.py'))
    with pytest.raises(ValueError, match='uncommitted source'):
        source.inspect_protocol(root)


def test_missing_source_and_changed_license_are_rejected(checkout):
    repo, root = checkout
    protocol = root / '01_upstream/ADNI_fMRI_protocol'
    file = protocol / 'LICENSE'
    original = file.read_bytes()
    file.write_text('synthetic incompatible replacement')
    with pytest.raises(ValueError, match='GPL license'):
        source.inspect_protocol(root)
    file.write_bytes(original)
    (protocol / 'CITATION.cff').unlink()
    with pytest.raises(ValueError, match='missing'):
        source.inspect_protocol(root)


def test_inert_legacy_marker_is_not_a_runtime_dependency(checkout):
    repo, root = checkout
    before = source.inspect_protocol(root)
    marker = root / '01_upstream/ADNI_fMRI_protocol/.git'
    marker.write_text('gitdir: /nonexistent/legacy-metadata\n')
    after = source.inspect_protocol(root)
    assert after['legacy_git_metadata_present']
    assert after['protocol_source_sha256'] == before['protocol_source_sha256']


def test_origin_manifest_and_history_index_are_consistent(checkout):
    repo, root = checkout
    path = root / '03_config/protocol_history.json'
    history = json.loads(path.read_text())
    history['commit_count'] += 1
    path.write_text(json.dumps(history))
    with pytest.raises(ValueError, match='metadata disagree'):
        source.inspect_protocol(root)


def test_import_contains_source_and_attribution_instead_of_subject_results():
    manifest = json.loads((ROOT / '03_config/protocol_sources.json').read_text())
    assert manifest['files']['LICENSE']
    assert manifest['files']['CITATION.cff']
    assert all(Path(name).suffix not in {'.csv', '.tsv', '.nii', '.gz', '.png', '.svg', '.html', '.ipynb'}
               for name in manifest['files'])


def test_sample_size_rendering_uses_explicit_synthetic_input(tmp_path):
    path = ROOT / '01_upstream/ADNI_fMRI_protocol/s8_final_qc/make_sample_size_table.py'
    spec = importlib.util.spec_from_file_location('integrated_sample_size', path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest = tmp_path / 'synthetic_stages.tsv'
    manifest.write_text('stage\tfolder\tdescription\tcount_from\tsubjects\tsessions\n'
                        'Synthetic start\ts3/\tSynthetic fixture only\t\t10\t20\n'
                        'Synthetic final\ts8/\tSynthetic fixture only\t\t8\t15\n')
    stages = module.load_stages(manifest, 'sub', 'ses')
    assert stages[-1].dropped_str == '2/5'
    assert 'Synthetic final' in module.render_markdown(stages)


def test_notebook_reference_copies_have_no_recorded_execution_outputs():
    import hashlib
    manifest = json.loads((ROOT / '03_config/protocol_notebooks.json').read_text())
    assert len(manifest['notebooks']) == 5
    for record in manifest['notebooks']:
        path = ROOT / record['export_path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['export_sha256']
        notebook = json.loads(path.read_text())
        assert notebook['metadata']['source_import']['original_blob'] == record['original_blob']
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                assert cell['outputs'] == [] and cell['execution_count'] is None
