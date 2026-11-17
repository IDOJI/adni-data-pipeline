#!/usr/bin/env python

import argparse
import os
import pandas as pd
import numpy as np


def mriqc_exclude_column(iqm: pd.DataFrame) -> pd.Series:
    """Return nullable 0/1 flags; unknown or incomplete QC is never a pass.

    Accepts the column ``exclude_mriqc`` directly, or derives it from the
    ``adni_outlier_pipeline.R`` outputs ``excluded_any`` (bool) / ``qc_status_any``
    ("excluded"/"included"), so the R QC table can be used without renaming.
    """
    if "exclude_mriqc" in iqm.columns:
        col = iqm["exclude_mriqc"]
    elif "excluded_any" in iqm.columns:
        col = iqm["excluded_any"]
    elif "qc_status_any" in iqm.columns:
        col = iqm["qc_status_any"]
    else:
        raise ValueError(
            "MRIQC outliers file must have one of: 'exclude_mriqc', 'excluded_any', "
            "'qc_status_any'.")

    def to01(v):
        token = str(v).strip().lower()
        if token in ("1", "1.0", "true", "yes", "excluded", "fail"):
            return 1
        if token in ("0", "0.0", "false", "no", "included", "pass"):
            return 0
        return pd.NA

    flags = col.map(to01).astype('Int64')
    if 'qc_metrics_complete' in iqm:
        complete = iqm.qc_metrics_complete.astype(str).str.strip().str.lower().isin(('1', '1.0', 'true', 'yes'))
        flags.loc[~complete & flags.ne(1).fillna(True)] = pd.NA
    return flags


def assess_sessionwise_euler(euler_df, min_reference_subjects=10, threshold=5.0):
    """Score each reconstruction; a small/invalid reference requires review.

    The site reference is the median of participant medians in sqrt(-Euler)
    space, preventing repeated visits from overweighting the reference. Each
    session is compared separately: its quality is never averaged with visits.
    The minimum reference count is a project safeguard, not a validated
    universal biological threshold. Euler values from 0 through 2 are valid
    topologies and map to zero; nonfinite values or values above 2 are invalid.
    """
    if type(min_reference_subjects) is not int or min_reference_subjects < 3:
        raise ValueError('At least three reference participants must be required')
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError('Euler threshold must be finite and positive')
    required = ['sub', 'ses', 'site', 'avg_en']
    if any(c not in euler_df for c in required):
        raise ValueError('Euler table requires sub, ses, site and avg_en')
    optional = [c for c in ('reconstruction_id', 'mt1_image_id') if c in euler_df]
    frame = euler_df[required + optional].copy()
    for col in ('sub', 'ses', 'site'):
        frame[col] = frame[col].fillna('').astype(str).str.strip()
    if frame['sub'].eq('').any():
        raise ValueError('Euler reconstruction requires a participant identity')
    frame['avg_en'] = pd.to_numeric(frame.avg_en, errors='coerce')
    frame = frame.drop_duplicates()
    if frame.duplicated(['sub', 'ses']).any():
        raise ValueError('Conflicting Euler evidence for the same reconstruction/session')
    frame['exclude_euler'] = pd.Series(pd.NA, index=frame.index, dtype='Int64')
    frame['euler_qc_status'] = 'invalid_metric'
    frame['euler_qc_reason'] = 'missing_or_invalid_euler_or_site'
    frame['euler_reference_subjects'] = 0
    frame['euler_site_reference'] = np.nan
    known_site = ~frame.site.str.lower().isin(('', 'na', 'nan', 'unknown', 'none'))
    valid = np.isfinite(frame.avg_en) & frame.avg_en.le(2) & known_site
    frame['_transformed'] = np.sqrt((-frame.avg_en).clip(lower=0))
    for site, group in frame.loc[valid].groupby('site'):
        participants = group.groupby('sub')['_transformed'].median()
        reference = float(participants.median())
        frame.loc[group.index, 'euler_reference_subjects'] = len(participants)
        frame.loc[group.index, 'euler_site_reference'] = reference
        if len(participants) < min_reference_subjects:
            frame.loc[group.index, 'euler_qc_status'] = 'insufficient_reference'
            frame.loc[group.index, 'euler_qc_reason'] = 'site_reference_below_project_minimum'
            continue
        excluded = group['_transformed'] - reference > threshold
        frame.loc[group.index, 'exclude_euler'] = excluded.astype(int)
        frame.loc[group.index, 'euler_qc_status'] = np.where(excluded, 'fail', 'pass')
        frame.loc[group.index, 'euler_qc_reason'] = np.where(excluded, 'euler_site_outlier', '')
    return frame.drop(columns='_transformed').reset_index(drop=True)


