"""On-disk cache so the cockpit runs offline (no API call per launch).

``prepare`` runs the expensive stages once (ingest + Gemini locate) and writes
two JSON files per paper; the Streamlit app only ever reads them.
"""

from __future__ import annotations

import json
from pathlib import Path

from .locate import LocateOutput
from .sourcedoc import SourceDoc


def cache_dir(root: Path) -> Path:
    d = root / "data" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(root: Path, study: str, doc: SourceDoc, out: LocateOutput) -> None:
    d = cache_dir(root)
    (d / f"{study}.sourcedoc.json").write_text(doc.model_dump_json())
    (d / f"{study}.locate.json").write_text(out.model_dump_json())


def load(root: Path, study: str) -> tuple[SourceDoc, LocateOutput]:
    d = cache_dir(root)
    doc = SourceDoc.model_validate_json((d / f"{study}.sourcedoc.json").read_text())
    out = LocateOutput.model_validate_json((d / f"{study}.locate.json").read_text())
    return doc, out


def list_cached(root: Path) -> list[str]:
    d = cache_dir(root)
    return sorted(p.name[: -len(".sourcedoc.json")] for p in d.glob("*.sourcedoc.json"))
