# Qualification record

Executed 2026-10-08 on Linux with Python 3.12.14. This is a reviewed source candidate; no public release or hosted-CI execution is implied. Runtime dependencies: none. Tests and research adapters have separately installed dependencies.

## Verified behavior

- 103 automated tests pass, with Ruff formatting and selected error/import lint checks passing.
- An independently authored scalar oracle checks all 512 combinations of eight valid observation states across A/B/C, each under four declared policies: 2,048 exact routes. It checks complete selected bundles, early stopping, all exclusion reasons across 44 named common cohorts, 144 tiny case/record permutations, larger shuffles, scenario separation and entity namespace collisions.
- Independent review regressions cover incomplete named-cohort/contrast gating, non-object JSONL coercion, empty CSV headers, human-readable contrast direction and subnormal means. Additional strictness tests reject canonical numeric strings and malformed mapping schema/constant types.
- Fresh wheel and sdist installations run validate, replay, summarize and import-results outside the checkout. Imports resolve to each venv's site-packages, input byte hashes are unchanged, output semantics agree, and artifact audits exclude third-party data/binaries and development-only process files.
- Text/JSON/CSV metrics agree in the original six-case fixture. HTML parser checks verify escaped arbitrary source text and no scripts/remote assets. Input protection covers direct paths, symlinks and hardlinks even with --overwrite; this is ordinary trusted-filesystem behavior, not a hostile-race guarantee.

## Two actual study import workflows

The full studies were exercised through an installed wheel's actual validate → replay → summarize commands, using two independently structured native exports and mappings. Core analysis was not edited per study.

### Adapted odds-ratio study

Four scenarios, each with 100,000 planned cases and two recorded method outputs: 400,000 cases and 800,000 records overall. Each scenario ran separately because the analysis is explicitly scenario-specific. Every route and cohort row was written; no trace sampling occurred.

The exact raw-log-OR failure counts for exposure probability .25/.5 crossed with odds ratio 2/5 are 1,349; 12,016; 6; 1,328. Installed-CLI own-success bias/MSE/bias-MCSE and named raw-success conditional summaries match frozen independently generated feasibility results within relative 1e-11 / absolute 1e-13 tolerance; routing counts agree exactly.

At exposure probability .25 and odds ratio 5, raw own-success bias is approximately −.036223, always-add-half all-case bias approximately −.021070, always-add-half bias on raw-success cases approximately −.226267, and the complete raw→add-half pipeline bias approximately +.146138. The changing cohort/pipeline changes the target being summarized; these are log-scale simulation evaluations, not clinical findings.

The generator is a fresh adaptation of the published design, not the authors' R stream or full five-method reproduction. Frozen feasibility support enumeration covered 23,426 n=50 count tables per scenario with floating probability arithmetic; it is not a proof for arbitrary estimators.

### Published siman sample

The source SHA-256 is checked against the documented UCL/siman simcheck.dta. The source plan is three scenarios ×1,000 repetitions ×three methods. All 9,000 point outputs survive despite 6,000 missing df values. All nine own-method groups retain n=1,000; bias/MSE/bias-MCSE and all three CCA-minus-MI paired bias contrasts match the independent frozen summaries.

For MCAR, paired bias MCSE is .008366010318708567. Treating the two means as independent would give approximately .02173590702760332. This complete point-data import validates pairing and output-specific eligibility; it does not independently validate fallback routing.

The third-party dataset is not distributed, and no redistribution license is assumed. Only original conversion code, source attribution, hashes and derived numerical checks are included.

## Actual mature-package comparison

rsimsum 0.13.1 actually executed under WebR 0.6.0 / R 4.6.0 with Node 24.19.0, using official WebR binaries in a separate research environment. No imitation implementation was substituted.

For [1,2,4,5] at truth 0 with SE 1 and explicit estimate +/-1.96 intervals, bias 3, MSE 11.5, coverage .25, bias MCSE .9128709291752768 and MSE MCSE 5.545268253204709 agree to binary64 rounding. The installed rsimsum function was inspected to confirm the actual formulas. Coverage MCSE differs by the explicitly documented convention: .21650635094610965 with rsimsum's plug-in Bernoulli variance versus .25 with FallbackLedger's sample contribution variance.

The same comparison also passed against the installed FallbackLedger wheel. This is a complete-data convention check, not a claim about every rsimsum feature, missingness behavior or superiority.

Native-R reproduction: `Rscript --vanilla tools/crosscheck_rsimsum.R /path/to/evidence`. Stable rsimsum must already be installed in that R library. Downloaded R/npm binaries and copied reference implementation source are excluded from the distribution.

## Practical scale and known limits

The preliminary 1,000-case report took .45 seconds, approximately 16 MiB peak RSS and 2.8 MiB output. A 100,000-case /200,000-record run took 33.7 seconds with approximately 246 MiB peak RSS and 267 MiB combined report output, including about 72 MiB HTML. Full installed-study measurements, input hashes and output byte sizes are retained in [qualification-results.json](qualification-results.json). Timings are observations on this machine, not performance guarantees or incumbent benchmarks.

Serialization streams records, but validation/indexes/cohorts are held in memory. Large exact-trace HTML reports may be unwieldy in a browser; use the concise text/metrics CSV plus full machine-readable trace files, or run scientifically separate scenarios individually. Browser opening performance at 100,000 cases is not verified.

Pixel-level browser QA is unverified: the cloud Chromium process could not create required sockets, in this environment. Parser/escaping checks and text/CSV/JSON inspections passed; no pixel-perfect or browser-rendering claim is made.

Standalone HTML/text identify the estimand label/scale, declared scenario truth, nominal interval level when supplied, and the actual left/right members of every contrast. These context additions have focused escaping tests. No new authority is inferred from source-record IDs, provenance hashes or declared assumptions. The large-study measurement snapshot retains its original test-count receipt; the current total includes later presentation tests.

Python 3.12 was executed locally. The included hosted-CI definition targets Python 3.10–3.13, but hosted CI and those other interpreters have not executed for this unpublished candidate. PyPI installation is not claimed.

## Reproducing the full study check

After building/installing the package and obtaining the separately licensed source dataset:

```sh
python tools/qualify_studies.py --analysis-python /path/to/installed/venv/bin/python --source-python /path/to/python-with-numpy-pandas --siman-data /path/to/simcheck.dta --output /new/evidence/directory
```

This writes all reports and compares against original frozen expected summaries. Allow several hundred MiB of output per large scenario. For a normal package smoke check, use the much smaller tools/check_installed.py workflow instead.
