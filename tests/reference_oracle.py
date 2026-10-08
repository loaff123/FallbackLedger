"""Independent, scalar specification oracle for valid FallbackLedger inputs.

This file was authored from the approved design before reading product code.
It intentionally imports no FallbackLedger code, types, or eligibility helpers.
The reference takes ordinary input dictionaries, retaining whole selected rows.
It is a correctness oracle for routing/cohorts, not a second input validator.
"""

from copy import deepcopy


def route(methods, requirement, inapplicable, records):
    """Evaluate one case using only its method -> raw-record dictionary."""
    visited = []
    for position, method in enumerate(methods):
        record = records.get(method)
        step = {
            "method_id": method,
            "step_index": position,
            "action": None,
            "status": None if record is None else record["status"],
            "interval_status": None if record is None else record["interval_status"],
            "source_record_id": None if record is None else record["source_record_id"],
        }
        visited.append(step)
        if record is None:
            step["action"] = "missing_record"
            return _terminal("unresolved", "missing_record", visited)
        if record["status"] == "unknown":
            step["action"] = "unknown_result"
            return _terminal("unresolved", "unknown_result", visited)
        if record["status"] == "inapplicable":
            if inapplicable == "stop":
                step["action"] = "method_inapplicable"
                return _terminal("inapplicable", "method_inapplicable", visited)
            step["action"] = "skip_inapplicable"
            continue
        if record["status"] == "failed":
            step["action"] = "point_failed"
            continue
        if requirement == "point" or record["interval_status"] == "available":
            step["action"] = "selected"
            return {
                "state": "usable",
                "reason": "selected",
                "selected": deepcopy(record),
                "fallback_depth": position,
                "route": tuple(visited),
            }
        if record["interval_status"] == "unknown":
            step["action"] = "unknown_interval"
            return _terminal("unresolved", "unknown_interval", visited)
        if record["interval_status"] == "failed":
            step["action"] = "interval_failed"
        else:
            step["action"] = "interval_not_provided"
    return _terminal("exhausted", "no_usable_method", visited)


def _terminal(state, reason, visited):
    return {
        "state": state,
        "reason": reason,
        "selected": None,
        "fallback_depth": None,
        "route": tuple(visited),
    }


def record_state(record, requirement):
    """The usable-output partition for one raw or selected recorded bundle."""
    if record is None:
        return "unresolved", "missing_record"
    if record["status"] == "unknown":
        return "unresolved", "unknown_result"
    if record["status"] == "failed":
        return "explicit_failure", "point_failed"
    if record["status"] == "inapplicable":
        return "inapplicable", "method_inapplicable"
    if requirement == "point" or record["interval_status"] == "available":
        return "usable", "selected"
    if record["interval_status"] == "unknown":
        return "unresolved", "unknown_interval"
    if record["interval_status"] == "failed":
        return "explicit_failure", "interval_failed"
    return "explicit_unavailable", "interval_not_provided"


def replay(study, planned, results):
    """Return outcomes keyed by scenario, case, policy, independent of ordering."""
    by_case = {}
    for record in results:
        key = record["scenario_id"], record["case_id"]
        by_case.setdefault(key, {})[record["method_id"]] = record
    outcomes = {}
    for case in planned:
        key = case["scenario_id"], case["case_id"]
        for policy in study["policies"]:
            outcomes[(*key, policy["id"])] = route(
                policy["methods"],
                policy["requirement"],
                policy["inapplicable"],
                by_case.get(key, {}),
            )
    return outcomes


def common_cohorts(study, planned, results, outcomes=None):
    """Return exact common membership and *all* per-member exclusions.

    A selected point-policy bundle is treated as a single record for interval
    membership. Later records can never donate an interval to that policy.
    """
    if outcomes is None:
        outcomes = replay(study, planned, results)
    records = {(r["scenario_id"], r["case_id"], r["method_id"]): r for r in results}
    cohorts = {}
    for definition in study["cohorts"]:
        for scenario in study["scenarios"]:
            rows = {}
            for case in planned:
                if case["scenario_id"] != scenario["id"]:
                    continue
                case_key = case["scenario_id"], case["case_id"]
                exclusions = []
                for member in definition["members"]:
                    if member["kind"] == "method":
                        state, reason = record_state(
                            records.get((*case_key, member["id"])),
                            definition["requirement"],
                        )
                    else:
                        outcome = outcomes[(*case_key, member["id"])]
                        if outcome["state"] == "usable":
                            state, reason = record_state(
                                outcome["selected"], definition["requirement"]
                            )
                        else:
                            state, reason = outcome["state"], outcome["reason"]
                    if state != "usable":
                        exclusions.append((member["kind"], member["id"], state, reason))
                rows[case_key] = (not exclusions, tuple(sorted(exclusions)))
            cohorts[("common", definition["id"], scenario["id"])] = {
                "requirement": definition["requirement"],
                "members": tuple(
                    sorted((m["kind"], m["id"]) for m in definition["members"])
                ),
                "rows": rows,
            }
    return cohorts
