"""Exhaustive independent routing/cohort qualification.

The eight valid observation classes are crossed for A/B/C, giving 512 cases.
Every case is replayed under point/interval x inapplicable stop/skip policies.
The scalar oracle is independent of product internals. Product access below is
limited to the three public functions and transparent dataclass field adapters.
"""

import random
from copy import deepcopy
from dataclasses import asdict
from importlib import import_module
from itertools import permutations, product

import pytest
from reference_oracle import (
    common_cohorts,
    record_state,
    route,
)
from reference_oracle import (
    replay as oracle_replay,
)

CLASSES = (
    "absent",
    "unknown",
    "failed",
    "inapplicable",
    "point_only",
    "interval_unknown",
    "interval_failed",
    "interval_available",
)
REQUIREMENTS = ("point", "interval")
INAPPLICABLE = ("stop", "skip")
BUNDLE_FIELDS = (
    "scenario_id",
    "case_id",
    "method_id",
    "status",
    "reason",
    "estimate",
    "interval_status",
    "lower",
    "upper",
    "source_record_id",
    "estimand_id",
    "scale",
    "dataset_id",
    "configuration_id",
)


def _study():
    policies = [
        {
            "id": f"{requirement}_{mode}",
            "methods": ["A", "B", "C"],
            "requirement": requirement,
            "inapplicable": mode,
        }
        for requirement, mode in product(REQUIREMENTS, INAPPLICABLE)
    ]
    members = [{"kind": "method", "id": m} for m in ("A", "B", "C")] + [
        {"kind": "policy", "id": p["id"]} for p in policies
    ]
    # All member pairs make it difficult for an accidental union, a wrong
    # entity namespace, or a reused own-success cohort to look correct.
    common = []
    for requirement in REQUIREMENTS:
        common.append(
            {
                "id": f"all_{requirement}",
                "members": deepcopy(members),
                "requirement": requirement,
            }
        )
        for left in range(len(members)):
            for right in range(left + 1, len(members)):
                common.append(
                    {
                        "id": f"pair_{left}_{right}_{requirement}",
                        "members": [members[left], members[right]],
                        "requirement": requirement,
                    }
                )
    return {
        "schema_version": 1,
        "study_id": "independent-exhaustive-v1",
        "estimand": {"id": "theta", "label": "Original test contrast", "scale": "raw"},
        "scenarios": [{"id": "s", "truth": 0}],
        "methods": [{"id": m, "version": "original-test-v1"} for m in ("A", "B", "C")],
        "assumptions": {
            "independent_cases": True,
            "finite_second_moments": True,
            "finite_mse_contribution_variance": True,
        },
        "metrics": ["bias", "mse", "coverage", "completion"],
        "nominal_interval_level": 0.95,
        "policies": policies,
        "cohorts": common,
        "comparisons": [],
        "provenance": {"dataset_id": "original-fixture", "configuration_id": "v1"},
    }


def _record(scenario, case, method, observation):
    if observation == "absent":
        return None
    # Every method has a distinct numeric bundle. An implementation that
    # copies A's point estimate into B's interval selection will be detected.
    offset = {"A": 2.25, "B": -7.5, "C": 19.125}[method]
    result = {
        "scenario_id": scenario,
        "case_id": case,
        "method_id": method,
        "status": "ok",
        "reason": f"diagnostic:{observation}:{method}",
        "estimate": offset,
        "interval_status": "available",
        "lower": offset - 0.75,
        "upper": offset + 1.25,
        "source_record_id": f"source:{scenario}:{case}:{method}",
        "estimand_id": "theta",
        "scale": "raw",
        "dataset_id": "original-fixture",
        "configuration_id": "v1",
    }
    if observation in ("unknown", "failed", "inapplicable"):
        result.update(
            status=observation,
            estimate=None,
            interval_status="unknown",
            lower=None,
            upper=None,
        )
    elif observation != "interval_available":
        result.update(
            interval_status={
                "point_only": "not_provided",
                "interval_unknown": "unknown",
                "interval_failed": "failed",
            }[observation],
            lower=None,
            upper=None,
        )
    return result


