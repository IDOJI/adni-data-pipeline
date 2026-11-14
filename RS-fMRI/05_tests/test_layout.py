"""Guard a unified owned pipeline with preserved provenance and optional pins."""
import configparser
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def test_numbered_directories_and_integrated_source_declaration_agree():
    assert (ROOT / 'pipeline').is_dir()
    assert (ROOT / 'provenance').is_dir()
    assert not (ROOT / '01_upstream').exists()
    assert not (ROOT / '02_custom').exists()
    names = ('config', 'workflow', 'tests', 'docs')
    for number, name in enumerate(names, 3):
        assert (ROOT / f'{number:02}_{name}').is_dir()
        assert not (ROOT / name).exists()
    lock = json.loads((ROOT / '03_config/upstream.lock.json').read_text())
    module = configparser.ConfigParser()
    module.read(REPO / '.gitmodules')
    assert 'submodule "upstream/ADNI_fMRI_protocol"' not in module
    assert lock['distribution'] == 'integrated-source'
    entries = subprocess.check_output(['git', '-C', str(REPO), 'ls-files', '--stage', '--',
                                      'RS-fMRI/' + lock['path']], text=True).splitlines()
    assert len(entries) > 1
    gitlinks = [entry for entry in entries if entry.startswith('160000 ')]
    assert len(gitlinks) == 4
    assert all('/s11_atlas_bold/01_sources/' in entry for entry in gitlinks)
    assert len(module.sections()) == 5  # SNP and the four optional atlas sources remain submodules.


def test_document_links_resolve_and_imported_code_hash_is_preserved():
    files = [REPO / 'README.md', ROOT / 'README.md', *sorted((ROOT / '06_docs').glob('*.md')),
             *sorted((ROOT / 'pipeline').glob('*/README.md'))]
    for path in files:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            resolved = (path.parent / target.strip('<>').split('#')[0]).resolve()
            assert resolved.exists(), (path, target)
    imported = json.loads((ROOT / '03_config/imported_sources.json').read_text())['motion_duration_qc']
    assert hashlib.sha256((ROOT / imported['destination']).read_bytes()).hexdigest() == imported['sha256']
    # The external data hierarchy and upstream source schema keep their names.
    assert 'ADNI_DATA/config/' in (ROOT / 'README.md').read_text()
    assert (ROOT / 'pipeline/config/config_adni.yaml').is_file()


def test_ci_pytest_and_private_configuration_paths_are_current():
    config = configparser.ConfigParser()
    config.read(ROOT / 'pytest.ini')
    assert config['pytest']['testpaths'] == '05_tests'
    assert 'provenance' in config['pytest']['norecursedirs'].split()
    ci = yaml.safe_load((REPO / '.github/workflows/tests.yml').read_text())
    job = ci['jobs']['synthetic-validation']
    assert job['defaults']['run']['working-directory'] == 'RS-fMRI'
    assert 'python 04_workflow/lab.py doctor' in [step.get('run') for step in job['steps']]
    assert not any('submodule update' in step.get('run', '') for step in job['steps'])
    for suffix in ('yaml', 'json'):
        path = f'RS-fMRI/03_config/lab_config.local.{suffix}'
        result = subprocess.run(['git', '-C', str(REPO), 'check-ignore', '--no-index', path], capture_output=True, text=True)
        assert result.returncode == 0, path


def test_protocol_document_links_resolve_to_owned_sources():
    lock = json.loads((ROOT / '03_config/upstream.lock.json').read_text())
    text = (ROOT / 'README.md').read_text()
    links = re.findall(r'\[([^]]+)\]\(([^)]+)\)', text)
    original_steps = [(label, url) for label, url in links if url.startswith('pipeline/s') and url.endswith('/README.md')]
    documented = {url.split('/')[1] for _, url in original_steps}
    expected = {p.name for p in (ROOT / 'pipeline').glob('s*') if (p / 'README.md').is_file()}
    assert documented == expected
    for label, url in original_steps + [(label, url) for label, url in links if label == 'CITATION.cff']:
        assert url.startswith(lock['path'] + '/'), (label, url)
        assert (ROOT / url).is_file()
