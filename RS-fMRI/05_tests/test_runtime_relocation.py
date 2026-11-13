import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('relocation',ROOT/'04_workflow/runtime_relocation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_active_work_holds_migration_without_service_changes(tmp_path):
    root=tmp_path/'runtime';root.mkdir();calls=[]
    def runner(argv,**kwargs):
        calls.append(argv);return SimpleNamespace(stdout='statmind-fmriprep-SYNTHETIC\n')
    assert m.step({'source':str(root),'destination':str(tmp_path/'target'),'subjects':['SYNTHETIC']},runner) is False
    assert len(calls)==1 and calls[0][0]=='docker'
    assert root.is_dir() and not root.is_symlink()


def test_nonempty_target_is_preserved(tmp_path):
    source=tmp_path/'runtime';source.mkdir();(source/'data').write_bytes(b'image')
    target=tmp_path/'target';target.mkdir();(target/'user-file').write_text('preserve')
    st=source.stat()
    with pytest.raises(ValueError,match='not empty'):m.relocate(source,target,[st.st_dev,st.st_ino])
    assert (source/'data').read_bytes()==b'image' and (target/'user-file').read_text()=='preserve'


def test_atomic_move_preserves_identity_bytes_and_old_absolute_paths(tmp_path):
    source=tmp_path/'runtime';source.mkdir();(source/'data').write_bytes(b'image')
    target=tmp_path/'target';target.mkdir();st=source.stat()
    m.relocate(source,target,[st.st_dev,st.st_ino])
    assert source.is_symlink() and source.samefile(target)
    assert target.stat().st_ino==st.st_ino
    assert (source/'data').read_bytes()==(target/'data').read_bytes()==b'image'
    m.relocate(source,target,[st.st_dev,st.st_ino])


def test_rename_crash_window_recovers_only_original_directory(tmp_path):
    source=tmp_path/'runtime';source.mkdir();st=source.stat();target=tmp_path/'target'
    source.rename(target)
    with pytest.raises(ValueError,match='identity differs'):m.relocate(source,target,[st.st_dev,st.st_ino+1])
    assert not source.exists()
    m.relocate(source,target,[st.st_dev,st.st_ino]);assert source.samefile(target)


def test_missing_postprocessing_never_advances(tmp_path):
    root=tmp_path/'runtime';h=root/'continuous5';h.mkdir(parents=True)
    (h/'state.json').write_text(json.dumps({'SYNTHETIC':{'status':'completed_QC_pending'}}))
    (root/'postprocessing').mkdir();(root/'postprocessing/metrics_export_status.json').write_text('{}')
    (h/'offload_settings.json').write_text('{}');(h/'offload_receipts').mkdir()
    fake=tmp_path/'offloader.py';fake.write_text('class Offloader:\n def __init__(self,*args):pass\n def check_volume(self):pass\n')
    cfg={'source':str(root),'subjects':['SYNTHETIC'],'offloader_source':str(fake)}
    assert m.ready(cfg,lambda *a,**k:SimpleNamespace(stdout=''))==(False,'waiting_for_validated_postprocessing_and_archival')


def test_successful_idle_move_checks_before_resuming(tmp_path,monkeypatch):
    source=tmp_path/'runtime';h=source/'continuous5';h.mkdir(parents=True)
    (h/'verified-batch-feed').mkdir();(source/'postprocessing/config').mkdir(parents=True)
    st=source.stat();target=tmp_path/'target';calls=[]
    monkeypatch.setattr(m,'ready',lambda *args:(True,'ready'))
    def runner(argv,**kwargs):
        calls.append(argv);return SimpleNamespace(stdout='',returncode=1 if argv[:2]==['launchctl','print'] else 0)
    cfg={'source':str(source),'destination':str(target),'source_identity':[st.st_dev,st.st_ino],
         'services':['com.codex.adni-sb-queue-five'],'xcpd_config_id':'config','subjects':['SYNTHETIC'],'checks':[['validate','runtime']]}
    assert m.step(cfg,runner)
    assert source.samefile(target)
    assert calls.index(['validate','runtime'])<next(i for i,v in enumerate(calls) if v[:2]==['launchctl','enable'])
    assert json.loads((h/'runtime-relocation/status.json').read_text())['status']=='completed'
    assert not any('kill' in x or '-k' in x for a in calls for x in a)
