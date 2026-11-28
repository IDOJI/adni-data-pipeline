"""Scientific boundaries for actual-date EPI/T1 reference proposals."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "pipeline/s3b_image_selection/pairing.py"
SPEC = importlib.util.spec_from_file_location("date_pairing", PATH)
pairing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pairing)


def image(image_id, modality="T1", day="2025-01-15", ptid="SYNTHETIC_A", **overrides):
    row = dict(PTID=ptid, MRI_STUDY_DATE=day, MODALITY=modality, IMAGE_ID=str(image_id),
               SERIES_UID=f"synthetic.{image_id}", SEARCH_PHASE="ADNI3", ELIGIBLE=True,
               QC_STATUS="pass", QUALITY="1", SERIES_SELECTED=False, EXCLUSION_REASONS="",
               REVIEW_FLAGS="", NFQ_RAW_QC_STATUS="pass" if modality == "EPI" else "",
               MANUFACTURER="Synthetic", SCANNER_MODEL="Synthetic", FIELD_STRENGTH="3", ACCELERATION="")
    row.update(overrides)
    return row


def test_actual_dates_override_visit_codes_and_preserve_every_epi():
    rows = [image(1, "EPI", VISCODE="m06"), image(2, VISCODE="m12"),
            image(3, "EPI", day="2025-01-20", VISCODE="m06")]
    original = deepcopy(rows)
    pool, links, epis = pairing.build_pairs(rows)
    assert len(pool) == 1 and len(links) == 2 and len(epis) == 2
    assert epis[0]["T1_PAIRING_STATUS"] == "same_day_proposed"
    assert epis[1]["T1_PAIRING_STATUS"] == "cross_date_review"
    assert epis[1]["SIGNED_T1_MINUS_EPI_DAYS"] == -5
    assert rows == original
    assert all(not row["PREPROCESSING_READY"] and not row["ANALYSIS_READY"] for row in epis)
    assert set(epis[0]) == set(pairing.EPI_FIELDS)


def test_all_dates_and_failed_candidates_remain_auditable_without_cross_subject_pairs():
    rows = [image(1, "EPI"), image(2), image(3, day="2024-01-01", ELIGIBLE=False),
            image(4, ptid="SYNTHETIC_B"), image(5, "EPI", ptid="SYNTHETIC_C", ELIGIBLE=False)]
    pool, links, epis = pairing.build_pairs(rows)
    assert len(pool) == 3 and len(links) == 2 and len(epis) == 2
    assert {row["T1_IMAGE_ID"] for row in links} == {"2", "3"}
    assert not next(row for row in links if row["T1_IMAGE_ID"] == "3")["REFERENCE_ELIGIBLE"]
    assert epis[1]["T1_PAIRING_STATUS"] == "no_reference_candidate"
    assert epis[1]["EPI_METADATA_QC_STATE"] == "blocked"


def test_t1_clinical_exclusion_does_not_remove_reference_candidate():
    _, _, epis = pairing.build_pairs([image(1, "EPI"), image(2, CLINICAL_ELIGIBLE=False, DX_DATE_DIFF_DAYS=90)])
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == "2"


def test_same_day_is_preferred_even_when_quality_is_pending():
    _, _, epis = pairing.build_pairs([image(1, "EPI"), image(2, QC_STATUS="unknown", QUALITY=""),
                                     image(3, day="2025-01-14")])
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == "2"
    assert epis[0]["T1_PAIRING_STATUS"] == "same_day_qc_pending"


def test_same_day_priority_is_qc_then_chosen_then_grade():
    candidates = [image(2, QC_STATUS="unknown", SERIES_SELECTED=True), image(3, QUALITY=1),
                  image(4, QUALITY=3, SERIES_SELECTED=True), image(5, QUALITY=2, SERIES_SELECTED=True)]
    _, _, epis = pairing.build_pairs([image(1, "EPI"), *candidates])
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == "5"


def test_ties_ignore_image_id_acceleration_and_input_order():
    rows = [image(1, "EPI"), image(200, ACCELERATION="Unaccelerated"), image(2, ACCELERATION="Accelerated")]
    _, _, epis = pairing.build_pairs(rows)
    assert epis[0]["T1_TOP_CANDIDATE_IDS"] == "2;200"
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == ""
    assert epis[0]["T1_PAIRING_STATUS"] == "same_day_tie_review"
    assert pairing.build_pairs(list(reversed(rows))) == pairing.build_pairs(rows)


def test_crossdate_priority_quality_before_distance_and_distance_before_chosen():
    rows = [image(1, "EPI"), image(2, day="2025-01-14", QC_STATUS="unknown"),
            image(3, day="2025-01-12"), image(4, day="2025-01-10", SERIES_SELECTED=True)]
    _, _, epis = pairing.build_pairs(rows)
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == "3"
    assert epis[0]["T1_PAIRING_STATUS"] == "cross_date_review"


def test_equidistant_past_future_ties_not_resolved():
    _, links, epis = pairing.build_pairs([image(1, "EPI"), image(2, day="2025-01-14"), image(3, day="2025-01-16")])
    assert epis[0]["T1_TOP_TIE_COUNT"] == 2
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == ""
    assert {row["SIGNED_T1_MINUS_EPI_DAYS"] for row in links} == {-1, 1}
    assert "future_anatomy_requires_research_timepoint_review" in epis[0]["REVIEW_FLAGS"]


def test_review_window_is_inclusive_and_preserves_outside_inventory():
    rows = [image(1, "EPI"), image(2, day="2025-01-05"), image(3, day="2025-01-04")]
    _, links, epis = pairing.build_pairs(rows, {"cross_date_candidate_window_days": 10})
    assert [row["WITHIN_REVIEW_WINDOW"] for row in links] == [False, True]
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == "2"
    assert epis[0]["T1_PAIRING_STATUS"] == "cross_date_review"
    _, _, unbounded = pairing.build_pairs(rows)
    assert "cross_date_window_not_authorized_inventory_only" in unbounded[0]["REVIEW_FLAGS"]


@pytest.mark.parametrize("window", [0, -1, True, 1.5, "30"])
def test_invalid_review_windows_rejected(window):
    with pytest.raises(ValueError):
        pairing.build_pairs([], {"cross_date_candidate_window_days": window})


@pytest.mark.parametrize("change", [{"cross_date_automatic_assignment": True}, {"ties": "latest"}, {"unknown": True}])
def test_policy_cannot_silently_authorize_different_method(change):
    with pytest.raises(ValueError):
        pairing.build_pairs([], change)


@pytest.mark.parametrize("fields,expected", [
    ({}, "documented"), ({"ELIGIBLE": ""}, "pending"), ({"ELIGIBLE": False}, "blocked"),
    ({"QC_STATUS": "unknown", "QUALITY": ""}, "pending"), ({"QUALITY": ""}, "pending"),
    ({"QUALITY": 4}, "blocked"), ({"QUALITY": -1}, "blocked"), ({"QUALITY": "NaN"}, "blocked"),
    ({"QC_STATUS": "conflict"}, "blocked"), ({"EXCLUSION_REASONS": "deleted_scan"}, "blocked"),
    ({"NFQ_RAW_QC_STATUS": ""}, "pending"), ({"NFQ_RAW_QC_STATUS": "unknown"}, "pending"),
    ({"NFQ_RAW_QC_STATUS": "fail"}, "blocked"),
    ({"SOURCE_QC_STATUS": "blocked"}, "blocked"), ({"SOURCE_QC_STATUS": "pending"}, "pending"),
    ({"SOURCE_QC_STATUS": "pass"}, "documented"), ({"SOURCE_QC_STATUS": ""}, "pending"),
    ({"SOURCE_QC_STATUS": None}, "pending"), ({"SOURCE_QC_STATUS": "unrecognized"}, "blocked"),
])
def test_source_evidence_never_promoted_when_missing_or_failed(fields, expected):
    _, _, epis = pairing.build_pairs([image(1, "EPI", **fields), image(2)])
    assert epis[0]["EPI_METADATA_QC_STATE"] == expected
    assert not epis[0]["PREPROCESSING_READY"]
    if expected != "documented":
        assert epis[0]["PAIRING_REVIEW_REQUIRED"]


@pytest.mark.parametrize("fields", [{"QUALITY": ""}, {"QUALITY": 4}, {"QC_STATUS": "conflict"},
                                    {"ELIGIBLE": ""}, {"EXCLUSION_REASONS": "failed_conversion"},
                                    {"SOURCE_QC_STATUS": "blocked"}])
def test_invalid_t1_pass_claims_or_failures_cannot_be_proposed(fields):
    pool, links, epis = pairing.build_pairs([image(1, "EPI"), image(2, **fields)])
    assert not pool[0]["REFERENCE_ELIGIBLE"]
    assert not links[0]["REFERENCE_ELIGIBLE"]
    assert epis[0]["T1_PAIRING_STATUS"] == "no_reference_candidate"


def test_pending_aggregate_t1_remains_unknown_despite_local_pass():
    pool, links, epis = pairing.build_pairs([image(1, "EPI"), image(2, SOURCE_QC_STATUS="pending")])
    assert pool[0]["QC_STATUS"] == "pass"  # Preserve the original local grade evidence.
    assert pool[0]["SOURCE_QC_STATE"] == "pending"
    assert links[0]["REFERENCE_ELIGIBLE"]
    assert links[0]["T1_QC_STATUS"] == "unknown"
    assert epis[0]["T1_PAIRING_STATUS"] == "same_day_qc_pending"
    assert epis[0]["PAIRING_REVIEW_REQUIRED"]


def test_pending_aggregate_does_not_outrank_documented_t1():
    _, _, epis = pairing.build_pairs([image(1, "EPI"), image(2, SOURCE_QC_STATUS="pending", SERIES_SELECTED=True),
                                     image(3, SOURCE_QC_STATUS="pass", QUALITY=3)])
    assert epis[0]["PROPOSED_T1_IMAGE_ID"] == "3"


def test_aggregate_pass_cannot_override_a_local_failure():
    pool, _, epis = pairing.build_pairs([image(1, "EPI", SOURCE_QC_STATUS="pass", QUALITY=4),
                                        image(2, SOURCE_QC_STATUS="pass", QC_STATUS="fail")])
    assert pool[0]["SOURCE_QC_STATE"] == "blocked"
    assert not pool[0]["REFERENCE_ELIGIBLE"]
    assert epis[0]["EPI_METADATA_QC_STATE"] == "blocked"


def test_protocol_scanner_and_duplicate_uid_flags():
    rows = [image(1, "EPI", SEARCH_PHASE="ADNI4", SERIES_UID="same"),
            image(2, "EPI", SERIES_UID="same"), image(3, MANUFACTURER="Different", SCANNER_MODEL="Other")]
    _, _, epis = pairing.build_pairs(rows)
    assert epis[0]["PROTOCOL_SCOPE"] == "extension_review"
    assert {"protocol_extension_review", "phase_mismatch", "manufacturer_mismatch", "scanner_model_mismatch",
            "duplicate_epi_series_uid_review"}.issubset(set(epis[0]["REVIEW_FLAGS"].split(";")))


@pytest.mark.parametrize("overrides", [{"MRI_STUDY_DATE": "m06"}, {"MRI_STUDY_DATE": "2025-02-30"},
                                        {"PTID": ""}, {"MODALITY": "other"}, {"IMAGE_ID": "bad"}])
def test_invalid_identity_cannot_be_guessed(overrides):
    with pytest.raises(ValueError):
        pairing.build_pairs([image(1, **overrides)])


def test_duplicate_ids_fail_instead_of_first_row_selection():
    with pytest.raises(ValueError, match="Duplicate IMAGE_ID"):
        pairing.build_pairs([image(1), image("I1", day="2025-01-16")])


@pytest.mark.parametrize("invalid_id", ["II1", "Ii1", "iI1", "ii1"])
def test_image_id_accepts_only_one_optional_prefix(invalid_id):
    with pytest.raises(ValueError, match="IMAGE_ID"):
        pairing.build_pairs([image(invalid_id)])


@pytest.mark.parametrize("valid_id", ["1", "I1", "i1", "I001"])
def test_single_image_id_prefix_is_normalized(valid_id):
    pool, _, _ = pairing.build_pairs([image(valid_id)])
    assert pool[0]["IMAGE_ID"] == "1"


def test_no_epi_still_preserves_t1_pool():
    pool, links, epis = pairing.build_pairs([image(1)])
    assert len(pool) == 1 and not links and not epis
