"""Validate the exact installed XCP-D input query, then exec its original CLI."""
import json
import os
from pathlib import Path
import sys

import pandas as pd
from bids.layout import BIDSLayout, Query
from bids.layout.index import BIDSLayoutIndexer
from xcp_d.data import load as load_data
from xcp_d.utils.atlas import collect_atlases
from xcp_d.utils.bids import collect_data


def main():
    job = Path('/job')
    expected = json.loads((job / 'expected_input.json').read_text())
    filters = json.loads((job / 'bids_filter.json').read_text())
    filters = {k: {kk: Query.NONE if vv is None else vv for kk, vv in v.items()} for k, v in filters.items()}
    layout = BIDSLayout('/input', validate=False, config=['bids', 'derivatives', str(load_data('xcp_d_bids_config2.json'))],
                        indexer=BIDSLayoutIndexer(validate=False, ignore=['sourcedata', 'logs', 'figures']))
    # Mirror the CLI's session-id expansion before checking the exact selected set.
    query = dict(filters['bold'], subject=expected['subject'], suffix='bold', extension='.nii.gz' if expected['file_format'] == 'nifti' else '.dtseries.nii')
    query['session'] = [expected['session'], Query.NONE] if expected['session'] else Query.NONE
    actual = layout.get(return_type='file', **query)
    wanted = '/input/' + expected['relative_bold']
    if actual != [wanted]:
        raise ValueError(f'CLI-expanded selection is not exactly one requested run: {actual}')
    data = collect_data(layout=layout, input_type='fmriprep', participant_label=expected['subject'],
                           bids_filters=filters, file_format=expected['file_format'],
                           anat_session=expected['session'] or Query.NONE,
                           func_sessions=[expected['session']] if expected['session'] else [Query.NONE])
    selected = data['bold']
    if selected != [wanted]:
        raise ValueError(f'Exact BOLD selection failed: {selected}; expected {[wanted]}')
    atlas = collect_atlases(datasets={'xcpdatlases': '/home/xcp_d/.cache/xcp_d/XCPDAtlases',
                                     'xcpd4s': '/home/xcp_d/.cache/xcp_d/AtlasPack'},
                            atlases=expected['atlases'], file_format=expected['file_format'], bids_filters=filters)
    for name in expected['atlases']:
        if name not in atlas:
            raise ValueError('Requested atlas unavailable: ' + name)
        labels = pd.read_csv(atlas[name]['labels'], sep='\t')
        if len(labels.loc[labels['index'] != 0]) != expected['expected_rois'][name]:
            raise ValueError('Atlas ROI label count differs: ' + name)
    (job / 'container_preflight.json').write_text(json.dumps({'selected_bold': selected, 'anatomy': data,
         'atlases': atlas, 'selection_verified': True}, indent=2, default=str) + '\n')
    if 'duration_settings' in expected:
        from xcp_d.utils.modified_data import flag_bad_run
        from xcp_d.utils.confounds import _infer_dummy_scans
        cfg=expected['duration_settings']
        confounds='/input/'+expected['relative_confounds']
        if not Path(confounds).is_file():raise ValueError('Exact-run confounds missing')
        duration=flag_bad_run(motion_file=confounds,dummy_scans=cfg['dummy_scans'],TR=expected['tr'],
                    motion_filter_type=None if cfg['motion_filter_type']=='none' else cfg['motion_filter_type'],
                    motion_filter_order=4,band_stop_min=None,band_stop_max=None,head_radius=cfg['head_radius'],
                    fd_thresh=cfg['fd_threshold'],censor_between=cfg['censor_between'])
        if duration < cfg['min_time']:
            dummy=int(_infer_dummy_scans(dummy_scans=cfg['dummy_scans'],confounds_file=confounds))
            retained=int(round(duration/expected['tr']));n=expected['n_original_volumes']
            gate={'remaining_duration_sec':float(duration),'n_remaining_volumes':retained,
                  'n_original_volumes':n,'n_removed_dummy_volumes':dummy,'n_censored_volumes':n-dummy-retained,
                  'censoring_proportion':(n-dummy-retained)/(n-dummy),'tr':expected['tr'],
                  'fd_threshold':cfg['fd_threshold'],'metric_source':'XCP-D 26.2.0 flag_bad_run; no denoising executed'}
            (job/'duration_gate.json').write_text(json.dumps(gate,indent=2)+'\n')
            raise SystemExit(42)
    os.execvp('xcp_d', ['xcp_d', *sys.argv[1:]])


if __name__ == '__main__':
    main()
