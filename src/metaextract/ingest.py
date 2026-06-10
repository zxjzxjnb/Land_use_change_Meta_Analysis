"""Deterministic PDF ingest → :class:`SourceDoc` (Architecture v3.1 §8 M0a).

PyMuPDF reads the PDF into addressable blocks (paragraphs / figures) and the
word-level geometry beneath them. This is the geometric ground truth the cockpit
needs for click-to-jump-and-highlight; the LLM never produces coordinates.

Note on tables: ``find_tables()`` returns nothing on borderless journal tables
(no ruling lines) and emits structure-tree errors, so it is **not used**. Instead
each table *row* already arrives as its own text block, and every number keeps an
exact word bbox — which is what value-level verification actually needs. Logical
table grouping (which blocks form "Table 2") is a Tier-2 concern, layered on top
of this geometry later, not a deterministic-ingest one.
"""

from __future__ import annotations

import re
from pathlib import Path

from .sourcedoc import BBox, SourceBlock, SourceDoc, Word

_TEXT_BLOCK = 0  # PyMuPDF block-type code for text (1 = image)


def ingest_pdf(pdf_path: str | Path) -> SourceDoc:
    """Parse a PDF into a :class:`SourceDoc` with bbox-addressable blocks."""
    import fitz  # PyMuPDF; imported lazily so the rest of the package needn't have it

    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)

    blocks: list[SourceBlock] = []
    page_sizes: dict[int, tuple[float, float]] = {}

    try:
        for pno, page in enumerate(doc, start=1):
            page_sizes[pno] = (float(page.rect.width), float(page.rect.height))
            words = _page_words(page)
            _ingest_text_blocks(page, pno, blocks, words)
            _ingest_figures(page, pno, blocks)
    finally:
        doc.close()

    return SourceDoc(
        doc_id=pdf_path.stem,
        n_pages=len(page_sizes),
        page_sizes=page_sizes,
        blocks=blocks,
    )


def _page_words(page) -> list[Word]:
    """All words on the page as (text, bbox); the precise-highlight layer."""
    out: list[Word] = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        text = text.strip()
        if text:
            out.append(Word(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1)))
    return out


def _ingest_text_blocks(
    page, pno: int, out: list[SourceBlock], page_words: list[Word]
) -> None:
    for bi, b in enumerate(page.get_text("blocks")):
        x0, y0, x1, y1, text, _bno, btype = b
        if btype != _TEXT_BLOCK:
            continue
        text = _normalize_ws(text)
        if not text:
            continue
        bbox = BBox(x0=x0, y0=y0, x1=x1, y1=y1)
        contained = [w for w in page_words if bbox.contains_center_of(w.bbox)]
        out.append(
            SourceBlock(
                block_id=f"p{pno}.b{bi}",
                kind="paragraph",
                page=pno,
                bbox=bbox,
                text=text,
                words=contained,
            )
        )


def _ingest_figures(page, pno: int, out: list[SourceBlock]) -> None:
    """Image regions as figure blocks (jumpable; numbers come via §6 digitizer)."""
    seen: set[tuple] = set()
    for fi, info in enumerate(page.get_image_info(), start=1):
        rect = info.get("bbox")
        if not rect:
            continue
        key = tuple(round(v) for v in rect)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            SourceBlock(
                block_id=f"p{pno}.fig{fi}",
                kind="figure",
                page=pno,
                bbox=BBox.from_rect(rect),
            )
        )


def _normalize_ws(text: str) -> str:
    """Collapse the per-word newlines PyMuPDF emits into single spaces."""
    return re.sub(r"\s+", " ", (text or "")).strip()