def _exhaustive_data():
    planned, records = [], []
    for number, observations in enumerate(product(CLASSES, repeat=3)):
        case = f"{number:03d}:" + "/".join(observations)
        planned.append({"scenario_id": "s", "case_id": case})
        for method, observation in zip(("A", "B", "C"), observations):
            record = _record("s", case, method, observation)
            if record is not None:
                records.append(record)
    return _study(), planned, records


def _public_api():
    try:
        api = import_module("fallbackledger")
    except ModuleNotFoundError as exc:
        pytest.fail(f"FallbackLedger public package is not implemented yet: {exc}")
    for name in ("validate", "replay", "summarize"):
        assert callable(getattr(api, name, None)), f"Missing public API: {name}"
    return api


def _run(study, planned, records, summarize=True):
    api = _public_api()
    report = api.validate(study, planned, records)
    assert report.validated is not None, report.issues
    replayed = api.replay(report.validated)
    summary = api.summarize(report.validated, replayed) if summarize else None
    return report.validated, replayed, summary


def _bundle_snapshot(record):
    if record is None:
        return None
    return {field: getattr(record, field) for field in BUNDLE_FIELDS}


def _outcome_snapshots(replayed):
    snapshots = {}
    for outcome in replayed.outcomes:
        key = outcome.scenario_id, outcome.case_id, outcome.policy_id
        assert key not in snapshots, f"Duplicate outcome {key}"
        snapshots[key] = {
            "state": outcome.state,
            "reason": outcome.reason,
            "selected": _bundle_snapshot(outcome.selected),
            "fallback_depth": outcome.fallback_depth,
            "route": tuple(
                {
                    name: getattr(step, name)
                    for name in (
                        "method_id",
                        "step_index",
                        "action",
                        "status",
                        "interval_status",
                        "source_record_id",
                    )
                }
                for step in outcome.route
            ),
        }
    return snapshots


def _common_snapshots(summary):
    snapshots = {}
    for cohort in summary.cohorts:
        if cohort.id[0] != "common":
            continue
        assert len(cohort.id) == 2
        key = (*cohort.id, cohort.scenario_id)
        assert key not in snapshots, f"Duplicate cohort {key}"
        rows = {}
        for row in cohort.rows:
            case_key = row.case.scenario_id, row.case.case_id
            assert case_key not in rows, f"Duplicate membership row {case_key}"
            exclusions = tuple(
                sorted(
                    (e.member.kind, e.member.id, e.state, e.reason)
                    for e in row.exclusions
                )
            )
            rows[case_key] = (row.included, exclusions)
        snapshots[key] = {
            "requirement": cohort.requirement,
            "members": tuple(sorted((m.kind, m.id) for m in cohort.members)),
            "rows": rows,
        }
    return snapshots


@pytest.fixture(scope="module")
def exhaustive():
    study, planned, records = _exhaustive_data()
    _, replayed, summary = _run(study, planned, records)
    return study, planned, records, replayed, summary


@pytest.mark.parametrize("requirement,mode", tuple(product(REQUIREMENTS, INAPPLICABLE)))
def test_all_512_three_method_observation_combinations_match_scalar_oracle(
    exhaustive, requirement, mode
):
    study, planned, records, replayed, _ = exhaustive
    expected = oracle_replay(study, planned, records)
    actual = _outcome_snapshots(replayed)
    assert len(actual) == 512 * 4
    policy = f"{requirement}_{mode}"
    for key, reference in expected.items():
        if key[2] == policy:
            assert actual[key] == reference, f"Mismatch for {key}"


def test_every_common_cohort_is_exact_intersection_with_all_exclusion_reasons(
    exhaustive,
):
    study, planned, records, _, summary = exhaustive
    assert _common_snapshots(summary) == common_cohorts(study, planned, records)


