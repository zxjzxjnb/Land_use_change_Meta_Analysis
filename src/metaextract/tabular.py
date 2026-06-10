"""Column- and row-aware table parsing for the multi-pairing assist (cockpit).

A borderless journal table like P1's Table 2 pairs values control-vs-treatment,
reusing the control across treatments (natural forest → artificial / shrub /
farmland). Re-typing every cell is the throughput killer the cockpit must avoid.

The unlock is geometry, on two axes:

* **columns** — a row's value tokens align in x (39.38 & 31.69 & 25.04 & 23.37);
  clustering value x's gives the columns. No fragile header detection.
* **rows** — ingest sometimes merges several short table rows into one block
  (p4.b14 = pH + Moisture + Total-N). Their mean/sd lines interleave in y so a
  plain y-gap can't split them, but the **left-most name column has exactly one
  word per row** (pH@129, Moisture@142, Total@159); those anchors define the rows
  and every value snaps to the nearest anchor by y.

So a block parses into rows, each row into columns. Every number keeps its bbox
so it still lights up in the PDF. This is a *pre-fill the human confirms*, not an
auto-extract — and when a block holds several rows the cockpit makes the human
pick the right one rather than guessing a variable→row-label match.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from .sourcedoc import SourceBlock, Word

_IS_VALUE = re.compile(r"^[−+\-]?\.?\d")  # starts with a digit (units start with a letter)


class ParsedCell(BaseModel):
    mean: Optional[Word] = None
    dispersion: Optional[Word] = None


class TableRow(BaseModel):
    label: str  # the row's name text (e.g. "pH", "Moisture content")
    cells: dict[str, ParsedCell]  # column label -> cell


def _xc(w: Word) -> float:
    return (w.bbox.x0 + w.bbox.x1) / 2


def _yc(w: Word) -> float:
    return (w.bbox.y0 + w.bbox.y1) / 2


def _cluster_1d(points: list[float], tol: float) -> list[float]:
    """Greedy 1-D clustering; returns sorted cluster centroids."""
    out: list[list[float]] = []
    for p in sorted(points):
        if out and p - out[-1][-1] <= tol:
            out[-1].append(p)
        else:
            out.append([p])
    return [sum(c) / len(c) for c in out]


def column_count(block: SourceBlock, xtol: float = 18.0) -> int:
    """Discover how many value columns a table block has (label-free), by
    clustering its value tokens' x-centers. Used to parse papers whose column
    labels we don't know in advance."""
    xs = [_xc(w) for _i, w in enumerate(block.words) if _IS_VALUE.match(w.text)]
    return len(_cluster_1d(xs, xtol)) if xs else 0


def parse_block(
    block: SourceBlock,
    labels: list[str],
    xtol: float = 18.0,
    ytol: float = 6.0,
    anchor_xtol: float = 4.0,
) -> list[TableRow]:
    """Parse a (possibly multi-row) table block into rows × columns.

    Returns [] when the value columns don't match ``labels`` (so the cockpit falls
    back to manual entry instead of mis-aligning silently).
    """
    vals = [(i, w) for i, w in enumerate(block.words) if _IS_VALUE.match(w.text)]
    if not vals:
        return []

    col_centers = _cluster_1d([_xc(w) for _, w in vals], xtol)
    if len(col_centers) != len(labels):
        return []
    left_edge = col_centers[0] - xtol

    # row anchors: words in the left-most name column, one per row
    nonval = [w for w in block.words if not _IS_VALUE.match(w.text) and _xc(w) < left_edge]
    if nonval:
        # row anchors sit in the left-most name column (by x0); wrapped continuation
        # words are indented a few points, so a tight x0 tolerance keeps one per row.
        name_x0 = min(w.bbox.x0 for w in nonval)
        anchor_words = sorted((w for w in nonval if w.bbox.x0 <= name_x0 + anchor_xtol), key=_yc)
        anchors: list[dict] = []
        for w in anchor_words:
            if anchors and _yc(w) - anchors[-1]["y"] <= ytol:
                continue  # same row's wrapped name
            anchors.append({"y": _yc(w), "words": []})
    else:
        anchors = [{"y": min(_yc(w) for _, w in vals), "words": []}]

    anchor_ys = [a["y"] for a in anchors]

    def nearest(y: float) -> int:
        return min(range(len(anchor_ys)), key=lambda k: abs(anchor_ys[k] - y))

    # full row labels: every non-value word snaps to its nearest anchor row
    for w in nonval:
        anchors[nearest(_yc(w))]["words"].append(w)

    # values snap to (row by y, column by x)
    grid: list[dict[str, list[tuple[int, Word]]]] = [{} for _ in anchors]
    for i, w in vals:
        ri = nearest(_yc(w))
        ci = min(range(len(col_centers)), key=lambda k: abs(col_centers[k] - _xc(w)))
        grid[ri].setdefault(labels[ci], []).append((i, w))

    rows: list[TableRow] = []
    for a, cols in zip(anchors, grid):
        if not cols:
            continue
        label = " ".join(w.text for w in sorted(a["words"], key=lambda w: (_yc(w), _xc(w))))
        cells = {
            col: ParsedCell(
                mean=ws_sorted[0][1],
                dispersion=ws_sorted[1][1] if len(ws_sorted) > 1 else None,
            )
            for col, ws in cols.items()
            for ws_sorted in [sorted(ws, key=lambda iw: iw[0])]  # reading order
        }
        rows.append(TableRow(label=label.strip(), cells=cells))
    return rows


def make_pairings(cells: dict[str, ParsedCell], labels: list[str], control: str) -> list[dict]:
    """Control × each treatment → one candidate record per treatment.

    Each carries the raw value tokens (for the CSV) and their bboxes (for PDF
    highlighting). The human still confirms before these become records.
    """
    ctrl = cells.get(control)
    if ctrl is None or ctrl.mean is None:
        return []
    out: list[dict] = []
    for label in labels:
        if label == control:
            continue
        cell = cells.get(label)
        if cell is None or cell.mean is None:
            continue
        out.append(
            {
                "control_group": control,
                "treatment_group": label,
                "mean_c": ctrl.mean.text,
                "sd_c": ctrl.dispersion.text if ctrl.dispersion else "",
                "mean_t": cell.mean.text,
                "sd_t": cell.dispersion.text if cell.dispersion else "",
                "_bboxes": [
                    w.bbox
                    for w in (ctrl.mean, ctrl.dispersion, cell.mean, cell.dispersion)
                    if w is not None
                ],
            }
        )
    return out
