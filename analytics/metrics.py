"""
Analytics & Risk Metrics
=========================
Functions that operate on the tidy DataFrame produced by ``SimulationEngine.run_all``.

Provided
--------
- ``funding_ratio_stats``   — cross-sectional summary at a given step
- ``fan_chart_data``        — percentile bands over time (for plotting)
- ``duration_gap``          — interest rate hedge effectiveness measure
- ``compute_var_cvar``      — VaR and CVaR of funding ratio / portfolio return

Extension points
----------------
- Add surplus-at-risk (SaR): distribution of (portfolio − liability) changes.
- Add tracking-error attribution by asset sleeve.
- Add regulatory / actuarial metrics (technical provisions, solvency ratio).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

@dataclass
class FundingRatioStats:
    """Cross-sectional summary of the funding ratio distribution at one step."""

    step:                 int
    n_scenarios:          int
    mean:                 float
    median:               float
    std:                  float
    p5:                   float
    p25:                  float
    p75:                  float
    p95:                  float
    prob_deficit:         float   # P(FR < 1)
    prob_fully_funded:    float   # P(FR ≥ 1)
    expected_shortfall:   float   # E[FR | FR < 1]  (conditional mean in deficit)

    def __str__(self) -> str:
        return (
            f"Step {self.step} (n={self.n_scenarios})\n"
            f"  Median FR       : {self.median:.2%}\n"
            f"  Mean FR         : {self.mean:.2%}  ±{self.std:.2%}\n"
            f"  5th–95th pct    : {self.p5:.2%} – {self.p95:.2%}\n"
            f"  P(deficit)      : {self.prob_deficit:.1%}\n"
            f"  Expected shortfall (FR|FR<1): {self.expected_shortfall:.2%}"
        )


def funding_ratio_stats(df: pd.DataFrame, step: int) -> FundingRatioStats:
    """
    Compute cross-sectional statistics of the funding ratio at ``step``.

    Parameters
    ----------
    df   : DataFrame produced by ``SimulationEngine.run_all``.
    step : simulation step index (0 = initial, 1 = after first period, …).
    """
    fr      = df.loc[df["step"] == step, "funding_ratio"].dropna().values
    deficit = fr[fr < 1.0]
    return FundingRatioStats(
        step               = step,
        n_scenarios        = len(fr),
        mean               = float(np.mean(fr)),
        median             = float(np.median(fr)),
        std                = float(np.std(fr)),
        p5                 = float(np.percentile(fr,  5)),
        p25                = float(np.percentile(fr, 25)),
        p75                = float(np.percentile(fr, 75)),
        p95                = float(np.percentile(fr, 95)),
        prob_deficit       = float(np.mean(fr < 1.0)),
        prob_fully_funded  = float(np.mean(fr >= 1.0)),
        expected_shortfall = float(np.mean(deficit)) if len(deficit) > 0 else float(np.nan),
    )


# ---------------------------------------------------------------------------
# Fan chart
# ---------------------------------------------------------------------------

def fan_chart_data(
    df:         pd.DataFrame,
    steps:      Sequence[int] | None = None,
    percentiles: Sequence[float]     = (5, 25, 50, 75, 95),
) -> pd.DataFrame:
    """
    Compute percentile bands of the funding ratio over time.

    Returns a DataFrame with columns ``step, mean, p5, p25, p50, p75, p95``
    suitable for drawing a fan chart.
    """
    if steps is None:
        steps = sorted(df["step"].unique())

    records = []
    for s in steps:
        fr = df.loc[df["step"] == s, "funding_ratio"].dropna().values
        row = {"step": s, "mean": float(np.mean(fr))}
        for p in percentiles:
            row[f"p{int(p)}"] = float(np.percentile(fr, p))
        records.append(row)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# VaR / CVaR
# ---------------------------------------------------------------------------

def compute_var_cvar(
    df:          pd.DataFrame,
    step:        int,
    column:      str   = "funding_ratio",
    confidence:  float = 0.95,
) -> tuple[float, float]:
    """
    Value-at-Risk and Conditional VaR (Expected Shortfall) of ``column`` at ``step``.

    For funding ratio (higher is better) VaR is the left-tail quantile.

    Returns
    -------
    var  : float — the (1 − confidence) quantile
    cvar : float — mean below the VaR quantile
    """
    values = df.loc[df["step"] == step, column].dropna().values
    var    = float(np.percentile(values, (1.0 - confidence) * 100))
    cvar   = float(np.mean(values[values <= var]))
    return var, cvar


# ---------------------------------------------------------------------------
# Duration gap
# ---------------------------------------------------------------------------

def duration_gap(
    liability_duration:  float,
    portfolio_duration:  float,
    liability_pv:        float,
    portfolio_value:     float,
) -> float:
    """
    Duration gap (years): surplus-weighted mismatch between asset and liability
    interest rate sensitivity.

    A gap of zero means the portfolio and liability respond identically to a
    parallel yield shift (rate risk fully hedged).  A positive gap means the
    portfolio is *longer* than the liability (benefits from rising rates).

    Formula
    -------
        gap = D_assets × (A/L) − D_liabilities
    """
    if liability_pv == 0:
        return 0.0
    return portfolio_duration * (portfolio_value / liability_pv) - liability_duration


# ---------------------------------------------------------------------------
# Attribution helpers
# ---------------------------------------------------------------------------

def period_return_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Summary of portfolio period returns across all scenarios and steps.

    Useful for sanity-checking calibration against historical data.
    """
    r = df.dropna(subset=["period_return"])["period_return"]
    return pd.DataFrame([{
        "mean_annual_return": r.mean(),
        "std_annual_return":  r.std(),
        "min_return":         r.min(),
        "max_return":         r.max(),
        "skewness":           float(pd.Series(r).skew()),
        "kurtosis":           float(pd.Series(r).kurt()),
    }])


