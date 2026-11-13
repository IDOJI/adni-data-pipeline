"""Explicit source-review exclusions, separate from execution errors and final QC.

The external, fingerprinted policy records every exact selected pair. Incidents
preserve input-verification failures without changing source metadata or images.
No model calls or research-inclusion approvals are made by this module.
"""
import datetime as dt
import csv
import fcntl
import hashlib
import html
import io
import json
from pathlib import Path
import re
import uuid


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.writing')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n');tmp.replace(path)


def identity(row):
    return {'subject':row['subject'], 'ptid':row['ptid'],
            'epi_image_id':str(row['epi_image_id']),
            't1_image_id':str(row.get('t1_image_id', row.get('mt1_image_id', ''))),
            'epi_date':row['epi_date'], 't1_date':row.get('t1_date', row.get('mt1_date', ''))}


def reasons(row, epi, candidates=None):
    """Use existing review/QC/pairing fields; do not invent numeric cutoffs."""
    result = []
    if not epi:return ['epi_source_missing']
    result += [x for x in epi.get('REVIEW_FLAGS', '').split(';') if x]
    if str(epi.get('PAIRING_REVIEW_REQUIRED', '')).lower() in ('true','1','yes'):
        result.append('pairing_review_required')
    if epi.get('EPI_METADATA_QC_STATE') != 'documented':result.append('source_QC_pending')
    if epi.get('EPI_QC_STATUS') != 'pass':result.append('epi_source_QC_not_pass')
    if epi.get('T1_PAIRING_STATUS') != 'same_day_proposed':result.append('pairing_not_verified_same_day')
    if str(epi.get('PROPOSED_T1_IMAGE_ID')) != str(row['t1_image_id']):result.append('t1_proposal_differs')
    if candidates is not None:
        for role, iid in [('epi',row['epi_image_id']),('t1',row['t1_image_id'])]:
            source = candidates.get(str(iid))
            if not source:result.append(role+'_source_missing');continue
            result += [role+'_source:'+x for x in source.get('REVIEW_FLAGS','').split(';') if x]
            if (source.get('QC_STATUS') != 'pass' or source.get('EXCLUSION_REASONS')
                    or str(source.get('ELIGIBLE','')).lower() not in ('true','1')):
                result.append(role+'_source_not_eligible')
    return sorted(set(result))


def policy(root):
    path = Path(root)/'continuous5/settings.json'
    if not path.is_file():return None
    scope = read(path).get('source_review_policy')
    if not scope or not scope.get('enabled'):return None
    if sha(scope['path']) != scope['sha256']:raise ValueError('Source-review policy fingerprint changed')
    data = read(scope['path'])
    if data.get('schema') != 1 or data.get('action') != 'skip' or data.get('allow_review_exceptions') is not False:
        raise ValueError('Invalid source-review skip policy')
    return data


def blocked(root, subject, row=None):
    data = policy(root)
    if data is None:return None
    entry = data['subjects'].get(subject)
    if entry is None:return {'subject':subject,'skip_reasons':['source_policy_pair_missing']}
    if row is not None and identity(row) != entry['identity']:
        return {**entry,'skip_reasons':['selected_pair_differs_from_source_policy']}
    incident = Path(root)/'continuous5/source_review_skips'/(subject+'.json')
    if incident.is_file() and read(incident).get('status') == 'skipped_source_review':return read(incident)
    return entry if entry.get('skip_reasons') else None


class ReviewSkip(ValueError):
    def __init__(self, record):
        self.record = record
        super().__init__('Source review automatically skipped: '+';'.join(record['skip_reasons']))


def enforce(root, subject, row=None):
    record = blocked(root, subject, row)
    if record:raise ReviewSkip(record)


def record_skip(root, row, skip_reasons, evidence=None):
    ident = identity(row);subject = ident['subject']
    if not re.fullmatch(r'ADNI[0-9]+S[0-9]+',subject):raise ValueError('Invalid skip subject')
    path = Path(root)/'continuous5/source_review_skips'/(subject+'.json')
    prior = read(path) if path.exists() else {}
    rec = {'schema':1,'status':'skipped_source_review','subject':subject,'identity':ident,
           'skip_reasons':sorted(set(skip_reasons)),
           'skipped_at':prior.get('skipped_at',dt.datetime.now(dt.timezone.utc).isoformat()),
           'scope':'skip further automatic preprocessing/postprocessing; preserve existing inputs and results',
           'evidence':evidence or prior.get('evidence',{}), 'LLM_calls':0}
    if rec != prior:save(path,rec)
    document = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Source review skip</title>'
                '<h1>Skipped: '+html.escape(subject)+'</h1><p>Further automatic processing is excluded. '
                'Existing source files and results are preserved.</p><ul>'+
                ''.join('<li>'+html.escape(x)+'</li>' for x in rec['skip_reasons'])+'</ul>'
                '<p>EPI '+html.escape(ident['epi_image_id'])+' ('+html.escape(ident['epi_date'])+
                '); T1 '+html.escape(ident['t1_image_id'])+' ('+html.escape(ident['t1_date'])+')</p></html>\n')
    report = path.with_suffix('.html')
    if not report.exists() or report.read_text() != document:report.write_text(document)
    return rec


def prune_visual_review(root, path, lock_path):
    """Archive excluded review rows before the base aggregator validates its scope.

    Preserve the complete original file and all excluded annotations. Unknown
    identities remain in the active file for the ordinary validation guard.
    """
    data = policy(root);path = Path(path)
    if data is None or not path.is_file():return 0
    with Path(lock_path).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        raw = path.read_bytes();reader = csv.DictReader(io.StringIO(raw.decode()),delimiter='\t')
        fields = reader.fieldnames;rows = list(reader)
        if not fields or 'sub' not in fields or any(None in row for row in rows):
            raise ValueError('Malformed visual QC table; preserve it')
        keep = [];excluded = []
        for row in rows:
            subject = row['sub'].removeprefix('sub-')
            if subject in data['subjects'] and blocked(root,subject):excluded.append(row)
            else:keep.append(row)
        if not excluded:return 0
        digest = hashlib.sha256(raw).hexdigest()
        archive = path.parent/'source_review_excluded';archive.mkdir(exist_ok=True)
        snapshot = archive/('visual-review-'+digest+'.tsv')
        if snapshot.exists() and snapshot.read_bytes()!=raw:raise ValueError('Review snapshot changed')
        if not snapshot.exists():snapshot.write_bytes(raw)
        text = io.StringIO(newline='');writer = csv.DictWriter(text,fieldnames=fields,delimiter='\t',lineterminator='\n')
        writer.writeheader();writer.writerows(keep)
        tmp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.writing');tmp.write_text(text.getvalue())
        if path.read_bytes()!=raw:
            tmp.unlink();raise ValueError('Visual QC changed during policy update; preserve edits')
        tmp.replace(path)
        save(archive/('exclusion-'+digest+'.json'),{'original_file':str(path),'original_sha256':digest,
            'snapshot':str(snapshot),'excluded_rows':excluded,'retained_rows':len(keep),
            'reason':'explicit source-review skip policy; original review annotations preserved'})
        return len(excluded)
