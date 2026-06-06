"""Post-extraction sanity checks.

LLM extraction is fast but not infallible: it can transpose a digit, read the
wrong column, or pair the wrong control. For scientific data that is
unacceptable silently, so every extracted data point is screened and annotated
with human-readable flags. Rows with flags are surfaced for review rather than
dropped, keeping a human in the loop where it matters.
"""

from __future__ import annotations

from .schema import ExtractionResult, ResponseVariable


# Plausible ranges for common moderators; values outside these are almost
# certainly a misread rather than a real measurement.
PH_RANGE = (2.0, 11.0)
TEMP_RANGE_C = (-25.0, 35.0)
PRECIP_RANGE_MM = (0.0, 12000.0)


def validate_data_point(rv: ResponseVariable) -> list[str]:
    """Return a list of warning flags for one treatment/control data point."""
    flags: list[str] = []

    # Pairing: a usable effect size needs both arms.
    if rv.mean_t is None or rv.mean_c is None:
        flags.append("missing_mean")

    # Standard deviations must be non-negative; sample sizes positive integers.
    for label, sd in (("sd_t", rv.sd_t), ("sd_c", rv.sd_c)):
        if sd is not None and sd < 0:
            flags.append(f"negative_{label}")
    for label, n in (("n_t", rv.n_t), ("n_c", rv.n_c)):
        if n is not None and (n <= 0 or n != int(n)):
            flags.append(f"implausible_{label}")

    # A coefficient of variation far above 1 is suspicious for soil properties
    # and often signals a mean/SD column swap.
    for mean, sd, arm in ((rv.mean_t, rv.sd_t, "t"), (rv.mean_c, rv.sd_c, "c")):
        if mean and sd and mean != 0 and abs(sd / mean) > 3:
            flags.append(f"high_cv_{arm}")

    # Treatment and control must be different groups.
    if (
        rv.treatment_group
        and rv.control_group
        and rv.treatment_group == rv.control_group
    ):
        flags.append("treatment_equals_control")

    return flags


def _check_range(value, lo, hi, name) -> list[str]:
    if value is not None and not (lo <= value <= hi):
        return [f"{name}_out_of_range"]
    return []


def validate_result(result: ExtractionResult) -> dict[int, list[str]]:
    """Validate a whole extraction.

    Returns a mapping from response-variable index to its flags. Index ``-1``
    holds study-level (moderator) flags. An empty mapping means the extraction
    passed every check.
    """
    flags: dict[int, list[str]] = {}

    soil = result.moderator_variables.soil_background
    climate = result.moderator_variables.climate
    study_flags = (
        _check_range(soil.initial_ph, *PH_RANGE, "ph")
        + _check_range(climate.mean_annual_temperature_c, *TEMP_RANGE_C, "temp")
        + _check_range(
            climate.mean_annual_precipitation_mm, *PRECIP_RANGE_MM, "precip"
        )
    )
    if study_flags:
        flags[-1] = study_flags

    for i, rv in enumerate(result.response_variables):
        rv_flags = validate_data_point(rv)
        if rv_flags:
            flags[i] = rv_flags

    return flags
