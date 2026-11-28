"""Synthetic interface tests against the pinned upstream consumer."""
import csv
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handoff = load('handoff', 'pipeline/s5c_validate_handoff/run.py')
upstream = load('upstream_filters', 'pipeline/s7_fmriprep/make_bids_filters.py')


def table(tmp_path, visits=('bl', 'm12')):
    path = tmp_path / 'final_heuristics.tsv'
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['Subject_ID', 'VISCODE', 'NIfTI_exists', 'JSON_exists', 'T1w_exists'], delimiter='\t')
        w.writeheader()
        for v in visits:
            w.writerow(dict(Subject_ID='999_S_9999', VISCODE=v, NIfTI_exists='TRUE', JSON_exists='True', T1w_exists='1'))
    return path


def test_exact_sessions_roundtrip_through_original_consumer(tmp_path):
    source = table(tmp_path)
    before = source.read_bytes()
    out = tmp_path / 'handoff'
    result = handoff.process(source, out)
    assert result['sessions'] == 2 and result['subjects'] == 1
    assert upstream.load_subject_sessions(out / 'mriqc_sessions.csv') == {'sub-ADNI999S9999': {'M000', 'M012'}}
    with (out / 'mriqc_subjects.csv').open() as f:
        assert list(csv.DictReader(f)) == [{'Subject_ID': '999_S_9999', 'sessions': 'M000 M012'}]
    assert source.read_bytes() == before
    assert json.loads((out / 'handoff.json').read_text())['research_inclusion'] == 'not_determined'
    with pytest.raises(ValueError, match='new output'):
        handoff.process(source, out)


@pytest.mark.parametrize('visits', [('bl', 'M000'), ('sc',), ('20200101',), ()])
def test_duplicates_unknown_sessions_and_empty_are_rejected_before_writing(tmp_path, visits):
    source = table(tmp_path, visits)
    with pytest.raises(ValueError):
        handoff.process(source, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_bad_flags_and_bad_delimiter_never_promote_survival(tmp_path):
    source = table(tmp_path)
    source.write_text(source.read_text().replace('TRUE', 'FALSE'))
    with pytest.raises(ValueError, match='contradicts'):
        handoff.process(source, tmp_path / 'out')
    source.write_text('Subject_ID,VISCODE\n999_S_9999,bl\n')
    with pytest.raises(ValueError, match='Expected upstream'):
        handoff.process(source, tmp_path / 'out')


def test_outputs_in_repo_are_rejected(tmp_path):
    with pytest.raises(ValueError, match='outside'):
        handoff.process(table(tmp_path), ROOT.parent / 'results/test')
