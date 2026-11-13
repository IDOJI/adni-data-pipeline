"""Shared, uniquely named atlas space/grid/TR contracts."""
import math
from pathlib import Path
import re
import numpy as np


def entities(path):
    return dict(re.findall(r'(?:^|_)(sub|ses|task|acq|run|echo|dir|rec|space)-([^_\.]+)', Path(path).name))


def tr_seconds(img, metadata):
    value = metadata.get('RepetitionTime')
    header = float(img.header.get_zooms()[3])
    unit = img.header.get_xyzt_units()[1]
    scale = {'sec': 1, 'msec': .001, 'usec': .000001}.get(unit)
    header = header * scale if scale is not None else None
    if value is None:
        value = header
    if value is None or not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError('A valid TR in seconds is required from JSON or known NIfTI temporal units')
    if header is not None and (not math.isfinite(header) or not np.isclose(header, float(value), rtol=1e-4, atol=1e-5)):
        raise ValueError('JSON and NIfTI TR disagree')
    return float(value)


def grid_equal(a, b):
    return a.shape[:3] == b.shape[:3] and np.allclose(a.affine, b.affine, rtol=0, atol=1e-5)

