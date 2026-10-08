import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def write_inputs(tmp_path, data):
    study, planned, results = data
    s = tmp_path / "study.json"
    s.write_text(json.dumps(study))
    p = tmp_path / "planned.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scenario_id", "case_id"])
        w.writeheader()
        w.writerows(planned)
    r = tmp_path / "results.jsonl"
    r.write_text("".join(json.dumps(row) + "\n" for row in results))
    return s, p, r


def cli(*args):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / "src"))
    return subprocess.run(
        [sys.executable, "-m", "fallbackledger", *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
    )


def arguments(inputs):
    s, p, r = inputs
    return ["--study", s, "--planned", p, "--results", r]


def test_cli_end_to_end_and_input_immutability(tmp_path, data):
    inputs = write_inputs(tmp_path, data)
    before = [p.read_bytes() for p in inputs]
    a = arguments(inputs)
    assert cli("validate", *a, "--out", tmp_path / "validation.json").returncode == 0
    assert (
        cli(
            "replay",
            *a,
            "--out",
            tmp_path / "replay.json",
            "--csv",
            tmp_path / "replay.csv",
        ).returncode
        == 0
    )
    run = cli("summarize", *a, "--output-dir", tmp_path / "report")
    assert run.returncode == 0, run.stderr
    expected = {
        "validation.json",
        "replay.json",
        "replay.csv",
        "summary.json",
        "metrics.csv",
        "cohorts.csv",
        "summary.txt",
        "report.html",
    }
    assert {p.name for p in (tmp_path / "report").iterdir()} == expected
    summary = json.loads((tmp_path / "report" / "summary.json").read_text())
    bias = next(
        m
        for m in summary["metrics"]
        if m["subject"] == {"kind": "policy", "id": "point"} and m["metric"] == "bias"
    )
    assert bias["value"] == 3.25 and bias["n"] == 4 and bias["planned_n"] == 6
    assert [p.read_bytes() for p in inputs] == before


def test_require_complete_writes_report_then_exit3(tmp_path, data):
    inputs = write_inputs(tmp_path, data)
    result = cli(
        "summarize",
        *arguments(inputs),
        "--output-dir",
        tmp_path / "report",
        "--require-complete",
    )
    assert result.returncode == 3 and (tmp_path / "report" / "summary.json").exists()
    assert "incomplete" in result.stderr.lower()


def test_structural_error_is_actionable_exit2(tmp_path, data):
    data[2].append(data[2][0])
    inputs = write_inputs(tmp_path, data)
    result = cli("validate", *arguments(inputs), "--out", tmp_path / "validation.json")
    assert result.returncode == 2
    report = json.loads((tmp_path / "validation.json").read_text())
    assert any(i["code"] == "duplicate_result" for i in report["issues"])


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_overwrite_never_mutates_input_via_alias(tmp_path, data, alias):
    inputs = write_inputs(tmp_path, data)
    source = inputs[0]
    before = source.read_bytes()
    target = source if alias == "direct" else tmp_path / "alias.json"
    if alias == "symlink":
        target.symlink_to(source)
    if alias == "hardlink":
        os.link(source, target)
    result = cli("validate", *arguments(inputs), "--out", target, "--overwrite")
    assert result.returncode == 2 and "input" in result.stderr.lower()
    assert source.read_bytes() == before


def test_existing_output_requires_explicit_overwrite(tmp_path, data):
    inputs = write_inputs(tmp_path, data)
    target = tmp_path / "validation.json"
    target.write_text("existing")
    result = cli("validate", *arguments(inputs), "--out", target)
    assert result.returncode == 2 and target.read_text() == "existing"
    assert (
        cli("validate", *arguments(inputs), "--out", target, "--overwrite").returncode
        == 0
    )


def test_row_permutation_changes_byte_provenance_not_semantics(tmp_path, data):
    inputs = write_inputs(tmp_path, data)
    a = arguments(inputs)
    assert cli("summarize", *a, "--output-dir", tmp_path / "one").returncode == 0
    data[1].reverse()
    data[2].reverse()
    write_inputs(tmp_path, data)
    assert cli("summarize", *a, "--output-dir", tmp_path / "two").returncode == 0
    one = json.loads((tmp_path / "one" / "summary.json").read_text())
    two = json.loads((tmp_path / "two" / "summary.json").read_text())
    assert one.pop("metadata")["input_bytes"] != two.pop("metadata")["input_bytes"]
    assert one == two


@pytest.mark.parametrize(
    "mapping",
    [[], {"schema_version": 1, "columns": []}, {"schema_version": 1, "columns": None}],
)
def test_malformed_mapping_reports_exit2_without_traceback(tmp_path, data, mapping):
    inputs = write_inputs(tmp_path, data)
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(mapping))
    result = cli(
        "validate",
        *arguments(inputs),
        "--mapping",
        path,
        "--out",
        tmp_path / "validation.json",
    )
    assert result.returncode == 2 and "Traceback" not in result.stderr


def test_empty_native_csv_requires_declared_mapping_columns(tmp_path):
    source = tmp_path / "native.csv"
    source.write_text("wrong\n")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "columns": {"estimate": "beta"},
                "status_from_estimate": True,
            }
        )
    )
    result = cli(
        "import-results",
        "--input",
        source,
        "--mapping",
        mapping,
        "--out",
        tmp_path / "results.jsonl",
    )
    assert result.returncode == 2 and "missing" in result.stderr.lower()
