"""Assemble QC-approved XCP-D FC and fit a cross-sectional ComBat model."""
from collections import Counter, defaultdict
import json
import math
from importlib.metadata import version
from pathlib import Path
import re
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pipeline'))
from _shared import finish, new_output, read, snapshot, verify_bundle, write
from s3b_image_selection.selection_identity import image_id, scan_date
from s9b_validate_inclusion.run import participant
from s10_xcpd_integrated_qc import pipeline as s10
from s14_fc_harmonization.connectome import ATLAS, UPPER, archived_edges, require
from s14_fc_harmonization.model import design, feature_check, fit

CLINICAL = ('PTID', 'IMAGE_ID', 'MRI_STUDY_DATE', 'SOURCE_MODALITY', 'INCLUSION_STATUS',
            'SOURCE_QC_STATUS', 'CLINICAL_STATUS')
QC = (*s10.KEYS, 'ptid', 'epi_image_id', 'epi_date', 'pair_id', 'config_id', 'final_qc_status',
      'final_include', 'xcpd_status', 'functional_outputs_valid', 'source_pair', 'xcpd_attempt', 'site')
SCANNER = ('image_id', 'ptid', 'date', 'site', 'scanner', 'review_ref', 'preprocessing_profile')
FIELDS = ('ptid', 'image_id', 'date', 'site', 'scanner', 'batch', 'age', 'sex', 'diagnosis',
          'run_key', 'review_ref', 'tie_choice_ref', 'decision', 'reason')


def known(value):
    return str(value or '').strip().lower() not in {'', 'na', 'n/a', 'unknown', 'pending', 'none', 'nan'}


def records_by_id(rows, field):
    index = defaultdict(list)
    for row in rows:
        index[image_id(row[field])].append(row)
    return index


def clinical_key_agrees(row, qc):
    # The historical audit explicitly uses artificial session labels for individual IDA images.
    # Its independent PTID/Image ID/date binding is checked for every observation.
    if row.get('INPUT_SCOPE') == 'metadata_audit_not_step8_or_BIDS':
        return True
    for k in s10.KEYS:
        a, b = row.get(k, ''), qc[k]
        if k == 'sub':
            if a and participant(a) != participant(b):
                return False
        elif a and a.removeprefix(k + '-') != b.removeprefix(k + '-'):
            return False
    return True


def assemble(clinical, qc_rows, maps, config_id, inputs):
    qc = records_by_id(qc_rows, 'epi_image_id')
    scanners = records_by_id(maps, 'image_id')
    audit, candidates, clinical_ids = [], [], Counter()
    for row in clinical:
        try:
            clinical_ids[image_id(row['IMAGE_ID'])] += 1
        except ValueError:
            pass
    for row in clinical:
        if row['SOURCE_MODALITY'] != 'EPI' and row.get('MODALITY') != 'EPI':
            continue
        item = dict.fromkeys(FIELDS, '')
        item.update(ptid=row['PTID'], image_id=row['IMAGE_ID'], date=row['MRI_STUDY_DATE'],
                    age=row.get('MRI_AGE_YEARS', ''), sex=row.get('BIOLOGICAL_SEX', ''),
                    diagnosis=row.get('DIAGNOSIS', ''), decision='held')
        audit.append(item)
        try:
            iid = image_id(item['image_id'])
            item.update(image_id=iid, ptid=participant(item['ptid']), date=scan_date(item['date']))
            ptid, date = item['ptid'], item['date']
            item['site'] = ptid.split('_')[0]
            # Attribute attrition to a scanner only when its independent identity matches.
            valid_map = False
            if len(scanners[iid]) == 1:
                m = scanners[iid][0]
                try:
                    valid_map = (participant(m['ptid']) == ptid and scan_date(m['date']) == date
                                 and m['site'] == item['site'] and all(known(m[k]) for k in
                                     ('scanner', 'review_ref', 'preprocessing_profile')))
                except ValueError:
                    pass
                if valid_map:
                    item.update(scanner=m['scanner'], batch=json.dumps([m['site'], m['scanner']]),
                                review_ref=m['review_ref'], tie_choice_ref=m.get('tie_choice_ref', '').strip())
            require(row['SOURCE_MODALITY'] == 'EPI' and row.get('MODALITY', 'EPI') in ('', 'EPI'),
                    'source_modality_unverified')
            require(clinical_ids[iid] == 1, 'reused_clinical_image_id')
            require(row['INCLUSION_STATUS'] == 'eligible' and row['SOURCE_QC_STATUS'] == 'pass'
                    and row['CLINICAL_STATUS'] == 'pass', 'step9b_' + row['INCLUSION_STATUS'])
            require(len(qc[iid]) == 1, 'missing_or_ambiguous_final_qc_run')
            q = {k: '' if v == 'NA' else v for k, v in qc[iid][0].items()}
            require(q['config_id'] == config_id and q['task'] == 'task-rest', 'incompatible_qc_profile_or_task')
            require(participant(q['sub']) == participant(q['ptid']) == ptid and scan_date(q['epi_date']) == date
                    and clinical_key_agrees(row, q), 'clinical_qc_identity_conflict')
            item['run_key'] = s10.run_key(q)
            require(q['final_qc_status'] == 'include' and q['final_include'].lower() in ('true', '1'),
                    'final_qc_' + q['final_qc_status'])
            require(q['xcpd_status'] == 'success' and q['functional_outputs_valid'].lower() in ('true', '1'),
                    'xcpd_not_validated')
            require(valid_map, 'missing_ambiguous_or_unverified_scanner_mapping')
            require(item['site'] == q['site'], 'scanner_site_conflict')
            require(known(item['age']) and item['sex'] in {'Male', 'Female'}
                    and item['diagnosis'] in {'1', '2', '3'}, 'incomplete_biological_covariates')
            age = float(item['age'])
            require(math.isfinite(age) and age > 0, 'invalid_age')
            item['age'] = age
            labels, edges, profile = archived_edges(q, m, config_id, inputs)
            candidates.append((item, labels, edges, profile))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            item['reason'] = str(exc)
    # Final QC rows absent from the 9.B input are visible in the audit, including those
    # whose Image ID belongs to a non-EPI 9.B record.
    epi_ids = {r['image_id'] for r in audit}
    for iid in sorted(qc.keys() - epi_ids):
        for q in qc[iid]:
            item = dict.fromkeys(FIELDS, '')
            item.update(ptid=q['ptid'], image_id=iid, date=q['epi_date'], site=q['site'],
                        run_key=s10.run_key(q), decision='held', reason='no_step9b_epi_record')
            audit.append(item)
    return audit, candidates


