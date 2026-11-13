"""Drain a fixed cohort, then rebind an idle installation to owned source.

The private plan lives outside the repository. No image is launched by this tool.
Existing images, records, scientific settings and caches are never rewritten.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import time

LAB = Path(__file__).resolve().parents[1]
MANAGED = re.compile(r'^(?:statmind-(?:mriqc|fmriprep)-|(?:adni|statmind)-xcpd-)ADNI\d+S\d+-')


def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.writing');tmp.write_text(json.dumps(value, indent=2)+'\n');tmp.replace(path)


def running(runner=subprocess.run):
    result = runner(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True, check=True, timeout=30)
    return [n for n in result.stdout.splitlines() if MANAGED.match(n)]


def busy(path):
    if not path.exists():return False
    with path.open('a') as handle:
        try:fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:return True
    return False


def readiness(plan, runner=subprocess.run):
    root = Path(plan['runtime']);here = root/'continuous5'
    if read(here/'source-copy-gate/status.json')['status'] != 'admission_held_for_repository_migration':
        raise ValueError('Admission hold must remain active until explicit later resume')
    active = running(runner)
    if active:return False, {'reason':'waiting_for_imaging', 'active_containers':active}
    failures = []
    for subject in plan['subjects']:
        if busy(here/'rolling/jobs'/(subject+'.lock')):
            return False, {'reason':'waiting_for_subject_worker', 'subject':subject}
        path = here/'rolling/jobs'/(subject+'.json')
        state = read(path) if path.exists() else read(here/'state.json').get(subject, {})
        if state.get('status') in ('deferred_or_failed', 'skipped_source_review'):
            # Preserve failed work and its original receipts; never relaunch with
            # a different source identity merely to make the migration finish.
            failures.append(subject);continue
        if state.get('status') != 'completed_QC_pending':
            return False, {'reason':'waiting_for_preprocessing', 'subject':subject}
        receipts = [read(p) for p in (here/'offload_receipts').glob(subject+'_*.json')]
        good = [r for r in receipts if r.get('status') == 'archived_and_local_space_reclaimed']
        if not good:return False, {'reason':'waiting_for_postprocessing_and_archive', 'subject':subject}
        for receipt in good:
            pair = Path(receipt['external_path'])
            if not (pair/'archive_manifest.json').is_file():
                return False, {'reason':'waiting_for_archive_manifest', 'subject':subject}
            if not (pair/'results/export_manifest.json').is_file():
                return False, {'reason':'waiting_for_S12', 'subject':subject}
    return True, {'reason':'ready', 'terminal_failures_preserved':failures}


def validate_sources(plan):
    repo = Path(plan['repository']).resolve()
    if repo != LAB.parent.resolve():raise ValueError('Plan targets a different repository')
    root = Path(plan['runtime']).resolve()
    if root == repo or root in repo.parents or repo in root.parents:raise ValueError('Runtime must remain external')
    python = Path(plan['python'])
    if python != LAB/'.venv/bin/python':raise ValueError('Use the repository-owned Python environment')
    settings = Path(plan['runtime'])/'continuous5/settings.json'
    generated = Path(plan['proof_directory'])/'settings.integrated.sha256.json'
    allowed = [plan['settings_before_sha256']]
    if generated.exists():allowed.append(read(generated)['sha256'])
    if sha(settings) not in allowed:raise ValueError('Queue settings changed during the handoff')
    if sha(plan['old_deployment']) != plan['old_deployment_sha256']:
        raise ValueError('Historical deployment changed during the handoff')
    rebound = Path(plan['proof_directory'])/'plists.integrated.sha256.json'
    rebound_hashes = read(rebound) if rebound.exists() else {}
    for path, digest in plan.get('plist_sha256', {}).items():
        if sha(path) not in (digest, rebound_hashes.get(path)):
            raise ValueError('Service configuration changed during the handoff: '+path)
    for item in plan['files']:
        target = repo/item['relative']
        if not target.resolve().is_relative_to(repo) or target.is_symlink():raise ValueError('Redirected source target')
        if sha(item['staged']) != item['after_sha256']:raise ValueError('Staged source changed')
        current = sha(target) if target.exists() else None
        if current not in (item['before_sha256'], item['after_sha256']):
            raise ValueError('Concurrent source modification: '+item['relative'])


def service(action, label, runner=subprocess.run):
    if not label.startswith('com.codex.adni-sb-'):raise ValueError('Unexpected service label')
    return runner(['launchctl', action, f'gui/{os.getuid()}/{label}'], capture_output=True, text=True, timeout=30)


def install_sources(plan):
    repo = Path(plan['repository']);proof = Path(plan['proof_directory'])
    for item in plan['files']:
        destination = repo/item['relative'];backup = proof/'source-before'/item['relative']
        if destination.exists() and not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True);shutil.copy2(destination, backup)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name+'.migration-writing')
        shutil.copy2(item['staged'], temporary);temporary.replace(destination)


def deployment(plan):
    """Bind historical analysis identity to reviewed owned source without an old read."""
    proof = Path(plan['proof_directory']);old = read(proof/'deployment.before.json')
    cfg = read(plan['xcpd_config']);protocol = LAB/'pipeline'
    steps = ('summarize_motion_from_confounds', 'extract_euler_from_freesurfer', 'finalize_inclusion')
    binding = {'historical_repo':cfg['repo'], 'effective_repo':str(protocol),
               's8_sha256':plan['historical_s8_sha256'], 'source_binding_only':True}
    if binding['s8_sha256'] != {s:sha(protocol/'s8_final_qc'/(s+'.py')) for s in steps}:
        raise ValueError('S8 behavior differs from the historical deployment')
    result = {**old, 'legacy_preprocessing':str(LAB/'pipeline/s7b_sessionwise_preprocessing'),
              'legacy_xcpd':str(LAB/'pipeline/s10_xcpd_integrated_qc'), 'legacy_subjects':[],
              'active_xcpd':{}, 'legacy_sources_sha256':{}, 'repository_binding':binding}
    result['integrated_sources_sha256'] = {
        str(LAB/path):sha(LAB/path) for path in plan['bound_sources']}
    result['independent_repository'] = {'at':now(), 'python':plan['python'],
        'historical_deployment':str(proof/'deployment.before.json'),
        'current_cohort':plan['subjects'], 'automatic_resume':False}
    save(plan['deployment'], result)
    settings = read(proof/'settings.before.json')
    registry = read(proof/'continuation.before.json')
    for route in registry['subjects'].values():
        route.update(backend=str(LAB/'pipeline/s7b_sessionwise_preprocessing/run.py'))
        route['backend_sha256'] = sha(route['backend'])
        # Input/config/receipt identities are never changed or re-signed here.
    registry['source_rebinding'] = {'at':now(), 'previous_registry':settings['verified_continuation'],
        'scope':'future executable source only; existing attempts and scientific settings immutable'}
    rp = proof/'continuation.integrated.json';save(rp, registry)
    settings['verified_continuation'] = {'path':str(rp), 'sha256':sha(rp)}
    settings['repository_migration'] = {'deployment':plan['deployment'], 'admission_held':True,
        'resume_requires_explicit_request':True, 'cpu_quota_per_container':1.5}
    save(Path(plan['runtime'])/'continuous5/settings.json', settings)
    save(proof/'settings.integrated.sha256.json', {'sha256':sha(Path(plan['runtime'])/'continuous5/settings.json')})


def rewire_services(plan):
    proof = Path(plan['proof_directory']);folder = Path.home()/'Library/LaunchAgents'
    hashes = {}
    for label in plan['services']:
        path = folder/(label+'.plist');original = proof/'plists-before'/(label+'.plist')
        if not original.exists():
            original.parent.mkdir(exist_ok=True);shutil.copy2(path, original)
        data = plistlib.loads(original.read_bytes());args = data['ProgramArguments']
        args = [plan['python'] if x == plan['old_python'] else
                plan['deployment'] if x == plan['old_deployment'] else x for x in args]
        if label.endswith('-cpu-budget'):
            args = [plan['python'], '-u', str(LAB/'04_workflow/cpu_budget.py'),
                    '--root', plan['runtime'], '--cpus', '1.5', 'watch']
        data['ProgramArguments'] = args
        data.setdefault('EnvironmentVariables', {}).update(
            R_LIBS_USER=str(LAB/'.R-library'), PYTHONDONTWRITEBYTECODE='1')
        if plan['old_repository'] in json.dumps(data):raise ValueError('Service still references old repository: '+label)
        for arg in args:
            if arg.endswith('.py') and not Path(arg).resolve().is_relative_to(LAB.resolve()):
                raise ValueError('Service source remains outside this repository: '+label)
        temporary = path.with_suffix('.migration-writing');temporary.write_bytes(plistlib.dumps(data));temporary.replace(path)
        hashes[str(path)] = sha(path)
        save(proof/'plists.integrated.sha256.json', hashes)


def update_operating_notes(plan):
    """Optional local bookkeeping; never a dependency of the imaging pipeline."""
    notes = plan.get('operating_notes', {})
    if not notes:return
    path = Path(notes['registry']);lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        parts = line.split('|')
        if len(parts) != 11:continue
        key = parts[1].strip();entry = notes['rows'].get(key)
        if entry:
            parts[3] = ' '+entry['lifecycle']+' '
            if entry.get('source'):parts[7] = ' '+entry['source']+' '
            parts[8] = ' '+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()+' '
            addition = '독립 저장소 전환 검증 완료·현재 묶음 이후 자동 처리 중지'
            if addition not in parts[9]:parts[9] = parts[9].rstrip()+'; '+addition+' '
            lines[i] = '|'.join(parts)
    temporary = path.with_name(path.name+'.writing');temporary.write_text('\n'.join(lines)+'\n');temporary.replace(path)
    subprocess.run([plan['python'], notes['registry_checker']], check=True, timeout=30, capture_output=True)
    with Path(notes['history']).open('a') as stream:
        stream.write('\n\n# 🟥1️⃣ 독립 저장소 전환 자동 완료 — '+now()+' 📦\n\n'
            '- 현재 묶음 처리 종료·성공 대상 후처리/외장 보관/S12 확인 후 유휴 전환 완료\n'
            '- 기존 리포 읽기 차단 상태에서 새 Python·프로토콜·큐·후처리 검사 통과\n'
            '- 실행 코드와 Python/R 환경 통합 저장소로 전환, 과거 설정·영상·실행 기록 보존\n'
            '- 작업 서비스 비활성 유지·새 대상 자동 재개 없음·기존 리포 삭제 없음\n')


def verify(plan, runner=subprocess.run):
    """Read-only commands cannot access the legacy checkout even if it remains on disk."""
    profile = '(version 1)(allow default)(deny file-read* (subpath '+json.dumps(plan['old_repository'])+'))'
    prefix = ['/usr/bin/sandbox-exec', '-p', profile] if Path('/usr/bin/sandbox-exec').exists() else []
    commands = [
        [plan['python'], '-c', 'import numpy,pandas,nibabel,yaml,scipy,nilearn; print("imports passed")'],
        [plan['python'], str(LAB/'04_workflow/lab.py'), 'doctor'],
        [plan['python'], str(LAB/'04_workflow/live_services.py'), '--config', plan['xcpd_config'],
         '--deployment', plan['deployment'], 'check'],
        [plan['python'], str(LAB/'04_workflow/queue_service.py'), '--root', plan['runtime'],
         '--deployment', plan['deployment'], '--check']]
    if plan.get('rscript'):
        library = str(LAB/'.R-library')
        code = '.libPaths(c('+json.dumps(library)+', .libPaths())); library(jsonlite); stopifnot(startsWith(find.package("jsonlite"), '+json.dumps(library)+')); cat("owned R library passed\\n")'
        commands.append([plan['rscript'], '--vanilla', '-e', code])
    results = []
    for cmd in commands:
        result = runner(prefix+cmd, cwd=LAB, capture_output=True, text=True, timeout=120)
        results.append({'command':cmd, 'returncode':result.returncode, 'stdout':result.stdout[-5000:], 'stderr':result.stderr[-3000:]})
        if result.returncode:
            save(Path(plan['proof_directory'])/'checks.failed.json', results)
            raise RuntimeError('Independent read-only check failed: '+str(cmd))
    save(Path(plan['proof_directory'])/'checks.passed.json', {'legacy_reads_denied':bool(prefix), 'results':results})


def step(plan, runner=subprocess.run):
    report = Path(plan['runtime'])/'continuous5/independent-repository.json'
    old = read(report) if report.exists() else {}
    if old.get('status') == 'completed':return True
    validate_sources(plan)
    ready, details = readiness(plan, runner)
    if not ready:
        save(report, {'status':'draining_current_subjects', 'at':now(), 'subjects':plan['subjects'],
                      'new_admission_held':True, 'LLM_calls':0, **details});return False
    # At the handoff boundary no imaging container or subject worker owns work.
    # Disable only the explicitly captured ADNI services; never signal an image.
    for label in plan['services']:
        result = service('disable', label, runner)
        if result.returncode:raise RuntimeError('Could not hold service '+label)
        service('bootout', label, runner)
    if running(runner):raise RuntimeError('An imaging container appeared after the idle boundary')
    save(report, {'status':'installing_at_idle_boundary', 'at':now(), 'subjects':plan['subjects'], **details})
    install_sources(plan)
    deployment(plan)
    rewire_services(plan)
    verify(plan, runner)
    warnings = []
    try:update_operating_notes(plan)
    except Exception as exc:warnings.append('Optional operating-note update: '+str(exc))
    save(report, {'status':'completed', 'at':now(), 'subjects':plan['subjects'],
        'new_admission_held':True, 'services_rebound_and_disabled':plan['services'],
        'repository':plan['repository'], 'python':plan['python'],
        'legacy_checkout_required':False, 'old_repository_deleted':False,
        'scientific_configuration_rewritten':False, 'automatic_resume':False,
        'proof_directory':plan['proof_directory'], 'LLM_calls':0, 'bookkeeping_warnings':warnings, **details})
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('action', choices=['check', 'watch'])
    a = p.parse_args();plan = read(a.plan);validate_sources(plan)
    if a.action == 'check':
        print(json.dumps({'sources_valid':True, 'readiness':readiness(plan)}));return
    directory = Path(plan['proof_directory'])
    with (directory/'migration.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            try:
                if step(plan):return
            except Exception as exc:
                save(Path(plan['runtime'])/'continuous5/independent-repository.json',
                     {'status':'migration_held_error', 'at':now(), 'error':str(exc), 'new_admission_held':True, 'LLM_calls':0})
            time.sleep(30)


if __name__ == '__main__':main()
