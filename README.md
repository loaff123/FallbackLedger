# FallbackLedger

Replay declared fallback policies on archived simulation-study outputs. Keep the planned case grid, recorded failures, missing attempts, exact comparison cohorts and paired Monte Carlo uncertainty together.

**Development candidate.** Python 3.10+, no runtime dependencies. This is an analysis workflow, not an estimator runner or a policy optimizer. Qualification evidence and tested limitations are in [docs/qualification.md](docs/qualification.md).

## The question it answers

Your simulation ran methods A and B on the same datasets. A sometimes failed. You want to report A on its successful cases, compare A and B on an explicitly named common cohort, and evaluate a predeclared “A, then B if A fails” pipeline without silently changing denominators.

A missing A record does not prove that A failed. A valid point estimate without a confidence interval is still useful for point metrics. A fallback must select one complete recorded result bundle. These distinctions drive every route and summary here.

## Try it

From a source checkout:

```sh
python -m pip install .
fallbackledger validate --study examples/tiny/study.json --planned examples/tiny/planned.csv --results examples/tiny/results.jsonl --out validation.json
fallbackledger replay --study examples/tiny/study.json --planned examples/tiny/planned.csv --results examples/tiny/results.jsonl --out replay.json --csv replay.csv
fallbackledger summarize --study examples/tiny/study.json --planned examples/tiny/planned.csv --results examples/tiny/results.jsonl --output-dir report
```

Open `report/report.html` locally. It contains all case-policy routes and all included/excluded cohort rows; it has no scripts, external styles or remote assets. `summary.txt` is a concise readout. JSON and CSV files provide machine-readable metrics, source lineage and membership.

The six original example cases deliberately include incomplete results. The point pipeline completes 4/6 cases with conditional bias 3.25; the interval pipeline completes 3/6 and selects B's entire bundle when A is point-only. The A-minus-B bias contrast is −1 on exactly two common cases, with a zero sample MCSE and an explicit degeneracy warning.

Exit 0 means the command completed on structurally valid input; it does not mean every method succeeded. Invalid contracts exit 2. Add `--require-complete` to request exit 3 when any requested metric/cohort is incomplete; artifacts remain available for inspection. Existing output files require `--overwrite`, which never authorizes changing an input through a symlink or hardlink.

## Three explicit inputs

1. `study.json`: scalar estimand and scale, per-scenario truth, methods and versions, assumptions, requested metrics, ordered fallback policies, named common cohorts and paired comparisons.
2. `planned.csv`: the independently declared `(scenario_id, case_id)` grid. It is never inferred from observed method outputs.
3. A CSV or JSONL result export with one record per `(scenario_id, case_id, method_id)` and an explicit status.

See [the schema](docs/schema.md) for every field, enum and mapping rule. Existing exports can bind source columns and documented status codes through a small declarative mapping:

```sh
fallbackledger summarize --study study.json --planned planned.csv --results existing-export.csv --mapping mapping.json --output-dir report
```

No expressions, code plugins or generic “drop every row with any missing field” filter are evaluated. The [siman example](examples/siman/README.md) preserves point estimates even when a degrees-of-freedom field is intentionally absent. Optional adapters may need NumPy or pandas; the package itself does not.

## Parsed-record API

```python
from fallbackledger import validate, replay, summarize

report = validate(study_dict, planned_rows, result_rows)
if report.validated is None:
    raise ValueError(report.issues)
validated = report.validated
routes = replay(validated)
summary = summarize(validated, routes)
```

Outputs are frozen dataclasses and immutable tuples. Canonical digests prevent accidental combination of outputs from different validated inputs. File provenance includes exact byte hashes; hashes do not establish authenticity or independence.

## What is measured

- Bias: mean estimation error on the named cohort
- MSE: mean squared error on the named cohort
- Coverage: proportion of available declared intervals containing the scenario truth
- Completion: observed usable/replayable cases divided by all planned cases
- Paired contrasts: left-minus-right **within-case contributions** on the same explicit common cohort

MCSE uses sample contribution variance divided by cohort size. It requires independent simulation cases and finite contribution variance; MSE MCSE requires a separate fourth-error-moment declaration. Small/empty cohorts, constant samples, arithmetic overflow and unresolved results receive explicit diagnostics. Unbounded confidence intervals can be valid; NaN bounds cannot.

Own-success and common-success results are conditional summaries. They do not repair selection bias. A pipeline quantity describes all planned cases only when every planned case has a usable output for that metric. There is no automatic winner, missing-at-random assumption, causal claim, significance-based routing, nested-replicate inference or cross-validation-fold inference. See [statistical interpretation](docs/statistics.md).

## Existing tools and positioning

[rsimsum](https://ellessenne.github.io/rsimsum/) already provides mature simulation metrics and uncertainty. [mlr3](https://mlr3.mlr-org.com/) provides runtime learner fallback, and [SimEngine](https://avi-kenny.github.io/SimEngine/) integrates simulation execution and errors. Use them when their existing workflow fits.

A competent pandas/tidyverse script can perform these joins and summaries too. FallbackLedger offers a reusable contract for planned-grid validation, replay of archived outputs, whole-bundle selection, named cohorts, paired uncertainty and case-level evidence. It does not claim a new statistical method or superior estimators. The motivating methodology is Wünsch et al. (2025), [Rethinking the Handling of Method Failure in Comparison Studies](https://pmc.ncbi.nlm.nih.gov/articles/PMC12509789/).

## Development

```sh
python -m pip install -e '.[test]'
python -m pytest
python -m build
python tools/check_installed.py --dist dist --output /tmp/fallbackledger-installed-check
```

Tests include an independently authored scalar oracle over 2,048 declared policy routes, exact common-cohort intersections, paired contribution checks, CLI round trips and passive report escaping. Qualification also exercises two actual study import shapes and an actual rsimsum runtime cross-check. Hosted CI is not claimed until it actually executes for a published commit.

Original code and fixtures are MIT licensed. Third-party research datasets, package binaries and copied implementation source are not distributed.
