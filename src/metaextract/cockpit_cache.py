"""On-disk cache so the cockpit runs offline (no API call per launch).

``prepare`` runs the expensive stages once (ingest + Gemini locate) and writes
two JSON files per paper; the Streamlit app only ever reads them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .locate import LocateOutput
from .sourcedoc import SourceDoc


@dataclass(frozen=True)
class CacheEntry:
    """One selectable cockpit cache: a study plus the task pack that located it."""

    study: str
    stamp: str | None = None

    @property
    def label(self) -> str:
        return self.study if self.stamp is None else f"{self.study} - {self.stamp}"


def cache_dir(root: Path) -> Path:
    d = root / "data" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(root: Path, study: str, doc: SourceDoc, out: LocateOutput) -> None:
    d = cache_dir(root)
    (d / f"{study}.sourcedoc.json").write_text(doc.model_dump_json())
    locate_name = (
        f"{study}.{out.task_stamp}.locate.json"
        if out.task_stamp
        else f"{study}.locate.json"
    )
    (d / locate_name).write_text(out.model_dump_json())


def load(root: Path, study: str, stamp: str | None = None) -> tuple[SourceDoc, LocateOutput]:
    d = cache_dir(root)
    doc = SourceDoc.model_validate_json((d / f"{study}.sourcedoc.json").read_text())
    locate_name = f"{study}.{stamp}.locate.json" if stamp else f"{study}.locate.json"
    out = LocateOutput.model_validate_json((d / locate_name).read_text())
    return doc, out


def list_cached(root: Path) -> list[str]:
    d = cache_dir(root)
    return sorted(p.name[: -len(".sourcedoc.json")] for p in d.glob("*.sourcedoc.json"))


def list_cache_entries(root: Path) -> list[CacheEntry]:
    """List cache entries the cockpit can open without mixing task packs."""
    d = cache_dir(root)
    entries: list[CacheEntry] = []
    for study in list_cached(root):
        legacy = d / f"{study}.locate.json"
        if legacy.exists():
            entries.append(CacheEntry(study=study, stamp=None))

        prefix = f"{study}."
        suffix = ".locate.json"
        for path in sorted(d.glob(f"{study}.*.locate.json")):
            stamp = path.name[len(prefix): -len(suffix)]
            if stamp:
                entries.append(CacheEntry(study=study, stamp=stamp))
    return sorted(entries, key=lambda e: (e.study, e.stamp or ""))
