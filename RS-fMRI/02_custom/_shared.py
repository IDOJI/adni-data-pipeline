"""Read-only source handling and external, versioned validation artifacts."""
import csv
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path, required=()):
    path = Path(path)
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream, delimiter='\t' if path.suffix == '.tsv' else ',')
        fields = reader.fieldnames or []
        if len(set(fields)) != len(fields) or not set(required) <= set(fields):
            raise ValueError('Missing or duplicate required columns in ' + path.name)
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError('Malformed delimited rows in ' + path.name)
    return rows


def write(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    if not fields:
        raise ValueError('An empty output requires an explicit schema')
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t' if Path(path).suffix == '.tsv' else ',')
        writer.writeheader()
        writer.writerows(rows)


def new_output(path, inputs):
    path = Path(path).resolve()
    if path == REPO or REPO in path.parents or path in REPO.parents:
        raise ValueError('Results must be outside the repository')
    if path.exists():
        raise ValueError('Use a new output directory')
    for item in inputs:
        item = Path(item).resolve()
        if path == item or path in item.parents or item in path.parents:
            raise ValueError('Output and input paths must be disjoint')
    return path


def snapshot(inputs):
    return {str(Path(p).resolve()): sha(p) for p in inputs}


def unchanged(record):
    if any(sha(path) != value for path, value in record.items()):
        raise ValueError('A source changed during validation')


def finish(output, kind, inputs, summary):
    unchanged(inputs)
    value = {'kind': kind, 'inputs_sha256': inputs, 'summary': summary,
             'outputs_sha256': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
             'shared_io_sha256': sha(__file__), 'analysis_ready': False}
    (output / 'artifact.json').write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    return value


def verify_bundle(directory, kind):
    directory = Path(directory).resolve()
    record = json.loads((directory / 'artifact.json').read_text())
    if record.get('kind') != kind:
        raise ValueError('Unexpected validation artifact kind')
    for name, digest in record['outputs_sha256'].items():
        if Path(name).name != name or sha(directory / name) != digest:
            raise ValueError('Validation artifact changed: ' + name)
    return record
