#!/usr/bin/env python3
"""Audit original ADNI MRI QC, deletion and raw NFQ evidence before conversion."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import finish, new_output, read, snapshot, unchanged, write, sha
import qc_registry as qc
import nfq_quality as nfq


def process(sources, nfq_sources, output_dir):
    if 'MRIQC' not in sources:
        raise ValueError('The original MRIQC Study Files table is required')
    if not set(sources) <= {'MRIQC', 'ADNI3_QC', 'GO2_QC', 'DELETED'}:
        raise ValueError('Unsupported raw quality source')
    files = list(sources.values()) + list(nfq_sources.values())
    output = new_output(output_dir, files)
    hashes = snapshot(files)
    registry, summary, unlinked = qc.build_registry(sources)
    if not registry:
        raise ValueError('Empty source registry')
    spine = [row for _, row in qc.read_source(sources['MRIQC'])[0]]
    raw = {name: qc.read_source(path)[0] for name, path in nfq_sources.items()}
    nfq_spine, evidence, holds, raw_audit = nfq.map_raw_nfq(spine, raw)
    candidates = [row for row in registry.values() if row['MODALITY'] == 'EPI']
    nfq_rows = nfq.candidate_qc(candidates, nfq_spine, evidence, holds)
    by_id = {r['IMAGE_ID']: r for r in nfq_rows}
    audits = []
    for iid, row in sorted(registry.items(), key=lambda pair: int(pair[0])):
        if row['MODALITY'] not in {'T1', 'EPI'}:
            continue
        n = by_id.get(iid, {})
        blocked = row['QC_BLOCKED'] or n.get('NFQ_RAW_QC_STATUS') in {'fail', 'hold'}
        confirmed = row['QC_CONFIRMED_PASS'] and (row['MODALITY'] == 'T1' or n.get('NFQ_RAW_QC_STATUS') == 'pass')
        status = 'blocked' if blocked else 'pass' if confirmed else 'pending'
        audits.append({**row, **n, 'SOURCE_QC_STATUS': status,
                       'PREPROCESSING_ALLOWED': not blocked, 'RESEARCH_QC_CONFIRMED': status == 'pass'})
    if not audits:
        raise ValueError('No T1/EPI images in source registry')
    unchanged(hashes)
    output.mkdir(parents=True)
    qc.write_outputs(output, registry, summary, unlinked)
    write(output / 'image_qc.tsv', audits)
    write(output / 'nfq_raw_audit.tsv', raw_audit, list(raw_audit[0]) if raw_audit else ['NFQ_SOURCE', 'NFQ_SOURCE_ROW', 'NFQ_MATCH_STATUS'])
    return finish(output, 'source_qc_v1', hashes, {
        'images': len(audits), 'source_qc_status': dict(Counter(r['SOURCE_QC_STATUS'] for r in audits)),
        'policy': 'Blocked source evidence cannot proceed; absent/unverified QC is pending, not pass. NFQ grade is independent of ST.',
        'implementation_sha256': {name: sha(Path(__file__).with_name(name)) for name in ('run.py', 'qc_registry.py', 'nfq_quality.py')},
        't1_pairing_validated': False, 'nfq_sources_provided': sorted(nfq_sources)})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mriqc-table', required=True, help='Original ADNI MRIQC Study Files table, not MRIQC software group metrics')
    p.add_argument('--adni3-qc')
    p.add_argument('--go2-qc')
    p.add_argument('--deleted-scans')
    p.add_argument('--nfq', action='append', default=[], metavar='SOURCE=PATH')
    p.add_argument('--output-dir', required=True)
    a = p.parse_args()
    try:
        sources = {'MRIQC': a.mriqc_table}
        for key, path in [('ADNI3_QC', a.adni3_qc), ('GO2_QC', a.go2_qc), ('DELETED', a.deleted_scans)]:
            if path:
                sources[key] = path
        raw = {}
        for arg in a.nfq:
            name, sep, path = arg.partition('=')
            if not sep or not name or not path or name in raw:
                raise ValueError('Use a unique NFQ SOURCE=PATH')
            raw[name] = path
        print(json.dumps(process(sources, raw, a.output_dir)['summary'], ensure_ascii=False))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
