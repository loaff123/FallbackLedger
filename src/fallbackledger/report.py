"""Passive, streaming serializers for immutable analysis outputs."""

import csv
import html
import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from pathlib import Path

from .models import MethodResult

REPORT_FILES = (
    "validation.json",
    "replay.json",
    "replay.csv",
    "summary.json",
    "metrics.csv",
    "cohorts.csv",
    "summary.txt",
    "report.html",
)
METRIC_COLUMNS = (
    "scenario_id",
    "subject_kind",
    "subject_id",
    "metric",
    "cohort_id",
    "target",
    "n",
    "planned_n",
    "value",
    "mcse",
    "mcse_reason",
    "formula_id",
    "warnings",
    "diagnostic",
    "orientation",
    "left",
    "right",
    "analyzed_cases",
)
REPLAY_COLUMNS = (
    "scenario_id",
    "case_id",
    "policy_id",
    "state",
    "reason",
    "selected_method",
    "source_record_id",
    "fallback_depth",
    "estimate",
    "lower",
    "upper",
    "route",
)
COHORT_COLUMNS = (
    "scenario_id",
    "cohort_id",
    "requirement",
    "members",
    "case_id",
    "included",
    "exclusions",
)


def _default(value):
    if is_dataclass(value):
        result = {field.name: getattr(value, field.name) for field in fields(value)}
        if isinstance(value, MethodResult):
            for key in ("lower", "upper"):
                if result[key] is not None and math.isinf(result[key]):
                    result[key] = "inf" if result[key] > 0 else "-inf"
        return result
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def dumps(value):
    return json.dumps(
        value,
        default=_default,
        allow_nan=False,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def metadata(validated):
    provenance = dict(validated.provenance)
    return dict(
        schema_version=1,
        tool_version="0.1.0",
        study_id=validated.spec.study_id,
        canonical_digest=validated.canonical_digest,
        input_bytes={k: v for k, v in provenance.items() if k.endswith("_sha256")},
        input_paths={k: v for k, v in provenance.items() if k.endswith("_path")},
        assumptions=validated.spec.assumptions,
    )


def protected_inputs(validated):
    return tuple(Path(v) for k, v in validated.provenance if k.endswith("_path"))


def check_destinations(paths, inputs=(), overwrite=False):
    paths = tuple(Path(p) for p in paths)
    inputs = tuple(Path(p) for p in inputs)
    for i, path in enumerate(paths):
        for source in inputs:
            if path.resolve() == source.resolve() or (
                path.exists() and source.exists() and os.path.samefile(path, source)
            ):
                raise ValueError(
                    f"Output {path} aliases input {source}; inputs cannot be overwritten"
                )
        for other in paths[:i]:
            if path.resolve() == other.resolve() or (
                path.exists() and other.exists() and os.path.samefile(path, other)
            ):
                raise ValueError(f"Output paths alias each other: {path}, {other}")
        if path.exists() and (not overwrite or not path.is_file()):
            raise ValueError(
                f"Output exists: {path}; use --overwrite for existing files"
            )
        if path.is_symlink() and not path.exists():
            raise ValueError(f"Output is a dangling symlink: {path}")
    return paths


@contextmanager
def output_stream(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            yield stream
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    with output_stream(path) as stream:
        json.dump(
            value,
            stream,
            default=_default,
            allow_nan=False,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        stream.write("\n")


def validation_document(report):
    valid = report.validated
    return dict(
        valid=valid is not None,
        issues=report.issues,
        canonical_digest=valid.canonical_digest if valid else None,
        planned_cases=len(valid.cases) if valid else None,
        observed_records=len(valid.results) if valid else None,
    )


def replay_document(validated, replayed):
    return dict(
        metadata=metadata(validated),
        canonical_digest=replayed.canonical_digest,
        outcomes=replayed.outcomes,
    )


def summary_document(validated, summary):
    return dict(metadata=metadata(validated), **_default(summary))


def write_replay_csv(path, replayed):
    with output_stream(path) as stream:
        writer = csv.DictWriter(stream, fieldnames=REPLAY_COLUMNS)
        writer.writeheader()
        for row in replayed.outcomes:
            selected = row.selected
            d = {
                key: getattr(row, key)
                for key in (
                    "scenario_id",
                    "case_id",
                    "policy_id",
                    "state",
                    "reason",
                    "fallback_depth",
                )
            }
            d.update(
                selected_method=selected.method_id if selected else None,
                source_record_id=selected.source_record_id if selected else None,
                estimate=selected.estimate if selected else None,
                lower=selected.lower if selected else None,
                upper=selected.upper if selected else None,
                route=dumps(row.route),
            )
            writer.writerow(d)


def write_metrics_csv(path, summary):
    with output_stream(path) as stream:
        writer = csv.DictWriter(stream, fieldnames=METRIC_COLUMNS)
        writer.writeheader()
        for row in summary.metrics:
            d = _default(row)
            subject = d.pop("subject")
            d.update(subject_kind=subject.kind, subject_id=subject.id)
            for key in ("cohort_id", "warnings", "left", "right"):
                d[key] = dumps(d[key])
            writer.writerow(d)


def write_cohorts_csv(path, summary):
    with output_stream(path) as stream:
        writer = csv.DictWriter(stream, fieldnames=COHORT_COLUMNS)
        writer.writeheader()
        for cohort in summary.cohorts:
            common = dict(
                scenario_id=cohort.scenario_id,
                cohort_id=dumps(cohort.id),
                requirement=cohort.requirement,
                members=dumps(cohort.members),
            )
            for row in cohort.rows:
                writer.writerow(
                    dict(
                        common,
                        case_id=row.case.case_id,
                        included=str(row.included).lower(),
                        exclusions=dumps(row.exclusions),
                    )
                )


def _label(subject):
    return subject.kind + ":" + subject.id


def write_text(path, validated, summary):
    with output_stream(path) as stream:
        stream.write(
            f"FallbackLedger: {validated.spec.study_id}\nEstimand: {validated.spec.estimand_label} ({validated.spec.scale})\n\n"
        )
        for scenario in validated.spec.scenarios:
            stream.write(
                f"Declared scenario truth: {scenario.id} = {scenario.truth!r}\n"
            )
        if validated.spec.nominal_interval_level is not None:
            stream.write(
                f"Nominal interval level: {validated.spec.nominal_interval_level!r}\n"
            )
        stream.write("\n")
        for count in summary.counts:
            if count.requirement == "point":
                stream.write(
                    f"{count.scenario_id} {_label(count.subject)}: usable {count.usable_cases}/{count.planned_cases}; unresolved {count.unresolved_cases}; explicit failure {count.explicit_failure_cases}; exhausted {count.exhausted_cases}; inapplicable {count.inapplicable_cases}\n"
                )
        stream.write("\nMetrics (each line names its cohort and denominator):\n")
        for row in summary.metrics:
            value = "unavailable" if row.value is None else repr(row.value)
            mcse = (
                "unavailable: " + str(row.mcse_reason)
                if row.mcse is None
                else repr(row.mcse)
            )
            stream.write(
                f"{row.scenario_id} {_label(row.subject)} {row.metric} = {value}; MCSE {mcse}; n={row.n}/{row.planned_n}; cohort={dumps(row.cohort_id)}; target={row.target}"
            )
            if row.orientation:
                stream.write(
                    "; "
                    + _label(row.left)
                    + " minus "
                    + _label(row.right)
                    + " ("
                    + row.orientation
                    + ")"
                )
            if row.warnings or row.diagnostic:
                stream.write("; diagnostics=" + dumps((row.warnings, row.diagnostic)))
            stream.write("\n")
        stream.write("\nAssumptions and limits:\n")
        for note in summary.warnings:
            stream.write("- " + note + "\n")
        stream.write("Declarations: " + dumps(summary.assumptions) + "\n")


def write_html(path, validated, replayed, summary):
    def escape(value):
        return html.escape(str(value), quote=True)

    def table_row(stream, values, header=False):
        tag = "th" if header else "td"
        stream.write(
            "<tr>"
            + "".join("<" + tag + ">" + escape(v) + "</" + tag + ">" for v in values)
            + "</tr>\n"
        )

    with output_stream(path) as stream:
        stream.write(
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>FallbackLedger report</title><style>body{font:15px system-ui,sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem;color:#182632}h1,h2{color:#143b51}table{border-collapse:collapse;width:100%;font-size:13px;margin:1rem 0}th,td{border:1px solid #ccd5db;padding:.45rem;text-align:left;vertical-align:top;overflow-wrap:anywhere;white-space:pre-wrap}th{background:#eaf1f5}details{margin:1rem 0;overflow:auto}summary{font-weight:600;cursor:pointer}.note{background:#fff5d8;padding:1rem}.wide{overflow:auto}</style><body>'
        )
        stream.write(
            "<h1>"
            + escape(validated.spec.study_id)
            + "</h1><p>"
            + escape(validated.spec.description)
            + "</p><p>Estimand: "
            + escape(validated.spec.estimand_label)
            + "; scale: "
            + escape(validated.spec.scale)
            + "</p>"
        )
        for scenario in validated.spec.scenarios:
            stream.write(
                "<p>Declared scenario truth: "
                + escape(scenario.id)
                + " = "
                + escape(repr(scenario.truth))
                + "</p>"
            )
        if validated.spec.nominal_interval_level is not None:
            stream.write(
                "<p>Nominal interval level: "
                + escape(repr(validated.spec.nominal_interval_level))
                + "</p>"
            )
        stream.write(
            '<div class="note"><strong>Read the cohort before the number.</strong><ul>'
        )
        for note in summary.warnings:
            stream.write("<li>" + escape(note) + "</li>")
        stream.write(
            "</ul><p>Declared assumptions: "
            + escape(dumps(summary.assumptions))
            + '</p></div><h2>Observed denominators</h2><div class="wide"><table>'
        )
        table_row(
            stream,
            [
                "Scenario",
                "Subject",
                "Required output",
                "Planned",
                "Observed records",
                "Usable",
                "Explicit failure",
                "Explicit unavailable",
                "Unresolved",
                "Inapplicable",
                "Exhausted",
            ],
            True,
        )
        for c in summary.counts:
            table_row(
                stream,
                [
                    c.scenario_id,
                    _label(c.subject),
                    c.requirement,
                    c.planned_cases,
                    c.observed_records,
                    c.usable_cases,
                    c.explicit_failure_cases,
                    c.explicit_unavailable_cases,
                    c.unresolved_cases,
                    c.inapplicable_cases,
                    c.exhausted_cases,
                ],
            )
        stream.write(
            '</table></div><h2>Metrics and paired contrasts</h2><div class="wide"><table>'
        )
        table_row(
            stream,
            [
                "Scenario",
                "Subject",
                "Metric",
                "Cohort",
                "Target",
                "n / planned",
                "Value",
                "MCSE",
                "Diagnostics",
            ],
            True,
        )
        for r in summary.metrics:
            table_row(
                stream,
                [
                    r.scenario_id,
                    _label(r.subject),
                    r.metric
                    + (
                        " "
                        + _label(r.left)
                        + " minus "
                        + _label(r.right)
                        + " ("
                        + r.orientation
                        + ")"
                        if r.orientation
                        else ""
                    ),
                    dumps(r.cohort_id),
                    r.target,
                    f"{r.n} / {r.planned_n}",
                    r.value if r.value is not None else "unavailable",
                    r.mcse if r.mcse is not None else r.mcse_reason,
                    dumps((r.warnings, r.diagnostic)),
                ],
            )
        stream.write(
            "</table></div><p>MCSE formula: sample standard deviation of within-case contributions / sqrt(n). Contrasts use left-minus-right contributions on the identical declared cohort.</p><h2>Exact policy routes</h2><details><summary>All "
            + str(len(replayed.outcomes))
            + " planned case-policy outcomes</summary><table>"
        )
        table_row(
            stream,
            [
                "Scenario",
                "Case",
                "Policy",
                "State / reason",
                "Selected method / source",
                "Fallback depth",
                "Visited route and producer diagnostics",
            ],
            True,
        )
        for r in replayed.outcomes:
            table_row(
                stream,
                [
                    r.scenario_id,
                    r.case_id,
                    r.policy_id,
                    r.state + " / " + r.reason,
                    (r.selected.method_id + " / " + r.selected.source_record_id)
                    if r.selected
                    else "",
                    r.fallback_depth if r.fallback_depth is not None else "",
                    dumps(r.route),
                ],
            )
        stream.write("</table></details><h2>Exact cohort membership</h2>")
        for c in summary.cohorts:
            stream.write(
                "<details><summary>"
                + escape(c.scenario_id + " " + dumps(c.id))
                + "; "
                + str(sum(r.included for r in c.rows))
                + " / "
                + str(len(c.rows))
                + " included</summary><p>Requirement: "
                + escape(c.requirement)
                + "; named members: "
                + escape(dumps(c.members))
                + "</p><table>"
            )
            table_row(
                stream, ["Case", "Included", "All excluded members and reasons"], True
            )
            for r in c.rows:
                table_row(
                    stream,
                    [r.case.case_id, str(r.included).lower(), dumps(r.exclusions)],
                )
            stream.write("</table></details>")
        stream.write(
            "<h2>Provenance</h2><p>"
            + escape(dumps(metadata(validated)))
            + "</p><p>Hashes identify supplied bytes and declarations; they do not establish authenticity, independence, or estimator quality.</p></body></html>\n"
        )


def write_report(validated, replayed, summary, destination, overwrite=False, issues=()):
    if (
        validated.canonical_digest != replayed.canonical_digest
        or validated.canonical_digest != summary.canonical_digest
    ):
        raise ValueError("Report objects have mismatched canonical digests")
    destination = Path(destination)
    paths = check_destinations(
        [destination / name for name in REPORT_FILES],
        protected_inputs(validated),
        overwrite,
    )
    destination.mkdir(parents=True, exist_ok=True)
    write_json(
        paths[0],
        dict(
            valid=True,
            issues=issues,
            canonical_digest=validated.canonical_digest,
            planned_cases=len(validated.cases),
            observed_records=len(validated.results),
        ),
    )
    write_json(paths[1], replay_document(validated, replayed))
    write_replay_csv(paths[2], replayed)
    write_json(paths[3], summary_document(validated, summary))
    write_metrics_csv(paths[4], summary)
    write_cohorts_csv(paths[5], summary)
    write_text(paths[6], validated, summary)
    write_html(paths[7], validated, replayed, summary)
    return paths
