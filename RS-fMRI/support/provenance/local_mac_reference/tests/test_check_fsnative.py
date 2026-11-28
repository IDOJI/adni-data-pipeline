import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
source=Path(__file__).parents[1]/'check_fsnative.py'
if not source.exists():
    source=Path(__file__).with_name('check_fsnative.py')
spec=importlib.util.spec_from_file_location('check_fsnative',source)
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def wrapped(rows):
    return [SimpleNamespace(data=np.asarray(row,dtype=float)) for row in rows]


def test_correct_frames_and_constant_zero_count():
    result=tool.validate_frames(wrapped([[0,1,5],[0,2,5],[0,3,5]]),3,3)
    assert result['constant_vertices']==2
    assert result['constant_zero_vertices']==1
    assert result['nonfinite_values']==0


def test_frame_count_mismatch_rejected():
    with pytest.raises(ValueError,match='frame count'):
        tool.validate_frames(wrapped([[0],[1]]),1,3)


def test_vertex_count_mismatch_rejected():
    with pytest.raises(ValueError,match='vertex count'):
        tool.validate_frames(wrapped([[0,1],[0]]),2,2)


@pytest.mark.parametrize('bad',[np.nan,np.inf,-np.inf])
def test_nonfinite_values_rejected(bad):
    with pytest.raises(ValueError,match='nonfinite'):
        tool.validate_frames(wrapped([[0,1],[0,bad]]),2,2)


def test_output_must_not_overlap_source(tmp_path):
    p=tmp_path/'source'
    assert not tool.disjoint(p,p/'report.json')
    assert not tool.disjoint(p/'report.json',p)
    assert tool.disjoint(p,tmp_path/'qc/report.json')
