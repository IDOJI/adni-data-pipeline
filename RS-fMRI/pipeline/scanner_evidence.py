"""Compare scanner evidence without treating two missing values as agreement."""
import math
import re

FIELDS = {'MANUFACTURER': 'Manufacturer', 'FIELD_STRENGTH': 'MagneticFieldStrength',
          'SCANNER_MODEL': 'ManufacturersModelName'}


def normalized(field, value):
    token = str(value if value is not None else '').strip().casefold()
    if token in {'', 'other', 'unknown', 'n/a', 'na', 'none'}:
        return ''
    if field == 'FIELD_STRENGTH':
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:t|tesla)?', token)
        if not match or not math.isfinite(float(match[1])) or float(match[1]) <= 0:
            raise ValueError('Invalid magnetic field strength')
        return format(float(match[1]), 'g')
    token = re.sub(r'[^a-z0-9]+', '', token)
    if field == 'MANUFACTURER':
        for vendor, variants in {'ge': ('ge', 'gemedicalsystems', 'gehealthcare', 'generalelectric'),
                                 'siemens': ('siemens', 'siemenshealthineers', 'siemenshealthcare'),
                                 'philips': ('philips', 'philipsmedicalsystems', 'philipshealthcare')}.items():
            if token in variants:
                return vendor
    return token


def comparison(left, right, field):
    a, b = (normalized(field, side.get(field)) for side in (left, right))
    return 'unknown' if not a or not b else 'match' if a == b else 'mismatch'
