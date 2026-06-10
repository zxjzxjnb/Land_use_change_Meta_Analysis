"""MetaExtract verification cockpit (Architecture v3.1 §3, M0b).

One screen: located regions on the right, the PDF with the evidence highlighted
on the left. Click a region → the page jumps and outlines the block; type a value
→ that exact number lights up in the source. AI located; the human verifies and
assembles records. Runs offline from the cache written by scripts/prepare_paper.py.

Launch:  streamlit run app/cockpit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from metaextract import cockpit_cache  # noqa: E402
from metaextract.highlight import locate_value  # noqa: E402
from metaextract.render import render_page, render_region  # noqa: E402
from metaextract.sampling import find_sample_size_candidates  # noqa: E402
from metaextract.sourcedoc import BBox  # noqa: E402
from metaextract.tabular import make_pairings, parse_block  # noqa: E402

SLOT_ROLES = [
    ("mean_c", "Xc"),
    ("sd_c", "Sc"),
    ("n_c", "Nc"),
    ("mean_t", "Xe"),
    ("sd_t", "Se"),
    ("n_t", "Ne"),
]
ROLE_LABELS = dict(SLOT_ROLES)

st.set_page_config(page_title="MetaExtract cockpit", layout="wide")


@st.cache_data(show_spinner=False)
def _render(pdf_path: str, page: int, outline: tuple, values: tuple, dpi: int = 135) -> bytes:
    return render_page(
        pdf_path, page,
        outline=[BBox(x0=a, y0=b, x1=c, y1=d) for a, b, c, d in outline],
        values=[BBox(x0=a, y0=b, x1=c, y1=d) for a, b, c, d in values],
        dpi=dpi,
    )


@st.cache_data(show_spinner=False)
def _render_crop(pdf_path: str, page: int, bbox: tuple) -> bytes:
    return render_region(pdf_path, page, BBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]))


def _figure_caption(doc, page):
    caps = [b.text for b in doc.blocks_on(page) if b.text.strip().lower().startswith("fig")]
    return caps[0] if caps else ""


def _locate_on_page(doc, page, value):
    """Highlight a value wherever it sits on the page — not just the located block.
    Essential for transposed / multi-block tables where the value the human reads
    lives in a different block than the one the region points at."""
    out = []
    for b in doc.blocks_on(page):
        m = locate_value(b, value)
        if m:
            out.append(m.bbox)
    return out


def _pdf_path(study: str) -> Path:
    return ROOT / "data" / "sample_papers" / f"{study}.pdf"


def main() -> None:
    st.title("MetaExtract — verification cockpit")

    papers = cockpit_cache.list_cached(ROOT)
    if not papers:
        st.warning("No cached papers. Run `python scripts/prepare_paper.py P1` first.")
        return

    study = st.sidebar.selectbox("Paper", papers)
    doc, out = cockpit_cache.load(ROOT, study)
    records = st.session_state.setdefault(f"records_{study}", [])

    # --- Tier 1 screening summary ---
    s = out.screening
    st.sidebar.markdown(f"**Include:** {'✅' if s.include else '❌'}")
    st.sidebar.markdown(f"**Variables found:** {len(s.target_variables_present)}")
    st.sidebar.markdown(f"**Moderators:** {', '.join(s.moderators_present) or '—'}")
    if out.problems:
        st.sidebar.error(f"{len(out.problems)} hallucinated block_id(s) dropped")
    st.sidebar.metric("Records assembled", len(records))

    if not out.regions:
        st.info("No located regions in this paper.")
        return

    labels = [f"{r.variable_name}  ·  {r.citation.block_id} (p{r.citation.page})" for r in out.regions]
    idx = st.sidebar.radio("Located regions", range(len(out.regions)), format_func=lambda i: labels[i])
    region = out.regions[idx]
    block = doc.block(region.citation.block_id)

    # --- moderators (paper-level): AI suggests, human confirms + binds (v3.1 §2) ---
    mod_ai = {m.field: m.value for m in out.moderators}
    mod_fields = out.moderator_fields or list(mod_ai)
    with st.expander(f"📋 Moderators (paper-level) — {len(mod_ai)} AI-suggested · bind to all records"):
        st.caption(
            "AI suggested these paper/site-level values; edit/confirm. They bind to every "
            "exported record (v3.1 §2: AI may suggest, binding is human)."
        )
        mod_values: dict[str, str] = {}
        mcols = st.columns(3)
        for i, f in enumerate(mod_fields):
            mod_values[f] = mcols[i % 3].text_input(f, value=mod_ai.get(f, ""), key=f"mod_{study}_{f}")
    bound = {k: v.strip() for k, v in mod_values.items() if v.strip()}

    # --- sample size (n): deterministic finder surfaces candidates, human picks ---
    # (the LLM proved unreliable at n; regex over the source is not — v3.1: locate
    # reliably, human decides.)
    n_cands = find_sample_size_candidates(doc)
    default_n = ""
    if n_cands:
        pick = n_cands[0]
        if len(n_cands) > 1:
            pi = st.selectbox(
                "🧪 Sample size n — pick the replicate count",
                range(len(n_cands)),
                format_func=lambda k: f"n={n_cands[k].value} · {n_cands[k].phrase[:60]}",
                key=f"npick_{study}",
            )
            pick = n_cands[pi]
        default_n = pick.value
        st.caption(f"🧪 n = {pick.value} · source {pick.block_id} p{pick.page} — {pick.phrase}")
    else:
        st.caption("🧪 No sample-size statement found — enter Nc/Ne manually below.")

    left, right = st.columns([3, 2])

    # --- right: fill / assemble ---
    with right:
        st.subheader(region.variable_name)
        st.caption(f"{region.citation.kind} · {region.citation.block_id} · page {region.citation.page}")
        if region.ambiguous:
            st.warning("Model marked this region ambiguous — verify it really holds this variable.")

        values_to_highlight: list[BBox] = []
        if region.citation.kind == "figure":
            st.info("Figure — read values with a digitizer (WebPlotDigitizer); AI never reads chart values (v3.1 §6).")
            cap = _figure_caption(doc, region.citation.page)
            if cap:
                st.caption(f"📈 {cap[:240]}")
            status = st.selectbox(
                "Status", ["digitized", "located (not done)", "not in source"],
                key=f"fstatus_{region.region_id}",
            )
            fc, ft = st.columns(2)
            ctrl = fc.text_input("Control group", key=f"fctrl_{region.region_id}")
            trt = ft.text_input("Treatment group", key=f"ftrt_{region.region_id}")
            g = st.columns(4)
            mean_c = g[0].text_input("Xc", key=f"fmc_{region.region_id}")
            sd_c = g[1].text_input("Sc", key=f"fsc_{region.region_id}")
            mean_t = g[2].text_input("Xe", key=f"fmt_{region.region_id}")
            sd_t = g[3].text_input("Se", key=f"fst_{region.region_id}")
            digiref = st.text_input(
                "Digitizer ref (file / screenshot / axis calibration)", key=f"fref_{region.region_id}"
            )
            pair = {
                "control_group": ctrl, "treatment_group": trt,
                "mean_c": mean_c, "sd_c": sd_c, "mean_t": mean_t, "sd_t": sd_t,
                "n_c": default_n, "n_t": default_n,
                "source": "figure_digitized", "status": status, "digitizer_ref": digiref,
            }
            entered = {}
        else:
            st.text_area("Block text (source)", block.text, height=80, disabled=True)

            # --- multi-pairing assist: geometry-based, control reused across treatments ---
            cand_key = f"cand_{region.region_id}"
            with st.expander("⚡ Auto-pairing — fast path for simple tables (variable-per-row)"):
                st.caption(
                    "Only for plain tables where each row is one variable and columns are "
                    "treatments. Transposed/nested tables won't align — use manual entry below "
                    "(check the red highlights match)."
                )
                colspec = st.text_input(
                    "Columns left→right (comma-sep)", key=f"cols_{study}",
                    placeholder="e.g. NF,AF,SL,FL",
                )
                col_labels = [c.strip() for c in colspec.split(",") if c.strip()]
                n_c_val = n_t_val = default_n
                if len(col_labels) >= 2:
                    control_col = st.selectbox("Control column", col_labels, key=f"ctrlcol_{study}")
                    ncol, ecol = st.columns(2)
                    n_c_val = ncol.text_input("Nc (control n)", value=default_n, key=f"nc_{study}")
                    n_t_val = ecol.text_input("Ne (treatment n)", value=default_n, key=f"ne_{study}")
                    rows = parse_block(block, col_labels)
                    if not rows:
                        st.caption(
                            f"Couldn't align {len(col_labels)} columns here — fill manually below."
                        )
                    else:
                        if len(rows) == 1:
                            chosen = rows[0]
                        else:
                            ri = st.selectbox(
                                "This block holds several rows — pick the one for this variable",
                                range(len(rows)),
                                format_func=lambda k: f"{rows[k].label}  →  "
                                + ", ".join(
                                    f"{c}:{rows[k].cells[c].mean.text}"
                                    for c in col_labels if c in rows[k].cells
                                ),
                                key=f"row_{region.region_id}",
                            )
                            chosen = rows[ri]
                        if st.button("Generate pairings"):
                            st.session_state[cand_key] = make_pairings(chosen.cells, col_labels, control_col)
                cands = st.session_state.get(cand_key, [])
                if cands:
                    st.dataframe(
                        [{k: v for k, v in r.items() if k != "_bboxes"} for r in cands],
                        use_container_width=True, height=140,
                    )
                    if st.button(f"✓ Accept {len(cands)} pairings", type="primary"):
                        for r in cands:
                            rec = {k: v for k, v in r.items() if k != "_bboxes"}
                            records.append({
                                "paper_id": doc.doc_id, "variable_name": region.variable_name,
                                "source_block_id": region.citation.block_id,
                                "page": region.citation.page, "kind": region.citation.kind,
                                "unit": "", "dispersion": "",
                                "n_c": n_c_val, "n_t": n_t_val, **rec,
                            })
                        st.session_state[cand_key] = []
                        st.rerun()

            st.markdown("**Manual entry** — works for any table layout (transposed, nested, …)")
            c1, c2 = st.columns(2)
            ctrl = c1.text_input("Control group", key=f"ctrl_{region.region_id}")
            trt = c2.text_input("Treatment group", key=f"trt_{region.region_id}")
            entered = {}
            unmatched = []
            cols = st.columns(3)
            for j, (role, label) in enumerate(SLOT_ROLES):
                dflt = default_n if role in ("n_c", "n_t") else ""
                v = cols[j % 3].text_input(label, value=dflt, key=f"{role}_{region.region_id}")
                entered[role] = v
                if v.strip() and role not in ("n_c", "n_t"):  # n is from methods, not the table
                    hits = _locate_on_page(doc, region.citation.page, v.strip())
                    values_to_highlight.extend(hits)
                    if not hits:
                        unmatched.append(label)
            u1, u2 = st.columns(2)
            unit = u1.text_input("Unit", key=f"unit_{region.region_id}")
            dispersion = u2.selectbox("Dispersion", ["sd", "se"], key=f"disp_{region.region_id}")
            pair = {
                "control_group": ctrl,
                "treatment_group": trt,
                "unit": unit,
                "dispersion": dispersion,
                **entered,
            }
            if unmatched:
                st.warning(f"Not found on page {region.citation.page} (typo?): {', '.join(unmatched)}")

            if cands:  # candidate pairings take over the highlight
                values_to_highlight = [bb for r in cands for bb in r["_bboxes"]]

        if st.button("➕ Add record", type="primary"):
            records.append({
                "paper_id": doc.doc_id,
                "variable_name": region.variable_name,
                "source_block_id": region.citation.block_id,
                "page": region.citation.page,
                "kind": region.citation.kind,
                **pair,
            })
            st.rerun()

    # --- left: PDF with evidence highlighted ---
    with left:
        if region.citation.kind == "figure":
            png = _render_crop(str(_pdf_path(study)), region.citation.page, region.citation.bbox.as_tuple())
            st.image(png, use_container_width=True,
                     caption=f"page {region.citation.page} — figure region (digitize values from here)")
        else:
            outline = (region.citation.bbox.as_tuple(),)
            vals = tuple(b.as_tuple() for b in values_to_highlight)
            png = _render(str(_pdf_path(study)), region.citation.page, outline, vals)
            st.image(png, use_container_width=True,
                     caption=f"page {region.citation.page} — blue: located block · red: entered values")

    # --- assembled records + export ---
    if records:
        st.divider()
        st.subheader(f"Assembled records ({len(records)})")
        status = "bound" if bound else "unbound"
        df = pd.DataFrame(
            [{**bound, **r, "moderator_binding_status": status} for r in records]
        )
        if not bound:
            st.caption("⚠ No moderators bound yet — fill the Moderators panel to bind them.")
        st.dataframe(df, use_container_width=True, height=200)
        st.download_button(
            "⬇ Export meta_ready.csv",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"{study}_meta_ready.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
