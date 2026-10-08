"""Assemble denominator-aware metrics from exact named cohorts."""

from collections import Counter

from .cohorts import StudyIndex, build_cohorts
from .models import CountRow, EntityRef, MetricRow, SummaryResult
from .statistics import contribution, summarize_contributions

ASSUMPTION_NOTES = (
    "Conditional summaries describe recorded usable cases; common-success conditioning does not repair selection bias.",
    "MCSE uses sample contribution variance divided by n and assumes independent simulation cases and finite contribution variance.",
    "MSE MCSE requires finite variance of squared error, a fourth-error-moment condition; declarations are not verified.",
    "A zero sample MCSE does not imply zero population uncertainty. No confidence interval or winner is asserted.",
    "Observed completion counts replayable usable output; missing attempts are unresolved, not explicit failures.",
)


def _counts(index, scenario, member, requirement):
    terminal = Counter()
    events = Counter()
    observed_cases = 0
    for case in index.cases[scenario]:
        terminal[index.state(case, member, requirement).state] += 1
        rows = index.events(case, member)
        observed_cases += any(r is not None for r in rows)
        for row in rows:
            if row is None:
                events["missing_records"] += 1
                continue
            events["observed_records"] += 1
            if row.status == "failed":
                events["explicit_point_failures"] += 1
            if row.status == "unknown":
                events["unknown_records"] += 1
            if row.status == "inapplicable":
                events["inapplicable_records"] += 1
            if row.interval_status == "failed":
                events["explicit_interval_failures"] += 1
            if row.interval_status == "not_provided":
                events["explicit_interval_unavailable"] += 1
    return CountRow(
        scenario,
        member,
        requirement,
        len(index.cases[scenario]),
        events["observed_records"],
        observed_cases,
        events["missing_records"],
        events["explicit_point_failures"],
        events["explicit_interval_failures"],
        events["explicit_interval_unavailable"],
        events["unknown_records"],
        events["inapplicable_records"],
        terminal["usable"],
        terminal["explicit_failure"],
        terminal["explicit_unavailable"],
        terminal["unresolved"],
        terminal["inapplicable"],
        terminal["exhausted"],
        terminal["usable"],
    )


def _metric(
    spec, scenario, subject, metric, cohort_id, target, values, planned_n, **extra
):
    stats = summarize_contributions(values, spec.assumptions, metric)
    return MetricRow(
        scenario,
        subject,
        metric,
        cohort_id,
        target,
        len(values),
        planned_n,
        **stats,
        **extra,
    )


def summarize(validated, replayed):
    """Produce per-scenario summaries without silently changing named cohorts."""
    index = StudyIndex(validated, replayed)
    spec = validated.spec
    cohorts = build_cohorts(validated, replayed, index)
    metrics = []
    counts = []
    truths = {s.id: s.truth for s in spec.scenarios}
    for scenario, cases in index.cases.items():
        for member in index.entities:
            for requirement in ("point", "interval"):
                counts.append(_counts(index, scenario, member, requirement))
            if "completion" in spec.metrics:
                values = tuple(
                    float(index.state(case, member, "point").state == "usable")
                    for case in cases
                )
                metrics.append(
                    _metric(
                        spec,
                        scenario,
                        member,
                        "completion",
                        ("planned",),
                        "observed_usable_completion",
                        values,
                        len(cases),
                    )
                )
    for cohort in cohorts:
        included = tuple(r.case for r in cohort.rows if r.included)
        scenario = cohort.scenario_id
        planned = len(cohort.rows)
        for member in cohort.members:
            if cohort.id[0] == "common":
                target = "conditional_on_named_common_success"
            elif member.kind == "policy":
                target = (
                    "all_planned_cases"
                    if len(included) == planned
                    else "conditional_on_usable_output"
                )
            else:
                target = "conditional_on_recorded_usable_output"
            for name in spec.metrics:
                if name == "completion" or (
                    name == "coverage" and cohort.requirement != "interval"
                ):
                    continue
                if (
                    cohort.id[0] == "own"
                    and cohort.requirement == "interval"
                    and name != "coverage"
                ):
                    continue
                values = tuple(
                    contribution(
                        index.state(case, member, cohort.requirement).selected,
                        truths[scenario],
                        name,
                    )
                    for case in included
                )
                metrics.append(
                    _metric(
                        spec, scenario, member, name, cohort.id, target, values, planned
                    )
                )
    common = {(c.id[1], c.scenario_id): c for c in cohorts if c.id[0] == "common"}
    for comparison in spec.comparisons:
        for scenario, cases in index.cases.items():
            cohort = common[(comparison.cohort, scenario)]
            included = tuple(r.case for r in cohort.rows if r.included)
            for name in comparison.metrics:
                values = tuple(
                    contribution(
                        index.state(case, comparison.left, cohort.requirement).selected,
                        truths[scenario],
                        name,
                    )
                    - contribution(
                        index.state(
                            case, comparison.right, cohort.requirement
                        ).selected,
                        truths[scenario],
                        name,
                    )
                    for case in included
                )
                metrics.append(
                    _metric(
                        spec,
                        scenario,
                        EntityRef("comparison", comparison.id),
                        name,
                        cohort.id,
                        "paired_on_named_common_success",
                        values,
                        len(cases),
                        orientation="left_minus_right",
                        left=comparison.left,
                        right=comparison.right,
                    )
                )
    return SummaryResult(
        validated.canonical_digest,
        cohorts,
        tuple(metrics),
        tuple(counts),
        spec.assumptions,
        ASSUMPTION_NOTES,
    )
