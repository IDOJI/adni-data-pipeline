"""Convert a downloaded IDA collection to BIDS, then verify the resulting image pairs."""
from pathlib import Path
import re
import shutil
import subprocess

from support.study import existing, fixed_text, parser, run, selection_receipt, settings, stage_folder
from _shared import new_output, read
from s3b_image_selection.selection_identity import image_id, scan_date
from s5d_bids_identity import binding


def subjects(dicom, registry):
    """Check the actual IDA extraction before passing participant IDs to Clinica."""
    allowed = {r['IMAGE_ID']: (r['PTID'], r['MRI_STUDY_DATE']) for r in registry
               if r['DOWNLOAD_TIER'] in ('source_qc_pass', 'for_qc_review')}
    found = set()
    for image in dicom.glob('*/*/*/*'):
        if not image.is_dir() or image.name.startswith('.'):
            continue
        participant, _, day, token = image.relative_to(dicom).parts
        key = image_id(token)
        if allowed.get(key) != (participant, scan_date(day.split('_')[0])):
            raise ValueError(f'{image} does not match a selected Image ID, participant and date.')
        found.add(participant)
    if not found:
        raise ValueError(f'Expected extracted DICOMs at {dicom}/participant/series/date/ImageID/')
    return sorted(found)


def bids(args):
    receipt, selection = selection_receipt(args.study, args.selection)
    outputs = selection['outputs']
    with stage_folder(args.study, '02-bids') as folder:
        bids_root = (args.bids or folder / 'rawdata').expanduser().resolve()
        if args.action == 'convert':
            dicom = (args.dicom or args.study / 'LONI_download/sourcedata').expanduser().resolve()
            tables = (args.tables or args.study / 'LONI_download/clindata').expanduser().resolve()
            if not tables.is_dir():
                raise ValueError(f'Missing clinical tables directory: {tables}')
            if bids_root.exists():
                raise ValueError(f'BIDS output exists: {bids_root}. Use bind for existing BIDS.')
            new_output(bids_root, [dicom, tables, receipt])
            exe = shutil.which('clinica')
            if not exe:
                raise ValueError('Install Clinica and dcm2niix and put their executables on PATH.')
            registry = read(outputs['candidates']['path'])
            listed = subjects(dicom, registry)
            subject_file = fixed_text(folder / 'subjects.txt', '\n'.join(listed) + '\n')
            help_text = subprocess.check_output([exe, 'convert', 'adni-to-bids', '--help'], text=True)
            modality = re.search(r'\b(fMRI|FMRI)\b', help_text)
            subject_option = '--subjects_list' if '--subjects_list' in help_text else '--subjects-list'
            if not modality or subject_option not in help_text:
                raise ValueError('Check the installed Clinica adni-to-bids modality and subject-list options.')
            cmd = [exe, 'convert', 'adni-to-bids', '-m', 'T1', '-m', modality.group(),
                   subject_option, subject_file]
            if args.xml:
                cmd.extend(['--xml_path', args.xml.expanduser().resolve()])
            subprocess.run([*cmd, dicom, tables, bids_root], check=True)
            required = ['sub-*/ses-*/anat/*_T1w.nii*', 'sub-*/ses-*/func/*_bold.nii*']
            if (not (bids_root / 'dataset_description.json').is_file()
                    or any(not any(bids_root.glob(pattern)) for pattern in required)):
                raise ValueError(f'Clinica did not produce both T1w and BOLD. Check conversion records at {bids_root}')
            from support.conversion import fingerprints
            count = fingerprints(bids_root, dicom, registry, folder)
            print(f'BIDS folder: {bids_root}. Recorded {count} conversion fingerprints.')
            if not count:
                print('No unique Clinica source-to-output records. Supply independent --evidence for bind.')
            return
        if not bids_root.is_dir():
            raise ValueError(f'Missing BIDS directory: {bids_root}')
        captured = folder / 'conversion-hashes.csv'
        default_evidence = captured if captured.exists() else args.study / 'review/conversion-hashes.csv'
        evidence = existing(args.evidence or default_evidence)
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
                        ('dicom', 'Extracted DICOM directory'), ('tables', 'ADNI clinical/conversion tables'),
                        ('bids', 'New conversion destination or existing BIDS dataset'),
                        ('xml', 'Optional IDA XML metadata directory for Clinica'),
                        ('evidence', 'Independent conversion hash CSV or source-mapping JSON'),
                        ('binding-dir', 'Fresh folder for revised binding results')]:
        cli.add_argument('--' + flag, type=Path, help=label)
    run(cli, bids)
