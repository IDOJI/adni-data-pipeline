"""Individual, immutable QC explanations; final research inclusion remains deferred."""
import argparse
import hashlib
import html
import json
from pathlib import Path

REASONS={
 'mean_fd_above_threshold':'평균 머리 움직임(FD)이 설정한 기준을 초과했습니다.',
 'fd_proportion_above_threshold':'큰 움직임이 있는 시점의 비율이 설정한 기준을 초과했습니다.',
 'mriqc_excluded':'MRIQC 제외 표시가 있습니다.',
 'euler_excluded':'FreeSurfer Euler QC 제외 표시가 있습니다.',
 'skipped_insufficient_time':'움직임 시점을 제외한 유효 영상 길이가 최소 기준보다 짧아 XCP-D를 생략했습니다.',
}
METRICS=['mean_fd','median_fd','max_fd','n_original_volumes','n_fd_over_threshold','fd_over_threshold_proportion',
         'avg_euler','remaining_duration_sec','censoring_proportion','functional_outputs_valid']
THRESHOLDS=['pre_fd_threshold','pre_mean_fd_threshold','pre_fd_proportion_threshold','fd_threshold','min_time','min_coverage']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(pair,rows,cfg,config_id):
    pair=Path(pair);meta=json.loads((pair/'pair_metadata.json').read_text())
    runs=[]
    for row in rows:
        reasons=[]
        for name in ['pre_xcpd_reason','xcpd_errors','xcpd_warnings','final_exclusion_reason']:
            value=row.get(name,[])
            if isinstance(value,str):value=value.split(';')
            reasons.extend(str(v) for v in (value or []) if v)
        if row.get('xcpd_status')=='skipped_insufficient_time':reasons.append('skipped_insufficient_time')
        runs.append({'subject':row.get('sub'),'session':row.get('ses'),'task':row.get('task'),'run':row.get('run'),
          'pre_xcpd_qc_status':row.get('pre_xcpd_qc_status'),'xcpd_status':row.get('xcpd_status'),
          'xcpd_qc_status':row.get('xcpd_qc_status'),'metrics':{k:row.get(k) for k in METRICS},
          'reasons':list(dict.fromkeys(reasons)),'reason_explanations':[REASONS.get(v,v) for v in dict.fromkeys(reasons)]})
    report={'schema_version':1,'subject':meta['subject'],'pair_id':meta.get('pair_id',pair.name),'config_id':config_id,
      'thresholds':{k:cfg[k] for k in THRESHOLDS},'runs':runs,'final_research_inclusion':'pending_review',
      'retention':'Keep all available subject images, intermediate files and execution/QC evidence in verified external archive; QC failure does not mean file deletion.'}
    jp=pair/'qc_report.json';hp=pair/'qc_report.html'
    # A completed report is stable evidence, not an overwriteable final decision.
    if jp.exists() and hp.exists():return [jp,hp]
    esc=lambda value:html.escape(str(value))
    sections=[]
    for run in runs:
        explanations=''.join('<li>'+esc(v)+'</li>' for v in run['reason_explanations']) or '<li>현재 기록된 자동 제외 사유 없음. 최종 포함 확정은 별도 검토가 필요합니다.</li>'
        metrics=''.join('<tr><th>'+esc(k)+'</th><td>'+esc(v)+'</td></tr>' for k,v in run['metrics'].items())
        sections.append('<section><h2>'+esc(run['session'])+' / '+esc(run['task'])+'</h2><p>사전 QC: '+esc(run['pre_xcpd_qc_status'])+' · XCP-D: '+esc(run['xcpd_status'])+' · 후처리 QC: '+esc(run['xcpd_qc_status'])+'</p><ul>'+explanations+'</ul><table>'+metrics+'</table></section>')
    thresholds=''.join('<tr><th>'+esc(k)+'</th><td>'+esc(v)+'</td></tr>' for k,v in report['thresholds'].items())
    text='<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+esc(meta['subject'])+' QC</title><style>body{font:16px system-ui;max-width:960px;margin:40px auto;padding:0 20px;line-height:1.6}table{border-collapse:collapse}td,th{padding:7px 14px;border:1px solid #ccc;text-align:left}section{margin:28px 0}</style><h1>'+esc(meta['subject'])+' 개별 QC 리포트</h1><p>'+esc(meta.get('pair_id',pair.name))+'</p><p>QC 탈락 또는 XCP-D 생략은 전처리 실행 오류와 구분합니다. 최종 연구 포함·제외 판정은 보류 중이며, 탈락 대상도 파일을 보존합니다.</p>'+''.join(sections)+'<h2>적용한 기준</h2><table>'+thresholds+'</table><p><a href="fmriprep/sub-'+esc(meta['subject'])+'.html">fMRIPrep 보고서</a> · <a href="qc_report.json">정량 기록 JSON</a></p></html>'
    for path,content in [(jp,json.dumps(report,ensure_ascii=False,indent=2)+'\n'),(hp,text)]:
        temp=path.with_name(path.name+'.writing');temp.write_text(content);temp.replace(path)
    return [jp,hp]


def backfill(root,cfg):
    count=0
    for meta in Path(root).glob('*/*/pair_metadata.json'):
        pair=meta.parent
        if not (pair/'archive_manifest.json').exists():continue
        for ready in pair.glob('s10/*/archive_ready.json'):
            stage=ready.parent;pre=json.loads((stage/'pre_qc.json').read_text());rows=[]
            for original in pre['rows']:
                row=dict(original)
                records=sorted((stage/'runs').glob('*/attempt-*/execution.json'))
                for record in records:
                    rec=json.loads(record.read_text())
                    if all(rec.get('row',{}).get(k)==row.get(k) for k in ['sub','ses','task','run']):
                        validation=record.parent/'output_validation.json'
                        if validation.exists():row.update(json.loads(validation.read_text()))
                        else:row['xcpd_status']=rec['status']
                if row['pre_xcpd_qc_status']=='fail':row['xcpd_status']='skipped_pre_qc_fail'
                rows.append(row)
            paths=write(pair,rows,cfg,pre['config_id'])
            # Append-only report evidence for already archived subjects; original payload manifest is immutable.
            evidence=pair/'qc_report_addendum.json'
            if not evidence.exists():evidence.write_text(json.dumps({'original_archive_manifest_sha256':sha(pair/'archive_manifest.json'),'reports':{p.name:sha(p) for p in paths}},indent=2)+'\n')
            count+=1
    return count


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive-root',required=True,type=Path);parser.add_argument('--config',required=True,type=Path);args=parser.parse_args()
    print(json.dumps({'reports':backfill(args.archive_root,json.loads(args.config.read_text()))}))


if __name__=='__main__':main()