def compute_sitewise_euler_exclusion(euler_df):
    """
    Historical subject-averaged helper retained for frozen-source compatibility.
    New S8/S10 entry points use assess_sessionwise_euler instead.

    Expects columns:
      - 'sub'  : subject ID (e.g., 'sub-ADNI941S7074')
      - 'site' : site code (e.g., '941')
      - 'avg_en' : average Euler number (negative values)

    Returns:
      - euler_flags: pd.Series indexed by sub, True if subject should be excluded.
      - removed_subjects: list of subs to exclude.
    """
    tmp = (
        euler_df
        .groupby("sub", as_index=True)
        .agg({"avg_en": "mean", "site": "first"})
        .copy()
    )

    euler_nums = tmp["avg_en"].to_numpy(dtype=np.float32)
    site_series = tmp["site"].astype(str).copy()
    subjects = tmp.index.to_numpy()

    # Map site strings to integer codes (factorize is dtype-safe across pandas
    # versions; assigning ints into a string-dtype Series fails on newer pandas).
    codes, _ = pd.factorize(site_series)
    sites = codes.astype(np.int32)

    transformed = np.full_like(euler_nums, np.nan, dtype=np.float32)
    for site in np.unique(sites):
        mask = sites == site
        vals = euler_nums[mask]

        # only use negative Euler values
        neg_mask = vals < 0
        safe_vals = np.full_like(vals, np.nan, dtype=np.float32)
        safe_vals[neg_mask] = np.sqrt(-vals[neg_mask])

        med = np.nanmedian(safe_vals)
        transformed[mask] = safe_vals - med

    good_mask = np.logical_or(transformed <= 5, np.isnan(transformed))
    bad_mask = np.logical_not(good_mask)

    removed_subjects = list(subjects[bad_mask])

    euler_flags = pd.Series(False, index=subjects, name="exclude_euler")
    euler_flags.loc[removed_subjects] = True

    print(f"{len(removed_subjects)} subjects removed based on sitewise Euler.")
    return euler_flags, removed_subjects


