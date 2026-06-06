"""Command-line interface for metaextract.

Examples
--------
Extract every PDF in a folder to a tidy CSV::

    metaextract run --input data/sample_papers --out data/outputs/extracted.csv

Evaluate a run against hand-extracted ground truth::

    metaextract eval --pred data/outputs/extracted.csv \\
        --truth eval/ground_truth/truth.csv
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metaextract")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Extract data from a folder of PDFs.")
    p_run.add_argument("--input", required=True, help="Folder containing PDFs.")
    p_run.add_argument("--out", required=True, help="Output CSV path.")
    p_run.add_argument("--model", default=None, help="Gemini model id.")
    p_run.add_argument(
        "--cache", default=None, help="Optional dir to cache per-paper JSON."
    )

    p_eval = sub.add_parser("eval", help="Score predictions vs. ground truth.")
    p_eval.add_argument("--pred", required=True, help="Predicted CSV.")
    p_eval.add_argument("--truth", required=True, help="Ground-truth CSV.")
    p_eval.add_argument("--tol", type=float, default=0.05, help="Rel. tolerance.")
    p_eval.add_argument("--report", default=None, help="Optional JSON report path.")

    args = parser.parse_args(argv)

    if args.command == "run":
        from .extractor import DEFAULT_MODEL
        from .pipeline import run_folder

        run_folder(
            args.input,
            args.out,
            model=args.model or DEFAULT_MODEL,
            cache_dir=args.cache,
        )
        return 0

    if args.command == "eval":
        from .evaluate import evaluate, print_report

        report = evaluate(args.pred, args.truth, rel_tol=args.tol)
        print_report(report)
        if args.report:
            import json
            from pathlib import Path

            Path(args.report).write_text(json.dumps(report, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
