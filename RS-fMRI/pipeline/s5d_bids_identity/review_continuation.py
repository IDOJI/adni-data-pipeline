"""Narrow explicit technical retries that retain a source protocol review flag.

Identity, source QC, same-day pairing and protocol scope remain mandatory. Only
the protocol-status review flag can receive a documented technical continuation;
this never establishes imaging QC approval or research inclusion.
"""
import json
from pathlib import Path
import binding

SCOPE = 'technical_retry_only'
ALLOWED_FLAGS = {'epi_source:protocol_status_review:2'}


def authorize(row, auth):
    if (auth.get('schema') != 1 or auth.get('scope') != SCOPE
            or auth.get('authorization_type') != 'explicit_user_request'
            or not auth.get('request_text') or not auth.get('request_reference')):
        raise ValueError('Explicit bounded technical retry authorization required')
    for a, r in [('epi_key','EPI_KEY'),('ptid','PTID'),('epi_image_id','EPI_IMAGE_ID'),('t1_image_id','PROPOSED_T1_IMAGE_ID')]:
        if str(auth.get(a)) != str(row[r]):raise ValueError('Authorization pair differs: '+a)
    flags = set(filter(None, row['REVIEW_FLAGS'].split(';')))
    if not flags or not flags <= ALLOWED_FLAGS or flags != set(auth.get('review_flags', [])):
        raise ValueError('Unreviewed flag outside technical retry scope')
    if row['READINESS_BLOCKERS'] != 'pairing_review_pending' or row['BIDS_IDENTITY_STATUS'] != 'verified':
        raise ValueError('Other identity/source/pairing blockers remain')


def create(config, authorization, destination):
    cfg = binding.read_json(config); auth = binding.read_json(authorization)
    prior = binding.proof_files(cfg['pairing_receipt'])
    if binding.sha(cfg['images']) != prior['inputs']['candidates']['sha256']:
        raise ValueError('Image registry differs from pairing evidence')
    if binding.sha(cfg['epi_manifest']) not in {x['sha256'] for x in prior['outputs'].values() if x['path'].endswith('04.epi-analysis-manifest.csv')}:
        raise ValueError('EPI manifest differs from pairing evidence')
    inputs = {'config':config, 'authorization':authorization,
              **{k:cfg[k] for k in ['images','epi_manifest','pairing_receipt']},
              **{f'hash_evidence_{i}':p for i,p in enumerate(cfg['hash_evidence'])}}
    before = {k:binding.sha(p) for k,p in inputs.items()}
    images = binding.read_csv(cfg['images']); epis = binding.read_csv(cfg['epi_manifest'])
    image_rows, _, linked, _ = binding.bind(images, epis, cfg['bids_roots'], binding.load_expected(cfg['hash_evidence']))
    row = next(x for x in linked if x['EPI_KEY'] == auth['epi_key'])
    authorize(row, auth)
    verified = {x['IMAGE_ID']:x for x in image_rows if x['BIDS_STATUS']=='verified'}
    e = verified[row['EPI_IMAGE_ID']];t = verified[row['PROPOSED_T1_IMAGE_ID']]
    source = next(x for x in images if str(x['IMAGE_ID'])==row['EPI_IMAGE_ID'])
    plan = {'epi_key':row['EPI_KEY'],'ptid':row['PTID'],'epi_image_id':row['EPI_IMAGE_ID'],
            't1_image_id':row['PROPOSED_T1_IMAGE_ID'],'date':row['MRI_STUDY_DATE'],
            'phase':source['SEARCH_PHASE'].replace(' ',''),'subject':e['SUBJECT'],'session':e['SESSION'],
            'epi':e,'t1':t,'preprocessing_ready':False,'technical_execution_authorized':True,
            'analysis_ready':False,'review_flags':auth['review_flags'],'source_review_required':True}
    if before != {k:binding.sha(p) for k,p in inputs.items()}:raise ValueError('Inputs changed during authorization')
    record = {'schema':1,'scope':SCOPE,'plan':plan,'source_epimanifest_row':row,
              'inputs':{k:{'path':str(Path(p).resolve()),'sha256':before[k]} for k,p in inputs.items()},
              'code':{'path':str(Path(__file__).resolve()),'sha256':binding.sha(__file__)},
              'binding_code':{'path':str(Path(binding.__file__).resolve()),'sha256':binding.sha(binding.__file__)}}
    with Path(destination).open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2)
    return verify_plan(destination, auth['epi_key'])


def verify_plan(path, epi_key):
    receipt = binding.read_json(path)
    if receipt.get('schema')!=1 or receipt.get('scope')!=SCOPE:raise ValueError('Unknown technical retry receipt')
    for item in [*receipt['inputs'].values(),receipt['code'],receipt['binding_code']]:
        if binding.sha(item['path'])!=item['sha256']:raise ValueError('Technical retry evidence changed')
    binding.proof_files(receipt['inputs']['pairing_receipt']['path'])
    auth = binding.read_json(receipt['inputs']['authorization']['path'])
    authorize(receipt['source_epimanifest_row'],auth)
    plan = receipt['plan']
    if plan['epi_key']!=epi_key or not plan.get('technical_execution_authorized') or plan.get('analysis_ready') or plan.get('preprocessing_ready'):
        raise ValueError('Technical continuation scope changed')
    for role in ['epi','t1']:
        row = plan[role]
        if (row['PTID'],row['MRI_STUDY_DATE'],row['IMAGE_ID']) != (plan['ptid'],plan['date'],plan[role+'_image_id']):
            raise ValueError('Technical retry pair identity differs')
        if binding.sha(row['BIDS_NIFTI_PATH'])!=row['NIFTI_SHA256'] or binding.sha(row['BIDS_JSON_PATH'])!=row['JSON_SHA256']:
            raise ValueError('Technical retry input changed')
        if binding.read_json(row['BIDS_JSON_PATH']).get('SeriesInstanceUID')!=row['SERIES_UID']:
            raise ValueError('Technical retry Series UID differs')
    return plan
