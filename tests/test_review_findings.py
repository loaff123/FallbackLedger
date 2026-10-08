"""Independent review regressions, grounded in the approved v1 contract."""

import csv
import json

import pytest

from fallbackledger import replay, summarize, validate
from fallbackledger.cli import main


def _complete_points_incomplete_common_intervals():
    study = {
        "schema_version": 1,
        "study_id": "review-common-completeness",
        "estimand": {
            "id": "theta",
            "label": "Original review quantity",
            "scale": "raw",
        },
        "scenarios": [{"id": "s", "truth": 0}],
        "methods": [{"id": m, "version": "1"} for m in ("A", "B")],
        "assumptions": {"independent_cases": True, "finite_second_moments": True},
        "metrics": ["bias"],
        "policies": [],
        "cohorts": [
            {
                "id": "both_intervals",
                "requirement": "interval",
                "members": [
                    {"kind": "method", "id": "A"},
                    {"kind": "method", "id": "B"},
                ],
            }
        ],
        "comparisons": [
            {
                "id": "A_minus_B",
                "left": {"kind": "method", "id": "A"},
                "right": {"kind": "method", "id": "B"},
                "cohort": "both_intervals",
                "metrics": ["bias"],
            }
        ],
    }
    planned = [{"scenario_id": "s", "case_id": str(i)} for i in (1, 2)]
    records = []
    for i in (1, 2):
        for method in ("A", "B"):
            estimate = i + (0.5 if method == "B" else 0)
            records.append(
                {
                    "scenario_id": "s",
                    "case_id": str(i),
                    "method_id": method,
                    "status": "ok",
                    "reason": "",
                    "estimate": estimate,
                    "interval_status": "available" if i == 1 else "not_provided",
                    "lower": 0 if i == 1 else None,
                    "upper": 3 if i == 1 else None,
                    "source_record_id": f"{i}:{method}",
                    "estimand_id": "theta",
                    "scale": "raw",
                }
            )
    return study, planned, records


def _write_inputs(path, data):
    study, planned, records = data
    s, p, r = (path / name for name in ("study.json", "planned.csv", "results.jsonl"))
    s.write_text(json.dumps(study), encoding="utf-8")
    with p.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("scenario_id", "case_id"))
        writer.writeheader()
        writer.writerows(planned)
    r.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    return ["--study", str(s), "--planned", str(p), "--results", str(r)]


@pytest.mark.parametrize("with_policy", [False, True])
def test_require_complete_includes_requested_common_metrics_and_paired_contrasts(
    tmp_path, with_policy
):
    data = _complete_points_incomplete_common_intervals()
    if with_policy:
        data[0]["policies"] = [
            {
                "id": "point",
                "methods": ["A", "B"],
                "requirement": "point",
                "inapplicable": "stop",
            }
        ]
    report = validate(*data)
    assert report.validated is not None, report.issues
    summary = summarize(report.validated, replay(report.validated))
    assert all(
        row.n == row.planned_n for row in summary.metrics if row.cohort_id[0] == "own"
    )
    contrast = next(row for row in summary.metrics if row.subject.kind == "comparison")
    assert contrast.n == 1 and contrast.planned_n == 2
    args = _write_inputs(tmp_path, data)
    output = tmp_path / "report"
    code = main(["summarize", *args, "--output-dir", str(output), "--require-complete"])
    assert (output / "summary.json").is_file(), (
        "Completeness gates must retain diagnostics"
    )
    assert code == 3, (
        "A requested common-cohort metric/contrast lacks all-planned completion"
    )


@pytest.mark.parametrize("duplicate_estimate", [False, True])
def test_canonical_jsonl_record_must_be_an_object_not_key_value_pairs(
    tmp_path, duplicate_estimate
):
    data = _complete_points_incomplete_common_intervals()
    args = _write_inputs(tmp_path, data)
    malformed = [list(row.items()) for row in data[2]]
    if duplicate_estimate:
        malformed[0].append(["estimate", 987])
    (tmp_path / "results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in malformed)
    )
    code = main(["validate", *args, "--out", str(tmp_path / "validation.json")])
    assert code == 2, (
        "JSON arrays must not be converted to objects, even if dict() would accept them"
    )


@pytest.mark.parametrize(
    "header",
    [
        "garbage",
        "scenario_id,case_id,method_id,status,reason,estimate,interval_status,lower,upper,source_record_id,estimand_id",
    ],
)
def test_empty_results_csv_still_requires_all_canonical_header_fields(tmp_path, header):
    data = _complete_points_incomplete_common_intervals()
    args = _write_inputs(tmp_path, data)
    empty = tmp_path / "empty.csv"
    empty.write_text(header + "\n")
    args[-1] = str(empty)
    assert main(["validate", *args, "--out", str(tmp_path / "validation.json")]) == 2


def test_correct_header_empty_results_csv_remains_valid_but_incomplete(tmp_path):
    data = _complete_points_incomplete_common_intervals()
    args = _write_inputs(tmp_path, data)
    empty = tmp_path / "empty.csv"
    empty.write_text(",".join(data[2][0]) + "\n")
    args[-1] = str(empty)
    assert main(["validate", *args, "--out", str(tmp_path / "validation.json")]) == 0
    report = json.loads((tmp_path / "validation.json").read_text())
    assert report["valid"] and any(
        i["code"] == "missing_records" for i in report["issues"]
    )


def test_human_readable_contrast_reports_identify_actual_left_and_right(tmp_path):
    from html.parser import HTMLParser

    from fallbackledger.report import write_report

    class Rows(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows = []
            self.current = None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.current = []

        def handle_data(self, text):
            if self.current is not None:
                self.current.append(text)

        def handle_endtag(self, tag):
            if tag == "tr" and self.current is not None:
                self.rows.append(" ".join(self.current))
                self.current = None

    data = _complete_points_incomplete_common_intervals()
    comparison = data[0]["comparisons"][0]
    comparison["id"] = "contrast_1"
    comparison["left"], comparison["right"] = comparison["right"], comparison["left"]
    validated = validate(*data).validated
    replayed = replay(validated)
    summary = summarize(validated, replayed)
    write_report(validated, replayed, summary, tmp_path / "report")
    text_line = next(
        line
        for line in (tmp_path / "report" / "summary.txt").read_text().splitlines()
        if "comparison:contrast_1" in line
    )
    parser = Rows()
    parser.feed((tmp_path / "report" / "report.html").read_text())
    html_row = next(row for row in parser.rows if "comparison:contrast_1" in row)
    for rendered in (text_line, html_row):
        assert "method:B" in rendered and "method:A" in rendered, rendered
        assert rendered.index("method:B") < rendered.index("method:A"), rendered


@pytest.mark.parametrize("estimate", [float.fromhex("0x0.0000000000001p-1022"), 1e308])
def test_constant_finite_contributions_keep_their_mean_and_zero_sample_mcse(estimate):
    data = _complete_points_incomplete_common_intervals()
    data[0]["cohorts"] = []
    data[0]["comparisons"] = []
    for row in data[2]:
        row["estimate"] = estimate
    validated = validate(*data).validated
    assert validated is not None
    summary = summarize(validated, replay(validated))
    for row in summary.metrics:
        assert row.value == estimate, (
            "Dividing each contribution before summation must not silently underflow the mean"
        )
        assert row.mcse == 0
        assert "degenerate_sample" in row.warnings
