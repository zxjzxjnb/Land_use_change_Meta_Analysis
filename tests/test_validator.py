"""Unit tests for the validation and flattening logic.

These cover the deterministic, non-API parts of the pipeline, so the data-
quality guarantees are regression-protected without spending API calls.
"""

from metaextract.flatten import result_to_rows
from metaextract.schema import (
    Climate,
    ExtractionResult,
    Moderators,
    ResponseVariable,
    SoilBackground,
    StudyInfo,
)
from metaextract.validator import validate_data_point, validate_result


def test_clean_data_point_has_no_flags():
    rv = ResponseVariable(
        variable_name="soc",
        treatment_group="NPK",
        control_group="CK",
        mean_t=12.0,
        sd_t=1.5,
        n_t=4,
        mean_c=10.0,
        sd_c=1.2,
        n_c=4,
    )
    assert validate_data_point(rv) == []


def test_negative_sd_and_bad_n_are_flagged():
    rv = ResponseVariable(mean_t=1, mean_c=1, sd_t=-2.0, n_t=0)
    flags = validate_data_point(rv)
    assert "negative_sd_t" in flags
    assert "implausible_n_t" in flags


def test_treatment_equals_control_flagged():
    rv = ResponseVariable(
        mean_t=1, mean_c=1, treatment_group="CK", control_group="CK"
    )
    assert "treatment_equals_control" in validate_data_point(rv)


def test_out_of_range_ph_is_study_level_flag():
    result = ExtractionResult(
        moderator_variables=Moderators(
            soil_background=SoilBackground(initial_ph=99.0),
            climate=Climate(),
        )
    )
    flags = validate_result(result)
    assert "ph_out_of_range" in flags.get(-1, [])


def test_flatten_repeats_moderators_across_rows():
    result = ExtractionResult(
        study_info=StudyInfo(first_author="Smith", year=2020),
        response_variables=[
            ResponseVariable(variable_name="soc", mean_t=1, mean_c=1),
            ResponseVariable(variable_name="ph", mean_t=2, mean_c=2),
        ],
    )
    rows = result_to_rows(result, "smith2020.pdf")
    assert len(rows) == 2
    assert all(r["first_author"] == "Smith" for r in rows)
    assert {r["variable_name"] for r in rows} == {"soc", "ph"}


def test_empty_result_still_emits_one_review_row():
    rows = result_to_rows(ExtractionResult(), "empty.pdf")
    assert len(rows) == 1
    assert rows[0]["qa_flags"] == "no_response_variables"
