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
