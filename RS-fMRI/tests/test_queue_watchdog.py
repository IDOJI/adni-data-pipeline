import importlib.util,json
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location('watchdog',Path(__file__).resolve().parents[1]/'04_workflow/queue_watchdog.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
NOW=2000000000

def setup(tmp,age=0,mode='running'):
 d=tmp/'continuous5';d.mkdir();(d/'status.json').write_text(json.dumps({'updated_at':datetime.fromtimestamp(NOW-age,timezone.utc).isoformat(),'mode':mode}));return d

def test_fresh_and_disk_wait_do_not_restart(tmp_path):
 setup(tmp_path,mode='waiting_for_disk_capacity');calls=[]
 assert w.check(tmp_path,'com.codex.adni-test',now=NOW,runner=lambda *a,**k:calls.append(a))['status']=='healthy'
 assert calls==[]

def test_stale_restarts_only_controller(tmp_path):
 setup(tmp_path,age=181);calls=[]
 def run(argv,**kw):calls.append(argv);return SimpleNamespace(returncode=0,stderr='')
 assert w.check(tmp_path,'com.codex.adni-test',now=NOW,runner=run)['status']=='controller_restarted'
 assert calls==[['launchctl','kickstart','-k','gui/'+str(w.os.getuid())+'/com.codex.adni-test']]
 assert json.loads((tmp_path/'continuous5/watchdog_restarts.json').read_text())==[NOW]

def test_finished_and_maintenance_are_preserved(tmp_path):
 d=setup(tmp_path,age=1000,mode='queue_exhausted')
 assert w.check(tmp_path,'com.codex.adni-test',now=NOW)['status']=='queue_exhausted'
 (d/'watchdog_maintenance.json').write_text(json.dumps({'until_epoch':NOW+60}))
 assert w.check(tmp_path,'com.codex.adni-test',now=NOW)['status']=='maintenance'

def test_restart_storm_is_limited(tmp_path):
 d=setup(tmp_path,age=1000);(d/'watchdog_restarts.json').write_text(json.dumps([NOW-60,NOW-120,NOW-180]))
 assert w.check(tmp_path,'com.codex.adni-test',now=NOW)['status']=='recovery_rate_limited'