def earliest(candidates):
    groups = defaultdict(list)
    for entry in candidates:
        groups[entry[0]['ptid']].append(entry)
    selected = []
    for ptid in sorted(groups):
        entries = groups[ptid]
        first = min(e[0]['date'] for e in entries)
        tied = [e for e in entries if e[0]['date'] == first]
        choices = tied if len(tied) == 1 else [e for e in tied if known(e[0]['tie_choice_ref'])]
        for e in entries:
            item = e[0]
            if item['date'] != first:
                item['reason'] = 'later_eligible_visit'
            elif len(choices) != 1:
                item['reason'] = 'unresolved_earliest_day_tie'
            elif e is choices[0]:
                item.update(decision='selected', reason='earliest_eligible_acquisition')
                selected.append(e)
            else:
                item['reason'] = 'review_selected_other_same_day_acquisition'
    return selected


def run(config, audit_only=False):
    from protocol_source import inspect_protocol
    source = inspect_protocol()
    config = Path(config).expanduser().resolve()
    cfg = s10.load(config)
    required = {'inclusion_dir', 'final_qc', 'scanner_map', 'config_id', 'min_batch_size', 'output_dir'}
    require(set(cfg) == required, 'Use the documented Step 14 config fields')
    paths = {k: Path(cfg[k]).expanduser() for k in ('inclusion_dir', 'final_qc', 'scanner_map', 'output_dir')}
    require(all(p.is_absolute() for p in paths.values()), 'Use absolute input and output paths')
    minimum = cfg['min_batch_size']
    require(type(minimum) is int and minimum >= 2, 'min_batch_size must be an integer of at least two')
    cid = cfg['config_id']
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', cid), 'Invalid config_id')
    out = new_output(paths['output_dir'], [config, paths['inclusion_dir'], paths['final_qc'], paths['scanner_map']])
    inclusion = paths['inclusion_dir'] / 'inclusion_audit.tsv'
    inputs = snapshot([config, paths['inclusion_dir'] / 'artifact.json', inclusion])
    record = verify_bundle(paths['inclusion_dir'], 'final_inclusion_validation_v1')
    require(record['outputs_sha256'].get(inclusion.name) == inputs[str(inclusion.resolve())],
            '9.B inclusion table not covered by manifest')
    clinical = read(inclusion, CLINICAL)
    missing = []
    def table(name, required_fields):
        path = paths[name]
        if not path.is_file():
            missing.append('missing_' + name)
            return []
        inputs.update(snapshot([path]))
        return read(path, required_fields)

    qrows = table('final_qc', QC)
    if qrows:
        final_summary = paths['final_qc'].with_name('summary.json')
        if final_summary.is_file():
            inputs.update(snapshot([final_summary]))
            final = s10.load(final_summary)
            if final.get('cohort_finalization_deferred') is not False:
                missing.append('cohort_finalization_unconfirmed')
            if (final.get('runs') != len(qrows) or final.get('counts', {}).get('final_qc_status')
                    != dict(Counter(q['final_qc_status'] for q in qrows))):
                missing.append('final_qc_counts_disagree')
        else:
            missing.append('missing_final_qc_summary')
    mrows = table('scanner_map', SCANNER)
    # Keep outputs separate even when the configured archive moved to another drive.
    pair_dirs = {r[k] for rows, k in ((qrows, 'source_pair'), (mrows, 'pair_dir'))
                 for r in rows if known(r.get(k))}
    new_output(out, pair_dirs)
    audit, candidates = assemble(clinical, qrows, mrows, cid, inputs)
    selected = earliest(candidates)
    cohort = [e[0] for e in selected]
    frame, terms, matrix, problems = design(cohort, minimum)
    problems = missing + problems
    if len({e[1] for e in selected}) > 1:
        problems.append('mixed_roi_label_order')
    profiles = sorted({e[3] for e in selected})
    if len(profiles) > 1:
        problems.append('mixed_fmriprep_profiles')
    if selected and not problems:
        raw = np.stack([e[2] for e in selected])
        z = np.arctanh(raw)
        if feature_check(z, matrix):
            problems.append('edge_has_zero_residual_variance')
    status = 'blocked' if problems else 'audit_passed' if audit_only else 'fitted'
    summary = {'status': status, 'problems': problems, 'audit_only': audit_only, 'atlas': ATLAS,
               'config_id': cid, 'reviewed_fmriprep_profiles': profiles,
               'audited_epi_rows': len(audit), 'audited_participants': len({r['ptid'] for r in audit if r['ptid']}), 'selected_participants': len(selected),
               'decision_counts': dict(Counter(r['reason'] for r in audit)),
               'minimum_per_batch': minimum, 'batch_counts': dict(Counter(frame.batch)),
               'design_terms': terms, 'design_rank': int(np.linalg.matrix_rank(matrix)) if frame.shape[0] else 0,
               'repository_commit': source['repository_commit'], 'protocol_sha256': source['protocol_source_sha256'],
               'package_versions': {k: version(k) for k in ('numpy', 'pandas', 'scipy')}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent, prefix='.s14-') as temp:
        stage = Path(temp) / 'result'
        stage.mkdir()
        write(stage / 'decisions.tsv', audit, FIELDS)
        write(stage / 'cohort.tsv', cohort, FIELDS)
        strata = defaultdict(list)
        for row in audit:
            strata[row['site'], row['scanner'], row['diagnosis'], row['decision'], row['reason']].append(row)
        columns = ('site', 'scanner', 'diagnosis', 'decision', 'reason')
        write(stage / 'attrition.tsv',
              [{**dict(zip(columns, key)), 'runs': len(rows),
                'participants': len({r['ptid'] for r in rows if r['ptid']})}
               for key, rows in sorted(strata.items())], (*columns, 'runs', 'participants'))
        design_rows = []
        for (batch, sex, diagnosis), group in frame.groupby(['batch', 'sex', 'diagnosis'], sort=True):
            design_rows.append(dict(batch=batch, sex=sex, diagnosis=diagnosis, participants=len(group),
                                    min_age=group.age.min(), max_age=group.age.max()))
        write(stage / 'batch_design.tsv', design_rows,
              ('batch', 'sex', 'diagnosis', 'participants', 'min_age', 'max_age'))
        if status == 'fitted':
            try:
                adjusted, diagnostic = fit(z, frame, matrix, terms, stage)
            except (FloatingPointError, np.linalg.LinAlgError) as exc:
                raise ValueError('ComBat numerical failure: ' + str(exc)) from exc
            summary['package_versions']['neuroCombat'] = version('neuroCombat')
            labels = selected[0][1]
            write(stage / 'edges.tsv', (dict(index=n, roi_i=labels[i], roi_j=labels[j])
                                        for n, (i, j) in enumerate(zip(*UPPER))), ('index', 'roi_i', 'roi_j'))
            np.savez_compressed(stage / 'fc.npz', raw_r=raw, raw_z=z, adjusted_z=adjusted, adjusted_r=np.tanh(adjusted))
            s10.save(stage / 'diagnostics.json', diagnostic)
        result = finish(stage, 'cross_sectional_fc_combat_v1', inputs, summary)
        require(not out.exists(), 'Output already exists')
        stage.rename(out)
    return result['summary']
