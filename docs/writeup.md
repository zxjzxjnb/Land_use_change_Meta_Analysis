# Automating data extraction for a land-use-change soil meta-analysis

*A writeup of the problem, the design decisions, and the measured results.*

## The problem

A meta-analysis synthesises many primary studies into one quantitative answer —
here, *how does changing land use / management affect soil properties such as
organic carbon?* The statistical machinery (effect sizes, mixed models) is
standard. The bottleneck is upstream and unglamorous: a human reading each of
hundreds of papers and transcribing, by hand, the treatment mean, control mean,
their standard deviations, and sample sizes — usually buried in a results table,
sometimes only in a figure — plus the study-level context (climate, soil type,
duration) needed to explain why studies disagree.

At ~20–40 minutes per paper this is the part that takes weeks, and it is exactly
the kind of structured-but-tedious reading that modern multimodal LLMs are good
at. The goal of this project was not "can an LLM read a paper" (obviously yes)
but **"can a pipeline extract this data accurately enough to be useful, and can
I prove it?"**

## First prototype, and why it wasn't enough

The first version was a single notebook: PyPDF2 → text → one Gemini call → CSV.
It worked on one hand-picked paper and looked fine in a demo. Three things made
it unfit for real use, and each drove a design change:

| Problem in the prototype | Why it matters | Fix |
| --- | --- | --- |
| `PyPDF2` text + `re.sub(r"\s+"," ",text)` | Collapses table rows/columns — destroys the means/SDs, which live in tables | Send the **raw PDF** to Gemini's native document understanding |
| `lstrip("```json")` to clean output | `lstrip` strips *characters*, not a prefix — silently corrupts some outputs | **Structured output** via a Pydantic `response_schema`; no string surgery |
| `gemini-1.0-pro-vision`, hard-coded | Model is retired; also only ever fed text, so no vision benefit | Current, **configurable** model; PDF passed as a document part |
| One file at a time, manual filename | A meta-analysis is hundreds of papers | **Batch** over a folder, per-paper failure isolation, caching |
| No checks on the numbers | LLMs transpose digits and swap columns; silent errors poison the analysis | **Validation layer** with `qa_flags` |
| No accuracy measurement | "It works" is unfalsifiable | **Evaluation** against hand-extracted ground truth |

## Design

The pipeline is four stages (see the diagram in the [README](../README.md)):

1. **Extract** — `extractor.py` sends the PDF bytes to Gemini with a system
   instruction encoding the domain rules (report numbers verbatim, pair every
   treatment with a control, cite where each value was read) and a JSON schema
   the response must satisfy.
2. **Validate** — `validator.py` screens each data point: non-negative SDs,
   positive-integer sample sizes, plausible pH/temperature/precipitation,
   distinct treatment vs. control, and an outlier coefficient-of-variation
   check that catches mean/SD column swaps. Issues become human-readable flags,
   not deletions.
3. **Flatten** — `flatten.py` denormalises the nested result into one row per
   paired data point, ready for an effect-size calculation.
4. **Evaluate** — `evaluate.py` aligns the output with a gold-standard table on
   a study + variable + treatment/control key and reports row recall/precision
   and per-field numeric recovery within a tolerance.

A deliberate principle throughout: **keep a human in the loop where it is cheap
and valuable.** The tool's job is to do 95% of the transcription and to make the
remaining 5% — the flagged, uncertain rows — easy to find.

## Evaluation

*Methodology.* Ground truth is the subset of papers that were extracted by hand.
Each predicted data point is matched to its ground-truth counterpart; a numeric
cell counts as recovered if it is within ±5% of the true value (sample sizes
must match exactly). I report:

- **Row recall / precision** — did the pipeline find the right data points?
- **Per-field recovery** — of the values it found, how many are correct?
- **Mean absolute error** — how wrong are the misses?

<!-- Fill in from `metaextract eval ... --report report.json`. -->
*Results.* _To be completed on the held-out ground-truth set._

| | recall | precision |
| --- | --- | --- |
| Rows | _TBD_ | _TBD_ |

| field | recovery (±5%) | MAE |
| --- | --- | --- |
| mean_t | _TBD_ | _TBD_ |
| mean_c | _TBD_ | _TBD_ |
| sd_t / sd_c | _TBD_ | _TBD_ |
| n_t / n_c | _TBD_ | _TBD_ |

*Error analysis (to fill in):* which fields are hardest (typically SDs and
figure-only values), and what fraction of true errors the `qa_flags` already
caught.

## What I'd do next

- Confidence scores per value, and an active-review UI that shows the flagged
  cell next to the cropped source table.
- Figure-data extraction (digitising points from plots) as a dedicated step.
- A second-model cross-check for disagreement-based flagging.

## What this project demonstrates

End-to-end ownership of a messy real-world task: framing the problem, choosing
the right tool for the hard part (table reading), engineering for scale and
trust rather than a demo, and — the part most LLM side-projects skip —
**measuring** whether it actually works.
