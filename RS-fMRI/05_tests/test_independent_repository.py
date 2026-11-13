"""Synthetic idle-handoff tests: no real containers, services or private data."""
import importlib.util
import json
import plistlib
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB/'04_workflow'))
import independent_repository as migration
import cpu_budget
import live_services


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True);path.write_text(json.dumps(value))


def test_cpu_quota_targets_only_known_imaging_names():
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        if args[1]=='ps':return 'one two'
        if args[1]=='inspect':return json.dumps([
            {'Id':'one', 'Name':'/statmind-fmriprep-ADNI999S9999-M000', 'HostConfig':{'NanoCpus':4_000_000_000}, 'State':{'StartedAt':'fixed'}},
            {'Id':'two', 'Name':'/unrelated-web-service', 'HostConfig':{'NanoCpus':0}, 'State':{'StartedAt':'fixed'}}])
        return 'one'
    rows = cpu_budget.reconcile(1.5, runner)
    assert len(rows)==1 and rows[0]['cpus']==1.5
    assert [x for x in calls if x[1]=='update']==[['docker','update','--cpus','1.5','one']]
    assert not any('stop' in c or 'restart' in c for c in calls)


def fixture(tmp_path):
    save(tmp_path/'continuous5/source-copy-gate/status.json', {'status':'admission_held_for_repository_migration'})
    save(tmp_path/'continuous5/rolling/jobs/ADNI999S9999.json', {'status':'completed_QC_pending'})
    return {'runtime':str(tmp_path), 'subjects':['ADNI999S9999']}


def no_containers(*args, **kwargs):return SimpleNamespace(stdout='', returncode=0)


def test_active_imaging_prevents_all_migration_steps(tmp_path):
    plan = fixture(tmp_path)
    runner = lambda *a,**k:SimpleNamespace(stdout='statmind-fmriprep-ADNI999S9999-M000\n', returncode=0)
    ready, detail = migration.readiness(plan, runner)
    assert ready is False and detail['reason']=='waiting_for_imaging'


def test_archive_and_s12_are_required_after_calculation(tmp_path):
    plan = fixture(tmp_path);pair = tmp_path/'external/pair'
    save(tmp_path/'continuous5/offload_receipts/ADNI999S9999_pair.json',
         {'status':'archived_and_local_space_reclaimed','external_path':str(pair)})
    save(pair/'archive_manifest.json', {})
    assert migration.readiness(plan, no_containers)[1]['reason']=='waiting_for_S12'
    save(pair/'results/export_manifest.json', {})
    assert migration.readiness(plan, no_containers)[0] is True


def test_failure_remains_a_failure_and_is_not_relaunched(tmp_path):
    plan = fixture(tmp_path)
    save(tmp_path/'continuous5/rolling/jobs/ADNI999S9999.json', {'status':'deferred_or_failed'})
    ready, detail = migration.readiness(plan, no_containers)
    assert ready and detail['terminal_failures_preserved']==['ADNI999S9999']


def test_released_admission_hold_blocks_cutover(tmp_path):
    plan = fixture(tmp_path);save(tmp_path/'continuous5/source-copy-gate/status.json', {'status':'ready'})
    with pytest.raises(ValueError, match='Admission hold'):migration.readiness(plan, no_containers)


def test_pending_batch_never_stops_services(tmp_path, monkeypatch):
    plan = fixture(tmp_path)
    monkeypatch.setattr(migration, 'validate_sources', lambda unused:None)
    monkeypatch.setattr(migration, 'readiness', lambda *a:(False, {'reason':'waiting_for_imaging'}))
    monkeypatch.setattr(migration, 'service', lambda *a:pytest.fail('Must not stop any live service'))
    assert migration.step(plan) is False