@pytest.mark.parametrize("requirement", REQUIREMENTS)
@pytest.mark.parametrize("mode", INAPPLICABLE)
def test_oracle_anchors_early_stopping_and_exact_bundle(requirement, mode):
    selected = _record("s", "anchor", "A", "interval_available")
    later = _record("s", "anchor", "B", "interval_available")
    outcome = route(["A", "B", "C"], requirement, mode, {"A": selected, "B": later})
    assert outcome["state"] == "usable"
    assert outcome["fallback_depth"] == 0
    assert outcome["selected"] == selected
    assert outcome["selected"] is not selected
    assert [s["method_id"] for s in outcome["route"]] == ["A"]
    # Presence of a perfect-looking fallback cannot resolve an absent A.
    outcome = route(["A", "B"], requirement, mode, {"B": later})
    assert outcome["state"] == "unresolved"
    assert outcome["reason"] == "missing_record"
    assert len(outcome["route"]) == 1


def test_oracle_anchor_interval_failed_unknown_and_unavailable_are_distinct():
    states = {
        name: record_state(_record("s", "x", "A", name), "interval")
        for name in ("interval_failed", "interval_unknown", "point_only")
    }
    assert states == {
        "interval_failed": ("explicit_failure", "interval_failed"),
        "interval_unknown": ("unresolved", "unknown_interval"),
        "point_only": ("explicit_unavailable", "interval_not_provided"),
    }
    records = {
        "A": _record("s", "x", "A", "point_only"),
        "B": _record("s", "x", "B", "interval_available"),
    }
    outcome = route(["A", "B"], "interval", "stop", records)
    assert outcome["selected"] == records["B"]
    assert outcome["fallback_depth"] == 1
    assert [s["action"] for s in outcome["route"]] == [
        "interval_not_provided",
        "selected",
    ]


def test_oracle_anchor_skipping_inapplicable_preserves_exhaustion():
    records = {
        "A": _record("s", "x", "A", "inapplicable"),
        "B": _record("s", "x", "B", "failed"),
    }
    assert route(["A", "B"], "point", "stop", records)["state"] == "inapplicable"
    outcome = route(["A", "B"], "point", "skip", records)
    assert outcome["state"] == "exhausted"
    assert outcome["reason"] == "no_usable_method"
    assert outcome["fallback_depth"] is None
    assert [s["action"] for s in outcome["route"]] == [
        "skip_inapplicable",
        "point_failed",
    ]


def test_policy_interval_cohort_never_borrows_a_later_methods_bounds():
    study = _study()
    study["cohorts"] = [
        {
            "id": "selected-bundle-only",
            "requirement": "interval",
            "members": [
                {"kind": "policy", "id": "point_stop"},
                {"kind": "policy", "id": "interval_stop"},
            ],
        }
    ]
    planned = [{"scenario_id": "s", "case_id": "01"}]
    records = [
        _record("s", "01", "A", "point_only"),
        _record("s", "01", "B", "interval_available"),
    ]
    _, replayed, summary = _run(study, planned, records)
    actual = _outcome_snapshots(replayed)
    assert actual[("s", "01", "point_stop")]["selected"] == records[0]
    assert actual[("s", "01", "interval_stop")]["selected"] == records[1]
    assert _common_snapshots(summary)[("common", "selected-bundle-only", "s")][
        "rows"
    ] == {
        ("s", "01"): (
            False,
            (
                (
                    "policy",
                    "point_stop",
                    "explicit_unavailable",
                    "interval_not_provided",
                ),
            ),
        )
    }


def test_all_tiny_case_and_record_order_permutations_preserve_semantics():
    study = _study()
    study["cohorts"] = [study["cohorts"][0]]
    planned = [{"scenario_id": "s", "case_id": case} for case in ("01", "1", "é")]
    records = [
        _record("s", "01", "A", "interval_available"),
        _record("s", "1", "A", "failed"),
        _record("s", "1", "B", "point_only"),
        _record("s", "é", "B", "interval_available"),
    ]
    expected = oracle_replay(study, planned, records)
    expected_cohorts = common_cohorts(study, planned, records, expected)
    for planned_order in permutations(planned):
        for record_order in permutations(records):
            _, replayed, summary = _run(study, planned_order, record_order)
            assert _outcome_snapshots(replayed) == expected
            assert _common_snapshots(summary) == expected_cohorts


