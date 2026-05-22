"""
Portfolio Construction: LHP + RSP
===================================
The total portfolio is partitioned into two conceptually distinct sub-portfolios:

  LHP (Liability-Hedging Portfolio)
      Assets chosen to co-move with the liability drivers (rates, inflation).
      Typically: long nominal bonds, inflation-linked bonds, cash.

  RSP (Return-Seeking Portfolio)
      Assets chosen to generate excess returns above the liability discount rate.
      Typically: equity, credit, real assets, commodities.

Architecture
------------
Each sub-portfolio is defined by a set of ``AssetSleeve`` objects and their
*intra-sub-portfolio* weights (which must sum to 1.0).

The top-level ``hedge_ratio`` (0–1) controls what fraction of total assets
sits in the LHP; the remainder (1 − hedge_ratio) goes to the RSP.

Rebalancing
-----------
Rebalancing frequency is configurable at the top-portfolio level.  At each
rebalance step all values are reset to their target weights so that drift
does not accumulate between steps.

Extension points
----------------
- Add glide-path logic: automatically increase hedge_ratio as funding ratio rises.
- Add contributions / benefit payments as periodic cash flows.
- Add illiquidity constraints (e.g. cap on real-asset sell-downs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from assets.base import AssetSleeve
from assets.fx import FXModel
from scenarios.engine import MacroState


# ---------------------------------------------------------------------------
# Sleeve specification
# ---------------------------------------------------------------------------

@dataclass
class SleeveSpec:
    """
    A single sleeve allocation within a sub-portfolio.

    Parameters
    ----------
    sleeve : AssetSleeve
        The return-generating component.
    weight : float
        Intra-sub-portfolio weight (must sum to 1.0 across all sleeves in
        the same sub-portfolio).
    """

    sleeve: AssetSleeve
    weight: float  # weight within the LHP or RSP sub-portfolio


# ---------------------------------------------------------------------------
# Sub-portfolio
# ---------------------------------------------------------------------------

class SubPortfolio:
    """
    A collection of asset sleeves with fixed intra-weights.

    Tracks the current market value of each sleeve and the sub-portfolio
    total.  Rebalancing is handled by the parent ``Portfolio``.
    """

    def __init__(
        self,
        specs: list[SleeveSpec],
        initial_value: float,
        fx_model: FXModel | None = None,
    ) -> None:
        _validate_weights([s.weight for s in specs], label="sub-portfolio")
        self.specs          = specs
        self.total_value    = initial_value
        self._fx_model      = fx_model
        self.sleeve_values  = {
            s.sleeve.name: initial_value * s.weight for s in specs
        }

    # ------------------------------------------------------------------

    def step(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        """
        Advance all sleeves by one period.

        Returns
        -------
        weighted_return : float
            The value-weighted return of the sub-portfolio.
        """
        # Compute all FX returns once so every sleeve sees the same draw.
        fx_returns = self._fx_model.step(state_t, state_t1, dt) if self._fx_model else {}

        weighted_return = 0.0
        for spec in self.specs:
            local_r = spec.sleeve.period_return(state_t, state_t1, dt)
            fx_r = sum(
                exp * fx_returns[cur]
                for cur, exp in spec.sleeve.fx_exposures.items()
                if cur in fx_returns
            )
            r = local_r + fx_r
            old_val = self.sleeve_values[spec.sleeve.name]
            self.sleeve_values[spec.sleeve.name] = old_val * (1.0 + r)
            weighted_return += spec.weight * r

        self.total_value = sum(self.sleeve_values.values())
        return weighted_return

    def rebalance(self, target_value: float | None = None) -> None:
        """Reset sleeve values to target weights (within this sub-portfolio)."""
        base = target_value if target_value is not None else self.total_value
        self.total_value = base
        for spec in self.specs:
            self.sleeve_values[spec.sleeve.name] = base * spec.weight

    def sleeve_weights(self) -> dict[str, float]:
        """Current (possibly drifted) weights for reporting."""
        if self.total_value == 0.0:
            return {s.sleeve.name: 0.0 for s in self.specs}
        return {s.sleeve.name: v / self.total_value
                for s, v in zip(self.specs, self.sleeve_values.values())}

    def __repr__(self) -> str:
        parts = ", ".join(f"{s.sleeve.name}={s.weight:.1%}" for s in self.specs)
        return f"SubPortfolio([{parts}], value={self.total_value:,.0f})"


# ---------------------------------------------------------------------------
# Total portfolio
# ---------------------------------------------------------------------------

class Portfolio:
    """
    Total fund = LHP + RSP, mixed at the ``hedge_ratio`` level.

    Parameters
    ----------
    lhp_specs : list[SleeveSpec]
        Asset sleeves for the liability-hedging sub-portfolio.
        Weights must sum to 1.0.
    rsp_specs : list[SleeveSpec]
        Asset sleeves for the return-seeking sub-portfolio.
        Weights must sum to 1.0.
    initial_value : float
        Starting total market value of the fund.
    hedge_ratio : float
        Fraction of total assets allocated to the LHP.  Must be in [0, 1].
    rebalance_frequency : int
        Rebalance back to target weights every N steps.  Set to 0 to disable.
    """

    def __init__(
        self,
        lhp_specs: list[SleeveSpec],
        rsp_specs:  list[SleeveSpec],
        initial_value: float,
        hedge_ratio: float = 0.60,
        rebalance_frequency: int = 1,
        fx_model: FXModel | None = None,
    ) -> None:
        if not 0.0 <= hedge_ratio <= 1.0:
            raise ValueError(f"hedge_ratio must be in [0, 1], got {hedge_ratio}")

        self.hedge_ratio         = hedge_ratio
        self.rebalance_frequency = rebalance_frequency
        self._step_count         = 0
        self.total_value         = initial_value

        lhp_value = initial_value * hedge_ratio
        rsp_value = initial_value * (1.0 - hedge_ratio)

        self.lhp = SubPortfolio(lhp_specs, lhp_value)
        self.rsp = SubPortfolio(rsp_specs,  rsp_value, fx_model=fx_model)

    # ------------------------------------------------------------------
    # Stepping
    # ------------------------------------------------------------------

    def step(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        """
        Advance the whole portfolio by one period.

        Returns
        -------
        portfolio_return : float
            Value-weighted total return of the combined portfolio.
        """
        lhp_w = self.lhp.total_value / self.total_value if self.total_value else self.hedge_ratio
        rsp_w = self.rsp.total_value / self.total_value if self.total_value else (1.0 - self.hedge_ratio)

        r_lhp = self.lhp.step(state_t, state_t1, dt)
        r_rsp = self.rsp.step(state_t, state_t1, dt)

        self.total_value  = self.lhp.total_value + self.rsp.total_value
        self._step_count += 1

        if self.rebalance_frequency > 0 and self._step_count % self.rebalance_frequency == 0:
            self._rebalance()

        return lhp_w * r_lhp + rsp_w * r_rsp

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def _rebalance(self) -> None:
        """Rebalance to target hedge_ratio and intra-sub-portfolio weights."""
        self.lhp.rebalance(self.total_value * self.hedge_ratio)
        self.rsp.rebalance(self.total_value * (1.0 - self.hedge_ratio))

    # ------------------------------------------------------------------
    # Properties & reporting
    # ------------------------------------------------------------------

    @property
    def lhp_value(self) -> float:
        return self.lhp.total_value

    @property
    def rsp_value(self) -> float:
        return self.rsp.total_value

    @property
    def effective_hedge_ratio(self) -> float:
        """Current (possibly drifted) LHP fraction."""
        return self.lhp.total_value / self.total_value if self.total_value else 0.0

    def summary(self) -> dict:
        return {
            "total_value":           self.total_value,
            "lhp_value":             self.lhp_value,
            "rsp_value":             self.rsp_value,
            "effective_hedge_ratio": self.effective_hedge_ratio,
            "lhp_sleeve_values":     dict(self.lhp.sleeve_values),
            "rsp_sleeve_values":     dict(self.rsp.sleeve_values),
        }

    def __repr__(self) -> str:
        return (
            f"Portfolio(total={self.total_value:,.0f}, "
            f"LHP={self.lhp_value:,.0f} [{self.hedge_ratio:.0%}], "
            f"RSP={self.rsp_value:,.0f} [{1-self.hedge_ratio:.0%}])"
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _validate_weights(weights: list[float], label: str = "portfolio") -> None:
    total = sum(weights)
    if not np.isclose(total, 1.0, atol=1e-6):
        raise ValueError(
            f"Weights in {label} must sum to 1.0, got {total:.8f}.  "
            f"Values: {weights}"
        )
