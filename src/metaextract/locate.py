"""Tier 1 screen + Tier 2 locate (Architecture v3.1 §2, §7).

The locator is handed the *already-addressed* blocks of a :class:`SourceDoc` and
asked to do two cheap, low-error-cost jobs:

1. **Screen** the paper — include/exclude, which target variables and moderators
   are present (paper level only; never bound to a record, v3.1 §2).
2. **Locate** — for each target variable, name the ``block_id`` that contains it.
   It returns NO numbers and does NO treatment/control pairing.

The critical-path invariant (C1): the model may only *choose a block_id that
already exists*; all geometry (page, bbox) is attached afterwards from the
SourceDoc by :func:`resolve_regions`. A block_id the model invents is dropped and
reported, never given fabricated coordinates. ``build_payload`` and
``resolve_regions`` are pure and unit-tested without the API; :func:`locate` is a
thin Gemini wrapper around them.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from .records import Citation, ExtractedModerator, LocatedRegion, SampleSize, ScreeningResult
from .sourcedoc import SourceDoc

# How much of each block's text the model sees. Enough to recognize a variable;
# the model never needs to parse the grid (that is human/Tier-3 work).
_BLOCK_TEXT_CHARS = 320


class TaskSpec(BaseModel):
    """The single domain knob (v3.1 defers full TaskPack generality)."""

    domain: str
    target_variables: list[str]
    moderators: list[str]


# Default pack: land-use/management → soil & N2O meta-analysis (matches schema.py).
SOIL_AGRI_SPEC = TaskSpec(
    domain="soil_agri_n2o",
    target_variables=[
        "N2O emission", "soil organic carbon", "grain yield",
        "N uptake", "CH4 flux", "CO2 flux", "soil mineral nitrogen",
    ],
    moderators=[
        "site/location", "mean annual temperature", "mean annual precipitation",
        "soil type", "soil texture", "initial pH", "experiment duration",
    ],
)


# --- what we ask Gemini to return (no geometry, just block_id choices) ---
class RawRegion(BaseModel):
    block_id: str
    variable_name: str
    candidate_structure: Optional[str] = None
    ambiguous: bool = False


class RawModerator(BaseModel):
    field: str
    value: str
    block_id: Optional[str] = None


class RawSampleSize(BaseModel):
    value: Optional[str] = None
    n_control: Optional[str] = None
    n_treatment: Optional[str] = None
    note: Optional[str] = None
    block_id: Optional[str] = None


class LocatorResponse(BaseModel):
    include: bool
    reason: Optional[str] = None
    target_variables_present: list[str] = Field(default_factory=list)
    moderators_present: list[str] = Field(default_factory=list)
    regions: list[RawRegion] = Field(default_factory=list)
    moderators: list[RawModerator] = Field(default_factory=list)
    sample_size: Optional[RawSampleSize] = None


class LocateOutput(BaseModel):
    screening: ScreeningResult
    regions: list[LocatedRegion]
    moderators: list[ExtractedModerator] = Field(default_factory=list)
    moderator_fields: list[str] = Field(default_factory=list)  # full set, for the cockpit panel
    sample_size: Optional[SampleSize] = None
    problems: list[str] = Field(default_factory=list)


def build_payload(doc: SourceDoc) -> str:
    """Serialize blocks into a compact, addressable listing for the model."""
    lines = [
        "Addressable blocks (choose block_id values from this list only):",
        "",
    ]
    for b in doc.blocks:
        snippet = b.text[:_BLOCK_TEXT_CHARS].replace("\n", " ").strip()
        if b.kind == "figure":
            snippet = snippet or "(figure / image region)"
        lines.append(f"[{b.block_id}] p{b.page} {b.kind}: {snippet}")
    return "\n".join(lines)


def _system_instruction(spec: TaskSpec) -> str:
    return (
        "You are screening and locating data for a meta-analysis in the domain: "
        f"{spec.domain}.\n\n"
        "Target response variables to look for:\n  - "
        + "\n  - ".join(spec.target_variables)
        + "\n\nModerator variables to note (paper level only):\n  - "
        + "\n  - ".join(spec.moderators)
        + "\n\nYour job has two parts and STRICT limits:\n"
        "1. SCREEN: decide include/exclude, and list which target variables and "
        "moderators are present in the paper.\n"
        "2. LOCATE: for each target variable you find, output the block_id of the "
        "block that contains its data (prefer tables over figures).\n"
        "3. MODERATORS: read each moderator field's paper/site-level value as "
        "printed (e.g. site name, MAP/MAT, soil type/texture, elevation, sampling "
        "depth, study years, climate), with the block_id where you read it. These "
        "are paper-level context, NOT per-row values — report each once.\n"
        "4. SAMPLE SIZE: find the replicate count n behind the reported means. Look "
        "ONLY for a phrase that literally contains 'replicate', 'n = ', or "
        "'triplicate'/'duplicate'; the number attached to that word is n (e.g. "
        "'... x 3 replicates' -> n=3). Ignore counts of sites, sub-samples, plots, "
        "or total samples. Put the exact phrase in note, the integer in value, the "
        "block_id, and n_control/n_treatment if they differ. If no such phrase "
        "exists, leave sample_size null.\n\n"
        "HARD RULES:\n"
        "- Only use block_id values that appear in the provided block list. Never "
        "invent a block_id or describe a location in prose.\n"
        "- Do NOT report any response-variable numbers. Do NOT pair treatment vs "
        "control. Only locate where the variable's data lives.\n"
        "- Moderator values ARE allowed (they are single stated facts); copy them "
        "verbatim and cite the block_id. Omit a moderator you cannot find.\n"
        "- If you are unsure a block really contains the variable, set "
        "ambiguous=true rather than omitting it.\n"
        "- candidate_structure is an optional free-text hint about layout (e.g. "
        "'rows=treatments, cols=mean/sd/n'); it is a hint, not a commitment."
    )


def resolve_regions(
    doc: SourceDoc, raw: LocatorResponse, paper_id: str
) -> tuple[list[LocatedRegion], list[str]]:
    """Attach real geometry to model-chosen block_ids; drop+report invented ones.

    Pure and deterministic — this is the C1 guard, testable without the API.
    """
    regions: list[LocatedRegion] = []
    problems: list[str] = []
    seen: set[str] = set()

    for r in raw.regions:
        block = doc.block(r.block_id)
        if block is None:
            problems.append(
                f"unknown block_id {r.block_id!r} for variable "
                f"{r.variable_name!r} (dropped — model may have invented it)"
            )
            continue
        region_id = f"{paper_id}:{block.block_id}:{_slug(r.variable_name)}"
        if region_id in seen:
            continue
        seen.add(region_id)
        regions.append(
            LocatedRegion(
                region_id=region_id,
                paper_id=paper_id,
                variable_name=r.variable_name,
                citation=Citation(
                    block_id=block.block_id,
                    page=block.page,
                    bbox=block.bbox,
                    kind=block.kind,
                ),
                candidate_structure=r.candidate_structure,
                ambiguous=r.ambiguous,
            )
        )
    return regions, problems


def resolve_moderators(doc: SourceDoc, raw: LocatorResponse) -> list[ExtractedModerator]:
    """Keep each moderator value; attach a citation when its block_id is real."""
    mods: list[ExtractedModerator] = []
    seen: set[str] = set()
    for m in raw.moderators:
        if not m.value or _slug(m.field) in seen:
            continue
        seen.add(_slug(m.field))
        block = doc.block(m.block_id) if m.block_id else None
        citation = (
            Citation(block_id=block.block_id, page=block.page, bbox=block.bbox, kind=block.kind)
            if block is not None
            else None
        )
        mods.append(ExtractedModerator(field=m.field, value=m.value, citation=citation))
    return mods


def resolve_sample_size(doc: SourceDoc, raw: LocatorResponse) -> Optional[SampleSize]:
    """Keep the model's n statement; attach a citation when its block_id is real."""
    rs = raw.sample_size
    if rs is None or not (rs.value or rs.n_control or rs.n_treatment):
        return None
    block = doc.block(rs.block_id) if rs.block_id else None
    citation = (
        Citation(block_id=block.block_id, page=block.page, bbox=block.bbox, kind=block.kind)
        if block is not None
        else None
    )
    return SampleSize(
        value=rs.value, n_control=rs.n_control, n_treatment=rs.n_treatment,
        note=rs.note, citation=citation,
    )