def main():
    parser = argparse.ArgumentParser(
        description="Combine motion + sitewise Euler + MRIQC to derive final inclusion/exclusion."
    )
    parser.add_argument(
        "--motion-summary",
        required=True,
        help="Path to motion_summary.tsv from summarize_motion_from_confounds.py",
    )
    parser.add_argument(
        "--euler-summary",
        required=True,
        help="Path to euler_summary.tsv from extract_euler_from_freesurfer_logs.py",
    )
    parser.add_argument(
        "--iqm-outliers",
        default=None,
        help="Optional MRIQC outlier TSV with at least columns [sub, ses, exclude_mriqc].",
    )
    parser.add_argument(
        "--valid-sessions",
        default=None,
        help=(
            "Optional table with [sub, ses] listing the sessions that legitimately "
            "reached final QC (e.g. the sequential fMRIPrep survivors from "
            "collect_sample_sizes.py --dump-stage fmriprep). Motion-summary rows not "
            "in this list are dropped from BOTH output tables, since they were "
            "excluded at an earlier pipeline stage rather than at final QC."
        ),
    )
    parser.add_argument(
        "--fd-mean-thresh",
        type=float,
        default=0.5,
        help="Exclude runs with mean FD_P above this threshold (default: 0.5 mm).",
    )
    parser.add_argument(
        "--fd-prop-thresh",
        type=float,
        default=0.30,
        help="Exclude runs with > this proportion of frames above FD_P threshold (default: 0.30).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to save included_sessions.tsv and excluded_sessions.tsv",
    )
    parser.add_argument('--euler-min-reference-subjects', type=int, default=10,
                        help='Project safeguard for site references, not a literature cutoff (default: 10).')
    parser.add_argument('--euler-threshold', type=float, default=5.0)
    args = parser.parse_args()

    motion = pd.read_csv(args.motion_summary, sep="\t")
    euler = pd.read_csv(args.euler_summary, sep="\t")

    # Restrict to the sequentially-valid universe (sessions that survived every
    # earlier stage) so final QC only ever includes/excludes sessions that
    # legitimately reached it. Leaked sessions are dropped, not marked excluded.
    if args.valid_sessions is not None:
        sep = "\t" if os.path.splitext(args.valid_sessions)[1].lower() in (".tsv", ".tab") else ","
        valid = pd.read_csv(args.valid_sessions, sep=sep)
        for col in ("sub", "ses"):
            if col not in valid.columns:
                raise ValueError(f"--valid-sessions file must have a '{col}' column.")
        valid_ids = valid[["sub", "ses"]].astype(str).drop_duplicates()
        before = len(motion)
        motion = motion.astype({"sub": str, "ses": str}).merge(
            valid_ids, on=["sub", "ses"], how="inner")
        print(f"Restricted to {len(motion)} of {before} motion rows via --valid-sessions "
              f"(dropped {before - len(motion)} sessions excluded at an earlier stage).")

    for col in ('sub', 'ses'):
        motion[col] = motion[col].fillna('').astype(str)
    assessment = assess_sessionwise_euler(euler, args.euler_min_reference_subjects, args.euler_threshold)
    merged = motion.merge(assessment, on=['sub', 'ses'], how='left', validate='many_to_one')

    # Optional MRIQC exclusions
    if args.iqm_outliers is not None:
        sep = '\t' if os.path.splitext(args.iqm_outliers)[1].lower() in ('.tsv', '.tab') else ','
        iqm = pd.read_csv(args.iqm_outliers, sep=sep)
        for col in ('sub', 'ses'):
            iqm[col] = iqm[col].fillna('').astype(str)
        if iqm.duplicated(['sub', 'ses']).any():
            raise ValueError('Duplicate MRIQC session identities')
        iqm["exclude_mriqc"] = mriqc_exclude_column(iqm)
        merged = merged.merge(
            iqm[["sub", "ses", "exclude_mriqc"]],
            on=["sub", "ses"],
            how="left", validate='many_to_one',
        )
    else:
        merged["exclude_mriqc"] = pd.NA

    # Apply motion + Euler + MRIQC exclusion rules
    reasons = []
    exclude_flags = []
    statuses = []

    for _, row in merged.iterrows():
        row_reasons = []
        missing = []

        mean_fd = pd.to_numeric(row['mean_fd_p'], errors='coerce')
        proportion = pd.to_numeric(row['prop_fd_p_over_thresh'], errors='coerce')
        if not np.isfinite(mean_fd) or mean_fd < 0 or not np.isfinite(proportion) or not 0 <= proportion <= 1:
            missing.append('motion_metrics_missing_or_invalid')
        if mean_fd > args.fd_mean_thresh:
            row_reasons.append(f"mean_fd_p>{args.fd_mean_thresh}")

        if proportion > args.fd_prop_thresh:
            row_reasons.append(f"prop_fd_p_over_thresh>{args.fd_prop_thresh}")

        if pd.isna(row['exclude_euler']):
            missing.append('euler_missing_or_review_required')
        elif row["exclude_euler"] == 1:
            row_reasons.append("euler_site_outlier")

        if pd.isna(row['exclude_mriqc']):
            missing.append('mriqc_missing_or_invalid')
        elif row["exclude_mriqc"] == 1:
            row_reasons.append("mriqc_outlier")

        if row_reasons:
            exclude_flags.append(1)
            reasons.append(";".join(row_reasons))
            statuses.append('exclude')
        elif missing:
            exclude_flags.append(pd.NA)
            reasons.append(';'.join(missing))
            statuses.append('pending_review')
        else:
            exclude_flags.append(0)
            reasons.append("")
            statuses.append('include')

    merged["exclude"] = exclude_flags
    merged["exclude_reason"] = reasons
    merged['qc_status'] = statuses

    os.makedirs(args.output_dir, exist_ok=True)

    included = merged[merged.qc_status == 'include'].copy()
    excluded = merged[merged.qc_status == 'exclude'].copy()
    pending = merged[merged.qc_status == 'pending_review'].copy()

    included_path = os.path.join(args.output_dir, "included_sessions.tsv")
    excluded_path = os.path.join(args.output_dir, "excluded_sessions.tsv")

    included.to_csv(included_path, sep="\t", index=False)
    excluded.to_csv(excluded_path, sep="\t", index=False)
    pending.to_csv(os.path.join(args.output_dir, 'pending_review.tsv'), sep='\t', index=False)

    print(f"Wrote {len(included)} included rows to {included_path}")
    print(f"Wrote {len(excluded)} excluded rows to {excluded_path}")
    print(f'Wrote {len(pending)} pending rows; incomplete QC is not inclusion')


if __name__ == "__main__":
    main()
