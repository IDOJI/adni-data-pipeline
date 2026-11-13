"""Validated compatibility deployment for an already running ADNI pair workflow.

Keep historical scientific configuration and result identifiers immutable; record
code deployment separately. Never use this entry point to change analysis settings.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

import compute_slots
import source_review
from protocol_source import inspect_protocol

LAB = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def verify_deployment(path, config_path):
    dep = load(path)
    if sha(config_path) != dep['xcpd_config_sha256']:
        raise ValueError('Historical scientific configuration changed')
    cfg = load(config_path)
    pinned = LAB / 'pipeline'
    inspect_protocol(LAB)
    binding = dep.get('repository_binding')
    if binding:
        if binding['historical_repo'] != cfg['repo'] or Path(binding['effective_repo']).resolve() != pinned.resolve():
            raise ValueError('Repository binding differs from the reviewed integrated source')
    for stem in ('summarize_motion_from_confounds','extract_euler_from_freesurfer','finalize_inclusion'):
        expected = binding['s8_sha256'][stem] if binding else sha(Path(cfg['repo'])/'s8_final_qc'/(stem+'.py'))
        if expected != sha(pinned/'s8_final_qc'/(stem+'.py')):
            raise ValueError('Historical S8 semantics differ from the pinned upstream')
    for name, digest in {**dep['legacy_sources_sha256'],**dep.get('integrated_sources_sha256',{})}.items():
        if sha(name) != digest:
            raise ValueError('Legacy completion source changed: ' + name)
    if Path(cfg['root']).resolve() != Path(dep['root']).resolve():
        raise ValueError('Deployment runtime differs from historical configuration')
    root = Path(cfg['root']).resolve(); repository = LAB.parent.resolve()
    if root == Path('/') or root == repository or repository in root.parents or root in repository.parents:
        raise ValueError('Runtime must be external to the source repository')
    return dep, cfg


def execution_command_builder(original_command, override, config_id):
    """Override execution resources only; retain the immutable analysis identity."""
    if set(override) - {'resources', 'reason', 'approved_at'}:
        raise ValueError('Only execution resources may be overridden')
    resources = override.get('resources', {})
    if set(resources) != {'cpus', 'omp_nthreads', 'mem_mb', 'docker_memory'}:
        raise ValueError('Explicit complete execution resources are required')
    if not all(isinstance(resources[k], int) and resources[k] > 0 for k in ('cpus', 'omp_nthreads', 'mem_mb')):
        raise ValueError('Invalid execution resource limits')
    if not isinstance(resources['docker_memory'], str) or not resources['docker_memory'].endswith('g'):
        raise ValueError('Docker memory must be an explicit GiB limit')
    cap = int(resources['docker_memory'][:-1]) * 1024
    if resources['mem_mb'] >= cap or resources['omp_nthreads'] > resources['cpus']:
        raise ValueError('Execution memory/thread limits are inconsistent')
    def command(cfg, row, attempt, name):
        effective = {**cfg, 'resources': dict(resources)}
        argv = original_command(effective, row, attempt, name)
        destination = Path(attempt) / 'execution_environment.json'
        # Separate operational provenance; never replace historical configuration.
        destination.write_text(json.dumps({'config_id': config_id, 'historical_resources': cfg['resources'],
            'effective_resources': resources, 'override': override, 'scientific_configuration_unchanged': True}, indent=2)+'\n')
        return argv
    return command


def pipeline(config_path, deployment):
    dep, original = verify_deployment(deployment, config_path)
    p = module('live_integrated_xcpd', LAB / 'pipeline/s10_xcpd_integrated_qc/pipeline.py')
    if dep.get('xcpd_execution_override'):
        p.command = execution_command_builder(p.command, dep['xcpd_execution_override'], dep['xcpd_config_id'])
    original_upstream = p.upstream
    p.upstream = lambda unused_repo, name: original_upstream(p.DEFAULT_UPSTREAM, name)
    compute_slots.configure(dep['root'])

    class LivePipeline(p.Pipeline):
        def __init__(self):
            # This explicit compatibility path preserves the existing config bytes/ID.
            # The ordinary Pipeline constructor still rejects unreviewed repo paths.
            self.config_path = Path(config_path).resolve()
            self.cfg = dict(original)
            if self.cfg['combine_runs'] or not self.cfg['defer_final_decision'] or not self.cfg['linc_qc']:
                raise ValueError('Independent runs, deferred finalization and LINC QC required')
            if self.cfg['nuisance_regressors'] == '36P' and not self.cfg['global_signal_regression']:
                raise ValueError('36P requires accurate GSR provenance')
            self.config_id = self.cfg['run_id'] + '-' + p.digest(self.cfg)[:12]
            if self.config_id != dep['xcpd_config_id']:
                raise ValueError('Historical config_id differs')
            self.cfg['_config_id'] = self.config_id
            self.root = Path(self.cfg['root'])
            self.hub = self.root / 'postprocessing' / self.config_id
            if load(self.hub / 'configuration.json') != self.cfg:
                raise ValueError('Existing scientific configuration does not match')
            # Keep the original config bytes/ID; redirect only executable source.
            if dep.get('repository_binding'):
                self.cfg['repo'] = dep['repository_binding']['effective_repo']
                self.protocol_source = inspect_protocol(LAB)
            self.motion = p.upstream(self.cfg['repo'], 'summarize_motion_from_confounds')
            self.legacy = None
            if dep['active_xcpd']:
                legacy = module('frozen_xcpd_completion', Path(dep['legacy_xcpd']) / 'pipeline.py')
                self.legacy = legacy.Pipeline(config_path)
                self.legacy.pairs = lambda: []  # Never admit another target through legacy code.
            self.deployment = dep

        def pairs(self):
            pairs = super().pairs()
            pairs = [pair for pair in pairs if not source_review.blocked(self.root, load(Path(pair)/'pair_metadata.json')['subject'],load(Path(pair)/'pair_metadata.json'))]
            priority = set(dep.get('xcpd_recovery_priority', []))
            return sorted(pairs, key=lambda pair: load(Path(pair)/'pair_metadata.json')['subject'] not in priority)

        def prepare(self, pair):
            existed = (self.stage_dir(pair) / 'pre_qc.json').exists()
            rows = super().prepare(pair)
            if not existed:
                p.save(self.stage_dir(pair) / 'code_deployment.json', {
                    'deployment': str(Path(deployment).resolve()), 'deployment_sha256': sha(deployment),
                    'effective_upstream': str(p.DEFAULT_UPSTREAM), 'integrated_pipeline': p.__file__,
                    'integrated_pipeline_sha256': sha(p.__file__), 'scientific_config_id_unchanged': self.config_id})
            return rows

        def aggregate(self, cohort_ready=False, mriqc_flags=None):
            source_review.prune_visual_review(self.root,self.hub/'visual_review.tsv',self.hub/'aggregation.lock')
            return super().aggregate(cohort_ready,mriqc_flags)

        def run_one(self, row, force_retry=False):
            if source_review.blocked(self.root,row['sub'].removeprefix('sub-')):
                return {'status':'skipped_source_review'}
            attempt, record = self.latest(row)
            if record and record.get('status') in ('prepared', 'running'):
                expected = self.deployment['active_xcpd'].get(record.get('container'))
                if expected:
                    if record.get('pipeline_sha256') != expected['pipeline_sha256']:
                        raise ValueError('Active attempt source identity changed')
                    p.save(attempt / 'observer_handoff.json', {
                        'deployment_sha256': sha(deployment), 'container_id': expected['container_id'],
                        'original_pipeline_sha256': record['pipeline_sha256'],
                        'completion_source': str(Path(dep['legacy_xcpd']) / 'pipeline.py'),
                        'container_restarted': False})
                    return self.legacy.run_one(row, force_retry=False)
            result = super().run_one(row, force_retry)
            latest_attempt, latest_record = self.latest(row)
            override = dep.get('xcpd_execution_override', {}).get('resources', {})
            old_command = latest_record.get('command', []) if latest_record else []
            old_memory = old_command[old_command.index('--memory')+1] if '--memory' in old_command else None
            if (latest_record and latest_record.get('status') in ('failed', 'partial') and
                old_memory and override.get('docker_memory') and old_memory != override['docker_memory'] and
                len(list(self.attempt_root(row).glob('attempt-*'))) < self.cfg['max_attempts']):
                self.event('resource_revision_retry', run=p.run_key(row), previous_attempt=str(latest_attempt),
                           effective_resources=override)
                return super().run_one(row, force_retry=True)
            return result

        def once(self, pilot=False, prepare_only=False, retry_failed=False):
            # Reuse the base orchestration with a guarded run boundary, including
            # the host-wide five-subject lease shared with the preprocessing queue.
            original_run = self.run_one
            def leased(row, force_retry=False):
                previous, record = self.latest(row)
                finished = bool(record and (record['status'] == 'skipped_insufficient_time' or
                    (record['status'] == 'success' and (previous / 'output_manifest.json').exists())))
                if finished:
                    return original_run(row, force_retry)
                with compute_slots.lease(row['sub'].removeprefix('sub-'), 'xcpd'):
                    return original_run(row, force_retry)
            self.run_one = leased
            try:
                return super().once(pilot, prepare_only, retry_failed)
            finally:
                self.run_one = original_run

    return LivePipeline()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('action', choices=['check', 'watch', 'once'])
    args = parser.parse_args()
    app = pipeline(args.config, args.deployment)
    if args.action == 'check':
        print(json.dumps({'config_id':app.config_id, 'integrated_source':str(LAB),
                          'existing_pairs':len(app.pairs()), 'configuration_unchanged':True})); return
    with (app.hub / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            try:
                app.once()
            except Exception as exc:
                app.event('worker_error', error=f'{type(exc).__name__}: {exc}')
                if args.action != 'watch':raise
            if args.action != 'watch':break
            time.sleep(app.cfg['poll_seconds'])


if __name__ == '__main__':main()
