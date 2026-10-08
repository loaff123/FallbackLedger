"""Validate explicit study semantics without interpreting missingness as failure."""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict

from .models import (
    Assumptions,
    CaseKey,
    CohortSpec,
    Comparison,
    EntityRef,
    Issue,
    Method,
    MethodResult,
    Policy,
    Scenario,
    StudySpec,
    ValidatedStudy,
    ValidationReport,
)

RESULT_FIELDS = {
    "scenario_id",
    "case_id",
    "method_id",
    "status",
    "reason",
    "estimate",
    "interval_status",
    "lower",
    "upper",
    "source_record_id",
    "estimand_id",
    "scale",
}
OPTIONAL_RESULT_FIELDS = {"dataset_id", "configuration_id"}


class Invalid(ValueError):
    def __init__(self, code, path, message):
        self.issue = Issue("error", code, path, message)
        super().__init__(f"{path}: {message}")


def _fields(value, required, optional, path):
    if not isinstance(value, Mapping):
        raise Invalid("invalid_object", path, "Expected an object")
    unknown = set(value) - set(required) - set(optional)
    if unknown:
        raise Invalid(
            "unknown_field", path, f"Unknown fields: {sorted(unknown, key=str)}"
        )
    missing = set(required) - set(value)
    if missing:
        raise Invalid("missing_field", path, f"Missing fields: {sorted(missing)}")


