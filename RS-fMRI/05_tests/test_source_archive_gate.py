import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source_gate',ROOT/'04_workflow/source_archive_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)


def test_incomplete_copy_never_reads_or_activates(tmp_path):
    p=tmp_path/'source.zip';p.write_bytes(b'partial')
    assert gate.inspect_copy(p,100,['selected.zip'],0)['status']=='waiting_for_copy'


def test_complete_copy_checks_crc_and_registered_members(tmp_path):
    p=tmp_path/'source.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('selected.zip',b'synthetic payload')
    result=gate.inspect_copy(p,p.stat().st_size,['selected.zip'],0)
    assert result['status']=='validated' and result['zip_crc_verified']
    with pytest.raises(ValueError,match='required'):
        gate.inspect_copy(p,p.stat().st_size,['missing.zip'],0)
    data=p.read_bytes().replace(b'synthetic payload',b'SYNTHETIC payload');p.write_bytes(data)
    with pytest.raises(zipfile.BadZipFile):gate.inspect_copy(p,len(data),['selected.zip'],0)


def test_changing_copy_is_held(tmp_path,monkeypatch):
    p=tmp_path/'source.zip';p.write_bytes(b'a')
    monkeypatch.setattr(gate.time,'sleep',lambda seconds:p.write_bytes(b'new size'))
    assert gate.inspect_copy(p,1,[],1)['reason']=='source_still_changing'


def test_source_switch_waits_for_existing_calculations(tmp_path):
    h=tmp_path/'continuous5';h.mkdir();(h/'settings.json').write_text(json.dumps({'archive':'original'}))
    def runner(argv,**kw):
        assert argv[0]=='docker';return SimpleNamespace(stdout='statmind-fmriprep-SYNTHETIC\n')
    result=gate.activate({'root':str(tmp_path),'archive':'copy'}, {},runner)
    assert result=='validated_waiting_for_idle'
    assert json.loads((h/'settings.json').read_text())['archive']=='original'


def test_verified_source_switch_preserves_scope_and_starts_services(tmp_path):
    h=tmp_path/'continuous5';h.mkdir();(h/'source-copy-gate').mkdir()
    original={'archive':'cloud-original','archive_bytes':123,'archive_mtime_ns':2,
              'verified_continuation':{'path':'verified-registry','sha256':'unchanged'},
              'target_concurrency':5}
    (h/'settings.json').write_text(json.dumps(original));calls=[]
    def runner(argv,**kw):
        calls.append(argv);return SimpleNamespace(stdout='',returncode=0)
    cfg={'root':str(tmp_path),'archive':'external-copy','expected_bytes':123,
         'services':['com.codex.adni-sb-verified-feed','com.codex.adni-sb-postprocessing']}
    result=gate.activate(cfg,{'fingerprint':{'st_mtime_ns':3}},runner)
    settings=json.loads((h/'settings.json').read_text())
    assert result=='ready' and settings['archive']=='external-copy'
    assert settings['verified_continuation']==original['verified_continuation'] and settings['target_concurrency']==5
    assert json.loads((h/'source-copy-gate/settings.before-source-switch.json').read_text())==original
    assert len([c for c in calls if c[:2]==['launchctl','kickstart']])==2
    assert not any('-k' in c for c in calls)


def test_feeder_does_not_prepare_before_source_is_ready(tmp_path):
    import subprocess,sys
    h=tmp_path/'continuous5';h.mkdir();status=h/'source-status.json';status.write_text(json.dumps({'status':'waiting_for_copy'}))
    result=subprocess.run([sys.executable,str(ROOT/'04_workflow/verified_batch_feed.py'),
                           '--root',str(tmp_path),'--deployment',str(tmp_path/'not-used.json'),
                           '--gate-status',str(status)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert not (h/'cases').exists()
