"""Apply source-review skips before delegating to the unchanged S12 exporter."""
import argparse
import importlib.util
import json
from pathlib import Path
import time
import source_review


def export_candidate(exporter, pair, root):
    meta = source_review.read(Path(pair)/'pair_metadata.json')
    if source_review.blocked(root, meta['subject'], meta):return 'skipped_source_review'
    return exporter.export_pair(pair)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--archive-root',type=Path,required=True)
    parser.add_argument('--status',type=Path)
    parser.add_argument('--watch',action='store_true')
    args = parser.parse_args()
    if not (args.root/'continuous5/settings.json').is_file():raise ValueError('Managed runtime required')
    path = Path(__file__).resolve().parents[1]/'pipeline/s12_metrics_summary/run.py'
    spec = importlib.util.spec_from_file_location('source_review_unchanged_s12',path)
    exporter = importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    while True:
        results = {}
        for pair in sorted(args.archive_root.glob('*/EPI*_MT1*')):
            if not pair.is_dir():continue
            try:results[str(pair)] = export_candidate(exporter,pair,args.root)
            except Exception as exc:results[str(pair)] = 'error: '+str(exc)
        if args.status:source_review.save(args.status,{'at':time.time(),'pairs':results,'LLM_calls':0})
        print(json.dumps(results),flush=True)
        if not args.watch:break
        time.sleep(120)


if __name__=='__main__':main()
