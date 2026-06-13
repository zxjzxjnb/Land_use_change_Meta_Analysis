# LLM-assisted data extraction tool for Meta analysis

[![CI](https://github.com/zxjzxjnb/LLM-assisted-data-extraction-tool-for-Meta-analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/zxjzxjnb/LLM-assisted-data-extraction-tool-for-Meta-analysis/actions/workflows/ci.yml)

**Status: In Progress**

`metaextract` is a research prototype for testing whether AI-assisted workflows
can reduce the manual transcription burden in soil and land-use-change
meta-analysis. The project started as a one-shot PDF-to-CSV extractor, then
shifted toward a more conservative human-in-the-loop verification workflow:
AI helps screen papers, locate relevant evidence, and draft structured outputs;
humans confirm the values that would enter a meta-analysis.

This repository is not presented as a finished automatic extraction system. The
current codebase contains a working Python package, deterministic validation and
geometry tests, cached paper-level experiments, and a local verification cockpit
prototype. Larger-scale accuracy claims are still being evaluated.

## Why This Project Exists

Meta-analysis depends on careful manual extraction of treatment-control values:
means, standard deviations, sample sizes, experimental context, and source
provenance. Those values are often buried in tables, figure panels, captions, or
methods sections, and a silent transcription error can directly affect the
computed effect size.

This project asks a narrower engineering question:

> Can AI make the extraction workflow faster while keeping every value auditable
> against the source paper?

The current design therefore prioritizes evidence, review, and measurement over
full automation.

## Current Implementation

The repository has two related layers.

### 1. Package and CLI baseline

The original `metaextract` package supports:

- Gemini PDF input with Pydantic structured output
- typed extraction models for study metadata and treatment-control rows
- validation rules that emit `qa_flags` instead of silently dropping rows
- flattening into a tidy CSV format
- batch processing with optional JSON caching
- an evaluator for comparing predicted rows with hand-extracted ground truth

Key modules:

```text
src/metaextract/
  cli.py          Command-line interface
  extractor.py    Gemini PDF call and structured response parsing
  schema.py       Pydantic models for extraction results
  validator.py    Data-quality checks and QA flag generation
  flatten.py      Conversion from nested results to tidy CSV rows
  pipeline.py     Batch processing, retry logic, caching, and run summaries
  evaluate.py     Comparison against hand-extracted ground truth
```

### 2. Verification cockpit prototype

The newer direction is a local-first verification cockpit. Instead of trusting
the model to silently transcribe every number, the workflow emphasizes:

- deterministic PDF ingest with page, block, and word-level bounding boxes
- AI-assisted screening and location of relevant table or figure regions
- click-to-evidence review, where selected regions are rendered next to the PDF
- human-filled or human-confirmed values with source provenance
- geometry-assisted table parsing for simple table layouts
- deterministic sample-size candidate detection for common `n` statements
- cached paper runs for repeatable offline review
- **automatic progress saving** so a review can be paused and resumed across
  sessions (see below)

Records assembled in the cockpit are autosaved per paper, so closing the tab or
restarting the server does not lose work — reopening the same paper restores the
records and the bound moderators. Two files are written under `data/reviews/`
(git-ignored, local-only):

- `{study}.json` — the current draft (records + bound moderators), rewritten on
  every change and reloaded on open.
- `{study}.log.csv` — an append-only audit trail (add / accept / delete, each
  with a UTC timestamp) for review history.

Related files:

```text
app/cockpit.py                 Streamlit verification cockpit
src/metaextract/ingest.py       PDF -> SourceDoc with geometry
src/metaextract/sourcedoc.py    addressable source-document model
src/metaextract/highlight.py    value-to-bounding-box matching
src/metaextract/locate.py       AI-assisted screen + locate stage
src/metaextract/records.py      located-region and extraction-slot models
src/metaextract/reviewstore.py  durable draft + audit log (resume across sessions)
src/metaextract/tabular.py      geometry-assisted table pairing
src/metaextract/sampling.py     deterministic sample-size candidates
src/metaextract/render.py       PDF page rendering with highlights
```

## Evaluation Status

Evaluation is ongoing and should be read conservatively.

- Deterministic unit tests cover validation, location resolution, highlighting,
  sampling candidates, and table-geometry helpers.
- Cached P1-P12 paper experiments are included for development and analysis.
- One clean table paper has been used as a smoke test for geometry-assisted
  pairing against hand extraction.
- Corpus-level location and value checks exist in `scripts/benchmark.py`,
  `scripts/bench_values.py`, and `scripts/eval_against_gt.py`.
- The current evidence supports the human-in-the-loop direction, not a claim
  that the system can fully automate extraction across all paper formats.

The main open problem is generalization across diverse table and figure formats.
Simple normal tables can benefit from geometry-assisted pairing; transposed,
nested, or figure-heavy papers still require manual confirmation or digitization.

## Documentation Status

| Document | Status | How to read it |
| --- | --- | --- |
| [README.md](README.md) | Current public overview | Best entry point for the repository's present scope and limitations |
| [docs/writeup.md](docs/writeup.md) | Draft project writeup | Explains the motivation and design, but the results section still contains TBD placeholders |
| [docs/ARCHITECTURE_v2.md](docs/ARCHITECTURE_v2.md) | Design proposal | A schema-driven next-version architecture; not a statement of fully shipped code |
| [docs/ARCHITECTURE_v3.md](docs/ARCHITECTURE_v3.md) | Active cockpit blueprint | Most closely matches the current product direction and implemented prototype modules |

## Installation

```bash
pip install -e .
```

For development, install optional dependencies:

```bash
pip install -e ".[dev]"
```

Create a `.env` file or export the required environment variable for Gemini:

```bash
export GOOGLE_API_KEY="your-api-key"
```

For Vertex AI, configure the relevant Google Cloud environment variables:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="your-project"
export GOOGLE_CLOUD_LOCATION="us-central1"
```

## Usage

Run the baseline extractor over a folder of PDFs:

```bash
metaextract run \
  --input data/sample_papers \
  --out data/outputs/extracted.csv \
  --cache data/outputs/cache
```

Evaluate predicted rows against hand-extracted ground truth:

```bash
metaextract eval \
  --pred data/outputs/extracted.csv \
  --truth eval/ground_truth/truth.csv \
  --tol 0.05 \
  --report data/outputs/evaluation_report.json
```

Launch the local cockpit prototype after installing development dependencies:

```bash
streamlit run app/cockpit.py
```

The cockpit reads cached paper artifacts from `data/cache/`. To refresh a cached
study from `data/sample_papers/{study}.pdf`, use:

```bash
python scripts/prepare_paper.py P1
```

## Benchmark and Development Commands

Run deterministic tests:

```bash
pytest
```

Run location-oriented corpus checks over cached papers:

```bash
python scripts/benchmark.py
```

Run value-recall checks for table-like cached papers:

```bash
python scripts/bench_values.py
```

Run the one-paper ground-truth comparison script:

```bash
python scripts/eval_against_gt.py
```

These scripts are evaluation scaffolding, not a final benchmark suite. Their
results should be interpreted together with the cache coverage, paper type mix,
and known anomalies described in the architecture notes.

## Target Extraction Fields

The baseline schema and cockpit export logic are designed around:

- study metadata, including first author and publication year
- location, climate, and soil background moderators
- experimental design information
- paired treatment-control response variables
- treatment mean, SD, and sample size
- control mean, SD, and sample size
- source provenance such as table, figure, page, block, or evidence span
- QA flags or review status for risky rows

The intended downstream output is a reviewed, meta-analysis-ready table rather
than raw unverified model output.

## Changing target metrics (task packs)

Which metrics the locate-and-review workflow looks for is **not hard-coded** —
it lives in an editable YAML *task pack* under `data/taskpacks/`. Researchers
swap target metrics by editing that file alone, no code change:

```yaml
domain: soil_C_fractions_landuse
target_variables:
  - name: soil organic carbon        # canonical name (export column + cross-paper match)
    aliases: [SOC, TOC, organic carbon]   # synonyms papers use; normalized back to `name`
    unit_hint: g/kg
  - name: MBC
    aliases: [microbial biomass carbon]
moderators:
  - mean annual temperature
  - soil type
```

Workflow:

- **Bootstrap a pack from an existing Excel:** `python scripts/export_taskpack.py`
  imports the column vocabulary into `data/taskpacks/soil_C_fractions.yaml` as a
  starting point to edit.
- **Add aliases / units, or add/remove metrics:** edit the YAML.
- **Apply it:** `python scripts/prepare_paper.py P1` loads the default pack;
  point at another with `METAEXTRACT_TASKPACK=path/to/pack.yaml`.
- **Apply it to batch extraction guidance:** `metaextract run --taskpack
  data/taskpacks/soil_C_fractions.yaml --input ... --out ...` passes the same
  domain, canonical names, aliases, and unit hints into the extraction prompt.
- Adding or removing a metric requires a fresh `prepare_paper` locate pass for
  cached cockpit papers; otherwise the cockpit will still show the older cached
  located regions.

`TaskSpec.from_yaml()` / `to_yaml()` load and save packs programmatically, and a
bare string is still accepted wherever a metric is expected (so existing
GT-derived specs keep working).

Note: `--taskpack` constrains the model prompt and cache identity, but the
auto-extract path (`metaextract run` / `run_folder`) still emits to the fixed,
soil-specific schema in `schema.py`. So on that path, target-variable names from
any domain are honored, but task pack **moderators outside the soil schema are
not captured** — they are omitted from the prompt rather than silently dropped
(see `SCHEMA_NATIVE_DOMAINS` in `extractor.py`). The locate → cockpit path is
fully domain-general; generalizing the auto-extract schema is future work.

## Analysis families (which numbers a record holds)

Different meta-analysis designs collect different numbers per data point. A task
pack picks one with `analysis_family`; the cockpit builds its whole input form
(the slots, the auto-pairing fast path, the n picker, the export columns) from
that choice — nothing is hard-coded per design. Families are defined in
`src/metaextract/families.py`.

```yaml
domain: my_meta
analysis_family: continuous_two_arm   # default — omit to get this
target_variables:
  - name: soil organic carbon
    aliases: [SOC, TOC]
```

| Family | Per-record fields | Effect sizes | Status |
| --- | --- | --- | --- |
| `continuous_two_arm` (default) | `mean/sd/n` per arm (`Xc Sc Nc Xe Se Ne`) | lnRR, SMD / Hedges' g | **Validated** on the soil/land-use corpus (P1–P12) |
| `binary_two_arm` | `events/total` per arm | OR, RR | ⚠️ **Experimental — structurally supported, never tested on real binary-outcome papers** |

> ⚠️ **`binary_two_arm` and any future non-default family are untested.** The
> form renders and records export, but locate accuracy, the sample-size finder
> (it only recognizes "replicate/triplicate" wording, which medical/clinical
> papers don't use), and the validators were only ever measured on continuous
> soil-ecology papers. **If you try a non-default family on real papers, please
> open an issue with what worked and what didn't** — that feedback is what turns
> "structurally supported" into "validated". Omitting `analysis_family` keeps the
> validated continuous behavior unchanged.

## Roadmap

- tighten the cockpit export path for reviewed records
- separate paper-level moderators from record-level values until a human binds
  them
- add more explicit review logs and provenance reports
- improve support for figure digitization handoff
- expand evaluation beyond smoke tests into a larger curated ground-truth set
- report measured location recall, value recovery, correction rate, and review
  time per verified record

## Project Boundary

This project is a practical extraction and verification tool, not a full
meta-analysis platform. It does not replace effect-size modeling, statistical
synthesis, or expert review. Its goal is to make the evidence-gathering stage
faster, more inspectable, and easier to audit.

## License

MIT. See [LICENSE](LICENSE).
