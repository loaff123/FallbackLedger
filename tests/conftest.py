from copy import deepcopy

import pytest


def entity(kind, id):
    return {"kind": kind, "id": id}


def result(
    case, method, value=None, status="ok", interval="available", lower=-1, upper=10
):
    return dict(
        scenario_id="s",
        case_id=case,
        method_id=method,
        status=status,
        reason="" if status == "ok" else "recorded reason",
        estimate=value,
        interval_status=interval if status == "ok" else "unknown",
        lower=lower if status == "ok" and interval == "available" else None,
        upper=upper if status == "ok" and interval == "available" else None,
        source_record_id=f"{case}/{method}",
        estimand_id="theta",
        scale="real",
    )


@pytest.fixture
def data():
    study = dict(
        schema_version=1,
        study_id="tiny",
        estimand=dict(id="theta", label="Original scalar", scale="real"),
        scenarios=[dict(id="s", truth=0)],
        methods=[dict(id=m, version="1") for m in ["A", "B"]],
        assumptions=dict(
            independent_cases=True,
            finite_second_moments=True,
            finite_mse_contribution_variance=True,
        ),
        nominal_interval_level=0.95,
        metrics=["bias", "mse", "coverage", "completion"],
        policies=[
            dict(
                id="point", methods=["A", "B"], requirement="point", inapplicable="stop"
            ),
            dict(
                id="interval",
                methods=["A", "B"],
                requirement="interval",
                inapplicable="stop",
            ),
        ],
        cohorts=[
            dict(
                id="both",
                members=[entity("method", "A"), entity("method", "B")],
                requirement="point",
            )
        ],
        comparisons=[
            dict(
                id="A-B",
                left=entity("method", "A"),
                right=entity("method", "B"),
                cohort="both",
                metrics=["bias", "mse"],
            )
        ],
    )
    planned = [dict(scenario_id="s", case_id=f"{i:02d}") for i in range(1, 7)]
    rows = [
        result("01", "B", 10, lower=9, upper=11),
        result("02", "A", 1, lower=-1, upper=2),
        result("03", "A", status="failed"),
        result("03", "B", status="failed"),
        result("04", "A", 2, interval="not_provided"),
        result("04", "B", 3, lower=-1, upper=4),
        result("05", "A", 4, interval="unknown"),
        result("05", "B", 5, lower=4, upper=6),
        result("06", "A", status="failed"),
        result("06", "B", 6, lower="-inf", upper="inf"),
    ]
    return deepcopy((study, planned, rows))
