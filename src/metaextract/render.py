"""Render a PDF page to PNG with highlight boxes — the cockpit's visual engine.

This is what makes jump-to-evidence visible: given a page and the geometry from
deterministic ingest, draw the located block's outline and (optionally) tight
boxes around the specific values a human is confirming, then hand the image to
Streamlit. Proven in M0a; here it is packaged for reuse.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .sourcedoc import BBox

# Colors (RGB 0..1): block outline = blue, value highlight = red.
_OUTLINE = (0.13, 0.42, 0.86)
_VALUE = (0.90, 0.16, 0.16)


def render_page(
    pdf_path: str | Path,
    page: int,
    outline: Optional[list[BBox]] = None,
    values: Optional[list[BBox]] = None,
    dpi: int = 130,
    pad: float = 6.0,
) -> bytes:
    """Render 1-indexed ``page`` to PNG bytes with highlight boxes drawn on it."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        pg = doc[page - 1]
        for b in outline or []:
            r = fitz.Rect(b.x0 - pad, b.y0 - pad, b.x1 + pad, b.y1 + pad)
            pg.draw_rect(r, color=_OUTLINE, width=1.5)
        for b in values or []:
            pg.draw_rect(fitz.Rect(*b.as_tuple()), color=_VALUE, width=1.2)
        return pg.get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()


def render_region(
    pdf_path: str | Path,
    page: int,
    bbox: BBox,
    dpi: int = 170,
    pad: float = 14.0,
) -> bytes:
    """Render just a zoomed crop around ``bbox`` — for reading a figure to digitize."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        pg = doc[page - 1]
        clip = fitz.Rect(bbox.x0 - pad, bbox.y0 - pad, bbox.x1 + pad, bbox.y1 + pad)
        clip = clip & pg.rect  # keep inside the page
        return pg.get_pixmap(dpi=dpi, clip=clip).tobytes("png")
    finally:
        doc.close()
