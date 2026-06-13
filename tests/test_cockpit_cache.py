"""Cockpit cache isolation across task packs / analysis families."""

from metaextract import cockpit_cache
from metaextract.locate import LocateOutput
from metaextract.records import ScreeningResult
from metaextract.sourcedoc import SourceDoc


def _doc(study: str) -> SourceDoc:
    return SourceDoc(doc_id=study, n_pages=1)


def _out(study: str, stamp: str) -> LocateOutput:
    return LocateOutput(
        screening=ScreeningResult(paper_id=study, include=True),
        regions=[],
        task_stamp=stamp,
        analysis_family="binary_two_arm" if stamp.endswith("binary") else "continuous_two_arm",
    )


def test_stamped_locate_caches_can_coexist_for_one_study(tmp_path):
    root = tmp_path
    cockpit_cache.save(root, "P1", _doc("P1"), _out("P1", "soil.aaa"))
    cockpit_cache.save(root, "P1", _doc("P1"), _out("P1", "clinical.binary"))

    entries = cockpit_cache.list_cache_entries(root)
    assert [(e.study, e.stamp) for e in entries] == [
        ("P1", "clinical.binary"),
        ("P1", "soil.aaa"),
    ]

    _doc1, soil = cockpit_cache.load(root, "P1", stamp="soil.aaa")
    _doc2, clinical = cockpit_cache.load(root, "P1", stamp="clinical.binary")
    assert soil.task_stamp == "soil.aaa"
    assert clinical.task_stamp == "clinical.binary"
    assert clinical.analysis_family == "binary_two_arm"


def test_legacy_locate_cache_still_loads(tmp_path):
    root = tmp_path
    d = cockpit_cache.cache_dir(root)
    (d / "P1.sourcedoc.json").write_text(_doc("P1").model_dump_json())
    legacy = LocateOutput(screening=ScreeningResult(paper_id="P1", include=True), regions=[])
    (d / "P1.locate.json").write_text(legacy.model_dump_json())

    entries = cockpit_cache.list_cache_entries(root)
    assert [(e.study, e.stamp) for e in entries] == [("P1", None)]
    loaded_doc, out = cockpit_cache.load(root, "P1")
    assert loaded_doc.doc_id == "P1"
    assert out.analysis_family == "continuous_two_arm"
