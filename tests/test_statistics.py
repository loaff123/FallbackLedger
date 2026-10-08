import math

import pytest

from fallbackledger import replay, summarize, validate


def run(data):
    v = validate(*data).validated
    assert v is not None
    return summarize(v, replay(v))


def metric(summary, entity, name, cohort=None):
    rows = [
        r
        for r in summary.metrics
        if r.subject.kind == entity[0]
        and r.subject.id == entity[1]
        and r.metric == name
        and (cohort is None or r.cohort_id == cohort)
    ]
    assert len(rows) == 1, rows
    return rows[0]


def test_frozen_pipeline_metrics_and_denominators(data):
    summary = run(data)
    bias = metric(
        summary, ("policy", "point"), "bias", ("own", "policy", "point", "point")
    )
    assert bias.value == 3.25 and bias.n == 4 and bias.planned_n == 6
    assert bias.target == "conditional_on_usable_output"
    assert bias.mcse == pytest.approx(math.sqrt(14.75 / 3 / 4))
    assert (
        metric(
            summary, ("policy", "point"), "mse", ("own", "policy", "point", "point")
        ).value
        == 14.25
    )
    assert metric(
        summary, ("policy", "interval"), "bias", ("own", "policy", "interval", "point")
    ).value == pytest.approx(10 / 3)
    coverage = metric(
        summary,
        ("policy", "interval"),
        "coverage",
        ("own", "policy", "interval", "interval"),
    )
    assert coverage.value == 1 and coverage.n == 3 and coverage.mcse == 0
    assert "degenerate_sample" in coverage.warnings
    completion = metric(summary, ("policy", "point"), "completion")
    assert completion.value == pytest.approx(4 / 6) and completion.n == 6


def test_paired_contributions_on_identical_named_cohort(data):
    row = metric(run(data), ("comparison", "A-B"), "bias")
    assert row.value == -1 and row.mcse == 0 and row.n == 2
    assert row.cohort_id == ("common", "both") and row.orientation == "left_minus_right"


def test_point_policy_coverage_does_not_borrow_interval(data):
    row = metric(
        run(data),
        ("policy", "point"),
        "coverage",
        ("own", "policy", "point", "interval"),
    )
    assert row.n == 2 and row.value == 1


@pytest.mark.parametrize(
    "key,reason",
    [
        ("independent_cases", "independent_cases_not_declared"),
        ("finite_second_moments", "finite_second_moments_not_declared"),
    ],
)
def test_mcse_needs_declared_assumptions(data, key, reason):
    data[0]["assumptions"][key] = False
    row = metric(
        run(data), ("policy", "point"), "bias", ("own", "policy", "point", "point")
    )
    assert row.mcse is None and row.mcse_reason == reason and row.value == 3.25


def test_mse_variance_declaration_separate_from_bias(data):
    data[0]["assumptions"]["finite_mse_contribution_variance"] = False
    summary = run(data)
    assert (
        metric(
            summary, ("policy", "point"), "mse", ("own", "policy", "point", "point")
        ).mcse
        is None
    )
    assert (
        metric(
            summary, ("policy", "point"), "bias", ("own", "policy", "point", "point")
        ).mcse
        is not None
    )


def test_empty_and_single_case_cohorts(data):
    study, planned, rows = data
    planned[:] = [p for p in planned if p["case_id"] == "01"]
    rows[:] = [r for r in rows if r["case_id"] == "01"]
    summary = run(data)
    empty = metric(
        summary, ("policy", "point"), "bias", ("own", "policy", "point", "point")
    )
    assert empty.n == 0 and empty.value is None and empty.mcse_reason == "empty_cohort"
    single = metric(summary, ("method", "B"), "bias", ("own", "method", "B", "point"))
    assert single.n == 1 and single.mcse is None and single.mcse_reason == "n_lt_2"


def test_numeric_overflow_is_unavailable_without_dropping_cases(data):
    for r in data[2]:
        if r["estimate"] is not None:
            r["estimate"] = 1e308
    row = metric(
        run(data), ("policy", "point"), "mse", ("own", "policy", "point", "point")
    )
    assert (
        row.n == 4 and row.value is None and row.diagnostic == "nonfinite_contribution"
    )


def test_replay_from_different_input_is_rejected(data):
    original = validate(*data).validated
    r = replay(original)
    data[0]["scenarios"][0]["truth"] = 3
    with pytest.raises(ValueError, match="digest"):
        summarize(validate(*data).validated, r)


def test_completion_counts_partition_planned_cases(data):
    summary = run(data)
    for count in summary.counts:
        assert (
            sum(
                getattr(count, k)
                for k in [
                    "usable_cases",
                    "explicit_failure_cases",
                    "explicit_unavailable_cases",
                    "unresolved_cases",
                    "inapplicable_cases",
                    "exhausted_cases",
                ]
            )
            == count.planned_cases
        )
    point = next(
        c
        for c in summary.counts
        if c.subject.kind == "policy"
        and c.subject.id == "point"
        and c.requirement == "point"
    )
    assert (
        point.planned_cases == 6
        and point.usable_cases == 4
        and point.unresolved_cases == 1
    )
    assert point.exhausted_cases == 1 and point.explicit_point_failures == 3
