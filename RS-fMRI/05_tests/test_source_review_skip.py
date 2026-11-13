"""Synthetic automatic source-review skip policy boundaries."""
import json
from pathlib import Path
import sys
import pytest

LAB=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(LAB/'04_workflow'))
sys.path.insert(0,str(LAB/'pipeline/s5d_bids_identity'))
import source_review as review
import rolling
import queue_service as queue
import continuation
import source_review_metrics

SUB='ADNI999S0001'
def row():
    return {'subject':SUB,'ptid':'999_S_0001','epi_image_id':'11','t1_image_id':'12',
            'epi_date':'2000-01-01','t1_date':'2000-01-01'}

def epi():
    return {'REVIEW_FLAGS':'','PAIRING_REVIEW_REQUIRED':'False',
            'EPI_METADATA_QC_STATE':'documented','EPI_QC_STATUS':'pass',
            'T1_PAIRING_STATUS':'same_day_proposed','PROPOSED_T1_IMAGE_ID':'12',
            'PREPROCESSING_READY':'False','ANALYSIS_READY':'False','EPI_PHYSICAL_STATUS':'pending'}

def install(tmp_path, reasons=()):
    h=tmp_path/'continuous5';h.mkdir(exist_ok=True)
    p=h/'policy.json';review.save(p,{'schema':1,'action':'skip','allow_review_exceptions':False,
        'subjects':{SUB:{'identity':review.identity(row()),'skip_reasons':list(reasons)}}})
    review.save(h/'settings.json',{'source_review_policy':{'enabled':True,'path':str(p),'sha256':review.sha(p)}})
    return p

def test_final_qc_pending_placeholders_do_not_skip_every_valid_pair():
    assert review.reasons(row(),epi())==[]

@pytest.mark.parametrize('changes,reason',[
    ({'REVIEW_FLAGS':'epi_source:protocol_status_review:2'},'epi_source:protocol_status_review:2'),
    ({'PAIRING_REVIEW_REQUIRED':'True'},'pairing_review_required'),
    ({'EPI_METADATA_QC_STATE':'pending'},'source_QC_pending'),
    ({'EPI_QC_STATUS':'fail'},'epi_source_QC_not_pass'),
    ({'T1_PAIRING_STATUS':'tie'},'pairing_not_verified_same_day'),
    ({'PROPOSED_T1_IMAGE_ID':'13'},'t1_proposal_differs')])
def test_existing_source_uncertainty_is_automatically_skipped(changes,reason):
    assert reason in review.reasons(row(),{**epi(),**changes})

def test_t1_reviews_and_source_exclusions_are_also_checked():
    candidates={'11':{'QC_STATUS':'pass','ELIGIBLE':'True','EXCLUSION_REASONS':'','REVIEW_FLAGS':''},
                '12':{'QC_STATUS':'pass','ELIGIBLE':'True','EXCLUSION_REASONS':'','REVIEW_FLAGS':'protocol_status_review:2'}}
    assert 't1_source:protocol_status_review:2' in review.reasons(row(),epi(),candidates)
    candidates['12']['ELIGIBLE']='False'
    assert 't1_source_not_eligible' in review.reasons(row(),epi(),candidates)

def test_unknown_or_changed_pairs_cannot_bypass_pinned_policy(tmp_path):
    p=install(tmp_path)
    assert review.blocked(tmp_path,SUB,row()) is None
    assert review.blocked(tmp_path,'ADNI999S0002')['skip_reasons']==['source_policy_pair_missing']
    assert review.blocked(tmp_path,SUB,{**row(),'t1_image_id':'99'})['skip_reasons']==['selected_pair_differs_from_source_policy']
    p.write_text('{}')
    with pytest.raises(ValueError,match='fingerprint'):review.blocked(tmp_path,SUB)

def test_explicit_skip_cannot_be_revived_by_leftover_retry_budget():
    states={SUB:{'status':'skipped_source_review','retry_plan':{'fmriprep':{'remaining':99}}}}
    chosen,held,waiting=rolling.select_window([SUB,'B','C','D','E','F'],states,set(),{'B','C'},[SUB])
    assert chosen=={'B','C','D','E','F'} and held=={SUB} and not waiting

