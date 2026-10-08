import json

import pytest

from fallbackledger.io import load_json, map_results


def mapping():
    return dict(
        schema_version=1,
        columns=dict(case_id="rep", method_id="method", estimate="b"),
        constants=dict(
            scenario_id="s",
            estimand_id="theta",
            scale="real",
            source_record_id="source",
            interval_status="not_provided",
            lower=None,
            upper=None,
            reason="",
        ),
        status_from_estimate=True,
    )


def test_extra_df_does_not_drop_point_estimate():
    mapped = map_results([dict(rep="001", method="A", b="2.5", df="")], mapping())
    assert mapped[0]["case_id"] == "001"
    assert mapped[0]["status"] == "ok" and mapped[0]["estimate"] == 2.5
    assert "df" not in mapped[0]


def test_legacy_blank_is_unknown_not_failure():
    mapped = map_results([dict(rep="1", method="A", b="")], mapping())
    assert (
        mapped[0]["status"] == "unknown"
        and mapped[0]["reason"] == "import_missing_estimate"
    )
    assert mapped[0]["interval_status"] == "unknown"


def test_explicit_mapped_failure_is_preserved():
    m = mapping()
    m.pop("status_from_estimate")
    m["columns"]["status"] = "code"
    m["constants"]["reason"] = "documented failure"
    m["values"] = {"status": {"ERR": "failed"}}
    out = map_results([dict(rep="1", method="A", b="", code="ERR")], m)[0]
    assert out["status"] == "failed" and out["reason"] == "documented failure"


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_strict_json_rejects_duplicates_and_nonstandard_numbers(tmp_path, text):
    p = tmp_path / "bad.json"
    p.write_text(text)
    with pytest.raises(ValueError):
        load_json(p)


def test_ambiguous_mapping_is_rejected():
    m = mapping()
    m["constants"]["estimate"] = 1
    with pytest.raises(ValueError, match="both"):
        map_results([], m)


@pytest.mark.parametrize("value", ["NaN", "inf", "oops"])
def test_malformed_or_infinite_point_is_not_unknown(value):
    with pytest.raises(ValueError):
        map_results([dict(rep="1", method="A", b=value)], mapping())


@pytest.mark.parametrize(
    "mapping_value",
    [
        {"schema_version": True},
        {"schema_version": 1, "constants": {"reason": []}},
        {"schema_version": 1, "constants": {"estimate": {}}},
    ],
)
def test_mapping_schema_version_and_constants_are_strict(mapping_value):
    with pytest.raises(ValueError):
        map_results([], mapping_value)


def test_canonical_jsonl_does_not_coerce_numeric_strings(tmp_path, data):
    import csv

    from fallbackledger.io import load_inputs

    study, planned, records = data
    s = tmp_path / "study.json"
    s.write_text(json.dumps(study))
    p = tmp_path / "planned.csv"
    with p.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["scenario_id", "case_id"])
        writer.writeheader()
        writer.writerows(planned)
    records[0]["estimate"] = "10"
    r = tmp_path / "results.jsonl"
    r.write_text("".join(json.dumps(row) + "\n" for row in records))
    report = load_inputs(s, p, r)
    assert report.validated is None and any(
        i.code == "invalid_number" for i in report.issues
    )
