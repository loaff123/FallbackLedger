# Input and output contract

### Study JSON, schema_version `1`

Required fields:

- `schema_version`: integer 1.
- `study_id`: nonempty string.
- `estimand`: object with nonempty `id`, `label`, and `scale` strings.
- `scenarios`: nonempty array of `{id, truth}`; IDs unique, truth a finite JSON number (booleans forbidden).
- `methods`: nonempty array of `{id, version}`; IDs unique and strings nonempty.
- `assumptions`: `{independent_cases: boolean, finite_second_moments: boolean, finite_mse_contribution_variance: boolean}`. The final field is required when MSE is requested and optional otherwise. True records the author's declaration, not verification. False permits descriptive metrics but suppresses MCSE with a specific reason.
- `metrics`: nonempty unique array drawn from `bias`, `mse`, `coverage`, `completion`.
- `policies`: array of `{id, methods, requirement, inapplicable}`. IDs unique, `methods` is a nonempty ordered unique list of declared method IDs; `requirement` is `point` or `interval`; `inapplicable` is `stop` or `skip` and must be explicit.
- `cohorts`: array of `{id, members, requirement}`. Members are unique `{kind: "method"|"policy", id}` references; requirement is `point` or `interval`. These are the named common-success cohorts.
- `comparisons`: array of `{id, left, right, cohort, metrics}`. Left/right are distinct member references; `cohort` names an explicit common cohort that contains both. Metrics are unique bias/mse/coverage values; coverage requires an interval common cohort. Completion contrasts are outside v1.

Optional fields: `nominal_interval_level` (finite number strictly between 0 and 1), `description` string, and `provenance` object containing optional `dataset_id`, `configuration_id`, `source_url` strings. Coverage requires a nominal level declaration; the software does not verify that supplied bounds achieve it. Unknown fields in the canonical contract are rejected with a field path, preventing typo-driven silent changes. Metadata lives only in the documented provenance object.

Summary calculations are always separated by scenario. There is no pooled-across-scenarios estimand or implicit scenario weighting.

### Planned CSV

Header exactly `scenario_id,case_id`; every pair unique and nonempty; scenario IDs declared. At least one planned case per declared scenario. Strings preserve identity, including leading zeros; Unicode and whitespace inside nonempty IDs are preserved. Whitespace-only IDs are invalid. Input order does not define case identity or routing. Sorting uses Python's deterministic Unicode lexical ordering of `(scenario_id, case_id)`.

### Canonical result CSV or JSONL

One record per `(scenario_id,case_id,method_id)`; duplicates, unknown methods/scenarios, and off-grid cases are errors. Required keys/columns:

`scenario_id, case_id, method_id, status, reason, estimate, interval_status, lower, upper, source_record_id, estimand_id, scale`

- `status` is `ok`, `failed`, `unknown`, or `inapplicable`.
- `ok` requires a finite estimate. All other statuses require an absent estimate, preserving one unambiguous eligible point-state.
- `failed`, `unknown`, and `inapplicable` require a nonempty reason. `ok` may carry a diagnostic reason or an empty string.
- `interval_status` is `available`, `failed`, `not_provided`, or `unknown`.
- `available` requires status `ok` and ordered non-NaN bounds. Infinite endpoints are valid and serialize as the exact strings `-inf` and `inf` in JSON and CSV. Finite endpoints use numbers. JSON nonstandard NaN/Infinity literals are rejected. Point estimates cannot be infinite. An estimate need not lie within the supplied bounds; no such statistical assumption is imposed.
- Every non-available interval state requires absent bounds. `failed` requires a nonempty reason; it records explicit interval failure with a still-usable point estimate when status is `ok`. `not_provided` explicitly declares that this output does not supply intervals. `unknown` means interval observation is missing or undecided. Non-ok point statuses use interval_status `unknown`.
- `source_record_id` is a nonempty opaque string, not globally required unique: composite source identifiers may repeat across methods. Input path/hash and composite method key disambiguate source lineage.
- `estimand_id` and `scale` must exactly match the study. These declarations check consistency, not scientific equivalence.
- Optional `dataset_id` and `configuration_id` must match corresponding study provenance values if those values are declared; if absent in study, any supplied value is recorded but not interpreted.

CSV absent numbers are empty fields. JSONL absent numbers are null. No missing record is synthesized as a failed attempt. An unknown record counts as an observed record, but not as a known failure or usable output. Extra canonical CSV/JSONL fields are errors.

### Declarative mapping JSON, schema_version `1`

