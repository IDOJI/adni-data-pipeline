"""Audit or harmonize eligible 4S256 functional connectivity across scanners."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "start"))
from hashlib import sha256
from support.study import existing, finalized_master, parser, run, settings, stage_folder
from _shared import read
from s14_fc_harmonization.run import run as harmonize


def analysis(args):
    master = finalized_master(args.study, args.final_qc)
    ids = {r['config_id'] for r in read(master, ('config_id',))}
    if len(ids) != 1 or '' in ids:
        raise ValueError('Select a non-empty final QC master with one XCP-D configuration.')
    inclusion = (args.inclusion or args.study / '03-imaging/inclusion').expanduser().resolve()
    scanners = existing(args.scanners or args.study / 'review/scanners.tsv')
    with stage_folder(args.study, '04-harmonization') as folder:
        output = (args.output or folder / args.action).expanduser().resolve()
        # A fresh result directory gets a separate config even when rerunning an audit.
        label = sha256(str(output).encode()).hexdigest()[:12]
        config = settings(folder / f'{args.action}-{label}.json', dict(inclusion_dir=inclusion, final_qc=master,
                          config_id=ids.pop(), scanner_map=scanners, min_batch_size=5, output_dir=output))
        summary = harmonize(config, audit_only=args.action == 'audit')
        print(f"{summary['status']}: {summary['selected_participants']} participants. Results: {output}")
        if summary['status'] == 'blocked':
            raise ValueError(f"See {output / 'decisions.tsv'}. " + ', '.join(summary['problems']))


if __name__ == '__main__':
    cli = parser(__doc__, ('audit', 'fit'))
    for flag, label in [('inclusion', 'Step 9.B inclusion folder'), ('final-qc', 'Finalized XCP-D master TSV'),
                        ('scanners', 'Reviewed scanner map TSV'), ('output', 'New result directory')]:
        cli.add_argument('--' + flag, type=Path, help=label)
    run(cli, analysis)