def test_owned_binding_never_reads_absent_legacy_source(tmp_path):
    path = LAB/'pipeline/s10_xcpd_integrated_qc/pipeline.py'
    spec = importlib.util.spec_from_file_location('independent_test_xcpd', path)
    pipeline = importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
    cfg = pipeline.load(LAB/'03_config/xcpd_linc.example.json')
    cfg.update(root=str(tmp_path), repo=str(tmp_path/'absent-original-checkout'))
    config = tmp_path/'config.json';save(config, cfg)
    cid = cfg['run_id']+'-'+pipeline.digest(cfg)[:12]
    save(tmp_path/'postprocessing'/cid/'configuration.json', {**cfg, '_config_id':cid})
    save(tmp_path/'continuous5/settings.json', {'target_concurrency':5, 'global_compute_limit':5})
    binding = {'historical_repo':cfg['repo'],'effective_repo':str(pipeline.DEFAULT_UPSTREAM),
        's8_sha256':{name:live_services.sha(pipeline.DEFAULT_UPSTREAM/'s8_final_qc'/(name+'.py'))
                    for name in ['summarize_motion_from_confounds','extract_euler_from_freesurfer','finalize_inclusion']}}
    dep = tmp_path/'deployment.json';save(dep, {'root':str(tmp_path), 'xcpd_config_sha256':live_services.sha(config),
        'legacy_sources_sha256':{}, 'xcpd_config_id':cid, 'active_xcpd':{}, 'repository_binding':binding})
    before = config.read_bytes();app = live_services.pipeline(config, dep)
    assert app.config_id==cid and config.read_bytes()==before
    assert app.cfg['repo']==str(pipeline.DEFAULT_UPSTREAM)
    assert not Path(cfg['repo']).exists()
    binding['s8_sha256']['finalize_inclusion']='modified';data=json.loads(dep.read_text());data['repository_binding']=binding;save(dep,data)
    with pytest.raises(ValueError,match='S8 semantics'):live_services.verify_deployment(dep,config)


def test_adapter_uses_environment_inside_owned_repository():
    path = LAB/'pipeline/s7b_sessionwise_preprocessing/run.py'
    spec = importlib.util.spec_from_file_location('independent_adapter',path)
    adapter = importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    env = adapter.environment()
    assert env['PATH'].split(':')[0]==str(LAB/'.venv/bin')
    assert env['R_LIBS_USER']==str(LAB/'.R-library')


def test_concurrent_source_edits_hold_the_handoff(tmp_path, monkeypatch):
    repo = tmp_path/'repo';lab = repo/'RS-fMRI';lab.mkdir(parents=True)
    root = tmp_path/'runtime';proof = root/'proof';proof.mkdir(parents=True)
    settings = root/'continuous5/settings.json';save(settings, {'target_concurrency':5})
    target = lab/'worker.py';target.write_text('original')
    staged = proof/'staged.py';staged.write_text('reviewed')
    old_deployment = proof/'old-deployment.json';save(old_deployment, {})
    plan = {'repository':str(repo), 'runtime':str(root), 'proof_directory':str(proof),
        'python':str(lab/'.venv/bin/python'), 'settings_before_sha256':migration.sha(settings),
        'old_deployment':str(old_deployment),'old_deployment_sha256':migration.sha(old_deployment),
        'files':[{'relative':'RS-fMRI/worker.py', 'staged':str(staged),
                  'before_sha256':migration.sha(target), 'after_sha256':migration.sha(staged)}]}
    monkeypatch.setattr(migration, 'LAB', lab)
    migration.validate_sources(plan)
    target.write_text('another owner edited this')
    with pytest.raises(ValueError,match='Concurrent source'):migration.validate_sources(plan)
    assert target.read_text()=='another owner edited this'