def locate(
    doc: SourceDoc,
    spec: TaskSpec = SOIL_AGRI_SPEC,
    model: Optional[str] = None,
    client=None,
) -> LocateOutput:
    """Run Tier 1 + Tier 2 over an ingested SourceDoc via Gemini structured output."""
    from google.genai import types

    from .extractor import DEFAULT_MODEL, _build_client

    client = client or _build_client()
    response = client.models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=[build_payload(doc)],
        config=types.GenerateContentConfig(
            system_instruction=_system_instruction(spec),
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=_response_schema(),
        ),
    )
    parsed = getattr(response, "parsed", None)
    raw = (
        LocatorResponse.model_validate(parsed)
        if parsed is not None
        else LocatorResponse.model_validate_json(response.text)
    )

    regions, problems = resolve_regions(doc, raw, doc.doc_id)
    screening = ScreeningResult(
        paper_id=doc.doc_id,
        include=raw.include,
        reason=raw.reason,
        target_variables_present=raw.target_variables_present,
        moderators_present=raw.moderators_present,
    )
    return LocateOutput(
        screening=screening,
        regions=regions,
        moderators=resolve_moderators(doc, raw),
        moderator_fields=spec.moderators,
        sample_size=resolve_sample_size(doc, raw),
        problems=problems,
    )


def _response_schema() -> dict:
    """Inline $defs/$ref, which Gemini's response_schema does not accept."""
    schema = LocatorResponse.model_json_schema()
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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
