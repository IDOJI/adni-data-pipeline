"""Propose date-aware EPI/T1 references without authorizing image processing.

Adapted from the Research selection policy of 2026-11-01. The input is a
normalized image inventory, not a historical selection table. Source eligibility
is independent of the clinical diagnosis window. All input images remain in
the audit, including failed images and candidates outside the review window.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
import math
import re


DEFAULT_POLICY = {
    "version": "2026-11-17-date-image-selection-v1",
    "preserve_every_epi": True,
    "t1_pool": "all_source_T1_candidates_independent_of_T1_clinical_cutoff",
    "same_day_priority": ["documented_QC", "Mayo_chosen", "quality_grade"],
    "cross_date_priority": ["documented_QC", "absolute_date_gap", "Mayo_chosen", "quality_grade"],
    "cross_date_candidate_window_days": None,
    "cross_date_automatic_assignment": False,
    "ties": "retain_all_top_candidates_no_image_ID_tiebreak",
    "acceleration": "record_only_not_a_quality_rank",
    "unknown_quality": "retain_pending_never_promote_to_pass",
    "anatomical_reference_mode": "single_reference_proposal_no_automatic_multivisit_template",
    "readiness": "metadata_stage_only_no_preprocessing_or_analysis_ready_promotion",
}

POOL_EXTRA_FIELDS = ("REFERENCE_ELIGIBLE", "SOURCE_QC_STATE")
LINK_FIELDS = (
    "EPI_KEY", "PTID", "EPI_IMAGE_ID", "EPI_STUDY_DATE", "T1_IMAGE_ID",
    "T1_SERIES_UID", "T1_STUDY_DATE", "SIGNED_T1_MINUS_EPI_DAYS", "ABS_DATE_GAP_DAYS",
    "SAME_DATE", "T1_QC_STATUS", "T1_QUALITY", "T1_MAYO_CHOSEN", "T1_ACCELERATION",
    "T1_PHASE", "T1_MANUFACTURER", "T1_SCANNER_MODEL", "T1_FIELD_STRENGTH",
    "REFERENCE_ELIGIBLE", "WITHIN_REVIEW_WINDOW", "TOP_METADATA_CANDIDATE",
    "METADATA_PRIORITY_RANK", "REVIEW_FLAGS",
)
EPI_FIELDS = (
    "EPI_KEY", "PTID", "MRI_STUDY_DATE", "EPI_IMAGE_ID", "EPI_SERIES_UID",
    "EPI_PHASE", "PROTOCOL_SCOPE", "EPI_MANUFACTURER", "EPI_SCANNER_MODEL",
    "EPI_QC_STATUS", "EPI_RAW_NFQ_QC_STATUS", "EPI_METADATA_QC_STATE",
    "T1_TOTAL_CANDIDATE_COUNT", "T1_REFERENCE_ELIGIBLE_COUNT", "T1_SAME_DAY_ELIGIBLE_COUNT",
    "T1_TOP_CANDIDATE_IDS", "T1_TOP_CANDIDATE_DATES", "T1_TOP_TIE_COUNT",
    "PROPOSED_T1_IMAGE_ID", "PROPOSED_T1_DATE", "SIGNED_T1_MINUS_EPI_DAYS",
    "T1_PAIRING_STATUS", "PAIRING_REVIEW_REQUIRED", "REVIEW_FLAGS",
    "VERIFIED_BIDS_BOLD_PATH", "VERIFIED_BIDS_T1_PATH", "PREPROCESSING_READY",
    "ANALYSIS_READY", "READINESS_BLOCKERS",
)


def _text(value):
    return "" if value is None else str(value).strip()


def _truth(value):
    """Return True/False/None; absent evidence never means a successful check."""
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.inf
    return number if math.isfinite(number) else math.inf


def _phase(value):
    return _text(value).replace(" ", "").upper().removeprefix("ADNI")


def load_policy(supplied=None):
    policy = deepcopy(DEFAULT_POLICY)
    if supplied is not None:
        if not isinstance(supplied, dict) or set(supplied) - set(policy):
            raise ValueError("Unrecognized pairing policy fields")
        for key, value in supplied.items():
            if key != "cross_date_candidate_window_days" and value != policy[key]:
                raise ValueError(f"Unsupported pairing policy change: {key}")
        policy.update(deepcopy(supplied))
    window = policy["cross_date_candidate_window_days"]
    if window is not None and (type(window) is not int or window < 1):
        raise ValueError("Cross-date review window must be null or a positive integer")
    return policy


def _normalize(images):
    normalized, seen = [], set()
    for source in images:
        row = dict(source)
        for key in ("PTID", "MRI_STUDY_DATE", "MODALITY", "IMAGE_ID"):
            row[key] = _text(row.get(key))
            if not row[key]:
                raise ValueError(f"Missing image identity field: {key}")
        if row["MODALITY"] not in {"T1", "EPI"}:
            raise ValueError("Normalized modality must be T1 or EPI")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["MRI_STUDY_DATE"]):
            raise ValueError("MRI_STUDY_DATE must be an actual ISO acquisition date")
        date.fromisoformat(row["MRI_STUDY_DATE"])
        match = re.fullmatch(r"[Ii]?([0-9]+)", row["IMAGE_ID"])
        if not match:
            raise ValueError("IMAGE_ID must contain digits, optionally prefixed with I")
        row["IMAGE_ID"] = str(int(match.group(1)))
        if row["IMAGE_ID"] in seen:
            raise ValueError("Duplicate IMAGE_ID; reconcile source rows before pairing")
        seen.add(row["IMAGE_ID"])
        for key in ("QC_STATUS", "NFQ_RAW_QC_STATUS"):
            row[key] = _text(row.get(key)).lower()
        normalized.append(row)
    return sorted(normalized, key=lambda r: (r["PTID"], r["MRI_STUDY_DATE"], int(r["IMAGE_ID"])))


def source_qc_state(row):
    """Assess source evidence only: documented, pending, or blocked."""
    eligible = _truth(row.get("ELIGIBLE"))
    status = _text(row.get("QC_STATUS")).lower()
    quality = _text(row.get("QUALITY"))
    # Legacy normalized inventories omit the aggregate state. When supplied,
    # that state is additional evidence and local grades cannot override it.
    source_status = _text(row.get("SOURCE_QC_STATUS")).lower()
    if (eligible is False or _text(row.get("EXCLUSION_REASONS"))
            or status not in {"", "pass", "unknown", "pending", "not_checked"}
            or source_status not in {"", "pass", "pending"}
            or (quality and _number(quality) not in (1, 2, 3))):
        return "blocked"
    if (eligible is not True or status != "pass" or _number(quality) not in (1, 2, 3)
            or ("SOURCE_QC_STATUS" in row and source_status != "pass")):
        return "pending"
    return "documented"


def reference_allowed(row):
    """Unknown QC may be inventoried as a candidate but cannot authorize use."""
    status = _text(row.get("QC_STATUS")).lower()
    quality = _text(row.get("QUALITY"))
    return (row.get("SERIES_CLASS", "target") == "target"
            and source_qc_state(row) != "blocked"
            and _truth(row.get("ELIGIBLE")) is True
            and not _text(row.get("EXCLUSION_REASONS"))
            and status in {"pass", "unknown"}
            and (not quality or _number(quality) in (1, 2, 3))
            and (status != "pass" or _number(quality) in (1, 2, 3)))


def _epi_state(row):
    state = source_qc_state(row)
    nfq = _text(row.get("NFQ_RAW_QC_STATUS")).lower()
    if state == "blocked" or nfq not in {"", "pass", "unknown", "pending", "not_checked"}:
        return "blocked"
    return "documented" if state == "documented" and nfq == "pass" else "pending"


def _flags(value):
    return [flag for flag in _text(value).split(";") if flag]


def make_link(epi, t1, policy):
    signed = (date.fromisoformat(t1["MRI_STUDY_DATE"])
              - date.fromisoformat(epi["MRI_STUDY_DATE"])).days
    same = signed == 0
    window = policy["cross_date_candidate_window_days"]
    within = same or window is None or abs(signed) <= window
    allowed = reference_allowed(t1)
    flags = ["t1_source:" + flag for flag in _flags(t1.get("REVIEW_FLAGS"))]
    if not same:
        flags.append("cross_date_requires_review")
        if signed > 0:
            flags.append("future_anatomy_requires_research_timepoint_review")
        if window is None:
            flags.append("cross_date_window_not_authorized_inventory_only")
    phase_e, phase_t = _phase(epi.get("SEARCH_PHASE")), _phase(t1.get("SEARCH_PHASE"))
    if phase_e and phase_t and phase_e != phase_t:
        flags.append("phase_mismatch")
    if not phase_e or not phase_t:
        flags.append("phase_unknown")
    for field, flag in (("MANUFACTURER", "manufacturer_mismatch"),
                        ("SCANNER_MODEL", "scanner_model_mismatch"),
                        ("FIELD_STRENGTH", "field_strength_mismatch")):
        if _text(epi.get(field)) and _text(t1.get(field)) and _text(epi[field]) != _text(t1[field]):
            flags.append(flag)
    if source_qc_state(t1) == "pending":
        flags.append("t1_quality_pending")
    if not within:
        flags.append("outside_cross_date_review_window")
    if not allowed:
        flags.append("t1_not_reference_eligible")
    return {
        "EPI_KEY": f"{epi['PTID']}:{epi['MRI_STUDY_DATE']}:I{epi['IMAGE_ID']}",
        "PTID": epi["PTID"], "EPI_IMAGE_ID": epi["IMAGE_ID"],
        "EPI_STUDY_DATE": epi["MRI_STUDY_DATE"], "T1_IMAGE_ID": t1["IMAGE_ID"],
        "T1_SERIES_UID": _text(t1.get("SERIES_UID")), "T1_STUDY_DATE": t1["MRI_STUDY_DATE"],
        "SIGNED_T1_MINUS_EPI_DAYS": signed, "ABS_DATE_GAP_DAYS": abs(signed),
        "SAME_DATE": same,
        "T1_QC_STATUS": "unknown" if source_qc_state(t1) == "pending" else t1["QC_STATUS"],
        "T1_QUALITY": _text(t1.get("QUALITY")), "T1_MAYO_CHOSEN": _text(t1.get("SERIES_SELECTED")),
        "T1_ACCELERATION": _text(t1.get("ACCELERATION")), "T1_PHASE": _text(t1.get("SEARCH_PHASE")),
        "T1_MANUFACTURER": _text(t1.get("MANUFACTURER")),
        "T1_SCANNER_MODEL": _text(t1.get("SCANNER_MODEL")),
        "T1_FIELD_STRENGTH": _text(t1.get("FIELD_STRENGTH")),
        "REFERENCE_ELIGIBLE": allowed, "WITHIN_REVIEW_WINDOW": within,
        "TOP_METADATA_CANDIDATE": False, "METADATA_PRIORITY_RANK": "",
        "REVIEW_FLAGS": ";".join(flags),
    }


def propose(links):
    eligible = [row for row in links if row["REFERENCE_ELIGIBLE"] and row["WITHIN_REVIEW_WINDOW"]]
    same_day = [row for row in eligible if row["SAME_DATE"]]
    short = same_day or eligible
    if not short:
        return [], "no_reference_candidate"

    def rank(row):
        known = 0 if row["T1_QC_STATUS"] == "pass" else 1
        chosen = 0 if _truth(row["T1_MAYO_CHOSEN"]) is True else 1
        grade = _number(row["T1_QUALITY"])
        return ((known, chosen, grade) if same_day
                else (known, row["ABS_DATE_GAP_DAYS"], chosen, grade))

    ranks = {key: index + 1 for index, key in enumerate(sorted({rank(row) for row in short}))}
    for row in short:
        row["METADATA_PRIORITY_RANK"] = ranks[rank(row)]
        row["TOP_METADATA_CANDIDATE"] = ranks[rank(row)] == 1
    # Sorting is for stable output only; all tied top candidates are retained.
    top = sorted((row for row in short if row["TOP_METADATA_CANDIDATE"]), key=lambda r: int(r["T1_IMAGE_ID"]))
    if not same_day:
        status = "cross_date_review"
    elif len(top) > 1:
        status = "same_day_tie_review"
    elif top[0]["T1_QC_STATUS"] != "pass":
        status = "same_day_qc_pending"
    else:
        status = "same_day_proposed"
    return top, status


def build_pairs(images, policy=None):
    """Return (all T1 pool rows, all within-subject links, one row per EPI).

    Neither a proposal nor a finite review window authorizes cross-date use.
    Clinical date matching and physical BIDS validation are separate stages.
    Caller input dictionaries are never modified.
    """
    policy = load_policy(policy)
    images = _normalize(images)
    by_subject, pool = defaultdict(list), []
    for row in images:
        if row["MODALITY"] == "T1":
            pool.append({**row, "REFERENCE_ELIGIBLE": reference_allowed(row),
                         "SOURCE_QC_STATE": source_qc_state(row)})
            by_subject[row["PTID"]].append(row)
    epis = [row for row in images if row["MODALITY"] == "EPI"]
    uid_counts = Counter((r["PTID"], _text(r.get("SERIES_UID"))) for r in epis if _text(r.get("SERIES_UID")))
    all_links, manifest = [], []
    for epi in epis:
        links = [make_link(epi, t1, policy) for t1 in by_subject[epi["PTID"]]]
        top, status = propose(links)
        chosen = top[0] if len(top) == 1 else {}
        flags = ["epi_source:" + flag for flag in _flags(epi.get("REVIEW_FLAGS"))]
        if status != "same_day_proposed":
            flags.append(status)
        for row in top:
            flags.extend(_flags(row["REVIEW_FLAGS"]))
        scope = "GO_2_3" if _phase(epi.get("SEARCH_PHASE")) in {"GO", "2", "3"} else "extension_review"
        if scope != "GO_2_3":
            flags.append("protocol_extension_review")
        state = _epi_state(epi)
        if state != "documented":
            flags.append("epi_original_QC_or_NFQ_pending")
        if state == "blocked":
            flags.append("epi_source_blocked")
        uid = _text(epi.get("SERIES_UID"))
        if not uid:
            flags.append("epi_series_uid_missing")
        elif uid_counts[(epi["PTID"], uid)] > 1:
            flags.append("duplicate_epi_series_uid_review")
        flags = sorted(set(flags))
        blockers = ["metadata_stage_not_an_execution_authorization", "verified_BIDS_mapping_pending",
                    "EPI_and_T1_physical_QC_required", "BOLD_T1_registration_QC_required",
                    "motion_coverage_signal_visual_QC_required", *flags]
        manifest.append({
            "EPI_KEY": f"{epi['PTID']}:{epi['MRI_STUDY_DATE']}:I{epi['IMAGE_ID']}",
            "PTID": epi["PTID"], "MRI_STUDY_DATE": epi["MRI_STUDY_DATE"],
            "EPI_IMAGE_ID": epi["IMAGE_ID"], "EPI_SERIES_UID": uid,
            "EPI_PHASE": _text(epi.get("SEARCH_PHASE")), "PROTOCOL_SCOPE": scope,
            "EPI_MANUFACTURER": _text(epi.get("MANUFACTURER")),
            "EPI_SCANNER_MODEL": _text(epi.get("SCANNER_MODEL")),
            "EPI_QC_STATUS": epi["QC_STATUS"], "EPI_RAW_NFQ_QC_STATUS": epi["NFQ_RAW_QC_STATUS"],
            "EPI_METADATA_QC_STATE": state, "T1_TOTAL_CANDIDATE_COUNT": len(links),
            "T1_REFERENCE_ELIGIBLE_COUNT": sum(row["REFERENCE_ELIGIBLE"] for row in links),
            "T1_SAME_DAY_ELIGIBLE_COUNT": sum(row["REFERENCE_ELIGIBLE"] and row["SAME_DATE"] for row in links),
            "T1_TOP_CANDIDATE_IDS": ";".join(row["T1_IMAGE_ID"] for row in top),
            "T1_TOP_CANDIDATE_DATES": ";".join(sorted({row["T1_STUDY_DATE"] for row in top})),
            "T1_TOP_TIE_COUNT": len(top), "PROPOSED_T1_IMAGE_ID": chosen.get("T1_IMAGE_ID", ""),
            "PROPOSED_T1_DATE": chosen.get("T1_STUDY_DATE", ""),
            "SIGNED_T1_MINUS_EPI_DAYS": chosen.get("SIGNED_T1_MINUS_EPI_DAYS", ""),
            "T1_PAIRING_STATUS": status, "PAIRING_REVIEW_REQUIRED": bool(flags),
            "REVIEW_FLAGS": ";".join(flags), "VERIFIED_BIDS_BOLD_PATH": "", "VERIFIED_BIDS_T1_PATH": "",
            "PREPROCESSING_READY": False, "ANALYSIS_READY": False,
            "READINESS_BLOCKERS": ";".join(blockers),
        })
        all_links.extend(links)
    return pool, all_links, manifest
