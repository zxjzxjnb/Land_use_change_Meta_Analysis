# MetaExtract — Architecture v2

A schema-driven, evidence-grounded, human-in-the-loop extraction framework for
meta-analysis.

This revision keeps the goals of the v1 design but fixes five structural risks
identified in review:

1. **Record assembly was under-specified.** v2 makes *records* (not spans) the
   extraction primitive, so the LLM emits already-paired records and assembly
   stops being a separate hard problem.
2. **LangExtract sat on the critical path.** v2 demotes span extraction to an
   optional *audit/highlight* helper. The primary extractor is schema-constrained
   structured output, which is what records actually need.
3. **Evidence was stored but never verified.** v2 adds a deterministic grounding
   check as a first-class stage.
4. **Units / effect size were hand-waved.** v2 makes them explicit layers.
5. **LLM `confidence` drove triage.** v2 triages on *verifiable* signals.

---

## 1. The three boundaries (what makes it "general")

Generality lives in mechanism, not in one giant schema. There are exactly three
pluggable surfaces; everything else is fixed framework code.

```
┌─────────────────────────────────────────────────────────┐
│  FRAMEWORK CORE  (fixed, domain-agnostic)                │
│  ingest · select · extract-runner · grounding-verify ·   │
│  unit-normalize · validate-runner · review · export ·    │
│  eval                                                     │
└─────────────────────────────────────────────────────────┘
        ▲                    ▲                     ▲
        │ TaskPack           │ ModelAdapter        │ UnitRegistry
        │ (domain expert)    │ (engineering)       │ (shared, extensible)
```

- **TaskPack** — the only thing a domain expert touches. Pure config + examples.
- **ModelAdapter** — swap Gemini / OpenAI / local Ollama behind one interface.
- **UnitRegistry** — canonical units + conversions, shared across task packs.

### TaskPack contents

```
taskpacks/agri_n2o_yield/
  pack.yaml            # domain, task, record type, outcomes, effect-size choice
  fields.yaml          # field definitions -> generates the Pydantic record model
  units.yaml           # allowed units per outcome + canonical target
  rules.yaml           # declarative validation rules
  validators.py        # OPTIONAL python escape hatch for rules a DSL can't express
  examples.jsonl       # few-shot: (source_block, expected records)
  selectors.yaml       # keywords / patterns for chunk selection
```

Switching domains = new TaskPack. No core code changes. This is the "domain
experts tune it" story, made concrete.

---

## 2. Pipeline (data contracts between every stage)

Each stage has a typed input and output. Stages are pure functions over these
contracts, so any stage can be tested, cached, or replaced in isolation.

```
RawInput
  │  ingest
  ▼
SourceDoc            (addressable blocks: stable ids, page, kind, text)
  │  select
  ▼
list[SourceBlock]    (candidate blocks only)
  │  extract            ← ModelAdapter + TaskPack.fields + examples
  ▼
list[Record]         (paired, every numeric field carries EvidenceValue)
  │  ground-verify      ← deterministic, no LLM
  ▼
list[Record]         (grounding_verified set per value; record-context checked)
  │  normalize          ← UnitRegistry + TaskPack.units
  ▼
list[Record]         (canonical units + effect-size precursors)
  │  validate           ← TaskPack.rules + validators.py
  ▼
list[Record]         (status + flags)
  │  review             ← human-in-the-loop (corrections recorded)
  ▼
list[Record]         (reviewed)
  │  export
  ▼
jsonl · meta_ready.csv · evidence_report.html · review_log.csv
```

---

## 3. Core data model

The whole framework is held together by these contracts. Task-specific fields are
generated from `fields.yaml`, but they all use the same evidence-carrying value
type, so grounding/normalization/validation are generic.

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

# ---------- Addressable source ----------
class SourceBlock(BaseModel):
    block_id: str                      # stable: "p5.table2", "p5.para3"
    kind: Literal["table", "paragraph", "figure_caption"]
    text: str                          # tables kept as MARKDOWN (structure preserved)
    page: Optional[int] = None

class SourceDoc(BaseModel):
    doc_id: str                        # = paper_id
    blocks: list[SourceBlock]