Canonical inputs need no mapping. A mapping contains `columns` (canonical field to source-column name), `constants` (canonical field to scalar value), optional `values` (canonical field to exact string-to-string value map), and optional `status_from_estimate: true`. No field can have both a column and a constant. IDs are never numerically coerced. Source extra columns are ignored, allowing a df column to remain irrelevant to point metrics.

`status_from_estimate` may be used only without an explicit status binding. It maps a present finite estimate to `ok` and an absent estimate to `unknown` with reason `import_missing_estimate`; malformed or infinite estimates are errors. It never infers an explicit failure from a blank. With an explicit status binding, an `ok` status plus a blank estimate remains a validation error. Source blank markers are only empty string, JSON null, and explicitly listed `missing_values` strings; `NaN` is not silently accepted. Non-executable value maps permit the producer to map documented failure codes to `failed`. Canonicalization is available as `import-results`; validate/replay/summarize also accept `--mapping` directly so adapters are not mandatory ceremony.

## Routing state machine and exact reasons

For every policy and planned case, visit its methods in order:

1. No result record: terminal `unresolved`, reason `missing_record`. Do not inspect later records.
2. `unknown`: terminal `unresolved`, reason `unknown_result`.
3. `inapplicable`: with stop, terminal `inapplicable`, reason `method_inapplicable`; with skip, append `skip_inapplicable` and continue. Skip does not remove the case from the planned denominator.
4. `failed`: append `point_failed` and continue.
5. `ok`, point requirement: select the complete recorded result bundle, terminal `usable`, reason `selected`.
6. `ok`, interval requirement: available selects the complete bundle; failed appends `interval_failed` and continues; not_provided appends `interval_not_provided` and continues; unknown terminates unresolved with `unknown_interval`.
7. End of chain after explicit failures, declared unavailable interval capabilities, or explicit inapplicability skips: terminal `exhausted`, reason `no_usable_method`.

Route entries record visited method ID, step index, action/reason, observed status, interval status, and source_record_id when observed. Selected result carries source method, source record, estimate and bounds from exactly that one record. `fallback_depth` is its zero-based chain index; null for non-usable outcomes. Later missing results are irrelevant after selection. Routing does not inspect truth, numeric error, coverage, significance, or the values of available estimates/bounds.

The result state partition per subject and requirement is `usable`, `explicit_failure`, `unresolved`, `inapplicable`; policies additionally have `exhausted` (known chain exhaustion). Methods with point ok but interval not_provided have interval state `explicit_unavailable`, distinct from recorded interval failure. These partitions are not collapsed into a generic failure count.

## Cohorts, counts, and metric semantics

Represent every analyzed entity as `(kind, id)` to avoid method/policy name collisions. Every row retains scenario_id; no result is pooled.

Automatic own cohorts are named `own:method:<id>:point`, `own:method:<id>:interval`, `own:policy:<id>:point`, and `own:policy:<id>:interval`. Interval cohorts are materialized when coverage is requested. Named common cohorts are prefixed `common:<id>`. Internal identity is a structured tuple; printable names are labels, so punctuation in user IDs cannot collide.

Every cohort has exact included and excluded case-key rows. Exclusions retain every failing member and that member's state/reason, not just a total. Named common membership is the intersection of the declared members' usable outputs for the declared requirement. Policy membership uses only its terminal selected bundle; a point policy that chose a point-only A does not borrow B's interval for coverage.

For every scenario/subject/requirement, expose:

- `planned_cases` (from the planned CSV).
- `observed_records` (method rows; for policies, count visited recorded route entries) and `cases_with_observed_records` (separate case count).
- `missing_records` (method absence; for policies, visited required missing attempts).
- `explicit_point_failures`, `explicit_interval_failures`, `explicit_interval_unavailable`, `unknown_records`, `inapplicable_records` as observed-event counts; these may overlap across point/interval fields and are not a case partition.
- Disjoint terminal case counts `usable_cases`, `explicit_failure_cases`, `explicit_unavailable_cases`, `unresolved_cases`, `inapplicable_cases`, `exhausted_cases` with all six keys present and sum exactly planned_cases. A method cannot have exhausted cases.
- `eligible_cases` for the selected cohort and `analyzed_cases` for each metric. The latter may differ only when a finite numerical contribution cannot be computed; the metric then becomes unavailable rather than silently dropping those cases.

For cohort C, error e_i = estimate_i - scenario truth. Bias is mean(e), MSE is mean(e squared), and coverage is mean(lower <= truth <= upper). Completion is usable-terminal cases / planned cases, labeled observed/replayable completion rather than imputed scientific success. Unknown attempts are reported in its denominator and never relabeled as explicit failures.

