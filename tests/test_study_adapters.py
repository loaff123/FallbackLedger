import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location("adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_odds_ratio_original_export_mapping_runs_cli(tmp_path):
    adapter = load(ROOT / "examples" / "odds_ratio" / "export.py")
    # Small deterministic tables avoid optional NumPy in the ordinary test suite.
    paths = adapter.export_tables(
        [[10, 10, 10, 20], [0, 20, 5, 25], [15, 15, 15, 5]], 0.5, 2, tmp_path
    )
    from fallbackledger import replay, summarize
    from fallbackledger.io import load_inputs

    report = load_inputs(*paths)
    assert report.validated is not None, report.issues
    outputs = replay(report.validated).outcomes
    assert [o.selected.method_id for o in outputs] == [
        "raw_log_OR",
        "always_add_half",
        "raw_log_OR",
    ]
    assert len(summarize(report.validated, replay(report.validated)).metrics) > 0


def test_siman_mapping_preserves_missing_df_point_outputs(tmp_path):
    adapter = load(ROOT / "examples" / "siman" / "export.py")
    rows = [
        dict(dgm="MCAR", rep=i, method=m, b=float(i), se=1, df=None)
        for i in [1, 2]
        for m in ["Full", "CCA", "MI"]
    ]
    paths = adapter.export_records(
        rows, tmp_path, planned_cases=[("MCAR", "1"), ("MCAR", "2")]
    )
    from fallbackledger.io import load_inputs

    report = load_inputs(*paths)
    assert report.validated is not None, report.issues
    assert len(report.validated.cases) == 2 and len(report.validated.results) == 6
    assert all(r.status == "ok" for r in report.validated.results)


def test_siman_declared_plan_is_not_inferred_from_observed_rows(tmp_path):
    adapter = load(ROOT / "examples" / "siman" / "export.py")
    rows = [
        dict(dgm="MCAR", rep=1, method=m, b=1, se=1, df=None)
        for m in ["Full", "CCA", "MI"]
    ]
    declared = [("MCAR", "1"), ("MCAR", "2")]
    paths = adapter.export_records(rows, tmp_path, planned_cases=declared)
    from fallbackledger.io import load_inputs

    report = load_inputs(*paths)
    assert len(report.validated.cases) == 2 and len(report.validated.results) == 3
