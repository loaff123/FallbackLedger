"""Per-case contribution summaries and explicit Monte Carlo assumptions."""

import math
import statistics as standard_statistics


def contribution(row, truth, metric):
    if metric == "coverage":
        return float(row.lower <= truth <= row.upper)
    error = row.estimate - truth
    if metric == "bias":
        return error
    if metric == "mse":
        return error * error
    raise ValueError(f"Unknown numerical metric: {metric}")


def summarize_contributions(values, assumptions, metric):
    n = len(values)
    base = dict(
        value=None,
        mcse=None,
        mcse_reason=None,
        warnings=(),
        diagnostic=None,
        analyzed_cases=0,
    )
    if not n:
        return dict(base, mcse_reason="empty_cohort")
    if not all(math.isfinite(x) for x in values):
        return dict(
            base, mcse_reason="numeric_unavailable", diagnostic="nonfinite_contribution"
        )
    try:
        # Sum first to preserve subnormal constant samples. The rare exact-sum
        # fallback avoids intermediate overflow for very large finite values.
        try:
            mean = math.fsum(values) / n
        except OverflowError:
            mean = float(standard_statistics.mean(values))
    except (OverflowError, ValueError):
        return dict(
            base, mcse_reason="numeric_unavailable", diagnostic="nonfinite_mean"
        )
    if not math.isfinite(mean):
        return dict(
            base, mcse_reason="numeric_unavailable", diagnostic="nonfinite_mean"
        )
    base.update(value=mean, analyzed_cases=n)
    if n < 2:
        return dict(base, mcse_reason="n_lt_2")
    if not assumptions.independent_cases:
        return dict(base, mcse_reason="independent_cases_not_declared")
    if not assumptions.finite_second_moments:
        return dict(base, mcse_reason="finite_second_moments_not_declared")
    if metric == "mse" and not assumptions.finite_mse_contribution_variance:
        return dict(base, mcse_reason="finite_mse_contribution_variance_not_declared")
    try:
        deviations = [x - mean for x in values]
        scale = max(abs(x) for x in deviations)
        if not math.isfinite(scale):
            raise OverflowError
        if scale == 0:
            return dict(base, mcse=0.0, warnings=("degenerate_sample",))
        mcse = scale * math.sqrt(
            math.fsum((x / scale) ** 2 for x in deviations) / (n - 1) / n
        )
        if not math.isfinite(mcse):
            raise OverflowError
    except (OverflowError, ValueError):
        return dict(
            base, mcse_reason="numeric_unavailable", diagnostic="nonfinite_mcse"
        )
    return dict(base, mcse=mcse)
