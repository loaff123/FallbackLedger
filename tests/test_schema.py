import math
from copy import deepcopy

import pytest

from fallbackledger import validate


def codes(report):
    return {i.code for i in report.issues if i.severity == "error"}


def test_valid_fixture_keeps_missing_attempts_and_infinite_bounds(data):
    report = validate(*data)
    assert report.validated is not None, report.issues
    assert len(report.validated.cases) == 6 and len(report.validated.results) == 10
    assert report.validated.results[-1].upper == math.inf
    assert any(i.code == "missing_records" for i in report.issues)


@pytest.mark.parametrize(
    "change,expected",
    [
        (lambda s, p, r: r.append(deepcopy(r[0])), "duplicate_result"),
        (lambda s, p, r: p.append(deepcopy(p[0])), "duplicate_case"),
        (lambda s, p, r: r[0].update(case_id="outside"), "off_grid"),
        (lambda s, p, r: r[0].update(method_id="C"), "unknown_method"),
        (lambda s, p, r: r[0].update(scale="log"), "incompatible_scale"),
        (lambda s, p, r: r[0].update(estimand_id="other"), "incompatible_estimand"),
        (lambda s, p, r: s["scenarios"][0].update(truth=True), "invalid_number"),
        (lambda s, p, r: r[0].update(estimate=None), "invalid_number"),
        (lambda s, p, r: r[0].update(estimate=float("inf")), "invalid_number"),
        (lambda s, p, r: r[0].update(lower=float("nan")), "invalid_number"),
        (lambda s, p, r: r[0].update(lower=12), "invalid_interval"),
        (lambda s, p, r: r[0].update(interval_status="unknown"), "unexpected_bounds"),
        (
            lambda s, p, r: r[0].update(status="failed", reason="failed explicitly"),
            "unexpected_estimate",
        ),
        (lambda s, p, r: r[2].update(reason=""), "missing_reason"),
        (lambda s, p, r: p[0].update(case_id="   "), "invalid_id"),
        (lambda s, p, r: s.update(metrcs=[]), "unknown_field"),
        (
            lambda s, p, r: s["assumptions"].pop("finite_mse_contribution_variance"),
            "missing_field",
        ),
        (
            lambda s, p, r: s["comparisons"][0]["metrics"].append("coverage"),
            "invalid_comparison",
        ),
    ],
)
def test_structural_error_prevents_validated_output(data, change, expected):
    change(*data)
    report = validate(*data)
    assert report.validated is None
    assert expected in codes(report), report.issues


def test_unknown_result_is_observed_not_explicit_failure(data):
    data[2][0].update(
        status="unknown",
        estimate=None,
        interval_status="unknown",
        lower=None,
        upper=None,
        reason="no output",
    )
    report = validate(*data)
    assert report.validated and report.validated.results[0].status == "unknown"


def test_source_record_ids_need_not_be_globally_unique(data):
    for row in data[2]:
        row["source_record_id"] = "same-source"
    assert validate(*data).validated


def test_immutable_models_preserve_leading_zero_case_ids(data):
    validated = validate(*data).validated
    assert validated.cases[0].case_id == "01"
    with pytest.raises((AttributeError, TypeError)):
        validated.spec.study_id = "changed"
    data[0]["study_id"] = "mutated-input"
    assert validated.spec.study_id == "tiny"


def test_order_independent_logical_digest(data):
    a = validate(*data).validated
    data[1].reverse()
    data[2].reverse()
    assert validate(*data).validated.canonical_digest == a.canonical_digest
