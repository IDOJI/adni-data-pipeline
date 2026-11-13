"""Explicit execution-only recovery profile around a frozen preprocessing backend.

The original command remains the cache identity. The effective container ceiling
and logging mounts are separately recorded for every actual attempt. Workflow
memory estimates, CPU/thread counts, images, seeds and scientific flags stay intact.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

LAB = Path(__file__).resolve().parents[1]


def effective_command(argv):
    argv = [str(x) for x in argv]
    if argv[:2] != ['docker', 'run'] or argv.count('--memory') != 1:
        raise ValueError('Expected one explicit Docker memory ceiling')
    image_index = argv.index('/data') - 1
    i = argv.index('--memory')
    if i >= image_index or '@sha256:' not in argv[image_index]:
        raise ValueError('Expected a pinned preprocessing image')
    if argv[i+1] not in ('8g', '16g'):
        raise ValueError('Unknown execution profile; retain and review')
    result = argv.copy(); result[i+1] = '16g'
    return result


class Transport:
    def __init__(self, original, logging):
        self.original = original; self.logging = logging

    def __getattr__(self, name):
        return getattr(self.original, name)

    def run(self, argv, *args, **kwargs):
        if list(argv[:2]) == ['docker', 'run']:
            log = kwargs.get('stdout')
            if not log or not getattr(log, 'name', None):
                raise ValueError('A recorded attempt console is required')
            folder = Path(log.name).parent
            resource_argv = effective_command(argv)
            effective = self.logging.augment(resource_argv, folder, self.original)
            proof = {'schema': 1, 'base_cache_argv': list(argv),
                     'effective_resource_argv': resource_argv, 'effective_docker_argv': effective,
                     'scope': 'Docker memory ceiling only; workflow/scientific options unchanged; ANTs verbose logging retained',
                     'docker_memory_ceiling': '16g',
                     'launcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     'LLM_calls': 0}
            (folder/'execution_environment.json').write_text(json.dumps(proof, indent=2)+'\n')
            argv = effective
        return self.original.run(argv, *args, **kwargs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runner', required=True, type=Path)
    p.add_argument('runner_args', nargs=argparse.REMAINDER)
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('recovery_iteration_logging', LAB/'02_custom/s7c_ants_iteration_logging/run.py')
    logging = importlib.util.module_from_spec(spec); spec.loader.exec_module(logging)
    path = args.runner.resolve()
    spec = importlib.util.spec_from_file_location('recovery_frozen_backend', path)
    backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
    backend.subprocess = Transport(subprocess, logging)
    original_dump = backend.dump
    def dump(destination, value):
        proof = Path(destination).with_name('execution_environment.json')
        if Path(destination).name == 'run.json' and proof.is_file():
            value['execution_environment'] = {'path': str(proof), 'sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}
        return original_dump(destination, value)
    backend.dump = dump
    forwarded = args.runner_args
    if forwarded[:1] == ['--']:forwarded = forwarded[1:]
    sys.argv = [str(path), *forwarded]
    backend.main()


if __name__ == '__main__':main()
