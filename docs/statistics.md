# Interpreting the numbers

Every result is scenario-specific. FallbackLedger does not pool scenarios or choose scientific targets.

## Contributions and Monte Carlo standard error

For the exact included cohort C with n cases and scenario truth theta:

- Bias contribution: z_i = estimate_i - theta
- MSE contribution: z_i = (estimate_i - theta)^2
- Coverage contribution: z_i = 1{lower_i <= theta <= upper_i}
- Observed completion contribution: z_i = 1{usable recorded/replayed output}, evaluated on the entire planned grid

A metric is the sample mean of its contributions. Its MCSE is sqrt(sum((z_i - mean(z))^2)/(n*(n-1))). Contrasts use d_i = z_left_i - z_right_i on the identical named common cohort and the same MCSE formula. They do not assume the two methods' averages are independent.

The author must declare independent simulation cases and finite second moments. MSE MCSE additionally requires finite variance of squared errors, equivalent to a fourth-error-moment condition. The software checks declarations, not their truth. Heavy tails can make finite-sample MCSE unreliable even when the moments exist. No normal-approximation confidence interval is automatically asserted.

The MCSE is null at n<2. Empty cohorts have null performance, not zero performance. At a constant observed contribution, including all-covered or none-covered intervals, the sample MCSE is zero and carries a degeneracy warning; population uncertainty is not thereby zero. Nonfinite contributions or floating-point arithmetic overflow make a metric unavailable without silently dropping cases.

## Conditioning is a target choice

An own-success cohort conditions on that method's recorded usable outputs. A common-success cohort conditions on every named member's usable output. These are sensitivity views, not selection-bias corrections. Missingness is not assumed to be random.

A complete pipeline describes the realized planned case grid only when all cases have usable outputs. A missing required early attempt remains unresolved even if a later method's output exists. Completion retains such cases in the planned denominator while identifying them separately from recorded failures. Coverage never treats a failed or missing interval as noncoverage.

A point-only policy can be complete for bias/MSE but incomplete for coverage. It is not rerouted later just to manufacture intervals. An interval policy can fall back when an interval explicitly failed or was explicitly not provided; an unknown interval observation stops replay. Every selected point/interval comes from one source record.

## Coverage conventions and actual rsimsum comparison

For observed coverage p, FallbackLedger uses sqrt(p*(1-p)/(n-1)), the same sample-variance convention as its other contribution MCSEs. rsimsum 0.13.1 uses the common plug-in Bernoulli convention sqrt(p*(1-p)/n). Both the convention and finite-sample difference are reported; agreement is expected only when definitions agree.

An actual rsimsum 0.13.1 run used estimates [1,2,4,5], truth 0, SE 1 and explicit estimate +/- 1.96 bounds. It returned bias 3, MSE 11.5, coverage .25; bias MCSE .9128709291752768 and MSE MCSE 5.545268253204709 agree with FallbackLedger to binary64 rounding. Coverage MCSE was .21650635094610965 versus FallbackLedger's .25, exactly the documented convention difference. See tools/crosscheck_rsimsum.R and the qualification record.

## Appropriate use

Independent replicated simulations with one scalar estimand per analysis. Not cross-validation folds, repeated observations within one experimental unit, multilevel simulation draws, policy tuning against truth, causal effects of fallback, estimator execution or automatic model selection. Bounds must be supplied; the package does not infer a normal or t interval from an SE/df column.