def _text(value, path, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise Invalid(
            "invalid_id",
            path,
            "Expected a nonempty string" if not empty else "Expected a string",
        )
    return value


def _number(value, path, bounds=False):
    if bounds and isinstance(value, str) and value in ("-inf", "inf"):
        return float(value)
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise Invalid(
            "invalid_number",
            path,
            "Expected a finite number"
            if not bounds
            else "Expected a number or -inf/inf",
        )
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise Invalid(
            "invalid_number", path, "Number is outside floating range"
        ) from None
    if math.isnan(number) or (not bounds and not math.isfinite(number)):
        raise Invalid(
            "invalid_number", path, "NaN and nonfinite point values are not allowed"
        )
    return number


def _choice(value, choices, path):
    if not isinstance(value, str) or value not in choices:
        raise Invalid("invalid_choice", path, f"Expected one of {sorted(choices)}")
    return value


def _list(value, path, nonempty=False):
    if not isinstance(value, (list, tuple)) or (nonempty and not value):
        raise Invalid(
            "invalid_array",
            path,
            "Expected an array" + (" with at least one item" if nonempty else ""),
        )
    return value


def _unique(values, path):
    if len(set(values)) != len(values):
        raise Invalid("duplicate_id", path, "Duplicate values are not allowed")
    return values


def _ref(raw, path, methods, policies):
    _fields(raw, {"kind", "id"}, set(), path)
    kind = _choice(raw["kind"], {"method", "policy"}, path + ".kind")
    id = _text(raw["id"], path + ".id")
    if id not in (methods if kind == "method" else policies):
        raise Invalid("unknown_reference", path, f"Unknown {kind} {id!r}")
    return EntityRef(kind, id)


def _spec(raw):
    required = {
        "schema_version",
        "study_id",
        "estimand",
        "scenarios",
        "methods",
        "assumptions",
        "metrics",
        "policies",
        "cohorts",
        "comparisons",
    }
    _fields(
        raw, required, {"nominal_interval_level", "description", "provenance"}, "study"
    )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise Invalid(
            "schema_version",
            "study.schema_version",
            "Only schema version 1 is supported",
        )
    _fields(raw["estimand"], {"id", "label", "scale"}, set(), "study.estimand")
    e = raw["estimand"]
    for key in e:
        _text(e[key], "study.estimand." + key)
    metrics = tuple(
        _choice(x, {"bias", "mse", "coverage", "completion"}, "study.metrics")
        for x in _list(raw["metrics"], "study.metrics", True)
    )
    _unique(metrics, "study.metrics")
    _fields(
        raw["assumptions"],
        {"independent_cases", "finite_second_moments"}
        | ({"finite_mse_contribution_variance"} if "mse" in metrics else set()),
        {"finite_mse_contribution_variance"},
        "study.assumptions",
    )
    for key, value in raw["assumptions"].items():
        if type(value) is not bool:
            raise Invalid(
                "invalid_boolean", "study.assumptions." + key, "Expected true or false"
            )
    assumptions = Assumptions(**raw["assumptions"])
    level = raw.get("nominal_interval_level")
    if level is not None:
        level = _number(level, "study.nominal_interval_level")
        if not 0 < level < 1:
            raise Invalid(
                "invalid_level",
                "study.nominal_interval_level",
                "Expected level strictly between 0 and 1",
            )
    if "coverage" in metrics and level is None:
        raise Invalid(
            "missing_field",
            "study.nominal_interval_level",
            "Coverage requires the nominal interval level",
        )
    scenarios = []
    for i, s in enumerate(_list(raw["scenarios"], "study.scenarios", True)):
        path = f"study.scenarios[{i}]"
        _fields(s, {"id", "truth"}, set(), path)
        scenarios.append(
            Scenario(_text(s["id"], path + ".id"), _number(s["truth"], path + ".truth"))
        )
    _unique([s.id for s in scenarios], "study.scenarios")
    methods = []
    for i, m in enumerate(_list(raw["methods"], "study.methods", True)):
        path = f"study.methods[{i}]"
        _fields(m, {"id", "version"}, set(), path)
        methods.append(
            Method(_text(m["id"], path + ".id"), _text(m["version"], path + ".version"))
        )
    mids = set(_unique([m.id for m in methods], "study.methods"))
    policies = []
    for i, p in enumerate(_list(raw["policies"], "study.policies")):
        path = f"study.policies[{i}]"
        _fields(p, {"id", "methods", "requirement", "inapplicable"}, set(), path)
        chain = tuple(
            _text(x, path + ".methods")
            for x in _list(p["methods"], path + ".methods", True)
        )
        _unique(chain, path + ".methods")
        if set(chain) - mids:
            raise Invalid(
                "unknown_method",
                path + ".methods",
                "Policy references an undeclared method",
            )
        policies.append(
            Policy(
                _text(p["id"], path + ".id"),
                chain,
                _choice(p["requirement"], {"point", "interval"}, path + ".requirement"),
                _choice(p["inapplicable"], {"stop", "skip"}, path + ".inapplicable"),
            )
        )
    pids = set(_unique([p.id for p in policies], "study.policies"))
    cohorts = []
    for i, c in enumerate(_list(raw["cohorts"], "study.cohorts")):
        path = f"study.cohorts[{i}]"
        _fields(c, {"id", "members", "requirement"}, set(), path)
        members = tuple(
            _ref(r, path + ".members", mids, pids)
            for r in _list(c["members"], path + ".members", True)
        )
        _unique(members, path + ".members")
        cohorts.append(
            CohortSpec(
                _text(c["id"], path + ".id"),
                tuple(sorted(members)),
                _choice(c["requirement"], {"point", "interval"}, path + ".requirement"),
            )
        )
    _unique([c.id for c in cohorts], "study.cohorts")
    cmap = {c.id: c for c in cohorts}
    comparisons = []
    for i, c in enumerate(_list(raw["comparisons"], "study.comparisons")):
        path = f"study.comparisons[{i}]"
        _fields(c, {"id", "left", "right", "cohort", "metrics"}, set(), path)
        left = _ref(c["left"], path + ".left", mids, pids)
        right = _ref(c["right"], path + ".right", mids, pids)
        cohort = _text(c["cohort"], path + ".cohort")
        cm = tuple(
            _choice(x, {"bias", "mse", "coverage"}, path + ".metrics")
            for x in _list(c["metrics"], path + ".metrics", True)
        )
        _unique(cm, path + ".metrics")
        if (
            cohort not in cmap
            or left == right
            or not {left, right} <= set(cmap[cohort].members)
            or ("coverage" in cm and cmap[cohort].requirement != "interval")
        ):
            raise Invalid(
                "invalid_comparison",
                path,
                "Contrast requires distinct members in its named cohort; coverage needs an interval cohort",
            )
        if set(cm) - set(metrics):
            raise Invalid(
                "invalid_comparison",
                path,
                "Comparison metrics must also be requested study metrics",
            )
        comparisons.append(
            Comparison(_text(c["id"], path + ".id"), left, right, cohort, cm)
        )
    _unique([c.id for c in comparisons], "study.comparisons")
    provenance = raw.get("provenance", {})
    _fields(
        provenance,
        set(),
        {"dataset_id", "configuration_id", "source_url"},
        "study.provenance",
    )
    for key, value in provenance.items():
        _text(value, "study.provenance." + key)
    return StudySpec(
        1,
        _text(raw["study_id"], "study.study_id"),
        e["id"],
        e["label"],
        e["scale"],
        tuple(sorted(scenarios, key=lambda x: x.id)),
        tuple(sorted(methods, key=lambda x: x.id)),
        assumptions,
        metrics,
        tuple(sorted(policies, key=lambda x: x.id)),
        tuple(sorted(cohorts, key=lambda x: x.id)),
        tuple(sorted(comparisons, key=lambda x: x.id)),
        level,
        _text(raw.get("description", ""), "study.description", True),
        tuple(sorted(provenance.items())),
    )


def _result(raw, path, spec, grid, method_ids):
    _fields(raw, RESULT_FIELDS, OPTIONAL_RESULT_FIELDS, path)
    for field in (
        "scenario_id",
        "case_id",
        "method_id",
        "source_record_id",
        "estimand_id",
        "scale",
    ):
        _text(raw[field], path + "." + field)
    if CaseKey(raw["scenario_id"], raw["case_id"]) not in grid:
        raise Invalid("off_grid", path, "Result does not name a planned case")
    if raw["method_id"] not in method_ids:
        raise Invalid("unknown_method", path, "Result names an undeclared method")
    if raw["estimand_id"] != spec.estimand_id:
        raise Invalid(
            "incompatible_estimand", path, "Result estimand differs from study"
        )
    if raw["scale"] != spec.scale:
        raise Invalid("incompatible_scale", path, "Result scale differs from study")
    status = _choice(
        raw["status"], {"ok", "failed", "unknown", "inapplicable"}, path + ".status"
    )
    reason = _text(raw["reason"], path + ".reason", True)
    if status != "ok" and not reason.strip():
        raise Invalid(
            "missing_reason",
            path + ".reason",
            "Non-ok outputs need a documented reason",
        )
    estimate = raw["estimate"]
    if status == "ok":
        estimate = _number(estimate, path + ".estimate")
    elif estimate is not None:
        raise Invalid(
            "unexpected_estimate",
            path + ".estimate",
            "Non-ok outputs must have an absent estimate",
        )
    interval = _choice(
        raw["interval_status"],
        {"available", "failed", "not_provided", "unknown"},
        path + ".interval_status",
    )
    lower = raw["lower"]
    upper = raw["upper"]
    if status != "ok" and interval != "unknown":
        raise Invalid(
            "invalid_interval",
            path + ".interval_status",
            "Non-ok point outputs must use unknown interval status",
        )
    if interval == "available":
        lower = _number(lower, path + ".lower", True)
        upper = _number(upper, path + ".upper", True)
        if lower > upper:
            raise Invalid(
                "invalid_interval", path, "Interval lower bound exceeds upper bound"
            )
    elif lower is not None or upper is not None:
        raise Invalid("unexpected_bounds", path, "Only available intervals have bounds")
    if interval == "failed" and not reason.strip():
        raise Invalid(
            "missing_reason", path + ".reason", "Interval failure needs a reason"
        )
    for key in OPTIONAL_RESULT_FIELDS:
        value = raw.get(key)
        if value is not None:
            _text(value, path + "." + key)
        declared = dict(spec.provenance).get(key)
        if declared is not None and value != declared:
            raise Invalid(
                "incompatible_provenance",
                path + "." + key,
                "Result must match declared study provenance",
            )
    return MethodResult(
        raw["scenario_id"],
        raw["case_id"],
        raw["method_id"],
        status,
        reason,
        estimate,
        interval,
        lower,
        upper,
        raw["source_record_id"],
        raw["estimand_id"],
        raw["scale"],
        raw.get("dataset_id"),
        raw.get("configuration_id"),
    )


def logical_digest(spec, cases, results):
    # Feed one record at a time; avoid a second complete JSON copy of large studies.
    h = hashlib.sha256()

    def feed(obj):
        h.update(
            json.dumps(
                obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        )
        h.update(b"\n")

    feed(asdict(spec))
    for case in cases:
        feed((case.scenario_id, case.case_id))
    for row in results:
        d = asdict(row)
        for key in ("lower", "upper"):
            if d[key] is not None and math.isinf(d[key]):
                d[key] = "inf" if d[key] > 0 else "-inf"
        feed(d)
    return h.hexdigest()


def validate(study, planned, results):
    """Return immutable validated data or actionable structural errors.

    Missing planned method records produce a warning, not a fabricated failure.
    """
    issues = []
    try:
        spec = _spec(study)
    except Invalid as error:
        return ValidationReport((error.issue,), None)
    cases = []
    grid = set()
    scenarios = {s.id for s in spec.scenarios}
    for i, raw in enumerate(planned):
        try:
            path = f"planned[{i}]"
            _fields(raw, {"scenario_id", "case_id"}, set(), path)
            case = CaseKey(
                _text(raw["scenario_id"], path + ".scenario_id"),
                _text(raw["case_id"], path + ".case_id"),
            )
            if case.scenario_id not in scenarios:
                raise Invalid("unknown_scenario", path, "Undeclared scenario")
            if case in grid:
                raise Invalid("duplicate_case", path, "Duplicate planned case")
            grid.add(case)
            cases.append(case)
        except Invalid as error:
            issues.append(error.issue)
    for missing in scenarios - {c.scenario_id for c in cases}:
        issues.append(
            Issue(
                "error",
                "empty_scenario",
                "planned",
                f"Scenario {missing!r} has no planned cases",
            )
        )
    rows = []
    seen = set()
    mids = {m.id for m in spec.methods}
    for i, raw in enumerate(results):
        try:
            path = f"results[{i}]"
            row = _result(raw, path, spec, grid, mids)
            key = (row.scenario_id, row.case_id, row.method_id)
            if key in seen:
                raise Invalid(
                    "duplicate_result",
                    path,
                    "Duplicate case-method output; retries need distinct method IDs",
                )
            seen.add(key)
            rows.append(row)
        except Invalid as error:
            issues.append(error.issue)
    if any(x.severity == "error" for x in issues):
        return ValidationReport(tuple(issues), None)
    missing = len(cases) * len(mids) - len(rows)
    if missing:
        issues.append(
            Issue(
                "warning",
                "missing_records",
                "results",
                f"{missing} planned case-method records absent; required missing attempts stop replay",
            )
        )
    cases = tuple(sorted(cases))
    rows = tuple(sorted(rows, key=lambda r: (r.scenario_id, r.case_id, r.method_id)))
    return ValidationReport(
        tuple(issues),
        ValidatedStudy(spec, cases, rows, logical_digest(spec, cases, rows)),
    )
