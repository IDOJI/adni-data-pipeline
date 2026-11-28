"""Logging transport around unchanged sessionwise or frozen preprocessing runners."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE = Path(__file__).with_name('antsRegistration')


def augment(argv, folder, runner=subprocess):
    """Keep the image/application arguments intact; add only logging mounts/PATH."""
    argv = [str(v) for v in argv]
    if argv[:2] != ['docker', 'run']:
        raise ValueError('Expected a Docker preprocessing command')
    image_index = argv.index('/data') - 1
    image = argv[image_index]
    if '@sha256:' not in image:
        raise ValueError('Iteration logging requires an immutable image digest')
    metadata = json.loads(runner.check_output(['docker', 'image', 'inspect', image], text=True))[0]
    paths = [v[5:] for v in metadata['Config']['Env'] if v.startswith('PATH=')]
    if len(paths) != 1 or not paths[0]:
        raise ValueError('Missing unambiguous original image PATH')
    folder = Path(folder).resolve()
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    code = folder / 'ants_logging_code' / digest
    code.mkdir(parents=True, exist_ok=True)
    script = code / 'antsRegistration'
    if script.exists() and script.read_bytes() != SOURCE.read_bytes():
        raise ValueError('Existing logging code snapshot differs')
    if not script.exists():
        shutil.copyfile(SOURCE, script); script.chmod(0o755)
    logs = folder / 'ants_iterations'; logs.mkdir(exist_ok=True)
    options = ['--mount', f'type=bind,src={code},dst=/opt/adni-ants-logging,readonly',
               '--mount', f'type=bind,src={logs},dst=/ants-logs',
               '--env', 'ADNI_ANTS_LOG_ROOT=/ants-logs',
               '--env', 'PATH=/opt/adni-ants-logging:' + paths[0]]
    effective = argv[:image_index] + options + argv[image_index:]
    proof = {'version': 1, 'base_docker_argv': argv, 'effective_docker_argv': effective,
             'image': image, 'original_image_path': paths[0], 'wrapper_sha256': digest,
             'logs': str(logs), 'scope': 'antsRegistration verbose=1; original cache/scientific command preserved',
             'LLM_calls': 0}
    (folder / 'ants_logging.json').write_text(json.dumps(proof, indent=2) + '\n')
    return effective


class Transport:
    def __init__(self, original):
        self.original = original

    def __getattr__(self, name):
        return getattr(self.original, name)

    def run(self, argv, *args, **kwargs):
        if list(argv[:2]) == ['docker', 'run']:
            log = kwargs.get('stdout')
            if not log or not getattr(log, 'name', None):
                raise ValueError('The preprocessing runner must supply a console log file')
            argv = augment(argv, Path(log.name).parent, self.original)
        return self.original.run(argv, *args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('runner_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    runner_path = args.runner.resolve()
    if not runner_path.is_file() or runner_path == Path(__file__).resolve():
        raise ValueError('Expected an existing distinct preprocessing runner')
    spec = importlib.util.spec_from_file_location('ants_logging_preprocessing_backend', runner_path)
    backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
    backend.subprocess = Transport(subprocess)
    forwarded = args.runner_args
    if forwarded[:1] == ['--']:
        forwarded = forwarded[1:]
    sys.argv = [str(runner_path), *forwarded]
    backend.main()


if __name__ == '__main__':
    main()
