#!/usr/bin/env python3
"""Build reproducible metadata for the atlas files already stored in this step."""
import argparse
import csv
import json
from pathlib import Path
import re

import nibabel as nb
import numpy as np
from sources import ROOT, digest, verify


def label_ids(path):
    img = nb.load(path)
    if len(img.shape) != 3:
        raise ValueError('Only 3-D discrete label atlases are supported')
    values = np.unique(np.asanyarray(img.dataobj))
    if not np.isfinite(values).all() or np.any(values < 0) or not np.allclose(values, np.rint(values), atol=1e-6, rtol=0):
        raise ValueError('Non-discrete atlas')
    return [int(v) for v in values if v != 0]


def entry(atlas_id, source, file, space, expected, names=None, **extra):
    observed = label_ids(file)
    if not observed:
        raise ValueError('Empty atlas')
    if extra.get('metadata_path'):
        extra['metadata_sha256'] = digest(ROOT / extra['metadata_path'])
    return {'id': atlas_id, 'source': source, 'path': str(file.relative_to(ROOT)),
            'space': space, 'kind': 'labels', 'background': 0, 'sha256': digest(file),
            'expected_labels': ({'range': [expected[0], expected[-1]]} if expected == list(range(expected[0], expected[-1] + 1)) else {'ids': expected}),
            'expected_regions': len(expected), 'observed_regions': len(observed),
            'source_missing_regions': len(set(expected) - set(observed)), **extra}


def build():
    lock = json.loads((ROOT / 'sources.lock.json').read_text())['sources']
    for name, spec in lock.items():
        verify(name, spec)
    records = []
    base = ROOT / '01_sources/neuroparc/atlases/label/Human'
    nominal = {}
    for line in (ROOT / '01_sources/neuroparc/README.md').read_text().splitlines():
        cells = [x.strip() for x in line.strip('|').split('|')]
        if len(cells) > 1 and cells[1].isdigit():
            nominal[cells[0]] = int(cells[1])
    files = sorted(base.glob('*_space-*_res-*.nii.gz'))
    references = {}
    for file in files:
        family = file.name.split('_space-')[0]
        if family not in references or '_res-1x1x1.' in file.name:
            references[family] = file
    for file in files:
        family = file.name.split('_space-')[0]
        metadata_file = base / 'Metadata-json' / file.name.replace('.nii.gz', '.json')
        metadata = json.loads(metadata_file.read_text()) if metadata_file.exists() else {}
        names = {k: v.get('label', 'ROI_' + k) for k, v in metadata.get('rois', {}).items()}
        expected = label_ids(references[family])
        declared = nominal.get(family)
        warnings = ['Source uses MNI152NLin6 without an Asym/Sym qualifier; no implicit alias to another space.']
        if declared and declared != len(expected):
            warnings.append('Source README region count differs from observed highest-resolution labels.')
        records.append(entry('neuroparc_' + file.name.removesuffix('.nii.gz'), 'neuroparc', file,
                             'MNI152NLin6', expected, names,
                             declared_regions=declared, source_warnings=warnings,
                             expected_labels_basis='highest_resolution_observed_source',
                             metadata_path=str(metadata_file.relative_to(ROOT)) if metadata_file.exists() else None,
                             label_format='neuroparc_json',
                             citation=metadata.get('MetaData', {}).get('Source', ''),
                             source_commit=lock['neuroparc']['commit']))
    base = ROOT / '01_sources/CBIG/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI'
    for file in sorted(base.glob('Schaefer2018_*_FSLMNI152_*mm.nii.gz')):
        count = int(re.search(r'_(\d+)Parcels_', file.name)[1])
        lut = base / 'freeview_lut' / (file.name.split('_FSLMNI152_')[0] + '.txt')
        names = {}
        for line in lut.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0].isdigit():
                names[fields[0]] = fields[1]
        records.append(entry('cbig_' + file.name.removesuffix('.nii.gz'), 'CBIG', file, 'MNI152NLin6Asym',
                             list(range(1, count + 1)), names, metadata_path=str(lut.relative_to(ROOT)), label_format='cbig_lut',
                             source_warnings=[], citation='https://doi.org/10.1093/cercor/bhx179',
                             expected_labels_basis='author_declared_parcel_count',
                             source_commit=lock['CBIG']['commit']))
    payload_file = ROOT / 'templateflow_payloads.json'
    payloads = json.loads(payload_file.read_text())
    for payload in payloads['payloads']:
        if '_atlas-' not in payload['filename']:
            continue  # Tissue/carpet segmentations are not atlas parcellations.
        file = ROOT / payload['cache_path']
        if not file.exists():
            raise ValueError('Fetch TemplateFlow payloads before building catalog')
        if file.stat().st_size != payload['size'] or digest(file, payload['annex_hash_algorithm']) != payload['annex_digest']:
            raise ValueError('TemplateFlow annex checksum mismatch')
        if payload.get('sha256') != digest(file):
            raise ValueError('TemplateFlow SHA-256 differs from the reviewed payload lock')
        table_name = re.sub(r'_res-\d+', '', file.name).replace('.nii.gz', '.tsv')
        table = ROOT / '01_sources/templateflow' / ('tpl-' + payload['space']) / table_name
        names, expected = {}, label_ids(file)
        warnings = []
        if table.exists():
            with table.open() as stream:
                lut = list(csv.DictReader(stream, delimiter='\t'))
            indices = {int(row['index']): row['name'] for row in lut if row.get('index', '').isdigit()}
            # Some source LUTs use XML offsets; do not guess label/name alignment.
            if 0 in indices and indices[0].lower() not in {'background', 'bg', 'unknown'}:
                warnings.append('LUT uses a non-background zero index; generic numeric labels retained instead of guessing offsets.')
            elif set(expected) <= set(indices):
                names = {str(i): indices[i] for i in indices if i > 0}
                expected = sorted(i for i in indices if i > 0)
            else:
                warnings.append('LUT and image indices differ; generic numeric labels retained.')
        match = re.search(r'desc-(\d+)Parcels', file.name)
        if match:
            expected = list(range(1, int(match[1]) + 1))
        records.append(entry('templateflow_' + file.name.removesuffix('.nii.gz'), 'templateflow', file,
                             payload['space'], expected, names, source_warnings=warnings,
                             metadata_path=str(table.relative_to(ROOT)) if table.exists() else None,
                             label_format='templateflow_tsv' if names else 'numeric',
                             expected_labels_basis='declared_schaefer_parcels' if match else 'indexed_lut' if names else 'observed_source_labels',
                             source_commit=payload['template_commit'],
                             citation='https://doi.org/10.1038/s41592-022-01681-2'))
    return {'schema': 1, 'kind': 'discrete_label_catalog', 'atlas_count': len(records),
            'notes': 'Sources are pinned; coordinates are not registration. No implicit MNI space aliases.', 'atlases': records}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Use a new catalog output path')
    result = build()
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'atlas_count': result['atlas_count'], 'spaces': sorted({x['space'] for x in result['atlases']})}))


if __name__ == '__main__':
    main()