# ---------- Evidence-carrying value (the key generic unit) ----------
class EvidenceValue(BaseModel):
    value: float | int | str
    unit: Optional[str] = None
    evidence_text: str                 # exact span the value was read from
    block_id: str                      # which SourceBlock it came from
    # filled by later stages, NOT by the model:
    grounding_verified: bool = False   # value literally found in evidence_text & block
    canonical_value: Optional[float] = None
    canonical_unit: Optional[str] = None

# ---------- A record = one paired treatment/control data point ----------
class Record(BaseModel):
    record_id: str                     # f"{paper_id}:{block_id}:{row}"  -> stable, cacheable
    paper_id: str
    source_block_ids: list[str]        # RECORD-level evidence: all fields share context
    schema_version: str

    # --- task fields are injected from fields.yaml; shown here for the agri pack ---
    outcome: str
    treatment: str
    control: str
    mean_t: EvidenceValue
    mean_c: EvidenceValue
    sd_t: Optional[EvidenceValue] = None
    sd_c: Optional[EvidenceValue] = None
    n_t: Optional[EvidenceValue] = None
    n_c: Optional[EvidenceValue] = None

    # --- framework-managed trust state ---
    effect: Optional["EffectSize"] = None
    status: Literal["valid", "needs_review", "invalid"] = "needs_review"
    flags: list[str] = Field(default_factory=list)

class EffectSize(BaseModel):
    kind: Literal["lnRR", "SMD", "MD"]
    estimate: Optional[float] = None
    variance: Optional[float] = None
    computable: bool = False           # false if required fields missing
    note: Optional[str] = None
