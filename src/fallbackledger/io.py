"""Strict portable input parsing and non-executable field mapping."""

import csv
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from .schema import OPTIONAL_RESULT_FIELDS, RESULT_FIELDS, validate


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"Duplicate JSON field: {key}")
        out[key] = value
    return out


def _constant(value):
    raise ValueError(f"Nonstandard JSON number: {value}")


def loads_json(text):
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)


def load_json(path):
    return loads_json(Path(path).read_text(encoding="utf-8"))


def read_records(path, required_columns=None, allowed_columns=None):
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if path.suffix.lower() in (".jsonl", ".ndjson"):
            for number, line in enumerate(stream, 1):
                if line.strip():
                    try:
                        row = loads_json(line)
                        if not isinstance(row, Mapping):
                            raise ValueError("JSONL record must be an object")
                        yield row
                    except ValueError as error:
                        raise ValueError(f"{path}:{number}: {error}") from error
        else:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError(f"{path}: missing CSV header")
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError(f"{path}: duplicate CSV header")
            if required_columns is not None and set(required_columns) - set(
                reader.fieldnames
            ):
                raise ValueError(
                    f"{path}: missing required CSV columns {sorted(set(required_columns) - set(reader.fieldnames))}"
                )
            if allowed_columns is not None and set(reader.fieldnames) - set(
                allowed_columns
            ):
                raise ValueError(
                    f"{path}: unexpected CSV columns {sorted(set(reader.fieldnames) - set(allowed_columns))}"
                )
            for number, row in enumerate(reader, 2):
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f"{path}:{number}: mismatched CSV column count")
                yield row


def _numeric(value, field, missing):
    if value is None or (isinstance(value, str) and value in missing):
        return None
    if field in ("lower", "upper") and value in ("-inf", "inf"):
        return value
    if isinstance(value, bool):
        raise ValueError(f"{field}: boolean is not a number")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{field}: invalid numeric value {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(
            f"{field}: nonfinite values require explicit -inf/inf interval strings"
        )
    return number


def map_results(records, mapping):
    allowed = {
        "schema_version",
        "columns",
        "constants",
        "values",
        "status_from_estimate",
        "missing_values",
    }
    if (
        not isinstance(mapping, Mapping)
        or set(mapping) - allowed
        or type(mapping.get("schema_version")) is not int
        or mapping.get("schema_version") != 1
    ):
        raise ValueError("Invalid mapping schema or fields")
    columns = mapping.get("columns", {})
    constants = mapping.get("constants", {})
    values = mapping.get("values", {})
    if not all(isinstance(x, Mapping) for x in (columns, constants, values)):
        raise ValueError("Mapping columns/constants/values must be objects")
    fields = RESULT_FIELDS | OPTIONAL_RESULT_FIELDS
    if any(
        value is not None and not isinstance(value, (str, int, float, bool))
        for value in constants.values()
    ):
        raise ValueError("Mapping constants must be scalar values or null")
    if set(columns) & set(constants):
        raise ValueError("A field cannot have both a column and a constant")
    if (set(columns) | set(constants) | set(values)) - fields:
        raise ValueError("Mapping names an unknown canonical field")
    if any(not isinstance(x, str) or not x for x in columns.values()):
        raise ValueError("Source column names must be nonempty strings")
    if any(
        not isinstance(x, Mapping)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in x.items())
        for x in values.values()
    ):
        raise ValueError("Value maps must map exact strings to strings")
    derive = mapping.get("status_from_estimate", False)
    if type(derive) is not bool:
        raise ValueError("status_from_estimate must be boolean")
    if derive and ("status" in columns or "status" in constants):
        raise ValueError("Derived status cannot also be bound explicitly")
    markers = mapping.get("missing_values", [])
    if not isinstance(markers, list) or any(not isinstance(x, str) for x in markers):
        raise ValueError("missing_values must be a string array")
    missing = {""} | set(markers)
    out = []
    for number, raw in enumerate(records, 1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Record {number}: expected an object")
        absent = set(columns.values()) - set(raw)
        if absent:
            raise ValueError(
                f"Record {number}: missing source columns {sorted(absent)}"
            )
        row = dict(constants)
        row.update((field, raw[col]) for field, col in columns.items())
        for field, value_map in values.items():
            if field in row:
                row[field] = value_map.get(str(row[field]), row[field])
        for field in ("estimate", "lower", "upper"):
            if field in row:
                row[field] = _numeric(row[field], field, missing)
        if derive:
            if "estimate" not in row:
                raise ValueError("Derived status needs an estimate binding")
            row["status"] = "ok" if row["estimate"] is not None else "unknown"
            if row["status"] == "unknown":
                row.update(
                    reason="import_missing_estimate",
                    interval_status="unknown",
                    lower=None,
                    upper=None,
                )
        if (
            row.get("status") in ("failed", "unknown", "inapplicable")
            and row.get("interval_status") == "not_provided"
        ):
            row["interval_status"] = "unknown"
        out.append(row)
    return tuple(out)


def _canonical(records, parse_csv=True):
    for raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError("Canonical result must be an object")
        row = dict(raw)
        if parse_csv:
            for field in ("estimate", "lower", "upper"):
                if field in row:
                    row[field] = _numeric(row[field], field, {""})
        for field in OPTIONAL_RESULT_FIELDS:
            if row.get(field) == "":
                row[field] = None
        yield row


def load_inputs(study_path, planned_path, results_path, mapping_path=None):
    study = load_json(study_path)
    if mapping_path:
        mapping = load_json(mapping_path)
        map_results((), mapping)  # Validate mapping types before header access.
        raw = read_records(
            results_path, required_columns=mapping.get("columns", {}).values()
        )
        results = map_results(raw, mapping)
    else:
        results = _canonical(
            read_records(
                results_path, RESULT_FIELDS, RESULT_FIELDS | OPTIONAL_RESULT_FIELDS
            ),
            parse_csv=Path(results_path).suffix.lower() not in (".jsonl", ".ndjson"),
        )
    report = validate(
        study,
        read_records(
            planned_path, {"scenario_id", "case_id"}, {"scenario_id", "case_id"}
        ),
        results,
    )
    if report.validated:
        paths = [
            ("study", study_path),
            ("planned", planned_path),
            ("results", results_path),
        ]
        if mapping_path:
            paths.append(("mapping", mapping_path))
        provenance = []
        for label, path in paths:
            h = hashlib.sha256()
            with Path(path).open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            provenance.extend(
                (
                    (label + "_path", str(Path(path).resolve())),
                    (label + "_sha256", h.hexdigest()),
                )
            )
        report = replace(
            report, validated=replace(report.validated, provenance=tuple(provenance))
        )
    return report
