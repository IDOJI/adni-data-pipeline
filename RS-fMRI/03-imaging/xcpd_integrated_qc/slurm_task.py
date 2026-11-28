"""Explicit Slurm-array entry; exports never submit jobs or send email."""
import fcntl
from pathlib import Path
import shutil
import subprocess
import sys

from pipeline import Pipeline, bids_filter, exact_one, load, now, run_key, save, sha, validate_outputs, xcp_args


def main():
    p = Pipeline(sys.argv[1]); index = int(sys.argv[2])
    mapping = load(p.hub / 'dry_run.json')
    chosen = mapping[index]['run']
    candidates = [r for pair in p.pairs() for r in p.prepare(pair) if r['candidate'] and run_key(r) == chosen]
    if len(candidates) != 1:
        raise ValueError('Array task cannot uniquely select its run')
    row = candidates[0]; root = p.attempt_root(row); root.mkdir(parents=True, exist_ok=True)
    with (root / 'slurm.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous, record = p.latest(row)
        if record and record['status'] == 'success':return
        if record and record['status'] in ('running', 'prepared'):
            raise ValueError('Existing unfinished execution must be reconciled before retry')
        attempt, _ = p.plan_attempt(row); attempt.mkdir(parents=True)
        for name in ('derivatives', 'work'):(attempt / name).mkdir()
        save(attempt / 'bids_filter.json', bids_filter(row, p.cfg))
        save(attempt / 'expected_input.json', {'relative_bold': str(Path(row['source_bold_file']).relative_to(Path(row['source_pair']) / 'fmriprep')),
             'relative_confounds':str(exact_one([Path(f) for f in row['input_files'] if f.endswith('_desc-confounds_timeseries.tsv')],'Exact confounds').relative_to(Path(row['source_pair'])/'fmriprep')),
             'subject':row['sub'].removeprefix('sub-'), 'session':row['ses'].removeprefix('ses-') or None,
             'file_format':p.cfg['file_format'], 'atlases':p.cfg['atlases'], 'expected_rois':p.cfg['expected_rois'], 'space':p.cfg['space'],
             'duration_settings':{k:p.cfg[k] for k in ('fd_threshold','min_time','dummy_scans','motion_filter_type','head_radius','censor_between')},
             'tr':row['tr'],'n_original_volumes':row['n_original_volumes']})
        shutil.copy2(Path(__file__).with_name('container_entry.py'), attempt / 'container_entry.py')
        image=Path(p.cfg['slurm']['image']).resolve()
        if not image.is_file():raise ValueError('Apptainer image missing')
        cmd=['apptainer','exec','--cleanenv','--env','TEMPLATEFLOW_HOME=/templateflow',
             '--bind',str((Path(row['source_pair'])/'fmriprep').resolve())+':/input:ro',
             '--bind',str(attempt.resolve())+':/job','--bind',p.cfg['templateflow']+':/templateflow',
             '--bind',p.cfg['license']+':/license.txt:ro',str(image),'python','/job/container_entry.py',*xcp_args(p.cfg,row)]
        for path,h in row['input_files'].items():
            if sha(path)!=h:raise ValueError('Input changed before Apptainer')
        record={'status':'running','backend':'apptainer','config_id':p.config_id,'row':row,'command':cmd,
                'started_at':now(),'sif_sha256':sha(image),'pipeline_sha256':sha(Path(__file__).with_name('pipeline.py'))}
        save(attempt/'execution.json',record)
        with (attempt/'container.log').open('w') as log:
            status=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
        unchanged=all(sha(path)==h for path,h in row['input_files'].items())
        qc=validate_outputs(attempt,row,p.cfg,status)
        if not unchanged:qc.update(xcpd_status='partial',functional_outputs_valid=False)
        save(attempt/'output_validation.json',qc)
        record.update(status=qc['xcpd_status'],finished_at=now(),exit_code=status,input_unchanged=unchanged)
        save(attempt/'execution.json',record)
        if qc['xcpd_status']=='success':
            save(attempt/'output_manifest.json',{str(f.relative_to(attempt/'derivatives')):sha(f) for f in (attempt/'derivatives').rglob('*') if f.is_file()})
        if qc['xcpd_status']!='success':raise SystemExit(1)


if __name__=='__main__':main()
