import pytest

from fallbackledger import replay, validate


def outcomes(data, policy):
    valid = validate(*data)
    assert valid.validated, valid.issues
    return {
        o.case_id: o for o in replay(valid.validated).outcomes if o.policy_id == policy
    }


def test_six_case_point_policy(data):
    rows = outcomes(data, "point")
    assert {k for k, o in rows.items() if o.state == "usable"} == {
        "02",
        "04",
        "05",
        "06",
    }
    assert rows["01"].state == "unresolved" and rows["01"].reason == "missing_record"
    assert len(rows["01"].route) == 1
    assert rows["02"].selected.method_id == "A" and len(rows["02"].route) == 1
    assert rows["03"].state == "exhausted" and len(rows["03"].route) == 2
    assert rows["06"].selected.method_id == "B" and rows["06"].fallback_depth == 1


def test_interval_fallback_uses_whole_b_bundle(data):
    rows = outcomes(data, "interval")
    assert {k for k, o in rows.items() if o.state == "usable"} == {"02", "04", "06"}
    assert rows["04"].selected.estimate == 3
    assert rows["04"].selected.lower == -1 and rows["04"].selected.upper == 4
    assert rows["04"].route[0].action == "interval_not_provided"
    assert rows["05"].reason == "unknown_interval" and len(rows["05"].route) == 1


def test_explicit_interval_failure_falls_back_but_keeps_point(data):
    data[2][6].update(interval_status="failed", reason="CI solver failed")
    assert outcomes(data, "point")["05"].selected.estimate == 4
    row = outcomes(data, "interval")["05"]
    assert row.selected.estimate == 5 and row.route[0].action == "interval_failed"


@pytest.mark.parametrize("action,state", [("stop", "inapplicable"), ("skip", "usable")])
def test_inapplicable_is_explicit_policy_choice(data, action, state):
    data[0]["policies"][0]["inapplicable"] = action
    data[2][8].update(status="inapplicable", reason="outside declared model")
    row = outcomes(data, "point")["06"]
    assert row.state == state
    assert row.route[0].action == (
        "method_inapplicable" if action == "stop" else "skip_inapplicable"
    )


def test_unknown_output_stops_despite_recorded_fallback(data):
    data[2][8].update(status="unknown", reason="status log missing")
    row = outcomes(data, "point")["06"]
    assert row.reason == "unknown_result" and row.selected is None


def test_routing_ignores_truth_and_available_value_magnitudes(data):
    before = outcomes(data, "interval")
    data[0]["scenarios"][0]["truth"] = 1e20
    for row in data[2]:
        if row["estimate"] is not None:
            row["estimate"] *= 1e20
    after = outcomes(data, "interval")
    for key in before:
        assert before[key].state == after[key].state
        assert before[key].route == after[key].route
