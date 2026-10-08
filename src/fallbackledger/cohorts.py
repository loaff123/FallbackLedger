"""Explicit eligibility and exact scenario-specific cohort membership."""

from .models import Cohort, CohortRow, EntityRef, EntityState, Exclusion


class StudyIndex:
    """Local lookup indexes; immutable public inputs are never mutated."""

    def __init__(self, validated, replayed):
        if replayed.canonical_digest != validated.canonical_digest:
            raise ValueError("Replay canonical digest does not match validated input")
        self.records = {
            (r.scenario_id, r.case_id, r.method_id): r for r in validated.results
        }
        self.outcomes = {
            (r.scenario_id, r.case_id, r.policy_id): r for r in replayed.outcomes
        }
        expected = {
            (c.scenario_id, c.case_id, p.id)
            for c in validated.cases
            for p in validated.spec.policies
        }
        if set(self.outcomes) != expected or len(self.outcomes) != len(
            replayed.outcomes
        ):
            raise ValueError(
                "Replay outcomes do not exactly cover planned policy cases"
            )
        self.cases = {
            s.id: tuple(c for c in validated.cases if c.scenario_id == s.id)
            for s in validated.spec.scenarios
        }
        self.entities = tuple(
            [EntityRef("method", m.id) for m in validated.spec.methods]
            + [EntityRef("policy", p.id) for p in validated.spec.policies]
        )

    def state(self, case, member, requirement):
        key = (case.scenario_id, case.case_id, member.id)
        if member.kind == "method":
            return record_state(self.records.get(key), requirement)
        outcome = self.outcomes[key]
        if outcome.state != "usable":
            return EntityState(outcome.state, outcome.reason, None)
        return record_state(outcome.selected, requirement)

    def events(self, case, member):
        key = (case.scenario_id, case.case_id, member.id)
        if member.kind == "method":
            return (self.records.get(key),)
        return tuple(
            self.records.get((case.scenario_id, case.case_id, step.method_id))
            for step in self.outcomes[key].route
        )


def record_state(row, requirement):
    if row is None:
        return EntityState("unresolved", "missing_record", None)
    if row.status == "unknown":
        return EntityState("unresolved", "unknown_result", None)
    if row.status == "failed":
        return EntityState("explicit_failure", "point_failed", None)
    if row.status == "inapplicable":
        return EntityState("inapplicable", "method_inapplicable", None)
    if requirement == "point" or row.interval_status == "available":
        return EntityState("usable", "selected", row)
    if row.interval_status == "unknown":
        return EntityState("unresolved", "unknown_interval", None)
    if row.interval_status == "failed":
        return EntityState("explicit_failure", "interval_failed", None)
    return EntityState("explicit_unavailable", "interval_not_provided", None)


def build_cohorts(validated, replayed, index=None):
    index = index or StudyIndex(validated, replayed)
    definitions = []
    for member in index.entities:
        definitions.append(
            (("own", member.kind, member.id, "point"), (member,), "point")
        )
        if "coverage" in validated.spec.metrics:
            definitions.append(
                (("own", member.kind, member.id, "interval"), (member,), "interval")
            )
    for cohort in validated.spec.cohorts:
        definitions.append((("common", cohort.id), cohort.members, cohort.requirement))
    output = []
    for scenario, cases in index.cases.items():
        for id, members, requirement in definitions:
            rows = []
            for case in cases:
                exclusions = []
                for member in members:
                    state = index.state(case, member, requirement)
                    if state.state != "usable":
                        exclusions.append(Exclusion(member, state.state, state.reason))
                rows.append(CohortRow(case, not exclusions, tuple(exclusions)))
            output.append(Cohort(id, scenario, requirement, members, tuple(rows)))
    return tuple(output)