```

Why this shape solves the v1 problems:

- **Record-level evidence** = `source_block_ids`. The grounding stage enforces
  that every field's `block_id` is in this set → kills cross-table / cross-year
  splicing at the data-contract level.
- **Evidence is part of the value**, not a parallel LangExtract artifact → no
  span-to-record assembly step.

---

## 4. Stage-by-stage

### 4.1 Ingest → `SourceDoc`
MVP accepts markdown table, pasted table, paragraph text, `.txt`. **Tables are
ingested as markdown** so row/column alignment survives (the only signal record
pairing has). Each block gets a stable `block_id`. PDF parsers (PyMuPDF / MinerU /
GROBID) are just additional ingest backends added later — they produce the same
`SourceDoc`, so nothing downstream changes.

### 4.2 Select → candidate blocks
Cheap keyword/structure filter from `selectors.yaml` (mean, SD, n, treatment,
N2O, kg N ha, …). Prefers table blocks. Reduces tokens; never the source of
truth.

### 4.3 Extract → `list[Record]`  ← the only LLM call on the critical path
The ModelAdapter is handed: the **record model generated from `fields.yaml`** as a
constrained-output schema (extends your existing
`schema.py:gemini_response_schema`), the candidate blocks, and few-shot
`examples.jsonl`. The model returns a **list of fully-paired records**, each
numeric field as an `EvidenceValue`. The model is told to copy `evidence_text`
verbatim and report the `block_id` it used.

> LangExtract is **optional** here and only as an *audit overlay*: it can
> re-highlight where each accepted value sits in the source for the review UI. It
> is never the primary extractor.

### 4.4 Ground-verify → deterministic, no LLM  ← the killer feature
For every `EvidenceValue`:
- the printed `value` must appear (tolerant numeric match) inside `evidence_text`;
- `evidence_text` must appear (normalized) inside the cited `block.text`;
- the value's `block_id` must be in the record's `source_block_ids`.

Pass → `grounding_verified = True`. Any failure → record flagged
`evidence_unverified` and forced to `needs_review`. This is cheap, deterministic,
and catches the dominant hallucination/splice failure modes that LLM confidence
cannot.

### 4.5 Normalize → `UnitRegistry`
Each outcome declares a canonical unit in `units.yaml` (e.g. N2O → `kg N ha-1`).
The registry holds dimensioned conversion factors; every `EvidenceValue` gets
`canonical_value` / `canonical_unit`. Non-convertible / unknown unit → flag
`unit_unconvertible`, never silently coerce. Effect sizes are computed **only on
canonical values**.

### 4.6 Validate → status + flags
Two rule sources, no home-grown expression language:

- **Declarative** (`rules.yaml`) using a fixed vocabulary:
  `required`, `range`, `enum`, `cross_field` (eq/neq/gt), `integer`.
- **Python escape hatch** (`validators.py`): any rule a table can't express
  (SD-vs-SE plausibility via CV, outlier detection, domain heuristics) is a
  plain function `(record) -> list[flag]`.

Plus the grounding/unit flags from 4.4–4.5. Final `status` is a pure function of
the flag set (any hard flag → `invalid`; any soft flag → `needs_review`; clean →
`valid`).

### 4.7 Review → human-in-the-loop (Streamlit)
Triage **by verifiable signal**, not LLM confidence: sort by status, then by flag
severity, then by `grounding_verified` count. Each field shows value · canonical ·
evidence span · which block · flags · accept/edit/reject. Corrections are written
to `review_log.csv` and appended to `examples.jsonl` (the tuning feedback loop).

### 4.8 Export
- `extracted_records.jsonl` — full fidelity (values, evidence, units, flags).
- `meta_ready.csv` — flat, canonical units, effect-size columns.
- `evidence_report.html` — every record next to its source span (audit).
- `review_log.csv` — human edit history.

---

## 5. Effect size as a declared layer (not an afterthought)
`pack.yaml` declares the effect-size kind per record type. Ecology / agri-env
default is **lnRR** (the field standard), not SMD.

```
lnRR     = ln(mean_t / mean_c)
var(lnRR)= sd_t^2/(n_t*mean_t^2) + sd_c^2/(n_c*mean_c^2)
```

If required inputs are missing (e.g. no SD), `EffectSize.computable = False` with
a note, rather than emitting a wrong number. SE/CI→SD conversion is a documented
helper in the normalize layer, surfaced as `flags` when applied.

---

## 6. Evaluation (with a defined matching key)
Field accuracy is undefined until predicted records are aligned to gold records.
v2 fixes the matching key explicitly:

- **Match key:** `(paper_id, outcome, normalized(treatment), normalized(control))`,
  one-to-one, greedy by numeric closeness on ties.
- **Metrics:** record recall/precision (pairing discovery); per-field MAE on
  canonical `mean_t/mean_c/sd_*/n_*`; exact match on `n_*`; unit-correctness;
  **grounding precision** (of values claimed verified, how many are truly in the
  source); human-correction rate.

This reuses and extends your existing `evaluate.py`.

---

## 7. Module map (old metaextract → v2)

| v2 stage          | reuse from current repo            |
|-------------------|------------------------------------|
| core data model   | `schema.py` (record-centric already) |
| extract           | `extractor.py` (Gemini structured output) |
| validate          | `validator.py` (move to rules + hooks) |
| flatten/export    | `flatten.py`                       |
| batch/cache       | `pipeline.py`                      |
| eval              | `evaluate.py` (+ matching key)     |
| **new** | ingest/SourceDoc · select · ground-verify · normalize/UnitRegistry · review UI · TaskPack loader |

---

## 8. Build order (revised)

- **V0** — SourceDoc + markdown-table ingest; record-centric extract (one pack);
  **ground-verify**; declarative validate; jsonl/CSV export. *(grounding from day 1)*
- **V1** — UnitRegistry + lnRR; Streamlit review with verifiable-signal triage;
  cache; review log feeding examples.
- **V2** — TaskPack loader generating the record model from `fields.yaml`; second
  pack (medical RCT binary, or psych continuous) to prove generality.
- **V3** — PDF ingest backends (PyMuPDF/MinerU/GROBID) producing SourceDoc; table
  localization; batch.
- **V4** — metafor / Python effect-size export package; forest plots.

---

## 9. One-line positioning
Records are the primitive; evidence is verified, not just stored; units and effect
sizes are declared layers; domain knowledge lives entirely in a versioned
TaskPack — so the same core serves N2O today and RCTs tomorrow.
