"""Guard a unified owned pipeline with preserved provenance and optional pins."""
import configparser
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent


def test_stage_layout_and_compatibility_paths():
    assert (ROOT / 'pipeline').is_dir()
    assert (ROOT / 'provenance').is_dir()
    tree = subprocess.check_output(
        ['git', '-C', str(REPO), 'ls-tree', 'HEAD:RS-fMRI'], text=True
    ).splitlines()
    assert [entry.split('\t')[1] for entry in tree if entry.startswith('040000 ')] == [
        '01-selection', '02-bids', '03-imaging', '04-harmonization', 'support']
    assert not any(entry.startswith('120000 ') for entry in tree)
    assert not (ROOT / '01_upstream').exists()
    assert not (ROOT / '02_custom').exists()
    names = ('config', 'workflow', 'tests', 'docs')
    for number, name in enumerate(names, 3):
        assert (ROOT / f'{number:02}_{name}').is_dir()
        assert (ROOT / f'{number:02}_{name}').resolve() == ROOT / name
    stages = ['01-selection', '02-bids', '03-imaging', '04-harmonization']
    former_scripts = ['01_select.py', '02_bids.py', '03_process.py', '04_harmonize.py']
    for stage, script in zip(stages, former_scripts):
        entry = ROOT / stage / 'run.py'
        assert entry.is_file() and not entry.is_symlink()
        assert (ROOT / 'start' / script).resolve() == entry
        assert (ROOT / 'stages' / stage / 'run.py').resolve() == entry
    for legacy, current in json.loads((ROOT / 'config/stage-paths.json').read_text()).items():
        source = ROOT / current
        assert not source.is_symlink() and (source / 'README.md').is_file()
        assert (ROOT / 'pipeline' / legacy).resolve() == source
    lock = json.loads((ROOT / '03_config/upstream.lock.json').read_text())
    module = configparser.ConfigParser()
    module.read(REPO / '.gitmodules')
    assert 'submodule "upstream/ADNI_fMRI_protocol"' not in module
    assert lock['distribution'] == 'integrated-source'
    entries = subprocess.check_output(['git', '-C', str(REPO), 'ls-files', '--stage', '--',
                                      'RS-fMRI/support/' + lock['path'], 'RS-fMRI/03-imaging/atlas_bold'], text=True).splitlines()
    assert len(entries) > 1
    gitlinks = [entry for entry in entries if entry.startswith('160000 ')]
    assert len(gitlinks) == 4
    assert all('/atlas_bold/01_sources/' in entry for entry in gitlinks)
    assert len(module.sections()) == 5  # SNP and the four optional atlas sources remain submodules.


def test_document_links_resolve_and_imported_code_hash_is_preserved():
    files = [REPO / 'README.md', ROOT / 'README.md', *sorted((ROOT / 'support/docs').glob('*.md')), *(note for stage in ROOT.glob('0[1-4]-*') for note in [stage / 'README.md', *(stage / 'docs').glob('*.md')]),
             *sorted((ROOT / 'pipeline').glob('*/README.md'))]
    for path in files:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            resolved = (path.resolve().parent / target.strip('<>').split('#')[0]).resolve()
            assert resolved.exists(), (path, target)
    imported = json.loads((ROOT / '03_config/imported_sources.json').read_text())['motion_duration_qc']
    assert hashlib.sha256((ROOT / imported['destination']).read_bytes()).hexdigest() == imported['sha256']
    # The external data hierarchy and upstream source schema keep their names.
    assert 'ADNI_DATA/config/' in (ROOT / '06_docs/protocol-index.md').read_text()
    assert (ROOT / 'pipeline/config/config_adni.yaml').is_file()


def test_ci_pytest_and_private_configuration_paths_are_current():
    config = configparser.ConfigParser()
    config.read(ROOT / 'pytest.ini')
    assert config['pytest']['testpaths'] == 'support/tests'
    assert 'provenance' in config['pytest']['norecursedirs'].split()
    ci = yaml.safe_load((REPO / '.github/workflows/tests.yml').read_text())
    job = ci['jobs']['synthetic-validation']
    assert job['defaults']['run']['working-directory'] == 'RS-fMRI'
    commands = [step['run'] for step in job['steps'] if 'run' in step]
    assert commands.index('python support/setup.py') < commands.index('python support/workflow/lab.py doctor')
    assert not any('submodule update' in step.get('run', '') for step in job['steps'])
    for suffix in ('yaml', 'json'):
        path = f'RS-fMRI/support/config/lab_config.local.{suffix}'
        result = subprocess.run(['git', '-C', str(REPO), 'check-ignore', '--no-index', path], capture_output=True, text=True)
        assert result.returncode == 0, path


def test_protocol_document_links_resolve_to_owned_sources():
    lock = json.loads((ROOT / '03_config/upstream.lock.json').read_text())
    index = ROOT / '06_docs/protocol-index.md'
    text = index.read_text()
    linked = {(index.parent / url).resolve() for url in re.findall(r'\]\(([^)]+)\)', text)
              if url.endswith('/README.md')}
    for stage in (ROOT / 'pipeline').glob('s*'):
        if (stage / 'README.md').is_file():
            assert (stage / 'README.md').resolve() in linked