def test_deterministic_random_permutations_of_exhaustive_population(exhaustive):
    study, planned, records, original_replay, original_summary = exhaustive
    expected = _outcome_snapshots(original_replay)
    expected_cohorts = _common_snapshots(original_summary)
    expected_metrics = tuple(asdict(metric) for metric in original_summary.metrics)
    randomizer = random.Random(710231)
    for _ in range(4):
        shuffled_planned, shuffled_records = list(planned), list(records)
        randomizer.shuffle(shuffled_planned)
        randomizer.shuffle(shuffled_records)
        _, replayed, summary = _run(study, shuffled_planned, shuffled_records)
        assert _outcome_snapshots(replayed) == expected
        assert _common_snapshots(summary) == expected_cohorts
        assert tuple(asdict(metric) for metric in summary.metrics) == expected_metrics


def test_truth_and_available_numeric_values_do_not_influence_routes(exhaustive):
    study, planned, records, original_replay, _ = exhaustive
    study = deepcopy(study)
    study["scenarios"][0]["truth"] = -99999.0
    changed = deepcopy(records)
    for record in changed:
        if record["status"] == "ok":
            record["estimate"] = 0.0
        if record["interval_status"] == "available":
            record["lower"], record["upper"] = "-inf", "inf"
    _, replayed, _ = _run(study, planned, changed, summarize=False)
    before, after = _outcome_snapshots(original_replay), _outcome_snapshots(replayed)
    assert before.keys() == after.keys()
    for key in before:
        assert {k: v for k, v in before[key].items() if k != "selected"} == {
            k: v for k, v in after[key].items() if k != "selected"
        }
        if before[key]["selected"]:
            assert (
                before[key]["selected"]["method_id"]
                == after[key]["selected"]["method_id"]
            )
            assert (
                before[key]["selected"]["source_record_id"]
                == after[key]["selected"]["source_record_id"]
            )


def test_common_cohorts_do_not_merge_identical_case_ids_across_scenarios():
    study = _study()
    study["scenarios"] = [{"id": "s", "truth": 0}, {"id": "s:2", "truth": 13}]
    study["cohorts"] = [
        {
            "id": "A+B",
            "requirement": "point",
            "members": [{"kind": "method", "id": "A"}, {"kind": "method", "id": "B"}],
        }
    ]
    planned = [
        {"scenario_id": scenario, "case_id": case}
        for scenario, case in product(("s", "s:2"), ("01", " 1 "))
    ]
    records = [
        _record("s", "01", "A", "interval_available"),
        _record("s", "01", "B", "point_only"),
        _record("s:2", "01", "A", "failed"),
        _record("s:2", "01", "B", "point_only"),
        _record("s:2", " 1 ", "A", "interval_available"),
        _record("s:2", " 1 ", "B", "interval_available"),
    ]
    _, replayed, summary = _run(study, planned, records)
    assert _outcome_snapshots(replayed) == oracle_replay(study, planned, records)
    actual = _common_snapshots(summary)
    assert actual == common_cohorts(study, planned, records)
    assert {
        case
        for case, (included, _) in actual[("common", "A+B", "s")]["rows"].items()
        if included
    } == {("s", "01")}
    assert {
        case
        for case, (included, _) in actual[("common", "A+B", "s:2")]["rows"].items()
        if included
    } == {("s:2", " 1 ")}


def test_method_policy_namespaces_remain_distinct_even_when_ids_match():
    study = _study()
    study["policies"] = [
        {
            "id": "A",
            "methods": ["B", "C"],
            "requirement": "point",
            "inapplicable": "stop",
        }
    ]
    study["cohorts"] = [
        {
            "id": "A",
            "requirement": "point",
            "members": [{"kind": "method", "id": "A"}, {"kind": "policy", "id": "A"}],
        }
    ]
    planned = [{"scenario_id": "s", "case_id": "case"}]
    records = [
        _record("s", "case", "A", "interval_available"),
        _record("s", "case", "B", "unknown"),
    ]
    _, replayed, summary = _run(study, planned, records)
    assert _outcome_snapshots(replayed) == oracle_replay(study, planned, records)
    assert _common_snapshots(summary) == common_cohorts(study, planned, records)
    ids = [cohort.id for cohort in summary.cohorts]
    assert ("own", "method", "A", "point") in ids
    assert ("own", "policy", "A", "point") in ids
    assert ("common", "A") in ids
