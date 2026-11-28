"""Convert a downloaded IDA collection to BIDS, then verify the resulting image pairs."""
from pathlib import Path

from support.study import existing, parser, run, selection_receipt, settings, stage_folder
from _shared import new_output
from s4_dcm2niix.convert import EVIDENCE, GENERATOR, convert, verify_conversion
from s5d_bids_identity import binding


def bids(args):
    receipt, selection = selection_receipt(args.study, args.selection)
    outputs = selection['outputs']
    with stage_folder(args.study, '02-bids') as folder:
        bids_root = (args.bids or folder / 'rawdata').expanduser().resolve()
        if args.action == 'convert':
            dicom = (args.dicom or args.study / 'LONI_download/sourcedata').expanduser().resolve()
            done, total = convert(receipt, dicom, bids_root)
            print(f'Converted {done}/{total} selected Image IDs. See {bids_root / EVIDENCE / "conversion-audit.tsv"}')
            if done != total:
                raise ValueError('Some selected images are held or missing. Review the audit before binding the available files.')
            return
        if not bids_root.is_dir():
            raise ValueError(f'Missing BIDS directory: {bids_root}')
        description = bids_root / 'dataset_description.json'
        generators = binding.read_json(description).get('GeneratedBy', []) if description.is_file() else []
        if any(g.get('Name') == GENERATOR for g in generators) or (bids_root / EVIDENCE / 'conversion.json').is_file():
            evidence = verify_conversion(bids_root, receipt)
            if args.evidence and existing(args.evidence) != evidence:
                raise ValueError('Use the conversion evidence recorded with this BIDS dataset.')
        else:
            captured = folder / 'conversion-hashes.csv'  # Historical external conversion receipts.
            fallback = captured if captured.exists() else args.study / 'review/conversion-hashes.csv'
            evidence = existing(args.evidence or fallback)
        bind_dir = (args.binding_dir or folder / 'binding').expanduser().resolve()
        bound = bind_dir / '07.binding-receipt.json'
        if not bound.is_file() and not (bind_dir / 'settings.json').is_file():
            new_output(bind_dir, [bids_root, receipt, evidence])
            bind_dir.mkdir(parents=True)
        config = settings(bind_dir / 'settings.json', dict(
            images=outputs['candidates']['path'], epi_manifest=outputs['epi']['path'],
            pairing_receipt=receipt, bids_roots=[bids_root], hash_evidence=[evidence], output_dir=bind_dir))
        if bound.exists():
            saved = binding.proof_files(bound)['outputs']
            for plan in binding.read_json(saved['plans']['path']):
                binding.verify_plan(bound, plan['epi_key'])
            summary = binding.read_json(saved['summary']['path'])
        else:
            summary = binding.run(config)
        print(f"Verified pairs: {summary['preprocessing_ready']}. Review {bind_dir}")
        if not summary['preprocessing_ready']:
            raise ValueError('No pairs are ready for imaging. See 04.epi-execution-manifest.csv.')


if __name__ == '__main__':
    cli = parser(__doc__, ('convert', 'bind'))
    for flag, label in [('selection', 'Existing Step 3.B selection receipt'),
                        ('dicom', 'Extracted IDA DICOM directory'),
                        ('bids', 'New conversion destination or existing BIDS dataset'),
                        ('evidence', 'Independent conversion hash CSV or source-mapping JSON'),
                        ('binding-dir', 'Fresh folder for revised binding results')]:
        cli.add_argument('--' + flag, type=Path, help=label)
    run(cli, bids)
