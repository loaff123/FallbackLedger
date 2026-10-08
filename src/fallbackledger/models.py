"""Immutable contracts shared by validation, replay and analysis."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, order=True, slots=True)
class CaseKey:
    scenario_id: str
    case_id: str


@dataclass(frozen=True, order=True, slots=True)
class EntityRef:
    kind: str
    id: str


@dataclass(frozen=True, slots=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    truth: float


@dataclass(frozen=True, slots=True)
class Method:
    id: str
    version: str


@dataclass(frozen=True, slots=True)
class Policy:
    id: str
    methods: tuple[str, ...]
    requirement: str
    inapplicable: str


@dataclass(frozen=True, slots=True)
class CohortSpec:
    id: str
    members: tuple[EntityRef, ...]
    requirement: str


@dataclass(frozen=True, slots=True)
class Comparison:
    id: str
    left: EntityRef
    right: EntityRef
    cohort: str
    metrics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Assumptions:
    independent_cases: bool
    finite_second_moments: bool
    finite_mse_contribution_variance: bool = False


@dataclass(frozen=True, slots=True)
class StudySpec:
    schema_version: int
    study_id: str
    estimand_id: str
    estimand_label: str
    scale: str
    scenarios: tuple[Scenario, ...]
    methods: tuple[Method, ...]
    assumptions: Assumptions
    metrics: tuple[str, ...]
    policies: tuple[Policy, ...]
    cohorts: tuple[CohortSpec, ...]
    comparisons: tuple[Comparison, ...]
    nominal_interval_level: Optional[float] = None
    description: str = ""
    provenance: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MethodResult:
    scenario_id: str
    case_id: str
    method_id: str
    status: str
    reason: str
    estimate: Optional[float]
    interval_status: str
    lower: Optional[float]
    upper: Optional[float]
    source_record_id: str
    estimand_id: str
    scale: str
    dataset_id: Optional[str] = None
    configuration_id: Optional[str] = None

    @property
    def case(self):
        return CaseKey(self.scenario_id, self.case_id)


@dataclass(frozen=True, slots=True)
class ValidatedStudy:
    spec: StudySpec
    cases: tuple[CaseKey, ...]
    results: tuple[MethodResult, ...]
    canonical_digest: str
    provenance: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[Issue, ...]
    validated: Optional[ValidatedStudy]

    @property
    def valid(self):
        return self.validated is not None


@dataclass(frozen=True, slots=True)
class RouteStep:
    method_id: str
    step_index: int
    action: str
    status: Optional[str]
    interval_status: Optional[str]
    source_record_id: Optional[str]
    source_reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    scenario_id: str
    case_id: str
    policy_id: str
    state: str
    reason: str
    selected: Optional[MethodResult]
    fallback_depth: Optional[int]
    route: tuple[RouteStep, ...]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    canonical_digest: str
    outcomes: tuple[PolicyOutcome, ...]


@dataclass(frozen=True, slots=True)
class EntityState:
    state: str
    reason: str
    selected: Optional[MethodResult]


@dataclass(frozen=True, slots=True)
class Exclusion:
    member: EntityRef
    state: str
    reason: str


@dataclass(frozen=True, slots=True)
class CohortRow:
    case: CaseKey
    included: bool
    exclusions: tuple[Exclusion, ...]


@dataclass(frozen=True, slots=True)
class Cohort:
    id: tuple[str, ...]
    scenario_id: str
    requirement: str
    members: tuple[EntityRef, ...]
    rows: tuple[CohortRow, ...]


@dataclass(frozen=True, slots=True)
class MetricRow:
    scenario_id: str
    subject: EntityRef
    metric: str
    cohort_id: tuple[str, ...]
    target: str
    n: int
    planned_n: int
    value: Optional[float]
    mcse: Optional[float]
    mcse_reason: Optional[str]
    formula_id: str = "sample_sd_over_sqrt_n"
    warnings: tuple[str, ...] = ()
    diagnostic: Optional[str] = None
    orientation: Optional[str] = None
    left: Optional[EntityRef] = None
    right: Optional[EntityRef] = None
    analyzed_cases: int = 0


@dataclass(frozen=True, slots=True)
class CountRow:
    scenario_id: str
    subject: EntityRef
    requirement: str
    planned_cases: int
    observed_records: int
    cases_with_observed_records: int
    missing_records: int
    explicit_point_failures: int
    explicit_interval_failures: int
    explicit_interval_unavailable: int
    unknown_records: int
    inapplicable_records: int
    usable_cases: int
    explicit_failure_cases: int
    explicit_unavailable_cases: int
    unresolved_cases: int
    inapplicable_cases: int
    exhausted_cases: int
    eligible_cases: int


@dataclass(frozen=True, slots=True)
class SummaryResult:
    canonical_digest: str
    cohorts: tuple[Cohort, ...]
    metrics: tuple[MetricRow, ...]
    counts: tuple[CountRow, ...]
    assumptions: Assumptions
    warnings: tuple[str, ...]
