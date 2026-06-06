# metaextract

LLM-assisted data extraction for ecological meta-analysis.

`metaextract` turns research-paper PDFs into a structured, analysis-ready table
for land-use-change soil meta-analysis. It focuses on the slowest part of the
workflow: extracting treatment/control means, standard deviations, sample sizes,
and study-level moderators from tables, figures, and text.

The project is designed as a human-in-the-loop extraction pipeline rather than a
one-shot demo. It uses native PDF understanding, a typed output schema, sanity
checks, cached batch processing, and an evaluation script for comparing model
outputs against hand-extracted ground truth.

## Why This Project Exists

Meta-analysis usually depends on a large amount of manual transcription. A
researcher reads each paper, finds treatment and control groups, records
`mean`, `SD`, and `n`, and repeats the same process across hundreds of studies.
That work is slow, error-prone, and difficult to audit.

This project asks a narrower and more useful question:

> Can an LLM-assisted pipeline extract most of the structured data, flag risky
> rows for human review, and measure its own agreement with manual extraction?

## Core Workflow

```text
PDF folder
   |
   v
Gemini native PDF understanding
   |
   v
Pydantic structured output schema
   |
   v
ExtractionResult objects
   |
   v
Validation and QA flags
   |
   v
Tidy CSV
   |
   v
Evaluation against hand-extracted ground truth
```

## What It Extracts

For each paper, the pipeline extracts:

- Study metadata, including first author and publication year
- Location, climate, and soil background moderators
- Experimental design information
- One row per paired treatment-control response variable
- Treatment mean, SD, and sample size
- Control mean, SD, and sample size
- Source provenance, such as table, figure, sampling depth, and measurement year
- QA flags for rows that need manual review

The output is denormalized into a single CSV so it can be used directly in an
effect-size workflow.

## Architecture

The package is organized around small, testable modules:

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

### Extraction

`extractor.py` sends the full PDF bytes to Gemini as a document input. This
preserves table and figure context better than flattening pages into plain text.
The model is instructed to return JSON that follows the Pydantic schema defined
in `schema.py`.

### Schema

`schema.py` defines the typed contract for the extraction result:

- `StudyInfo`
- `Moderators`
- `Location`
- `Climate`
- `SoilBackground`
- `ExperimentalDesign`
- `ResponseVariable`
- `ExtractionResult`

The schema is used both as the model response format and as the validation layer
for returned JSON.

### Validation

`validator.py` adds a trust layer after extraction. It flags issues such as:

- Missing treatment or control means
- Negative standard deviations
- Non-positive or non-integer sample sizes
- Implausible pH, temperature, or precipitation values
- Treatment and control groups that are identical
- Suspiciously high coefficient of variation

Rows are not silently dropped. They are emitted with `qa_flags` so a human
reviewer can focus on the most risky records.

### Flattening

`flatten.py` converts nested extraction results into a tidy long-format table:
one row per paired treatment-control data point, with study-level moderators
repeated across rows.

### Batch Pipeline

`pipeline.py` processes every PDF in an input folder. It supports:

- Per-paper failure isolation
- Simple retry logic
- Optional JSON caching
- A combined output CSV
- A `run_summary.json` file with success, failure, row, and QA counts

### Evaluation

`evaluate.py` compares predicted CSV rows against a manually extracted
ground-truth CSV. It reports:

- Row recall
- Row precision
- Numeric field recovery within a relative tolerance
- Per-field mean absolute error

This is the key step that turns the project from an LLM demo into a measurable
extraction system.

## Installation

```bash
pip install -e .
```

Create a `.env` file or export the required environment variables:

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

Run extraction over a folder of PDFs:

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

Use the package from Python:

```python
from metaextract import extract_from_pdf

result = extract_from_pdf("paper.pdf")
for row in result.response_variables:
    print(row.variable_name, row.mean_t, row.mean_c)
```

## Ground-Truth Evaluation Plan

A rigorous evaluation should use a manually extracted `truth.csv` with the same
row structure as the model output. Recommended columns include:

```text
source_file
first_author
year
site_name
sampling_depth_cm
measurement_year
variable_name
treatment_group
control_group
mean_t
sd_t
n_t
mean_c
sd_c
n_c
source
```

Recommended reporting:

- Row recall and precision for paired data-point discovery
- Per-field recovery for `mean_t`, `sd_t`, `n_t`, `mean_c`, `sd_c`, and `n_c`
- Exact-match accuracy for sample sizes
- Relative-error tolerance for continuous numeric values
- Error analysis by source type, especially table-sourced vs figure-sourced data
- QA-flag recall and precision, to measure whether validation catches risky rows
- Runtime and human review time per paper

## Current Status

The repository contains the extraction pipeline, schema, validation layer,
flattening logic, batch runner, CLI, and deterministic unit tests. The next most
important milestone is to run the system on a manually extracted ground-truth
set and publish the evaluation metrics.

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

The current tests cover deterministic validation and flattening logic without
calling the Gemini API.

## Limitations

- Figure-only values are harder to recover reliably than table values.
- The pipeline supports human review; it should not be treated as a fully
  automatic replacement for expert extraction.
- Accuracy claims depend on the ground-truth set and matching strategy.
- Costs and runtime depend on PDF length, paper count, model choice, and cache
  usage.

## Roadmap

- Add a stronger one-to-one row matching strategy in evaluation
- Publish metrics on a manually extracted benchmark set
- Add tests for evaluation and batch pipeline behavior
- Flag figure-sourced rows explicitly for review
- Add confidence or disagreement-based checks
- Build a review UI that shows flagged rows next to their source tables or
  figures

## License

MIT. See [LICENSE](LICENSE).
