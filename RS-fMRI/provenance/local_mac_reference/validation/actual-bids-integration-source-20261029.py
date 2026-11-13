import csv
import hashlib
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml

repo = Path(os.environ['ADNI_LEGACY_REFERENCE_ROOT'])
local = repo / 'local_mac'
work = Path(tempfile.mkdtemp(prefix='statmind-bids-integration-', dir='/private/tmp'))
config = yaml.safe_load((local / 'config.local.yaml').read_text())
config['runtime'] = str(work / 'runtime')
config['source_manifest'] = str(work / 'source_manifest.json')
config_path = work / 'integration.yaml'
config_path.write_text(yaml.safe_dump(config, sort_keys=False))
python = repo / '.venv/bin/python'
env = os.environ.copy()
env['PATH'] = str(repo / '.venv/bin') + os.pathsep + env.get('PATH', '')
env['PYTHONDONTWRITEBYTECODE'] = '1'
env['OMP_NUM_THREADS'] = '1'
env['OPENBLAS_NUM_THREADS'] = '1'
steps = [
    [str(python), str(local / 'make_source_manifest.py'), '--config', str(config_path)],
    [str(python), str(local / 'run.py'), '--config', str(config_path), 'prepare'],
    [str(python), str(local / 'run.py'), '--config', str(config_path), 'intake'],
]
completed = []
try:
    for command in steps:
        result = subprocess.run(command, cwd=repo, env=env, check=False, capture_output=True, text=True)
        completed.append({'command': command, 'exit_code': result.returncode,
                          'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            raise RuntimeError(f'Integration step failed: {command[-1]}')
    path = work / 'runtime/results/step5/intake_decisions.tsv'
    with path.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    values = {(row['sub'], row['ses']): (row['phase'], row['strict_upstream_eligible']) for row in rows}
    expected = {('sub-998S9999', 'ses-20000101'): ('ADNI3', 'True'),
                ('sub-999S99999', 'ses-20000102'): ('ADNI4', 'False')}
    if values != expected:
        raise RuntimeError(f'Unexpected actual-data intake decisions: {values}')
    output = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'real_BIDS_source_manifest_prepare_intake_passed',
              'scope': 'Temporary read-only source integration; no Docker processing and no alteration of the active pipeline.',
              'cases': rows, 'steps': completed, 'temporary_runtime_removed': True,
              'config': config,
              'generated_source_manifest': json.loads((work / 'source_manifest.json').read_text()),
              'prepared_input_manifest': json.loads((work / 'runtime/logs/intake_manifest.json').read_text()),
              'upstream_intake_provenance': json.loads((work / 'runtime/results/step5/intake_provenance.json').read_text()),
              'integration_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (Path('/private/tmp/statmind-reusable-check') / 'actual-bids-integration-20261029.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': output['status'], 'visits': len(rows), 'evidence': '/private/tmp/statmind-reusable-check/actual-bids-integration-20261029.json'}))
finally:
    # This directory was created exclusively for the integration test in the temporary root.
    if work.parent == Path('/private/tmp') and work.name.startswith('statmind-bids-integration-'):
        shutil.rmtree(work)
