"""Patch two audited MRIQC randomness sites in the disposable container only.

The installed MRIQC module remains NiPreps Apache-2.0 source. Its original
license header is retained. No threshold, distribution, model or image changes.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys

ORIGINAL_SHA256 = '204c42dc590dc331c3fe0b3dd6f6d07ac4e47b8e05fca40138901b240a97f4e3'


def transform(source):
    if hashlib.sha256(source).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('MRIQC source differs from the audited image; refusing an unreviewed patch')
    text = source.decode()
    old = 'data[excess] = np.random.normal(loc=wm_mu, scale=wm_sigma, size=excess.sum())'
    new = 'data[excess] = np.random.RandomState(int(__import__("os").environ["ADNI_RANDOM_SEED"])).normal(loc=wm_mu, scale=wm_sigma, size=excess.sum())'
    constructor = "Atropos(\n            initialization='PriorProbabilityImages',"
    assert text.count(old) == 1 and text.count(constructor) == 1
    return text.replace(old, new).replace(constructor, "Atropos(\n            use_random_seed=False,\n            initialization='PriorProbabilityImages',").encode()


def install():
    if os.environ.get('ADNI_SEED_POLICY') != 'fixed-seed-v1':
        raise ValueError('The MRIQC seed bootstrap requires an explicit fixed-seed policy')
    seed = int(os.environ['ADNI_RANDOM_SEED'])
    if not 0 <= seed < 2**32:
        raise ValueError('Invalid seed')
    spec = importlib.util.find_spec('mriqc')
    path = Path(spec.origin).parent/'workflows/anatomical/base.py'
    original = path.read_bytes()
    patched = transform(original)
    # Patches live only in this container's writable layer. The pinned image is unchanged.
    path.write_bytes(patched)
    Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
    proof = Path('/adni-seed-records')
    proof.mkdir(exist_ok=True)
    (proof/'mriqc-anatomical-base.seeded.py').write_bytes(patched)
    (proof/'mriqc-adapter.json').write_text(json.dumps({
        'policy': 'fixed-seed-v1', 'seed': seed, 'original_sha256': ORIGINAL_SHA256,
        'effective_sha256': hashlib.sha256(patched).hexdigest(),
        'changes': ['Reset the enhancement RandomState per invocation, independent of worker order.',
                    'Use deterministic Atropos initialization (use_random_seed=False).'],
        'qi2_seed': 1191935, 'qi2_note': 'Existing fixed upstream seed retained.',
        'image_source_changed': False}, indent=2)+'\n')
    return path


if __name__ == '__main__':
    install()
    os.execv('/opt/conda/bin/mriqc', ['/opt/conda/bin/mriqc', *sys.argv[1:]])
