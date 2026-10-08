# Adapted odds-ratio simulation

Original export code for a fresh adaptation of Wünsch et al. (2025), DOI 10.1002/sim.70257. It is not the authors' R random stream or full five-method comparison.

Install NumPy separately. Generate one scenario at a time; indices 0–3 correspond to exposure probability .25/.5 crossed with odds ratio 2/5. Each run has n=50 observations per simulated table and 100,000 planned cases by default, using NumPy SeedSequence([20261008, scenario_index]).

```sh
python examples/odds_ratio/export.py --scenario-index 1 --output-dir odds-input
fallbackledger summarize --study odds-input/study.json --planned odds-input/planned.csv --results odds-input/native_results.csv --mapping odds-input/mapping.json --output-dir odds-report
```

The native export has explicit zero-cell failure codes for raw log OR, and an always-add-half alternative. The declared pipeline chooses raw then add-half on explicit failure. The exact plan is generated before emitting result rows. Mappings, status codes and cohorts are inspectable. At this finite n, possible successful log-OR and half-correction values are bounded; the stated contribution moment assumptions apply to this specific finite example.

Full route and cohort reports can be large. All rows are retained; running scenarios separately preserves the per-scenario analysis and does not pool or silently sample cases.
