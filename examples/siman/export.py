"""Convert a user-supplied siman simcheck.dta to a separately mapped CSV.

The source dataset is not distributed. Install pandas separately for .dta input.
Published source: UCL/siman, commit 25b00347f5e9f514ad7708e8bb8d1d798a8e0f54.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

EXPECTED_SHA256 = "07e793f34341e5f5fef57590e405ef62caf5e58e88a6a19acc47374b725a0fb6"


def export_records(records, destination, *, planned_cases):
    records = list(records)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    planned = sorted((str(s), str(i)) for s, i in planned_cases)
    scenarios = sorted({s for s, i in planned})
    methods = ["CCA", "Full", "MI"]
    study = dict(
        schema_version=1,
        study_id="siman-simcheck",
        estimand=dict(
            id="treatment_effect",
            label="Simulation treatment effect",
            scale="coefficient",
        ),
        scenarios=[dict(id=s, truth=0) for s in scenarios],
        methods=[dict(id=m, version="published-simcheck") for m in methods],
        assumptions=dict(
            independent_cases=True,
            finite_second_moments=True,
            finite_mse_contribution_variance=True,
        ),
        metrics=["bias", "mse", "completion"],
        policies=[],
        cohorts=[
            dict(
                id="CCA_MI",
                members=[dict(kind="method", id=m) for m in ["CCA", "MI"]],
                requirement="point",
            )
        ],
        comparisons=[
            dict(
                id="CCA-minus-MI",
                left=dict(kind="method", id="CCA"),
                right=dict(kind="method", id="MI"),
                cohort="CCA_MI",
                metrics=["bias", "mse"],
            )
        ],
        description="Published simulation outputs; df is intentionally unused for point-estimate eligibility.",
    )
    mapping = dict(
        schema_version=1,
        columns=dict(
            scenario_id="dgm",
            case_id="rep",
            method_id="method",
            estimate="b",
            source_record_id="record",
        ),
        constants=dict(
            reason="",
            interval_status="not_provided",
            lower=None,
            upper=None,
            estimand_id="treatment_effect",
            scale="coefficient",
        ),
        status_from_estimate=True,
    )
    s = destination / "study.json"
    p = destination / "planned.csv"
    r = destination / "native_results.csv"
    m = destination / "mapping.json"
    s.write_text(json.dumps(study, indent=2) + "\n")
    m.write_text(json.dumps(mapping, indent=2) + "\n")
    with p.open("w", newline="") as stream:
        w = csv.writer(stream)
        w.writerow(["scenario_id", "case_id"])
        w.writerows(planned)
    with r.open("w", newline="") as stream:
        w = csv.writer(stream)
        w.writerow(["dgm", "rep", "method", "b", "se", "df", "record"])
        for row in records:
            w.writerow(
                [
                    str(row["dgm"]),
                    str(row["rep"]),
                    str(row["method"]),
                    row["b"],
                    row["se"],
                    row["df"],
                    f"{row['dgm']}/{row['rep']}/{row['method']}",
                ]
            )
    return s, p, r, m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dta", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.input_dta.read_bytes()).hexdigest() != EXPECTED_SHA256:
        parser.error("Input differs from the documented public simcheck.dta SHA-256")
    import pandas as pd

    data = pd.read_stata(args.input_dta)
    expected = {
        (s, i, m)
        for s in ["MCAR", "MAR", "MNAR"]
        for i in range(1, 1001)
        for m in ["Full", "CCA", "MI"]
    }
    actual = {
        (str(row.dgm), int(row.rep), str(row.method)) for row in data.itertuples()
    }
    if actual != expected or len(data) != 9000:
        parser.error("Input does not match the declared 3 x 1000 x 3 source study plan")
    rows = data.to_dict("records")
    for row in rows:
        row["rep"] = int(row["rep"])
    paths = export_records(
        rows,
        args.output_dir,
        planned_cases=[
            (s, str(i)) for s in ["MCAR", "MAR", "MNAR"] for i in range(1, 1001)
        ],
    )
    print(
        json.dumps(
            dict(
                paths=[str(p) for p in paths],
                records=len(data),
                missing_df=int(data["df"].isna().sum()),
            )
        )
    )


if __name__ == "__main__":
    main()
