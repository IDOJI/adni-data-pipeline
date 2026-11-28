#!/usr/bin/env python3
"""Adopt one verified orphan and continue the existing statMIND two-visit pilot.

The container remains untouched while Docker logs and its exit status are
observed. The same Docker process must actually finish before recovery occurs.
This is a one-shot process, not a scheduled or recurring job.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import adopt_orphan as adoption
import pilot
import qc
import run as local
import spatial_qc


def dump_event(path, record, action, **data):
    event = {'time': local.now(), 'action': action, **data}
    record['events'].append(event)
    local.dump(path, record)
    print(json.dumps(event, ensure_ascii=False), flush=True)


def start():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.local.yaml'))
    args = parser.parse_args()
    cfg = local.load(args.config)
    root = local.runtime(cfg)
    old_path = args.record.resolve()
    old = json.loads(old_path.read_text())
    if old.get('status') != 'running' or old['config'] != cfg:
        raise ValueError('The selected old invocation does not match the unchanged configuration')
    lock_value = json.loads((root / 'pipeline.lock').read_text())
    if old['case'] != lock_value['case'] or old['stage'] != lock_value['stage']:
        raise ValueError('Existing lock does not describe the selected invocation')
    old_pid = int(lock_value['pid'])
    if int((root / 'orchestration.lock').read_text()) != old_pid:
        raise ValueError('Existing orchestration owner does not match')
    adoption.assert_pid_absent(old_pid)
    expected_hash = adoption.digest(old_path)
    image_pos = old['command'].index(old['image']['resolved'])
    name_pos = old['command'].index('--name')
    name = old['command'][name_pos + 1]
    if old['command'][image_pos + 1:] == []:
        raise ValueError('Missing original application command')

    supervisor_lock = root / 'statmind-supervisor.lock'
    fd = os.open(supervisor_lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    orchestration_owned = False
    follower = None
    folder = root / 'logs' / ('supervisor_' + local.now().replace(':', '').replace('.', '') + '_' + uuid.uuid4().hex[:8])
    folder.mkdir()
    record_path = folder / 'run.json'
    status = {'started_at': local.now(), 'pid': os.getpid(), 'status': 'running', 'events': [],
              'original_run': str(old_path), 'original_run_sha256': expected_hash,
              'supervisor_sha256': adoption.digest(__file__),
              'recovery_source_sha256': adoption.digest(adoption.__file__),
              'scientific_inclusion': 'requires_representative_cohort_calibration_and_researcher_review'}
    try:
        shutil.copy2(__file__, folder / 'supervisor_source.py')
        shutil.copy2(adoption.__file__, folder / 'recovery_source.py')
        shutil.copy2(args.config, folder / 'config_source.yaml')
        inspection = subprocess.run(['docker', 'inspect', name], check=True, capture_output=True, text=True)
        inspected = json.loads(inspection.stdout)
        if len(inspected) != 1:
            raise ValueError('Expected exactly one live container')
        container_id = adoption.validate_inspect(old, inspected[0])
        inspect_path = folder / 'container-inspect.json'
        inspect_path.write_text(inspection.stdout)
        log_path = folder / 'docker-recovered-console.log'
        exit_path = folder / 'docker-wait-exit-code.txt'
        dump_event(record_path, status, 'verified_and_attached_to_running_container', container_id=container_id)
        with log_path.open('wb') as console:
            follower = subprocess.Popen(['docker', 'logs', '--follow', '--timestamps', container_id],
                                        stdout=console, stderr=subprocess.STDOUT)
            waited = subprocess.run(['docker', 'wait', container_id], capture_output=True, text=True)
            exit_path.write_text(waited.stdout)
            if waited.returncode != 0:
                raise ValueError('Docker wait failed; see captured wait output')
            if follower.wait(timeout=120) != 0:
                raise ValueError('Docker log follower did not end successfully')
        dump_event(record_path, status, 'observed_container_exit', exit_code=adoption.validate_wait_code(waited.stdout))
        adoption.recover(old_path, inspect_path, log_path, exit_path, expected_hash)
        dump_event(record_path, status, 'recovered_original_run_record')

        # Guard the entire continuation against another pilot.py invocation.
        orchestration = root / 'orchestration.lock'
        fd = os.open(orchestration, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        orchestration_owned = True

        for case in cfg['runs']:
            qc.latest_run(cfg, case, 'mriqc')
        if not pilot.finished(cfg, 'fmriprep', old['case']):
            raise ValueError('Recovered first fMRIPrep execution is not reusable')
        group = sorted((root / 'logs').glob('mriqc_group_*/run.json'))
        if not group:
            raise ValueError('No MRIQC group record')
        group_record = json.loads(group[-1].read_text())
        if group_record.get('exit_code') != 0 or not group_record.get('IQMs_unchanged'):
            raise ValueError('MRIQC group did not finish successfully')
        dump_event(record_path, status, 'verified_existing_mriqc_and_recovered_fmriprep')

        for case in cfg['runs']:
            if case == old['case']:
                continue
            attempts = list((root / 'logs').glob(f"*_fmriprep_sub-{case['subject']}_ses-{case['session']}/run.json"))
            if attempts:
                if not pilot.finished(cfg, 'fmriprep', case):
                    raise ValueError('Existing second-visit attempt requires inspection')
                dump_event(record_path, status, 'reused_verified_fmriprep', subject=case['subject'])
            else:
                if shutil.disk_usage(root).free < 25 * 1024**3:
                    raise ValueError('Less than 25 GiB free; preserve outputs and inspect available disk')
                profile = pilot.profile_for(cfg, case)
                dump_event(record_path, status, 'starting_fmriprep', subject=case['subject'], profile=profile)
                local.run_stage(cfg, 'fmriprep', case, profile)
                dump_event(record_path, status, 'completed_fmriprep', subject=case['subject'])
        qc.check_fmriprep(cfg)
        qc.final_qc(cfg)
        dump_event(record_path, status, 'completed_cifti_surface_motion_euler_checks')
        spatial_qc.inspect(cfg)
        dump_event(record_path, status, 'completed_spatial_numerical_qc')
        subprocess.run([sys.executable, str(Path(__file__).with_name('render_reports.py')), 'fmriprep'], check=True)
        dump_event(record_path, status, 'rendered_fmriprep_reports_for_visual_review')
        status['status'] = 'processing_and_numerical_checks_completed_visual_review_required'
    except BaseException as exc:
        status.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        if follower is not None and follower.poll() is None:
            follower.terminate()  # Stops only the log follower, never the processing container.
        if orchestration_owned:
            lock = root / 'orchestration.lock'
            if lock.exists() and lock.read_text().strip() == str(os.getpid()):
                lock.unlink()
        if supervisor_lock.exists() and supervisor_lock.read_text().strip() == str(os.getpid()):
            supervisor_lock.unlink()
        status['ended_at'] = local.now()
        local.dump(record_path, status)
        print(json.dumps({'status': status['status'], 'record': str(record_path)}), flush=True)


if __name__ == '__main__':
    start()
