"""Transport, live-stream and failure contracts; all inputs are synthetic."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / '02_custom/s7c_ants_iteration_logging'
spec = importlib.util.spec_from_file_location('ants_log_transport', STEP / 'run.py')
transport = importlib.util.module_from_spec(spec); spec.loader.exec_module(transport)


def test_transport_keeps_scientific_argv_and_cache_bytes(tmp_path):
    base = ['docker','run','--rm','--name','synthetic','--env','OMP_NUM_THREADS=2',
            'example@sha256:synthetic','/data','/out','participant','--random-seed','357']
    cache = tmp_path/'cache.json'; cache.write_text(json.dumps(base)); before = cache.read_bytes()
    fake = SimpleNamespace(check_output=lambda *a,**k:json.dumps([{'Config':{'Env':['PATH=/original/bin:/usr/bin']}}]))
    effective = transport.augment(base,tmp_path/'attempt',fake)
    assert effective[effective.index('example@sha256:synthetic'):] == base[base.index('example@sha256:synthetic'):]
    assert base == json.loads(before) and cache.read_bytes() == before
    assert 'PATH=/opt/adni-ants-logging:/original/bin:/usr/bin' in effective
    assert any('readonly' in arg for arg in effective)
    proof = json.loads((tmp_path/'attempt/ants_logging.json').read_text())
    assert proof['base_docker_argv']==base and proof['effective_docker_argv']==effective


def test_transport_does_not_intercept_other_subprocesses():
    calls=[]
    original=SimpleNamespace(run=lambda argv,**kw:calls.append(argv))
    transport.Transport(original).run(['git','rev-parse','HEAD'])
    assert calls==[['git','rev-parse','HEAD']]


def test_wrapper_streams_progress_before_exit_and_preserves_channels(tmp_path):
    binpath=tmp_path/'bin';binpath.mkdir();real=binpath/'antsRegistration'
    release=tmp_path/'release'
    real.write_text('#!'+sys.executable+'\n'+'''import os,sys,time
from pathlib import Path
print('Stage 0',flush=True)
print('Current level = 1',flush=True)
os.write(1,b'XXDIAGNOSTIC, 1, -0.42, 0.001, 0.2, 0.1\\r')
print('synthetic-stderr',file=sys.stderr,flush=True)
while not Path(sys.argv[1]).exists():time.sleep(.01)
print('XXDIAGNOSTIC, 2, -0.43, 0.0001, 0.3, 0.1',flush=True)
sys.exit(7)
''');real.chmod(0o755)
    env={**os.environ,'PATH':str(STEP)+os.pathsep+str(binpath)+os.pathsep+os.environ['PATH'],
         'ADNI_ANTS_LOG_ROOT':str(tmp_path/'logs')}
    child=subprocess.Popen([sys.executable,str(STEP/'antsRegistration'),str(release),'--verbose','0','--random-seed','357'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+10;progress=None
        while time.monotonic()<deadline:
            matches=list((tmp_path/'logs').glob('*/progress.json'))
            if matches:
                progress=json.loads(matches[0].read_text())
                if progress.get('iteration')==1:break
            time.sleep(.02)
        assert progress and progress['iteration']==1 and progress['stage']==0 and progress['level']==1
        assert child.poll() is None
        release.touch();out,err=child.communicate(timeout=10)
        assert child.returncode==7 and b'XXDIAGNOSTIC, 2' in out and b'synthetic-stderr' in err
        folder=matches[0].parent;record=json.loads((folder/'execution.json').read_text())
        assert record['exit_code']==7 and record['status']=='failed'
        assert record['effective_argv']==[str(real),str(release),'--random-seed','357','--verbose','1']
        assert (folder/'stdout.log').read_bytes()==out and (folder/'stderr.log').read_bytes()==err
        assert json.loads((folder/'progress.json').read_text())['iteration']==2
    finally:
        if child.poll() is None:child.kill();child.communicate()


def test_queue_uses_logging_for_both_legacy_and_new_stage_dispatch():
    sys.path.insert(0,str(ROOT/'04_workflow'))
    import queue_service as q
    for script in [Path('/private/frozen/run.py'),ROOT/'02_custom/s7b_sessionwise_preprocessing/run.py']:
        argv=q.stage_command(script,Path('/private/config.yaml'),'fmriprep','ADNI999S9999')
        assert Path(argv[1])==STEP/'run.py'
        assert argv[argv.index('--runner')+1]==str(script)
        assert argv[argv.index('--')+1:]==['--config','/private/config.yaml','run','--stage','fmriprep','--subject','ADNI999S9999']

def activation_module():
    spec=importlib.util.spec_from_file_location('ants_idle_activation',STEP/'activate_when_idle.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def activation_fixture(tmp_path):
    m=activation_module();h=tmp_path/'continuous5';h.mkdir()
    (h/'settings.json').write_text(json.dumps({'target_concurrency':5,'admission':{'slots':5,'floor_gib':20,'per_slot_gib':12}}))
    (h/'state.json').write_text('{}');(h/'status.json').write_text(json.dumps({'global_active_count':0}))
    original=json.loads((h/'settings.json').read_text())['admission'];m.arm(tmp_path)
    return m,h,original


def test_activation_never_restarts_while_container_is_running(tmp_path):
    m,h,original=activation_fixture(tmp_path);calls=[]
    def run(argv,**kwargs):
        calls.append(argv);assert argv[0]=='docker'
        return SimpleNamespace(stdout='statmind-fmriprep-ADNI999S9999-M000\n',returncode=0)
    d=m.check(tmp_path,'com.codex.adni-sb-queue-five',run)
    assert d['status']=='waiting_for_idle' and len(calls)==1
    assert json.loads((h/'settings.json').read_text())['admission']!=original


def test_activation_never_restarts_with_pending_host_worker(tmp_path):
    m,h,original=activation_fixture(tmp_path)
    (h/'state.json').write_text(json.dumps({'synthetic':{'status':'preparing'}}))
    def run(argv,**kwargs):
        assert argv[0]=='docker';return SimpleNamespace(stdout='',returncode=0)
    assert m.check(tmp_path,'com.codex.adni-sb-queue-five',run)['status']=='waiting_for_idle'


def test_idle_activation_is_graceful_and_restores_original_policy(tmp_path,monkeypatch):
    m,h,original=activation_fixture(tmp_path);monkeypatch.setattr(m.time,'sleep',lambda n:None);calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout='',stderr='',returncode=0)
    d=m.check(tmp_path,'com.codex.adni-sb-queue-five',run)
    assert d['status']=='waiting_for_new_controller'
    assert any(a[:3]==['launchctl','kill','SIGTERM'] for a in calls)
    assert not any('SIGKILL' in a or 'SIGSTOP' in a or '-k' in a for a in calls)
    (h/'status.json').write_text(json.dumps({'ants_iteration_logging_launcher':str(m.LAUNCHER),'controller_pid':123}))
    d=m.check(tmp_path,'com.codex.adni-sb-queue-five',lambda *a,**k:pytest.fail('Must not signal the new controller'))
    assert d['status']=='active' and d['admission_restored']
    assert json.loads((h/'settings.json').read_text())['admission']==original


def test_bare_verbose_preserves_following_computational_option():
    import runpy
    f = runpy.run_path(str(STEP / "antsRegistration"))["verbose_args"]
    args = ["--masks", "[", "mask,", "NULL", "]", "-v", "--winsorize-image-intensities", "[", "0.025,", "0.975", "]", "--write-composite-transform", "0"]
    assert f(args) == args[:5] + args[6:] + ["--verbose", "1"]
    assert f(["--version"]) == ["--version", "--verbose", "1"]
