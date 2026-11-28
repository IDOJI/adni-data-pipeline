"""Identify target acquisitions from the IDA search and independent MRIQC spine."""
import re
from collections import defaultdict

from scanner_evidence import normalized


def series_class(modality, description, qc):
    """Negative evidence overrides positive labels. BOLD alone does not establish rest."""
    descriptions = [str(d or '').strip().casefold().replace('_', ' ')
                    for d in (description, qc.get('SPINE_DESCRIPTION'))]
    for d in descriptions:
        if re.search(r'\b(?:relcbf|cbf|perfusion|(?:pc|p|c)?asl|dti|dwi|diffusion)\b', d):
            return 'non_target', 'perfusion_or_diffusion'
        if re.search(r'flair|calibration|scout|localizer', d) or (modality == 'T1' and d in {'ax','cor','smartbrain'}):
            return 'non_target', 'non_target_anatomical_sequence'
    if any('mocoseries' in d.replace(' ', '') for d in descriptions):
        return ('non_target', 'moco_excluded_by_spine') if descriptions[1] == 'mocoseries' else ('review', 'moco_source_unconfirmed')
    source_type = qc.get('SPINE_SERIES_TYPE', '').upper()
    if source_type in {'ASL', 'DTI', 'DWI', 'LOCALIZER', 'DERIVED', 'FLAIR', 'T2W'}:
        return 'non_target', 'non_target_MRIQC_series_type:' + source_type
    if modality == 'EPI' and any(re.search(r'\b(?:task(?![- ]?(?:free|rest)\b)|n[- ]?back|motor|sbref|fieldmap|derived)\b', d) for d in descriptions):
        return 'review', 'possible_task_or_derived_series'
    expected = 'BOLD' if modality == 'EPI' else 'T1W'
    if source_type != expected:
        return 'review', 'exact_MRIQC_' + expected + '_not_confirmed'
    if modality == 'EPI' and not any(re.search(r'\b(?:rs\s*fmri|fc\s*mri|resting|rest|task[- ]free)\b', d) for d in descriptions):
        return 'review', 'rest_not_documented'
    return 'target', 'spine_BOLD_and_rest_description' if modality == 'EPI' else 'spine_T1w'


def equipment(raw, columns, cell, qc):
    parts = defaultdict(list)
    for item in cell(raw, 'IMAGING_PROTOCOL', columns).split(';'):
        key, sep, value = item.partition('=')
        if sep:
            parts[key.strip().casefold()].append(value.strip())
    result, warnings = {}, []
    for field, key in zip(('MANUFACTURER', 'SCANNER_MODEL', 'FIELD_STRENGTH'), ('manufacturer', 'mfg model', 'field strength')):
        dedicated = cell(raw, field, columns)
        packed = parts[key]
        spine = qc.get('SPINE_' + field, '')
        values = [dedicated, *packed, spine]
        try:
            distinct = {normalized(field, v) for v in values} - {''}
        except ValueError:
            distinct = set()
            warnings.append('invalid_scanner_value:' + field)
        if len(distinct) > 1:
            warnings.append('scanner_evidence_conflict:' + field)
        result[field] = next(iter(distinct)) if len(distinct) == 1 else ''
        result['SEARCH_' + field] = dedicated or ';'.join(packed)
        result['SPINE_' + field] = spine
    return result, warnings
