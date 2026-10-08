"""Evaluate declared routing from observation state, never scientific performance."""

from .models import PolicyOutcome, ReplayResult, RouteStep


def replay(validated):
    """Replay each policy for each planned case, retaining complete route lineage."""
    records = {(r.scenario_id, r.case_id, r.method_id): r for r in validated.results}
    outcomes = []
    for case in validated.cases:
        for policy in validated.spec.policies:
            route = []
            selected = None
            depth = None
            state = "exhausted"
            reason = "no_usable_method"
            for index, method in enumerate(policy.methods):
                row = records.get((case.scenario_id, case.case_id, method))
                action = "selected"
                if row is None:
                    state, reason, action = (
                        "unresolved",
                        "missing_record",
                        "missing_record",
                    )
                elif row.status == "unknown":
                    state, reason, action = (
                        "unresolved",
                        "unknown_result",
                        "unknown_result",
                    )
                elif row.status == "inapplicable":
                    if policy.inapplicable == "skip":
                        action = "skip_inapplicable"
                    else:
                        state, reason, action = (
                            "inapplicable",
                            "method_inapplicable",
                            "method_inapplicable",
                        )
                elif row.status == "failed":
                    action = "point_failed"
                elif (
                    policy.requirement == "interval"
                    and row.interval_status != "available"
                ):
                    action = {
                        "failed": "interval_failed",
                        "not_provided": "interval_not_provided",
                        "unknown": "unknown_interval",
                    }[row.interval_status]
                    if row.interval_status == "unknown":
                        state, reason = "unresolved", "unknown_interval"
                else:
                    state, reason, selected, depth = "usable", "selected", row, index
                route.append(
                    RouteStep(
                        method,
                        index,
                        action,
                        row.status if row else None,
                        row.interval_status if row else None,
                        row.source_record_id if row else None,
                        row.reason if row else None,
                    )
                )
                if action not in (
                    "skip_inapplicable",
                    "point_failed",
                    "interval_failed",
                    "interval_not_provided",
                ):
                    break
            outcomes.append(
                PolicyOutcome(
                    case.scenario_id,
                    case.case_id,
                    policy.id,
                    state,
                    reason,
                    selected,
                    depth,
                    tuple(route),
                )
            )
    return ReplayResult(validated.canonical_digest, tuple(outcomes))
