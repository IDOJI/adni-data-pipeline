"""Choose ADNI images using their source QC, image IDs and acquisition dates."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "start"))

from support.study import existing, parser, run, settings, stage_folder
from _shared import snapshot, verify_bundle
from s3a_source_qc import run as qc
from s3b_image_selection import run as selection
from s5d_bids_identity.binding import proof_files


def select(args):
    data = args.study
    tables = (args.tables or data / 'LONI_download/clindata').expanduser().resolve()
    sources = {'MRIQC': existing(args.mriqc or tables / 'MRIQC.csv')}
    for name, override, filename in [('ADNI3_QC', args.adni3_qc, 'MAYO_ADNI3.csv'),
                                     ('GO2_QC', args.go2_qc, 'MAYO_GO2.csv'),
                                     ('DELETED', args.deleted, 'DELMRSCANS.csv')]:
        if override or (tables / filename).is_file():
            sources[name] = existing(override or tables / filename)
        else:
            print(f'Source QC has no {filename}. Check whether this table applies to your study.')
    nfq_paths = args.nfq or ([tables / 'NFQ.csv'] if (tables / 'NFQ.csv').is_file() else [])
    nfq = {str(i): existing(path) for i, path in enumerate(nfq_paths, 1)}
    if not nfq:
        print('No NFQ table supplied. EPI scans lack documented NFQ grades.')
    collections = [dict(modality=m, path=str(existing(path or data / 'collections' / (m + '.csv'))))
                   for m, path in [('T1', args.t1), ('EPI', args.epi)]]
    with stage_folder(data, '01-selection') as folder:
        qdir, images = folder / 'source-qc', folder / 'images'
        cfg = dict(collections=collections, source_qc=qdir, output_dir=images)
        if args.exclusions:
            cfg['confirmed_exclusions'] = existing(args.exclusions)
        config = settings(folder / 'selection.json', cfg)
        if qdir.exists():
            previous = verify_bundle(qdir, 'source_qc_v1')
            if previous['inputs_sha256'] != snapshot([*sources.values(), *nfq.values()]):
                raise ValueError('Source QC inputs changed. Use a new study folder.')
        else:
            qc.process(sources, nfq, qdir)
        if images.exists():
            summary = proof_files(images / '07.run-manifest.json')['summary']
        else:
            summary = selection.run(config)
        print(f"Download list: {images / '09.download-candidates.txt'}")
        print(f"Download tiers: {summary['download_tiers']}")


if __name__ == '__main__':
    cli = parser(__doc__)
    for flag in ('tables', 'mriqc', 'adni3-qc', 'go2-qc', 'deleted', 't1', 'epi', 'exclusions'):
        cli.add_argument('--' + flag, type=Path, help='Override the default path' if flag != 'exclusions'
                         else 'Reviewed Step 3.B exclusion CSV')
    cli.add_argument('--nfq', type=Path, action='append', help='NFQ CSV, repeat for multiple exports')
    run(cli, select)
