"""Guard the numbered lab layout without changing upstream's own directories."""
import configparser
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def test_numbered_directories_and_submodule_declaration_agree():
    names = ('upstream', 'custom', 'config', 'workflow', 'tests', 'docs')
    for number, name in enumerate(names, 1):
        assert (ROOT / f'{number:02}_{name}').is_dir()
        assert not (ROOT / name).exists()
    lock = json.loads((ROOT / '03_config/upstream.lock.json').read_text())
    module = configparser.ConfigParser()
    module.read(REPO / '.gitmodules')
    declared = module['submodule "upstream/ADNI_fMRI_protocol"']['path']
    assert declared == 'RS-fMRI/' + lock['path']
    assert (REPO / declared / '.git').is_file()
    # The submodule identifier remains stable for existing users' git config.
    assert module['submodule "upstream/ADNI_fMRI_protocol"']['url'] == lock['repository']


def test_document_links_resolve_and_imported_code_hash_is_preserved():
    files = [REPO / 'README.md', ROOT / 'README.md', *sorted((ROOT / '06_docs').glob('*.md')),
             *sorted((ROOT / '02_custom').glob('*/README.md'))]
    for path in files:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            resolved = (path.parent / target.strip('<>').split('#')[0]).resolve()
            upstream = (ROOT / '01_upstream/ADNI_fMRI_protocol').resolve()
            assert not resolved.is_relative_to(upstream), ('GitHub cannot follow a relative link into a submodule', path, target)
            assert resolved.exists(), (path, target)
    imported = json.loads((ROOT / '03_config/imported_sources.json').read_text())['motion_duration_qc']
    assert hashlib.sha256((ROOT / imported['destination']).read_bytes()).hexdigest() == imported['sha256']
    # The external data hierarchy and upstream source schema keep their names.
    assert 'ADNI_DATA/config/' in (ROOT / 'README.md').read_text()
    assert (ROOT / '01_upstream/ADNI_fMRI_protocol/config/config_adni.yaml').is_file()


def test_ci_pytest_and_private_configuration_paths_are_current():
    config = configparser.ConfigParser()
    config.read(ROOT / 'pytest.ini')
    assert config['pytest']['testpaths'] == '05_tests'
    assert '01_upstream' in config['pytest']['norecursedirs'].split()
    ci = yaml.safe_load((REPO / '.github/workflows/tests.yml').read_text())
    job = ci['jobs']['synthetic-validation']
    assert job['defaults']['run']['working-directory'] == 'RS-fMRI'
    assert 'python 04_workflow/lab.py doctor' in [step.get('run') for step in job['steps']]
    for suffix in ('yaml', 'json'):
        path = f'RS-fMRI/03_config/lab_config.local.{suffix}'
        result = subprocess.run(['git', '-C', str(REPO), 'check-ignore', '--no-index', path], capture_output=True, text=True)
        assert result.returncode == 0, path


def test_upstream_document_links_use_pinned_github_blob_urls():
    lock = json.loads((ROOT / '03_config/upstream.lock.json').read_text())
    prefix = lock['repository'].removesuffix('.git') + '/blob/' + lock['commit'] + '/'
    text = (ROOT / 'README.md').read_text()
    links = re.findall(r'\[([^]]+)\]\(([^)]+)\)', text)
    original_steps = [(label, url) for label, url in links if label.startswith('Upstream Step ')]
    assert len(original_steps) == 10
    for label, url in original_steps + [(label, url) for label, url in links if label == 'CITATION.cff']:
        assert url.startswith(prefix), (label, url)
        relative = url.removeprefix(prefix)
        assert not relative.startswith('/') and '..' not in Path(relative).parts
        subprocess.run(['git', '-C', str(ROOT / lock['path']), 'cat-file', '-e',
                        lock['commit'] + ':' + relative], check=True, capture_output=True)
