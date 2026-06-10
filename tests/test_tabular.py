"""Deterministic tests for geometry-based table parsing (cockpit multi-pairing).

No PDF/API: build blocks with words at known x/y (mimicking aligned columns and,
for the merged-block case, stacked rows) and assert columns, means/dispersions,
row separation, and control-reuse pairings.
"""

from metaextract.sourcedoc import BBox, SourceBlock, Word
from metaextract.tabular import make_pairings, parse_block


def _w(text, x, y, w=14):
    return Word(text=text, bbox=BBox(x0=x, y0=y, x1=x + w, y1=y + 8))


def _row_words(name_x, y, name, cells):
    """One visual row: a name word at name_x, then mean/sd words per column."""
    out = [_w(name, name_x, y)]
    for x, mean, *sd in cells:
        out.append(_w(mean, x, y))
        if sd:
            out.append(_w(sd[0], x, y))  # sd just after mean (reading order)
    return out


def _block(words) -> SourceBlock:
    return SourceBlock(block_id="p1.b1", kind="paragraph", page=1,
                       bbox=BBox(x0=0, y0=90, x1=300, y1=200), text="t", words=words)


def test_single_row_four_columns():
    blk = _block(_row_words(10, 100, "SOC",
                 [(100, "39.38", "2.33a"), (140, "31.69", "2.90ab"),
                  (180, "25.04", "1.35b"), (220, "23.37", "2.20b")]))
    rows = parse_block(blk, ["NF", "AF", "SL", "FL"])
    assert len(rows) == 1
    c = rows[0].cells
    assert c["NF"].mean.text == "39.38" and c["NF"].dispersion.text == "2.33a"
    assert c["FL"].mean.text == "23.37"


def test_unit_token_not_a_column():
    blk = _block(_row_words(10, 100, "BD", [(100, "0.97", "0.03c"), (140, "1.11", "0.06bc")]))
    blk.words.insert(1, _w("g/kg", 40, 100))  # unit between name and columns
    rows = parse_block(blk, ["NF", "AF"])
    assert len(rows) == 1 and set(rows[0].cells) == {"NF", "AF"}


def test_column_count_mismatch_returns_empty():
    blk = _block(_row_words(10, 100, "BD", [(100, "0.97", "0.03c"), (140, "1.11", "0.06bc")]))
    assert parse_block(blk, ["NF", "AF", "SL", "FL"]) == []  # asked 4, found 2


def test_merged_block_splits_into_rows():
    """The p4.b14 case: pH + Moisture stacked in one block must split cleanly."""
    words = _row_words(10, 100, "pH", [(100, "6.58", "0.15a"), (140, "6.68", "0.13a")])
    words += _row_words(10, 120, "Moisture", [(100, "39.49", "2.87a"), (140, "35.89", "3.95ab")])
    rows = parse_block(_block(words), ["NF", "AF"])
    assert len(rows) == 2
    assert rows[0].cells["NF"].mean.text == "6.58"
    assert rows[1].cells["NF"].mean.text == "39.49"  # NOT pH's value


def test_pairings_reuse_control():
    blk = _block(_row_words(10, 100, "SOC",
                 [(100, "39.38", "2.33a"), (140, "31.69", "2.90ab"), (180, "25.04", "1.35b")]))
    cells = parse_block(blk, ["NF", "AF", "SL"])[0].cells
    recs = make_pairings(cells, ["NF", "AF", "SL"], "NF")
    assert [r["treatment_group"] for r in recs] == ["AF", "SL"]
    assert all(r["mean_c"] == "39.38" for r in recs)
    assert recs[0]["mean_t"] == "31.69" and recs[1]["mean_t"] == "25.04"
