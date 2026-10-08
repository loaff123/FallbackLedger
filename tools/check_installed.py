"""Build-independent wheel/sdist installation and outside-checkout CLI check."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import venv
import zipfile
from pathlib import Path


def audit_archive(path):
    path = Path(path)
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    for name in names:
        parts = Path(name).parts
        if (
            any(
                p
                in {
                    ".git",
                    ".venv",
                    ".superpowers",
                    "__pycache__",
                    "node_modules",
                    "Rlibrary",
                }
                for p in parts
            )
            or name.endswith((".dta", ".wasm", ".rds"))
            or "docs/superpowers/" in name
        ):
            raise ValueError(f"disallowed distribution content: {name}")
    return sorted(names)


def run(command, cwd, log):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    proc = subprocess.run(
        [str(c) for c in command], cwd=cwd, env=env, text=True, capture_output=True
    )
    with Path(log).open("a") as stream:
        stream.write(
            "$ " + " ".join(map(str, command)) + "\n" + proc.stdout + proc.stderr + "\n"
        )
    if proc.returncode:
        raise RuntimeError(f"Command exited {proc.returncode}; see {log}")
    return proc.stdout


def hashes(paths):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def exercise(python, fixture, cwd, log):
    inputs = [
        fixture / "study.json",
        fixture / "planned.csv",
        fixture / "results.jsonl",
    ]
    before = hashes(inputs)
    location = run(
        [python, "-I", "-c", "import fallbackledger; print(fallbackledger.__file__)"],
        cwd,
        log,
    ).strip()
    if "site-packages" not in location or not Path(location).resolve().is_relative_to(
        Path(python).parent.parent.resolve()
    ):
        raise AssertionError(f"Installed check imported outside its venv: {location}")
    common = ["--study", inputs[0], "--planned", inputs[1], "--results", inputs[2]]
    run(
        [
            python,
            "-I",
            "-m",
            "fallbackledger",
            "validate",
            *common,
            "--out",
            cwd / "validation.json",
        ],
        cwd,
        log,
    )
    run(
        [
            python,
            "-I",
            "-m",
            "fallbackledger",
            "replay",
            *common,
            "--out",
            cwd / "replay.json",
            "--csv",
            cwd / "replay.csv",
        ],
        cwd,
        log,
    )
    run(
        [
            python,
            "-I",
            "-m",
            "fallbackledger",
            "summarize",
            *common,
            "--output-dir",
            cwd / "report",
        ],
        cwd,
        log,
    )
    summary = json.loads((cwd / "report" / "summary.json").read_text())
    point = next(
        m
        for m in summary["metrics"]
        if m["subject"] == {"kind": "policy", "id": "point"} and m["metric"] == "bias"
    )
    assert (point["value"], point["n"], point["planned_n"]) == (3.25, 4, 6)
    assert hashes(inputs) == before
    # A distinct native source shape exercises the actual import-results command.
    native = cwd / "native.csv"
    native.write_text("rep,engine,value\n01,A,2\n02,A,\n")
    mapping = cwd / "mapping.json"
    mapping.write_text(
        json.dumps(
            dict(
                schema_version=1,
                columns=dict(case_id="rep", method_id="engine", estimate="value"),
                constants=dict(
                    scenario_id="s",
                    reason="",
                    interval_status="not_provided",
                    lower=None,
                    upper=None,
                    source_record_id="native",
                    estimand_id="theta",
                    scale="real",
                ),
                status_from_estimate=True,
            )
        )
    )
    run(
        [
            python,
            "-I",
            "-m",
            "fallbackledger",
            "import-results",
            "--input",
            native,
            "--mapping",
            mapping,
            "--out",
            cwd / "imported.jsonl",
        ],
        cwd,
        log,
    )
    imported = [
        json.loads(line) for line in (cwd / "imported.jsonl").read_text().splitlines()
    ]
    assert [r["status"] for r in imported] == ["ok", "unknown"]
    return dict(
        import_path=location,
        input_sha256=before,
        metric=point,
        report_files=sorted(p.name for p in (cwd / "report").iterdir()),
        semantic_digest=summary["canonical_digest"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "examples" / "tiny",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output directory must be new to prove fresh environments")
    output.mkdir(parents=True)
    artifacts = sorted(args.dist.resolve().glob("*.whl")) + sorted(
        args.dist.resolve().glob("*.tar.gz")
    )
    if len(artifacts) != 2:
        parser.error("Expected exactly one wheel and one sdist")
    results = []
    for artifact in artifacts:
        kind = "wheel" if artifact.suffix == ".whl" else "sdist"
        root = output / kind
        root.mkdir()
        env = root / "venv"
        cwd = root / "outside-checkout"
        cwd.mkdir()
        fixture = cwd / "inputs"
        shutil.copytree(args.fixtures.resolve(), fixture)
        members = audit_archive(artifact)
        venv.EnvBuilder(with_pip=True).create(env)
        python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        log = root / "installed.log"
        run([python, "-m", "pip", "install", artifact], cwd, log)
        result = exercise(python, fixture, cwd, log)
        result.update(
            artifact=artifact.name,
            sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            members=members,
        )
        results.append(result)
    assert results[0]["semantic_digest"] == results[1]["semantic_digest"]
    (output / "installed-results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                installed_artifacts=2,
                verified=True,
                results=str(output / "installed-results.json"),
            )
        )
    )


if __name__ == "__main__":
    main()
