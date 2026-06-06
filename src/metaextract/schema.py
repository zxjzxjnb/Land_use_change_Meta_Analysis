"""Data schema for meta-analysis extraction.

These Pydantic models serve two purposes at once:

1.  They define the structured-output contract handed to Gemini (the JSON
    schema the model is forced to conform to via ``response_schema``), which
    removes almost all of the brittle string-parsing the original notebook
    relied on.
2.  They validate and normalise whatever the model returns before it ever
    reaches a CSV, so malformed or impossible values surface immediately.

The domain is a meta-analysis of how land-use / management change affects soil
properties. Each paper reports one or more *response variables* (e.g. soil
organic carbon) measured under a *treatment* and a paired *control*, together
with study-level *moderators* (climate, soil background, duration) that explain
heterogeneity between studies.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StudyInfo(BaseModel):
    first_author: Optional[str] = Field(
        None, description="Surname of the first author."
    )
    year: Optional[int] = Field(None, description="Publication year.")


class Location(BaseModel):
    site_name: Optional[str] = None
    coordinates: Optional[str] = Field(
        None, description="Latitude, longitude as reported, e.g. '34.5, 113.7'."
    )
    country: Optional[str] = None


class Climate(BaseModel):
    mean_annual_temperature_c: Optional[float] = None
    mean_annual_precipitation_mm: Optional[float] = None


class SoilBackground(BaseModel):
    soil_type_wrb: Optional[str] = Field(
        None, description="Soil classification (WRB or USDA Soil Taxonomy)."
    )
    texture: Optional[str] = Field(None, description="e.g. 'Loam', 'Sandy Loam'.")
    initial_ph: Optional[float] = None
    initial_soc_g_kg: Optional[float] = Field(
        None, description="Initial soil organic carbon, g/kg."
    )


class Treatment(BaseModel):
    name: Optional[str] = Field(None, description="Abbreviation, e.g. 'CK', 'NPK'.")
    description: Optional[str] = None


class ExperimentalDesign(BaseModel):
    duration_years: Optional[float] = None
    treatments_overview: list[Treatment] = Field(default_factory=list)


class Moderators(BaseModel):
    location: Location = Field(default_factory=Location)
    climate: Climate = Field(default_factory=Climate)
    soil_background: SoilBackground = Field(default_factory=SoilBackground)
    experimental_design: ExperimentalDesign = Field(
        default_factory=ExperimentalDesign
    )


class Provenance(BaseModel):
    source: Optional[str] = Field(
        None, description="Where the value was read, e.g. 'Table 2', 'Figure 3'."
    )
    sampling_depth_cm: Optional[str] = Field(
        None, description="e.g. '0-15'."
    )
    measurement_year: Optional[int] = None


class ResponseVariable(BaseModel):
    """One paired treatment-vs-control data point for the meta-analysis.

    The means/SDs/sample sizes are exactly what an effect-size calculation
    (e.g. log response ratio, Hedges' g) consumes, so getting these right is
    the whole point of the pipeline.
    """

    variable_name: Optional[str] = Field(
        None, description="e.g. 'soil_organic_carbon'."
    )
    unit: Optional[str] = None
    treatment_group: Optional[str] = None
    control_group: Optional[str] = None
    mean_t: Optional[float] = None
    sd_t: Optional[float] = None
    n_t: Optional[float] = None
    mean_c: Optional[float] = None
    sd_c: Optional[float] = None
    n_c: Optional[float] = None
    context: Provenance = Field(default_factory=Provenance)


class ExtractionResult(BaseModel):
    """Top-level object returned for a single paper."""

    study_info: StudyInfo = Field(default_factory=StudyInfo)
    moderator_variables: Moderators = Field(default_factory=Moderators)
    response_variables: list[ResponseVariable] = Field(default_factory=list)


def gemini_response_schema() -> dict:
    """Return a JSON schema suitable for Gemini's ``response_schema`` argument.

    Pydantic's ``model_json_schema`` emits ``$defs``/``$ref`` which the Gemini
    structured-output endpoint does not accept, so we inline the references.
    """
    schema = ExtractionResult.model_json_schema()
    defs = schema.pop("$defs", {})

    def _inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node.pop("$ref").split("/")[-1]
                node.update(_inline(defs[ref]))
            return {k: _inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_inline(v) for v in node]
        return node

    return _inline(schema)
