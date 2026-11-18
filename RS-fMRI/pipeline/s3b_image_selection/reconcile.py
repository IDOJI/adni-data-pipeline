"""Explain the union of legacy Search/QC IDs and new IDA inventory. Never selects images."""
import argparse
from collections import Counter
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from selection_identity import VERSION, image_id, scan_date
from _shared import finish, new_output, read, sha, snapshot, unchanged, write


def reconcile(receipt, legacy, output):
    proof = json.loads(Path(receipt).read_text())
    if proof['kind'] != VERSION or set(legacy) != {'EPI', 'T1'}:
        raise ValueError('Expected current selection receipt and both legacy modalities')
    data = proof['outputs']['candidates']
    download = proof['outputs']['download']
    inputs = [receipt, data['path'], download['path'], *legacy.values()]
    out = new_output(output, inputs)
    hashes = snapshot(inputs)
    if any(sha(item['path']) != item['sha256'] for item in (data, download)):
        raise ValueError('Selection evidence changed')
    listed = [image_id(s) for s in Path(download['path']).read_text().splitlines()]
    rows = read(data['path'], ('IMAGE_ID', 'PTID', 'MRI_STUDY_DATE', 'MODALITY', 'DOWNLOAD_ELIGIBLE', 'DOWNLOAD_REASONS'))
    current = {image_id(r['IMAGE_ID']): r for r in rows}
    eligible = {i for i,r in current.items() if r['DOWNLOAD_ELIGIBLE'] == 'True'}
    if len(rows) != len(current) or len(listed) != len(set(listed)) or set(listed) != eligible:
        raise ValueError('Download list and unique registry decisions disagree')
    old = {}
    for mod, path in legacy.items():
        for r in read(path, ('image_id','PTID','STUDY_DATE')):
            key = image_id(r['image_id'])
            if key in old:
                raise ValueError('Duplicate historical Image ID')
            old[key] = (mod, r['PTID'], scan_date(r['STUDY_DATE']))
    report = []
    for key in sorted(set(old) | set(current), key=int):
        row = current.get(key, {})
        if key in old and row and old[key] != (row['MODALITY'], row['PTID'], row['MRI_STUDY_DATE']):
            raise ValueError('Historical/current identity conflict; reconciliation requires review')
        prior, now = key in old, key in eligible
        change = ('retained' if prior else 'added') if now else ('removed' if prior else 'neither')
        reason = row.get('DOWNLOAD_REASONS', 'absent_from_supplied_search_exports')
        if not reason.strip():
            raise ValueError('Unexplained selection decision')
        if change == 'added':
            reason = 'absent_from_historical_intersection;' + reason
        report.append({'IMAGE_ID':key,'MODALITY':row.get('MODALITY') or old[key][0],
                       'LEGACY_MEMBER':prior, 'DOWNLOAD_MEMBER':now, 'CHANGE':change,
                       'REASON':reason, **{k:row.get(k,'') for k in
                       ('SEARCH_DESCRIPTION','SPINE_SERIES_TYPE','SPINE_DESCRIPTION','CLASS_REASON',
                        'SOURCE_QC_STATUS','QC_REASON','QC_SOURCE_ROWS','NFQ_RAW_REASON','NFQ_RAW_SOURCE_ROWS',
                        'SEARCH_PHASE','MRI_PROTOCOL_PHASE','EXCLUSION_REASONS','REVIEW_FLAGS')}})
    changes = [r for r in report if r['CHANGE'] in {'added','removed'}]
    unchanged(hashes)
    out.mkdir(parents=True)
    write(out/'all-images.csv', report)
    write(out/'changed-images.csv', changes, list(report[0]))
    counts = {m:dict(Counter(r['CHANGE'] for r in report if r['MODALITY']==m)) for m in legacy}
    return finish(out, 'historical_search_comparison_v1', hashes,
                  {'by_modality':counts,'changed':len(changes),'unexplained':0,
                   'comparison':'historical Search/QC membership vs manual download, before pairing or clinical selection'})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('receipt','legacy-t1','legacy-epi','output-dir'):
        p.add_argument('--'+arg, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(reconcile(a.receipt, {'T1':a.legacy_t1,'EPI':a.legacy_epi}, a.output_dir)['summary'], indent=2))
