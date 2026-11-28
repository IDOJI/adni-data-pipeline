"""Preprocess verified pairs, run XCP-D and complete imaging and clinical QC."""
from collections import defaultdict
import csv
from io import StringIO
from pathlib import Path

from support.study import existing, finalized_master, fixed_text, parser, run, selection_receipt, settings, stage_folder
from _shared import read, unchanged, verify_bundle
from s3b_image_selection.selection_identity import image_id, scan_date
from s9a_validate_clinical import run as clinical
from s9b_validate_inclusion import run as inclusion


def add_scan_age(study, links, folder):
    """Carry original scan-age evidence across the S10 to S9.A handoff."""
    _, proof = selection_receipt(study)
    sources = {m['path']: read(m['path']) for k, m in proof['inputs'].items() if k.startswith('collection_')}
    series = {(r['PTID'], r['IMAGE_ID'], r['MRI_STUDY_DATE']): r['SERIES_UID']
              for r in read(proof['outputs']['candidates']['path']) if r['MODALITY'] == 'EPI'}
    epi = defaultdict(list)
    for row in read(proof['outputs']['rows']['path']):
        if row['MODALITY'] == 'EPI':
            key = (row['PTID'], row['IMAGE_ID'], row['MRI_STUDY_DATE'])
            raw = sources[row['SOURCE_FILE']][int(row['SOURCE_ROW']) - 1]
            epi[key].append(dict(Age=raw.get('Age', raw.get('SEARCH_AGE', '')), Phase=row['SEARCH_PHASE'], SERIES_UID=series[key],
                                 collection_file=row['SOURCE_FILE'], collection_row=row['SOURCE_ROW']))
    scans = read(links, ('sub', 'ses', 'Image_ID', 'Scan_Date'))
    if not scans:
        raise ValueError('The finalization has no clinical scan links.')
    stream = StringIO()
    fields = ['Age', 'Phase', 'SERIES_UID', 'collection_file', 'collection_row']
    writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys([*scans[0], *fields])), delimiter='\t')
    writer.writeheader()
    for scan in scans:
        key = (clinical.link_subject(scan), image_id(scan['Image_ID']), scan_date(scan['Scan_Date']))
        if key not in epi:
            raise ValueError(f'Finalized EPI does not match the selected participant, image and date: {key}')
        for source in epi[key]:
            writer.writerow({**scan, **source})
    return fixed_text(folder / 'scan-links-with-age.tsv', stream.getvalue().replace('\r\n', '\n'))


def clinical_qc(args, folder):
    master = finalized_master(args.study, args.final_qc)
    included = existing(master.with_name('final_included_runs.tsv'))
    tables = (args.tables or args.study / 'LONI_download/clindata').expanduser().resolve()
    links = (existing(args.scan_links) if args.scan_links else
             add_scan_age(args.study, master.with_name('clinical_scan_links.tsv'), folder))
    source = (args.source_qc or args.study / '01-selection/source-qc').expanduser().resolve()
    dxsum, demog = existing(tables / 'DXSUM.csv'), existing(tables / 'PTDEMOG.csv')
    absence = existing(args.st_absence or args.study / 'review/confirmed-st-absence.csv')
    failures = existing(args.conversion_failures) if args.conversion_failures else None
    optional = {k: existing(tables / filename) for k, filename in [('dm', 'DM.csv'), ('adsl', 'ADSL.csv'),
                ('apoe', 'APOERES.csv')] if (tables / filename).is_file()}
    settings(folder / 'clinical-inputs.json', dict(final_qc=master, scan_links=links, source_qc=source,
             dxsum=dxsum, ptdemog=demog, confirmed_st_absence=absence, conversion_failures=failures, **optional))
    for dest, kind, compute in [
        ('clinical', 'clinical_validation_v2',
         lambda out: clinical.process(included, links, dxsum, demog, out, **optional)),
        ('inclusion', 'final_inclusion_validation_v1',
         lambda out: inclusion.process(source, folder / 'clinical', absence, out, failures))]:
        out = folder / dest
        if out.exists():
            unchanged(verify_bundle(out, kind)['inputs_sha256'])
        else:
            compute(out)
    print(f'Eligibility by image: {folder / "inclusion/inclusion_audit.tsv"}')


def process(args):
    with stage_folder(args.study, '03-imaging') as folder:
        if args.action == 'clinical':
            clinical_qc(args, folder)
        else:
            from support.imaging import run_images, cohort_iqms, finalize
            if args.action == 'run':
                run_images(args, folder)
            elif args.action == 'iqms':
                cohort_iqms(args, folder)
            else:
                finalize(args, folder)


if __name__ == '__main__':
    cli = parser(__doc__, ('run', 'iqms', 'finalize', 'clinical'))
    for flag, help_text in (
        ('binding', 'Run from an existing 5.D binding receipt'),
        ('pairs', 'Reviewed text file containing one verified epi_key per line'),
        ('templateflow', 'Populated local TemplateFlow directory'), ('license', 'FreeSurfer license file'),
        ('mriqc-flags', 'Reviewed cohort MRIQC flags for finalize'), ('final-qc', 'Existing final QC master for clinical'),
        ('tables', 'Clinical study files directory'), ('st-absence', 'Reviewed slice-timing exclusion CSV'),
        ('source-qc', 'Existing 3.A source QC directory'), ('scan-links', 'Audited scan links with age for clinical'),
        ('conversion-failures', 'Reviewed conversion exclusion CSV')):
        cli.add_argument('--' + flag, type=Path, help=help_text)
    cli.add_argument('--cohort-complete', action='store_true', help='Confirm the cohort is ready for final QC')
    run(cli, process)
