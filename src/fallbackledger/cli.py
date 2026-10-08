"""Command-line workflow for trusted local study exports."""

import argparse
import sys
from pathlib import Path

from .io import load_inputs, load_json, map_results, read_records
from .replay import replay
from .report import (
    check_destinations,
    dumps,
    output_stream,
    replay_document,
    validation_document,
    write_json,
    write_replay_csv,
    write_report,
)
from .summarize import summarize


def _parser():
    parser = argparse.ArgumentParser(
        prog="fallbackledger",
        description="Replay declared fallback policies and report exact simulation cohorts.",
    )
    parser.add_argument("--version", action="version", version="fallbackledger 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "replay", "summarize"):
        sub = commands.add_parser(name)
        for input_name in ("study", "planned", "results"):
            sub.add_argument("--" + input_name, type=Path, required=True)
        sub.add_argument("--mapping", type=Path)
        sub.add_argument("--overwrite", action="store_true")
        sub.add_argument(
            "--require-complete",
            action="store_true",
            help="Exit 3 if any requested metric, cohort, or paired contrast is incomplete.",
        )
        if name == "summarize":
            sub.add_argument("--output-dir", type=Path, required=True)
        else:
            sub.add_argument("--out", type=Path, required=True)
        if name == "replay":
            sub.add_argument("--csv", type=Path)
    sub = commands.add_parser("import-results")
    sub.add_argument("--input", type=Path, required=True)
    sub.add_argument("--mapping", type=Path, required=True)
    sub.add_argument("--out", type=Path, required=True)
    sub.add_argument("--overwrite", action="store_true")
    return parser


def _incomplete(validated, summary):
    if any(not row.included for cohort in summary.cohorts for row in cohort.rows):
        return True
    return any(row.n != row.planned_n or row.value is None for row in summary.metrics)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "import-results":
            check_destinations([args.out], [args.input, args.mapping], args.overwrite)
            mapping = load_json(args.mapping)
            map_results((), mapping)
            rows = map_results(
                read_records(
                    args.input, required_columns=mapping.get("columns", {}).values()
                ),
                mapping,
            )
            with output_stream(args.out) as stream:
                for row in rows:
                    stream.write(dumps(row) + "\n")
            print(
                f"Imported {len(rows)} records to {args.out}; validate against the study and planned grid next."
            )
            return 0
        inputs = [args.study, args.planned, args.results] + (
            [args.mapping] if args.mapping else []
        )
        if args.command != "summarize":
            outputs = [args.out] + (
                [args.csv] if args.command == "replay" and args.csv else []
            )
            check_destinations(outputs, inputs, args.overwrite)
        report = load_inputs(args.study, args.planned, args.results, args.mapping)
        if args.command == "validate":
            write_json(args.out, validation_document(report))
        if not report.validated:
            for issue in report.issues:
                print(
                    f"{issue.severity} {issue.code} {issue.path}: {issue.message}",
                    file=sys.stderr,
                )
            return 2
        validated = report.validated
        replayed = None
        summary = None
        if args.command in ("replay", "summarize") or args.require_complete:
            replayed = replay(validated)
        if args.command == "replay":
            write_json(args.out, replay_document(validated, replayed))
            if args.csv:
                write_replay_csv(args.csv, replayed)
        if args.command == "summarize" or args.require_complete:
            summary = summarize(validated, replayed)
        if args.command == "summarize":
            write_report(
                validated,
                replayed,
                summary,
                args.output_dir,
                args.overwrite,
                report.issues,
            )
        print(
            f"{args.command}: {len(validated.cases)} planned cases; {len(validated.results)} observed method records."
        )
        for issue in report.issues:
            print(f"{issue.severity} {issue.code}: {issue.message}", file=sys.stderr)
        if args.require_complete and _incomplete(validated, summary):
            print(
                "Incomplete: requested outputs are not usable on every planned case; inspect conditional targets and diagnostics.",
                file=sys.stderr,
            )
            return 3
        return 0
    except (ValueError, TypeError, OSError, OverflowError) as error:
        print(f"fallbackledger: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