For each numerical metric, store `value`, `n`, `planned_n`, `cohort_id`, `target`, `mcse`, `mcse_reason`, `formula_id`, and any numeric diagnostic. Own-success targets are conditional on recorded usable output. Common-success targets are conditional on the named member set. A pipeline metric is labeled `all_planned_cases` only when its metric cohort includes every planned case; otherwise it is explicitly `conditional_on_usable_output`. Coverage can be conditional while point metrics are all-planned. A requested unconditional realized-grid value is never fabricated by filling failed estimates or counting missing intervals as noncoverage.

For contributions z, MCSE = sqrt(sum((z-mean(z))^2)/(n-1)/n), formula `sample_sd_over_sqrt_n`. For paired contrasts on the explicitly named common cohort, compute within-case differences d_i = z_left_i - z_right_i and apply the same formula. Report contrast orientation `left_minus_right`. Never subtract separate own-success means or use independent-method variance sums.

MCSE is null for n<2, false independent_cases, or false finite_second_moments; each has a reason. State that MSE MCSE requires finite variance of squared error (a fourth error moment), which the generic declaration does not establish: require the explicit `finite_mse_contribution_variance` declaration from assumptions for MSE MCSE. MCSE is conditional on the chosen cohort and uses its realized n; it does not quantify uncertainty in a selected denominator or create causal guarantees. Completion MCSE uses 0/1 observed usability contributions across all planned cases with the same sample-variance convention.

At zero/one coverage or constant contributions, report MCSE zero with `degenerate_sample` warning; this is not evidence of zero population uncertainty. Empty cohorts have null metrics and `empty_cohort`, never zero performance. Nonfinite error, square, paired difference, mean or MCSE due to floating arithmetic yields an explicit unavailable metric diagnostic; no cases are silently dropped. Use compensated summation (`math.fsum`) and stable two-pass variance, catching overflow. Infinite CI endpoints are allowed only for coverage, never point contributions.

## API, CLI, and outputs

Public parsed-record API:

- `validate(study: Mapping, planned: Iterable[Mapping], results: Iterable[Mapping]) -> ValidationReport`
- `replay(validated: ValidatedStudy) -> ReplayResult`
- `summarize(validated: ValidatedStudy, replayed: ReplayResult) -> SummaryResult`

ValidationReport carries immutable `issues` and either a `ValidatedStudy` or null. Structural errors prevent replay; incompleteness yields nonfatal diagnostics. Domain objects are frozen dataclasses with immutable tuples, including all lineage. A caller cannot substitute a replay from a different validated input: replay objects carry canonical study/input digest checked by summarize.

Commands:

- `fallbackledger validate --study study.json --planned planned.csv --results results.csv [--mapping mapping.json] --out validation.json`
- `fallbackledger replay <same inputs> --out replay.json --csv replay.csv`
- `fallbackledger summarize <same inputs> --output-dir report/`
- `fallbackledger import-results --input export.csv --mapping mapping.json --out results.jsonl`

Summarize runs validate then replay internally to prevent stale intermediate misuse. CLI exit 0 means structurally valid completed command, even if the result is scientifically incomplete; exit 2 means structural/input/usage error. `--require-complete` changes exit to 3 when any requested metric/cohort/contrast lacks all-planned completion, without suppressing diagnostics/artifacts. Output paths may not equal any input path; report output writes reject existing target files unless `--overwrite` was explicitly supplied. Inputs are never mutated. Write via same-directory temporary files and replacement after successful serialization, using standard filesystem behavior without crash-atomicity guarantees.

Report directory includes `validation.json`, `replay.json`, `replay.csv`, `summary.json`, `metrics.csv`, `cohorts.csv`, `summary.txt`, `report.html`. JSON is strict allow_nan=False, sorted keys with deterministic record order. CSV is UTF-8 with fixed documented columns. Cohort CSV contains a row for every planned case per cohort with included boolean and JSON-encoded exclusions. The report's route table contains every case, not a sample. Metadata has tool/schema version, exact input/mapping byte SHA-256 when loaded from files, canonical parsed-input digest, and declared assumptions; hashes establish repeatability references, not authenticity. Input byte hashes change under row permutation, but replay/cohort/metric semantic content does not.

HTML is self-contained, no JavaScript or remote assets. All user/source values are escaped using html.escape, including attributes if any. It has summary counts, named cohorts/targets, metric formula/assumption notes, and collapsible full route and membership tables. Report renderers consume summary/replay immutable outputs; they do not select cohorts or recalculate metrics. Large studies produce correspondingly large traceable reports; no contrived resource ceilings or security claims. Text and HTML always state conditional targets, unresolved counts and uncertainty assumptions.