def test_old_technical_review_receipt_is_denied_before_any_launch(tmp_path):
    install(tmp_path,['protocol_review'])
    route={'runtime':str(tmp_path/'runs'/SUB),'receipt_type':'technical_review_continuation'}
    with pytest.raises(review.ReviewSkip):continuation.verify_route({'subjects':{SUB:route}},SUB)

def test_worker_records_skip_without_preparation_or_computation(tmp_path,monkeypatch):
    install(tmp_path,['protocol_review']);monkeypatch.setattr(queue,'ROOT',tmp_path)
    app=queue.Queue.__new__(queue.Queue);app.backend=lambda _: (None,None)
    updates=[];app.update=lambda subject,status,**extra:updates.append((subject,status,extra))
    app.prepare=lambda *_:pytest.fail('Skipped source must never be extracted or run')
    app._work(row())
    assert updates[-1][1]=='skipped_source_review'
    assert (tmp_path/'continuous5/source_review_skips'/f'{SUB}.json').is_file()

def test_skip_reports_are_idempotent_escape_html_and_preserve_inputs(tmp_path):
    install(tmp_path);raw=tmp_path/'image.nii.gz';raw.write_bytes(b'unchanged-input')
    record=review.record_skip(tmp_path,row(),['review:<unsafe>'])
    p=tmp_path/'continuous5/source_review_skips'/f'{SUB}.json';before=p.read_bytes()
    review.record_skip(tmp_path,row(),['review:<unsafe>'])
    assert p.read_bytes()==before and raw.read_bytes()==b'unchanged-input'
    assert '&lt;unsafe&gt;' in p.with_suffix('.html').read_text()
    assert review.blocked(tmp_path,SUB)['status']=='skipped_source_review'

def test_policy_is_optional_for_unmanaged_workspaces(tmp_path):
    assert review.policy(tmp_path) is None
    assert review.blocked(tmp_path,SUB) is None


def test_skipped_archive_never_reaches_s12_exporter(tmp_path):
    from types import SimpleNamespace
    install(tmp_path,['protocol_review'])
    pair=tmp_path/'archive';pair.mkdir();review.save(pair/'pair_metadata.json',row())
    exporter=SimpleNamespace(export_pair=lambda _:pytest.fail('Excluded archive must not be parsed again'))
    assert source_review_metrics.export_candidate(exporter,pair,tmp_path)=='skipped_source_review'


def test_valid_archive_uses_original_s12_exporter(tmp_path):
    from types import SimpleNamespace
    install(tmp_path)
    pair=tmp_path/'archive';pair.mkdir();review.save(pair/'pair_metadata.json',row())
    calls=[];exporter=SimpleNamespace(export_pair=lambda p:calls.append(p) or 'already_exported')
    assert source_review_metrics.export_candidate(exporter,pair,tmp_path)=='already_exported'
    assert calls==[pair]


def test_excluded_visual_annotations_are_archived_and_unknown_identities_retain_guard(tmp_path):
    install(tmp_path,['protocol_review'])
    path=tmp_path/'visual_review.tsv'
    original='sub\tvisual_qc_status\treview_notes\nsub-'+SUB+'\tfail\tPreserve this annotation\nsub-ADNI999S9999\tpass\tUnknown scope must remain\n'
    path.write_text(original)
    assert review.prune_visual_review(tmp_path,path,tmp_path/'aggregation.lock')==1
    assert 'sub-'+SUB not in path.read_text() and 'ADNI999S9999' in path.read_text()
    snapshots=list((tmp_path/'source_review_excluded').glob('*.tsv'))
    assert len(snapshots)==1 and snapshots[0].read_text()==original
    evidence=json.loads(next((tmp_path/'source_review_excluded').glob('*.json')).read_text())
    assert evidence['excluded_rows'][0]['review_notes']=='Preserve this annotation'
    assert review.prune_visual_review(tmp_path,path,tmp_path/'aggregation.lock')==0


def test_ordinary_pending_visual_review_is_not_removed(tmp_path):
    install(tmp_path)
    path=tmp_path/'visual_review.tsv';original='sub\tvisual_qc_status\nsub-'+SUB+'\tnot_reviewed\n';path.write_text(original)
    assert review.prune_visual_review(tmp_path,path,tmp_path/'aggregation.lock')==0
    assert path.read_text()==original
