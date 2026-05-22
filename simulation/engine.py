"""
Simulation Engine
=================
Runs a sequence of macro-state paths through the portfolio and liability model,
tracking the funding ratio at every step.

At each time step t → t+1 the engine:
  1. Calls ``portfolio.step(state_t, state_t1)`` to update asset values.
  2. Calls ``liability_model.present_value(state_t1)`` to revalue liabilities.
  3. Records funding ratio = portfolio value / liability PV.

A *factory* pattern is used for the portfolio so that each scenario starts
from an independent, fresh portfolio object (no state leak between scenarios).

Extension points
----------------
- Inject cash flows (benefit payments, contributions) between steps.
- Add a glide-path rule that adjusts hedge_ratio based on funding ratio.
- Record per-sleeve returns and values for detailed attribution analysis.
- Support sub-annual time steps (dt < 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from scenarios.engine import MacroState, StressScenario
from liabilities.model import LiabilityModel
from portfolio.portfolio import Portfolio

# RegimeLabel is imported lazily to avoid a hard dependency; only needed when
# regime_paths is actually passed to run_all / run_scenario.
_RegimeLabel = None

def _get_regime_label():
    global _RegimeLabel
    if _RegimeLabel is None:
        from scenarios.regimes import RegimeLabel
        _RegimeLabel = RegimeLabel
    return _RegimeLabel


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    """Stores the full time series for one simulated scenario."""

    scenario_id:    int
    steps:          list[int]
    macro_states:   list[MacroState]
    portfolio_values: list[float]
    liability_pvs:  list[float]
    funding_ratios: list[float]
    period_returns: list[float]  # length = n_steps; index 0 = return from t=0 to t=1
    regime_labels:  list | None = None  # list[RegimeLabel] if regime-switching engine used

    # ------------------------------------------------------------------

    def to_dataframe(self) -> pd.DataFrame:
        """Flatten to a tidy DataFrame with one row per (scenario, step)."""
        n = len(self.steps)
        # period_return is undefined at t=0 (no prior period)
        returns_padded = [np.nan] + self.period_returns

        macro_df = pd.DataFrame(
            {f: [getattr(s, f) for s in self.macro_states]
             for f in MacroState._FIELDS}
        )
        result_df = pd.DataFrame({
            "scenario":        self.scenario_id,
            "step":            self.steps,
            "portfolio_value": self.portfolio_values,
            "liability_pv":    self.liability_pvs,
            "funding_ratio":   self.funding_ratios,
            "period_return":   returns_padded[:n],
        })
        if self.regime_labels is not None:
            result_df["regime"]    = [r.label for r in self.regime_labels]
            result_df["regime_id"] = [int(r)  for r in self.regime_labels]
        return pd.concat([result_df, macro_df], axis=1)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

PortfolioFactory = Callable[[], Portfolio]


class SimulationEngine:
    """
    Runs macro paths through the portfolio + liability model.

    Parameters
    ----------
    liability_model    : LiabilityModel
        Shared across all scenarios (stateless — only called for PV queries).
    portfolio_factory  : callable() -> Portfolio
        Called once per scenario to produce a fresh, independent portfolio.
    dt                 : float
        Time step length in years (must match the scenario engine's dt).
    contribution_schedule : dict[int, float] or None
        Optional map from step index to cash contribution (+) or benefit
        payment (−) added to the portfolio before the step's return is applied.
        Values are in the same currency as ``initial_value``.
    """

    def __init__(
        self,
        liability_model:    LiabilityModel,
        portfolio_factory:  PortfolioFactory,
        dt: float           = 1.0,
        contribution_schedule: dict[int, float] | None = None,
    ) -> None:
        self.liability_model       = liability_model
        self.portfolio_factory     = portfolio_factory
        self.dt                    = dt
        self.contribution_schedule = contribution_schedule or {}

    # ------------------------------------------------------------------
    # Single scenario
    # ------------------------------------------------------------------

    def run_scenario(
        self,
        path:         list[MacroState],
        scenario_id:  int = 0,
        regime_path:  list | None = None,
    ) -> ScenarioResult:
        """
        Simulate one macro path.

        Parameters
        ----------
        path : list[MacroState]
            Length n_steps + 1.  path[0] is the initial state (t = 0).
        regime_path : list[RegimeLabel] or None
            Optional parallel list of regime labels (same length as path).
            When provided the result DataFrame will include ``regime`` and
            ``regime_id`` columns.

        Returns
        -------
        ScenarioResult
        """
        portfolio = self.portfolio_factory()
        n_steps   = len(path) - 1

        # t = 0 snapshot
        pv0 = self.liability_model.present_value(path[0])
        fr0 = portfolio.total_value / pv0 if pv0 > 0 else np.nan

        steps             = [0]
        macro_states      = [path[0]]
        portfolio_values  = [portfolio.total_value]
        liability_pvs     = [pv0]
        funding_ratios    = [fr0]
        period_returns    = []

        for t in range(n_steps):
            state_t  = path[t]
            state_t1 = path[t + 1]

            # Optional contribution / benefit payment at start of period
            contrib = self.contribution_schedule.get(t + 1, 0.0)
            if contrib != 0.0:
                # Adjust all sleeve values proportionally (simple approximation)
                scale = 1.0 + contrib / portfolio.total_value
                portfolio.lhp.rebalance(portfolio.lhp.total_value * scale)
                portfolio.rsp.rebalance(portfolio.rsp.total_value  * scale)
                portfolio.total_value = portfolio.lhp.total_value + portfolio.rsp.total_value

            # Advance portfolio and liability
            r  = portfolio.step(state_t, state_t1, self.dt)
            pv = self.liability_model.present_value(state_t1)
            fr = portfolio.total_value / pv if pv > 0 else np.nan

            period_returns.append(r)
            steps.append(t + 1)
            macro_states.append(state_t1)
            portfolio_values.append(portfolio.total_value)
            liability_pvs.append(pv)
            funding_ratios.append(fr)

        return ScenarioResult(
            scenario_id      = scenario_id,
            steps            = steps,
            macro_states     = macro_states,
            portfolio_values = portfolio_values,
            liability_pvs    = liability_pvs,
            funding_ratios   = funding_ratios,
            period_returns   = period_returns,
            regime_labels    = regime_path,
        )

    def run_stress(self, stress: StressScenario) -> ScenarioResult:
        """Convenience wrapper for a named stress scenario."""
        return self.run_scenario(stress.states, scenario_id=-1)

    # ------------------------------------------------------------------
    # Batch run
    # ------------------------------------------------------------------

    def run_all(
        self,
        paths:        list[list[MacroState]],
        *,
        regime_paths: list[list] | None = None,
        verbose:      bool = False,
    ) -> pd.DataFrame:
        """
        Run every path in ``paths`` and concatenate results into one DataFrame.

        Parameters
        ----------
        paths        : simulation output from ``MacroScenarioEngine.simulate``
                       or ``RegimeSwitchingEngine.simulate``.
        regime_paths : optional output of ``RegimeSwitchingEngine.simulate_with_regimes``.
                       When provided, a ``regime`` column is added to the result.
        verbose      : if True, print progress every 100 scenarios.
        """
        dfs = []
        for i, path in enumerate(paths):
            if verbose and i % 100 == 0:
                print(f"  Scenario {i} / {len(paths)} …")
            rpath  = regime_paths[i] if regime_paths is not None else None
            result = self.run_scenario(path, scenario_id=i, regime_path=rpath)
            dfs.append(result.to_dataframe())
        return pd.concat(dfs, ignore_index=True)
