"""Original adapted odds-ratio simulation export; NumPy only for generation.

Design follows Wünsch et al. (2025), DOI 10.1002/sim.70257. This is a fresh
adapted simulation, not the authors' random stream or full method comparison.
"""

import argparse
import csv
import itertools
import json
import math
from pathlib import Path


def export_tables(tables, exposure_probability, odds_ratio, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    scenario = f"px{exposure_probability}_or{odds_ratio}"
    method_ids = ["raw_log_OR", "always_add_half"]
    members = [{"kind": "method", "id": m} for m in method_ids] + [
        {"kind": "policy", "id": "raw_then_add_half"}
    ]
    study = dict(
        schema_version=1,
        study_id="adapted-odds-ratio",
        estimand=dict(id="log_OR", label="Log odds ratio", scale="log_odds_ratio"),
        scenarios=[dict(id=scenario, truth=math.log(odds_ratio))],
        methods=[dict(id=m, version="original-adapted-v1") for m in method_ids],
        assumptions=dict(
            independent_cases=True,
            finite_second_moments=True,
            finite_mse_contribution_variance=True,
        ),
        metrics=["bias", "mse", "completion"],
        policies=[
            dict(
                id="raw_then_add_half",
                methods=method_ids,
                requirement="point",
                inapplicable="stop",
            )
        ],
        cohorts=[dict(id="raw_success", members=members, requirement="point")],
        comparisons=[],
        description="Fresh adapted 2x2-table simulation. No patient-level or clinical conclusions.",
    )
    mapping = dict(
        schema_version=1,
        columns=dict(
            scenario_id="scenario",
            case_id="rep",
            method_id="engine",
            status="outcome",
            reason="why",
            estimate="beta",
            source_record_id="source",
        ),
        constants=dict(
            interval_status="not_provided",
            lower=None,
            upper=None,
            estimand_id="log_OR",
            scale="log_odds_ratio",
        ),
        values=dict(status={"returned": "ok", "zero_cell": "failed"}),
    )
    study_path = destination / "study.json"
    mapping_path = destination / "mapping.json"
    study_path.write_text(json.dumps(study, indent=2) + "\n")
    mapping_path.write_text(json.dumps(mapping, indent=2) + "\n")
    planned_path = destination / "planned.csv"
    raw_path = destination / "native_results.csv"
    with planned_path.open("w", newline="") as p, raw_path.open("w", newline="") as r:
        pw = csv.writer(p)
        rw = csv.writer(r)
        pw.writerow(["scenario_id", "case_id"])
        rw.writerow(["scenario", "rep", "engine", "outcome", "why", "beta", "source"])
        for number, table in enumerate(tables):
            case = f"{number:06d}"
            pw.writerow([scenario, case])
            raw_ok = all(cell > 0 for cell in table)
            # Use a scalar source-export formula independent of product analysis.
            raw = (
                sum(sign * math.log(cell) for sign, cell in zip([1, -1, -1, 1], table))
                if raw_ok
                else ""
            )
            half = sum(
                sign * math.log(float(cell) + 0.5)
                for sign, cell in zip([1, -1, -1, 1], table)
            )
            rw.writerow(
                [
                    scenario,
                    case,
                    "raw_log_OR",
                    "returned" if raw_ok else "zero_cell",
                    "" if raw_ok else "zero count cell makes raw log OR unavailable",
                    raw,
                    f"{scenario}/{case}/raw",
                ]
            )
            rw.writerow(
                [
                    scenario,
                    case,
                    "always_add_half",
                    "returned",
                    "",
                    half,
                    f"{scenario}/{case}/half",
                ]
            )
    return study_path, planned_path, raw_path, mapping_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=100000)
    parser.add_argument("--scenario-index", type=int, choices=range(4), required=True)
    args = parser.parse_args()
    if args.replicates < 1:
        parser.error("replicates must be positive")
    import numpy as np

    px, odds = list(itertools.product((0.25, 0.5), (2, 5)))[args.scenario_index]
    probabilities = [
        (1 - px) / 2,
        (1 - px) / 2,
        px / (1 + odds),
        px * odds / (1 + odds),
    ]
    rng = np.random.default_rng(np.random.SeedSequence([20261008, args.scenario_index]))
    tables = rng.multinomial(50, probabilities, size=args.replicates)
    paths = export_tables(tables, px, odds, args.output_dir)
    print(
        json.dumps(
            dict(
                paths=[str(p) for p in paths],
                planned=args.replicates,
                raw_failures=int((tables == 0).any(axis=1).sum()),
            )
        )
    )


if __name__ == "__main__":
    main()
