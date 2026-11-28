"""Image ID and actual scan date shared by selection and historical reconciliation."""
from datetime import datetime
import re

VERSION = 'date_based_selection_v3'


def image_id(value):
    token = str(value).strip()
    if not re.fullmatch(r'[Ii]?[0-9]+', token):
        raise ValueError('Image ID must be a numeric LONI image identifier')
    token = token.removeprefix('I').removeprefix('i')
    return str(int(token))


def scan_date(value):
    token = str(value).strip()
    for fmt in ('%Y-%m-%d', '%Y%m%d', '%m/%d/%Y', '%m/%d/%Y %H:%M:%S'):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(token).date().isoformat()
    except ValueError as exc:
        raise ValueError('Missing or invalid actual acquisition date; VISCODE is not a date substitute') from exc
