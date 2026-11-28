"""Record NIfTI fingerprints at conversion time from Clinica's source and output records."""
import csv
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path

from .study import fixed_text
from _shared import read, sha
from s3b_image_selection.selection_identity import image_id, scan_date


def fingerprints(bids, dicom, registry, folder):
    """Only called for the fresh destination immediately after a successful conversion."""
    selected = {r['IMAGE_ID']: r for r in registry}
    sources = defaultdict(list)
    for mod, filename in [('T1', 't1_paths.tsv'), ('EPI', 'fmri_paths.tsv')]:
        tables = list((bids / 'conversion_info').rglob(filename))
        if len(tables) != 1:
            continue
        table, = tables
        rows = read(table, ('Subject_ID', 'VISCODE', 'Image_ID', 'Scan_Date', 'Path'))
        counts = Counter((r['Subject_ID'], r['VISCODE']) for r in rows)
        table_hash = sha(table)
        for r in rows:
            if not r['Path'] or counts[r['Subject_ID'], r['VISCODE']] != 1:
                continue
            src = Path(r['Path']).resolve()
            if not src.is_dir() or not src.is_relative_to(dicom):
                continue
            parts = src.relative_to(dicom).parts
            if len(parts) != 4:
                continue
            iid = image_id(r['Image_ID'])
            day = scan_date(parts[2].split('_')[0])
            candidate = selected.get(iid, {})
            if (image_id(parts[3]) != iid or parts[0] != r['Subject_ID'] or day != scan_date(r['Scan_Date'])
                    or (candidate.get('PTID'), candidate.get('MODALITY'), candidate.get('MRI_STUDY_DATE'))
                        != (parts[0], mod, day)):
                continue
            sources[iid].append(dict(SOURCE_IMAGE_ID=iid, SOURCE_PTID=parts[0], STUDY_DATE=day, MODALITY=mod,
                                     source_dir=str(src), conversion_table=str(table), conversion_sha256=table_hash))
    candidates = defaultdict(list)
    for scans in sorted(bids.glob('sub-*/ses-*/*_scans.tsv')):
        scan_hash = sha(scans)
        for row in read(scans, ('filename', 'scan_id')):
            rel = Path(row['filename'])
            if (len(rel.parts) != 2 or rel.parts[0] not in ('anat', 'func') or '..' in rel.parts
                    or not rel.name.endswith(('_T1w.nii.gz', '_bold.nii.gz'))):
                continue
            try:
                iid = image_id(row['scan_id'])
            except ValueError:
                continue  # Clinica records n/a when it cannot match a scan.
            path = (scans.parent / rel).resolve()
            if not path.is_relative_to(scans.parent) or not path.is_file() or len(sources[iid]) != 1:
                continue
            source, = sources[iid]
            sub = scans.parent.parent.name.removeprefix('sub-').removeprefix('ADNI')
            if (sub != source['SOURCE_PTID'].replace('_', '')
                    or rel.name.endswith('_T1w.nii.gz') != (source['MODALITY'] == 'T1')):
                continue
            candidates[iid].append(dict(**source, scans_table=str(scans), scans_sha256=scan_hash,
                                        nifti=str(path), NIFTI_SHA256=sha(path)))
    path_counts = Counter(row['nifti'] for rows in candidates.values() for row in rows)
    records = [rows[0] for _, rows in sorted(candidates.items())
               if len(rows) == 1 and path_counts[rows[0]['nifti']] == 1]
    if records:
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=records[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)
        fixed_text(folder / 'conversion-hashes.csv', stream.getvalue())
    return len(records)
