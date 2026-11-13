"""Explicit seeded cohort IQM fitting/plots; never calibrate from a pilot pair."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

LAB = Path(__file__).resolve().parents[1]


def command(config, output, seed=1123):
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError('R seed must be an integer in [0, 2147483647]')
    output = Path(output).resolve()
    if output.is_relative_to(LAB.parent) or LAB.parent.is_relative_to(output):
        raise ValueError('Use an external new output directory')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new output directory; preserve historical cohort results')
    original = LAB/'pipeline/s6_mriqc/adni_outlier_pipeline.R'
    # Rscript -e has no --file argument, so the existing script resolves its repo
    # from the explicit cwd. Its scientific thresholds and fixed internal seeds remain intact.
    expression = 'if (!("iso_seed" %in% names(formals(rrobot::SHASH_out)))) stop("Use rrobot with explicit iso_seed support; R set.seed alone does not seed isotree");' + \
        'set.seed('+str(seed)+');source('+json.dumps(str(original))+', chdir=FALSE)'
    return ['Rscript', '--vanilla', '-e', expression, '--config', str(Path(config).resolve()), '--out-dir', str(output)]


def environment():
    # The upstream R script invokes `python -m utils.config_tools`. Use this
    # launcher's interpreter environment even when its venv was not activated.
    env = os.environ.copy()
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    libraries = [str(LAB/'.R-library/seeded'), str(LAB/'.R-library')]
    if env.get('R_LIBS_USER'):
        libraries.append(env['R_LIBS_USER'])
    env['R_LIBS_USER'] = os.pathsep.join(libraries)
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--seed', type=int, default=1123)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    args.config, args.out_dir = args.config.resolve(), args.out_dir.resolve()
    argv = command(args.config, args.out_dir, args.seed)
    print(json.dumps(argv))
    if args.execute:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        proof = {'seed_policy': 'fixed-seed-v1', 'global_R_seed': args.seed,
                 'SHASH_seed': 123456, 'example_selection_seed': 1,
                 'status': 'running', 'command': argv}
        receipt = args.out_dir/'seed-policy.json'
        receipt.write_text(json.dumps(proof, indent=2)+'\n')
        result = subprocess.run(argv, cwd=LAB/'pipeline', env=environment())
        proof.update(status='completed' if result.returncode == 0 else 'failed', returncode=result.returncode)
        receipt.write_text(json.dumps(proof, indent=2)+'\n')
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
