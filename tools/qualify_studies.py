"""Run two independently shaped study exports through an installed CLI.

NumPy/pandas belong to --source-python only. The analysis interpreter needs only
an installed FallbackLedger package. All report rows are retained, one odds-ratio
scenario per invocation, with no cross-scenario pooling.
"""

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, log):
    with Path(log).open("a") as stream:
        stream.write("$ " + " ".join(map(str, command)) + "\n")
        stream.flush()
        subprocess.run(
            [str(c) for c in command],
            check=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )


def matches(actual, expected):
    if not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-13):
        raise AssertionError(
            f"Numerical mismatch: {actual!r} vs frozen reference {expected!r}"
        )


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def analyze(python, directory, log):
    input_paths = [
        directory / name
        for name in ["study.json", "planned.csv", "native_results.csv", "mapping.json"]
    ]
    before = {p.name: file_hash(p) for p in input_paths}
    for command in ("validate", "replay", "summarize"):
        args = [
            python,
            "-I",
            "-m",
            "fallbackledger",
            command,
            "--study",
            input_paths[0],
            "--planned",
            input_paths[1],
            "--results",
            input_paths[2],
            "--mapping",
            input_paths[3],
        ]
        if command == "validate":
            args += ["--out", directory / "validation.json"]
        elif command == "replay":
            args += [
                "--out",
                directory / "replay.json",
                "--csv",
                directory / "replay.csv",
            ]
        else:
            args += ["--output-dir", directory / "report"]
        run(
            [
                sys.executable,
                ROOT / "tools" / "measure_cli.py",
                "--record",
                directory / f"{command}-time.json",
                "--log",
                directory / f"{command}.log",
                "--",
                *args,
            ],
            log,
        )
    assert {p.name: file_hash(p) for p in input_paths} == before
    with (directory / "report" / "metrics.csv").open(newline="") as stream:
        metrics = list(csv.DictReader(stream))
    with (directory / "report" / "replay.csv").open(newline="") as stream:
        counts = {}
        for row in csv.DictReader(stream):
            key = (row["state"], row["selected_method"])
            counts[key] = counts.get(key, 0) + 1
    # The report and standalone replay must be byte-identical semantic exports.
    assert file_hash(directory / "replay.csv") == file_hash(
        directory / "report" / "replay.csv"
    )
    return metrics, counts, before


def metric(rows, scenario, kind, id, name, cohort):
    selected = [
        r
        for r in rows
        if r["scenario_id"] == scenario
        and r["subject_kind"] == kind
        and r["subject_id"] == id
        and r["metric"] == name
        and json.loads(r["cohort_id"]) == cohort
    ]
    assert len(selected) == 1, selected
    return selected[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-python", type=Path, required=True)
    parser.add_argument("--source-python", type=Path, required=True)
    parser.add_argument("--siman-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("Use a new output directory for qualification")
    out.mkdir(parents=True)
    log = out / "qualification.log"
    evidence = []
    frozen = json.loads(
        (ROOT / "examples" / "odds_ratio" / "expected.json").read_text()
    )
    for number, expected in enumerate(frozen["scenarios"]):
        destination = out / f"odds-{number}"
        run(
            [
                args.source_python,
                ROOT / "examples" / "odds_ratio" / "export.py",
                "--scenario-index",
                number,
                "--output-dir",
                destination,
            ],
            log,
        )
        rows, counts, hashes = analyze(args.analysis_python, destination, log)
        assert counts == {
            ("usable", "raw_log_OR"): expected["raw_success"],
            ("usable", "always_add_half"): expected["raw_failure"],
        }
        scenario = f"px{expected['px']}_or{expected['odds_ratio']}"
        for subject, reference in expected["method_specific_success"].items():
            kind = "policy" if subject == "raw_then_add_half" else "method"
            cohort = ["own", kind, subject, "point"]
            bias = metric(rows, scenario, kind, subject, "bias", cohort)
            mse = metric(rows, scenario, kind, subject, "mse", cohort)
            assert int(bias["n"]) == reference["n"]
            matches(float(bias["value"]), reference["bias"])
            matches(float(bias["mcse"]), reference["bias_mcse"])
            matches(float(mse["value"]), reference["mse"])
            common = metric(
                rows, scenario, kind, subject, "bias", ["common", "raw_success"]
            )
            matches(
                float(common["value"]), expected["joint_raw_success"][subject]["bias"]
            )
        evidence.append(
            dict(
                study="odds_ratio",
                scenario=scenario,
                planned=100000,
                records=200000,
                raw_failures=expected["raw_failure"],
                checks="Exact route counts and frozen bias/MSE/bias-MCSE/conditional-cohort agreement",
                input_sha256=hashes,
                summarize_performance=json.loads(
                    (destination / "summarize-time.json").read_text()
                ),
                report_bytes=sum(
                    p.stat().st_size for p in (destination / "report").iterdir()
                ),
            )
        )
        print(
            f"Qualified {scenario}: {expected['raw_failure']}/100000 raw failures",
            flush=True,
        )
    destination = out / "siman"
    run(
        [
            args.source_python,
            ROOT / "examples" / "siman" / "export.py",
            "--input-dta",
            args.siman_data,
            "--output-dir",
            destination,
        ],
        log,
    )
    rows, counts, hashes = analyze(args.analysis_python, destination, log)
    assert counts == {}
    expected = json.loads((ROOT / "examples" / "siman" / "expected.json").read_text())
    for group in expected["groups"]:
        cohort = ["own", "method", group["method"], "point"]
        bias = metric(
            rows, group["scenario"], "method", group["method"], "bias", cohort
        )
        mse = metric(rows, group["scenario"], "method", group["method"], "mse", cohort)
        assert int(bias["n"]) == 1000
        matches(float(bias["value"]), group["bias"])
        matches(float(bias["mcse"]), group["bias_mcse"])
        matches(float(mse["value"]), group["mse"])
    for paired in expected["paired_CCA_minus_MI"]:
        row = metric(
            rows,
            paired["scenario"],
            "comparison",
            "CCA-minus-MI",
            "bias",
            ["common", "CCA_MI"],
        )
        assert int(row["n"]) == 1000
        matches(float(row["value"]), paired["mean_difference"])
        matches(float(row["mcse"]), paired["paired_mcse"])
    evidence.append(
        dict(
            study="siman",
            planned=3000,
            records=9000,
            missing_df_preserved=6000,
            checks="Nine n1000 groups and three paired contrasts match independently frozen source summaries",
            input_sha256=hashes,
            source_sha256=file_hash(args.siman_data),
            summarize_performance=json.loads(
                (destination / "summarize-time.json").read_text()
            ),
            report_bytes=sum(
                p.stat().st_size for p in (destination / "report").iterdir()
            ),
        )
    )
    (out / "verified-results.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("TWO_STUDY_CLI_QUALIFICATION_PASSED", flush=True)


if __name__ == "__main__":
    main()
