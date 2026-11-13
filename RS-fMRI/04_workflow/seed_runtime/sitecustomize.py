"""Seed Python processes in the explicitly selected MRIQC fixed-seed profile."""
import os

if os.environ.get('ADNI_SEED_POLICY') == 'fixed-seed-v1':
    import random
    import numpy
    seed = int(os.environ['ADNI_RANDOM_SEED'])
    random.seed(seed)
    numpy.random.seed(seed)
