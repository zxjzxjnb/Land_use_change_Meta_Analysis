"""Deterministic tests for the sample-size (n) candidate finder.

The point of going deterministic: the LLM mis-read P1's n (picked 5 or 7 from
"7 sites x 4 land use types x 3 replicates"); a regex finds the "3 replicates"
phrase reliably. These lock that in.
"""

from metaextract.sampling import find_sample_size_candidates
from metaextract.sourcedoc import BBox, SourceBlock, SourceDoc


def _doc(text: str) -> SourceDoc:
    b = SourceBlock(block_id="p3.b2", kind="paragraph", page=3,
                    bbox=BBox(x0=0, y0=0, x1=100, y1=10), text=text)
    return SourceDoc(doc_id="t", n_pages=3, blocks=[b])


def test_finds_replicate_count_not_sites():
    doc = _doc("A total of 84 samples (7 sites x 4 land use types x 3 replicates) were collected.")
    cands = find_sample_size_candidates(doc)
    assert [c.value for c in cands] == ["3"]  # not 84, 7, or 4
    assert cands[0].block_id == "p3.b2" and "replicates" in cands[0].phrase


def test_triplicate_reads_as_three():
    cands = find_sample_size_candidates(_doc("All assays were run in triplicate."))
    assert cands[0].value == "3"


def test_n_equals_pattern():
    cands = find_sample_size_candidates(_doc("Means are shown (n = 4)."))
    assert any(c.value == "4" for c in cands)


def test_no_statement_returns_empty():
    assert find_sample_size_candidates(_doc("Soil was sampled and analysed.")) == []
