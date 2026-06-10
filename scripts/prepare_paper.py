"""Run the expensive stages once and cache them for the cockpit.

Usage:  python scripts/prepare_paper.py P1 [model]

Ingests the paper's PDF, runs Gemini locate (Tier 1 screen + Tier 2 locate), and
writes data/cache/{study}.sourcedoc.json + {study}.locate.json. The Streamlit
cockpit reads only these, so it launches offline and makes no API calls.
"""

from __future__ import annotations

import sys
import time

from _gt import ROOT, build_spec, load_env

# Tried in order; Gemini's hosted models 503 under load, so fall back across them.
_MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"]


def _locate_with_retry(locate, doc, spec, models, attempts=4):
    last = None
    for model in models:
        for k in range(attempts):
            try:
                print(f"  calling {model} (try {k + 1})...")
                return locate(doc, spec=spec, model=model)
            except Exception as e:  # mostly transient 503 UNAVAILABLE
                last = e
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    time.sleep(6 * (k + 1))
                else:
                    break  # non-transient: try next model
    raise last


def main() -> None:
    study = sys.argv[1] if len(sys.argv) > 1 else "P1"
    models = [sys.argv[2]] if len(sys.argv) > 2 else _MODELS
    load_env()

    from metaextract import cockpit_cache
    from metaextract.ingest import ingest_pdf
    from metaextract.locate import locate

    pdf = ROOT / "data" / "sample_papers" / f"{study}.pdf"
    spec, _present, _rows = build_spec(study)

    doc = ingest_pdf(pdf)
    print(f"{study}: ingested {doc.n_pages} pages, {len(doc.blocks)} blocks.")
    out = _locate_with_retry(locate, doc, spec, models)
    cockpit_cache.save(ROOT, study, doc, out)

    print(
        f"cached -> data/cache/{study}.*.json | "
        f"{len(out.regions)} located regions, {len(out.problems)} problems"
    )


if __name__ == "__main__":
    main()