def test_cpu_service_moves_to_owned_source_without_starting_a_service(tmp_path, monkeypatch):
    home = tmp_path/'home';folder = home/'Library/LaunchAgents';folder.mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', lambda:home)
    proof = tmp_path/'proof';proof.mkdir()
    label = 'com.codex.adni-sb-cpu-budget';path = folder/(label+'.plist')
    path.write_bytes(plistlib.dumps({'Label':label, 'ProgramArguments':['/old/checkout/.venv/bin/python','-u','/separate/tool.py']}))
    plan = {'proof_directory':str(proof), 'services':[label], 'old_repository':'/old/checkout',
        'old_python':'/old/checkout/.venv/bin/python','python':str(LAB/'.venv/bin/python'),
        'old_deployment':'/runtime/old-deployment.json', 'deployment':'/runtime/new-deployment.json','runtime':'/runtime'}
    migration.rewire_services(plan)
    data = plistlib.loads(path.read_bytes())
    assert data['ProgramArguments'][2]==str(LAB/'04_workflow/cpu_budget.py')
    assert '/old/checkout' not in json.dumps(data)
    assert (proof/'plists-before'/(label+'.plist')).exists()


def test_complete_idle_handoff_stays_stopped_and_preserves_original_configuration(tmp_path, monkeypatch):
    plan = fixture(tmp_path);proof = tmp_path/'proof';proof.mkdir()
    pair = tmp_path/'external/pair'
    save(tmp_path/'continuous5/offload_receipts/ADNI999S9999_pair.json',
         {'status':'archived_and_local_space_reclaimed','external_path':str(pair)})
    save(pair/'archive_manifest.json', {});save(pair/'results/export_manifest.json', {})
    settings = {'target_concurrency':5,'verified_continuation':{'path':'old-scope','sha256':'historical'}}
    save(tmp_path/'continuous5/settings.json',settings);save(proof/'settings.before.json',settings)
    save(proof/'continuation.before.json', {'subjects':{}})
    save(proof/'deployment.before.json', {'xcpd_config_id':'fixed-config-id','root':str(tmp_path)})
    config = tmp_path/'historical-config.json';save(config, {'repo':'/absent/original/checkout'})
    before = config.read_bytes()
    home = tmp_path/'home';folder = home/'Library/LaunchAgents';folder.mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', lambda:home)
    label = 'com.codex.adni-sb-cpu-budget';plist = folder/(label+'.plist')
    plist.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':['/absent/original/checkout/.venv/bin/python','/old-tool.py']}))
    names = ['summarize_motion_from_confounds','extract_euler_from_freesurfer','finalize_inclusion']
    protocol = LAB/'pipeline'
    plan.update(repository=str(LAB.parent),python=str(LAB/'.venv/bin/python'),proof_directory=str(proof),
        files=[],bound_sources=[],settings_before_sha256=migration.sha(tmp_path/'continuous5/settings.json'),
        old_deployment=str(proof/'deployment.before.json'),old_deployment_sha256=migration.sha(proof/'deployment.before.json'),
        deployment=str(proof/'deployment.integrated.json'),xcpd_config=str(config),services=[label],
        old_python='/absent/original/checkout/.venv/bin/python',old_repository='/absent/original/checkout',
        historical_s8_sha256={n:migration.sha(protocol/'s8_final_qc'/(n+'.py')) for n in names})
    calls=[]
    def runner(args, **kwargs):
        calls.append(args);return SimpleNamespace(stdout='',stderr='',returncode=0)
    assert migration.step(plan,runner) is True
    report = json.loads((tmp_path/'continuous5/independent-repository.json').read_text())
    assert report['automatic_resume'] is False and report['legacy_checkout_required'] is False
    assert config.read_bytes()==before
    assert json.loads((proof/'deployment.integrated.json').read_text())['xcpd_config_id']=='fixed-config-id'
    assert not any(c[0]=='docker' and c[1] in ('run','start','stop','restart','pause') for c in calls)
    assert not any(c[0]=='launchctl' and c[1] in ('enable','bootstrap','kickstart') for c in calls)
    prior=len(calls);assert migration.step(plan,runner) is True and len(calls)==prior
