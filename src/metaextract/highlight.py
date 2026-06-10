"""Resolve an evidence string to a highlight bbox (Architecture v3.1 §3, C1).

This is the engine behind the cockpit's make-or-break feature. Given a block the
locator pointed at and the value/span a human or Tier-3 model is confirming, it
returns the exact word geometry to light up in the PDF. The match is tolerant of
the trailing marks journals love (``0.302***a``, ``12.3 ​b``) and of values that
span several words.

It is deterministic and offline: no LLM, no API. A returned ``Match`` is also the
input to grounding (v3.1 §5) — if a claimed value cannot be located in its cited
block, that *is* the grounding failure.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from .sourcedoc import BBox, SourceBlock, Word

# Strip everything except digits, sign, decimal point, and exponent marker, so a
# table value "−0.087*" compares equal to the number "-0.087".
_NUM_STRIP = re.compile(r"[^0-9eE.+\-]")
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


class Match(BaseModel):
    """Where an evidence string was found, ready to highlight."""

    bbox: BBox  # union box, for scroll-into-view + outline
    words: list[Word]  # the individual matched tokens, for tight highlighting
    exact: bool  # True = literal token match; False = numeric-equality match


def _num(token: str) -> Optional[float]:
    token = token.replace("−", "-")  # unicode minus → ASCII
    cleaned = _NUM_STRIP.sub("", token)
    try:
        return float(cleaned)
    except ValueError:
        return None


def locate_value(block: SourceBlock, value, rel_tol: float = 1e-9) -> Optional[Match]:
    """Find a numeric ``value`` among the block's words (symbol-tolerant)."""
    target = _num(str(value))
    if target is None:
        return locate_span(block, str(value))

    best: Optional[Word] = None
    best_exact = False
    for w in block.words:
        wv = _num(w.text)
        if wv is None:
            continue
        if wv == target or (target != 0 and abs(wv - target) / abs(target) <= rel_tol):
            exact = _NUM_STRIP.sub("", w.text.replace("−", "-")) == str(value).replace(
                "−", "-"
            )
            # Prefer an exact token match; otherwise take the first numeric hit.
            if best is None or (exact and not best_exact):
                best, best_exact = w, exact
    if best is None:
        return None
    return Match(bbox=best.bbox, words=[best], exact=best_exact)


def locate_span(block: SourceBlock, text: str) -> Optional[Match]:
    """Find a consecutive run of words matching the phrase ``text``."""
    query = [t for t in re.split(r"\s+", text.strip()) if t]
    if not query:
        return None
    words = block.words
    qn = [_norm(t) for t in query]
    for i in range(len(words) - len(query) + 1):
        window = words[i : i + len(query)]
        if all(_norm(w.text).startswith(q) or q.startswith(_norm(w.text)) for w, q in zip(window, qn)):
            box = BBox.union([w.bbox for w in window])
            if box is not None:
                return Match(bbox=box, words=window, exact=True)
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower().replace("−", "-")