# ---------------------------------------------------------------------------
# Regime-aware analytics  (only available when regime column is present)
# ---------------------------------------------------------------------------

def funding_ratio_by_regime(df: pd.DataFrame, step: int) -> pd.DataFrame:
    """
    Cross-sectional funding ratio statistics broken down by regime.

    Requires the DataFrame to contain a ``regime`` column (produced when
    ``SimulationEngine.run_all`` is called with ``regime_paths`` from a
    ``RegimeSwitchingEngine``).

    Returns one row per regime with the same statistics as
    ``FundingRatioStats``.
    """
    if "regime" not in df.columns:
        raise ValueError(
            "DataFrame has no 'regime' column.  Run the simulation with a "
            "RegimeSwitchingEngine and pass regime_paths to run_all()."
        )

    rows = []
    subset = df[df["step"] == step]
    for regime, grp in subset.groupby("regime"):
        fr      = grp["funding_ratio"].dropna().values
        deficit = fr[fr < 1.0]
        rows.append({
            "regime":              regime,
            "n_scenarios":         len(fr),
            "mean_fr":             float(np.mean(fr)),
            "median_fr":           float(np.median(fr)),
            "std_fr":              float(np.std(fr)),
            "p5_fr":               float(np.percentile(fr,  5)),
            "p95_fr":              float(np.percentile(fr, 95)),
            "prob_deficit":        float(np.mean(fr < 1.0)),
            "expected_shortfall":  float(np.mean(deficit)) if len(deficit) > 0 else float(np.nan),
        })
    return pd.DataFrame(rows).sort_values("regime").reset_index(drop=True)


def regime_transition_heatmap_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute empirical regime transition counts from a results DataFrame.

    Returns a pivot table (from_regime × to_regime) that can be plotted
    as a heatmap to validate the simulated Markov chain.
    """
    if "regime" not in df.columns:
        raise ValueError("DataFrame has no 'regime' column.")

    from_regime = df.groupby("scenario")["regime"].shift(1)
    to_regime   = df["regime"]
    pairs       = pd.DataFrame({"from": from_regime, "to": to_regime}).dropna()
    counts      = pairs.groupby(["from", "to"]).size().unstack(fill_value=0)

    # Normalise to row frequencies
    return counts.div(counts.sum(axis=1), axis=0)


def fan_chart_by_regime(
    df:    pd.DataFrame,
    steps: Sequence[int] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Compute a separate fan chart DataFrame for each regime.

    Returns a dict of ``{regime_label: fan_chart_df}`` where each
    ``fan_chart_df`` has the same structure as ``fan_chart_data`` output.

    Useful for plotting four overlapping fan charts colour-coded by regime.
    """
    if "regime" not in df.columns:
        raise ValueError("DataFrame has no 'regime' column.")

    result = {}
    for regime, grp in df.groupby("regime"):
        result[regime] = fan_chart_data(grp, steps=steps)
    return result
