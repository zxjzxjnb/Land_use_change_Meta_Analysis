"""Benchmark locate across the whole P1–P12 corpus (no per-paper config).

For each cached paper it reports two things that need no table-structure knowledge:
  * paper type — table vs figure (where the located data lives), and the mix;
  * location recall — of the GT variables this study reports, how many did Tier 2
    point a region at (matched by variable-name token overlap).

This answers "does locate hold across the corpus, and what fraction of papers are
figure-based (needing digitization)". Value-accuracy is a separate, table-only
step (see eval_against_gt.py / bench_values.py).
"""

from __future__ import annotations

import re

from _gt import ROOT, gt_spec_and_truth

STUDIES = [f"P{i}" for i in range(1, 13)]


def _toks(s):
    return set(re.findall(r"[a-z0-9]+", str(s).lower()))


def _recall(present, regions):
    """A GT variable counts as located if some region name shares >=2 tokens
    (or the GT name is short, >=1)."""
    located = 0
    for v in present:
        vt = _toks(v)
        need = 1 if len(vt) <= 2 else 2
        if any(len(vt & _toks(r.variable_name)) >= need for r in regions):
            located += 1
    return located


def main():
    from metaextract import cockpit_cache

    print(f"{'paper':6} {'type':7} {'regions':>7} {'tbl/fig':>8} {'GTvars':>6} {'located':>7} {'recall':>7}")
    print("-" * 56)
    agg = {"table": 0, "figure": 0, "mixed": 0, "recall_num": 0, "recall_den": 0, "done": 0}
    for s in STUDIES:
        try:
            doc, out = cockpit_cache.load(ROOT, s)
        except Exception:
            print(f"{s:6} (no cache)")
            continue
        tbl = sum(1 for r in out.regions if r.citation.kind == "paragraph")
        fig = sum(1 for r in out.regions if r.citation.kind == "figure")
        kind = "table" if fig == 0 else ("figure" if tbl == 0 else "mixed")
        _all_targets, _mods, present, _rows = gt_spec_and_truth(s)
        loc = _recall(present, out.regions)
        rec = loc / len(present) if present else 0.0
        agg[kind] += 1
        agg["recall_num"] += loc
        agg["recall_den"] += len(present)
        agg["done"] += 1
        print(f"{s:6} {kind:7} {len(out.regions):>7} {f'{tbl}/{fig}':>8} {len(present):>6} {loc:>7} {rec:>6.0%}")

    print("-" * 56)
    d = agg["done"]
    if d:
        overall = agg["recall_num"] / agg["recall_den"] if agg["recall_den"] else 0
        print(f"papers cached: {d}/12 | type mix: {agg['table']} table, "
              f"{agg['figure']} figure, {agg['mixed']} mixed")
        print(f"overall location recall: {agg['recall_num']}/{agg['recall_den']} = {overall:.0%}")


if __name__ == "__main__":
    main()
