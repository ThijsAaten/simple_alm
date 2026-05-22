"""
Liability Model
===============
Represents a stream of future cash-flow obligations whose present value is
sensitive to interest rates and inflation.

Key concepts
------------
- Cash flows are typed as ``"nominal"`` (fixed €) or ``"real"`` (CPI-indexed).
- Discounting uses the full Diebold-Li (Nelson-Siegel) yield curve built from
  the ``MacroState``.  All three factors — level, slope, and curvature — affect
  discount rates at every maturity, so curve-shape changes (steepening,
  flattening, hump) are correctly reflected in the liability PV.
- Real cash flows are discounted at the real yield curve derived from the
  ``real_rate`` macro state variable (long-end real yield).
- Duration and inflation sensitivity are computed via bump-and-reprice so they
  automatically remain consistent with any yield-curve shape in use.

Extension points
----------------
- Replace the Nelson-Siegel approximation with a full term-structure model.
- Add a credit-adjusted discount curve for corporate pension liabilities.
- Support lump-sum benefits, mortality tables, or stochastic cash flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from scenarios.engine import MacroState, YieldCurve


# ===========================================================================
# Cash-flow schedule
# ===========================================================================

@dataclass
class CashFlow:
    """A single liability obligation."""

    time:   float                        # years from valuation date
    amount: float                        # base amount (nominal € or today's real €)
    kind:   Literal["nominal", "real"]   # determines which yield curve is used


@dataclass
class LiabilitySchedule:
    """An ordered collection of liability cash flows."""

    cash_flows: list[CashFlow]

    # ------------------------------------------------------------------
    # Named constructors
    # ------------------------------------------------------------------

    @classmethod
    def level_annuity(
        cls,
        annual_payment: float,
        n_years: int,
        kind: Literal["nominal", "real"] = "nominal",
    ) -> LiabilitySchedule:
        """Uniform annual payments of a single type."""
        return cls([
            CashFlow(time=float(t), amount=annual_payment, kind=kind)
            for t in range(1, n_years + 1)
        ])

    @classmethod
    def blended_annuity(
        cls,
        annual_payment: float,
        n_years: int,
        real_fraction: float = 0.5,
    ) -> LiabilitySchedule:
        """
        Annual payment split between a CPI-linked tranche and a nominal tranche.

        Parameters
        ----------
        real_fraction : float
            Fraction of ``annual_payment`` that is CPI-indexed.  The remainder
            is fixed nominal.
        """
        flows: list[CashFlow] = []
        for t in range(1, n_years + 1):
            flows.append(CashFlow(float(t), annual_payment * real_fraction,        "real"))
            flows.append(CashFlow(float(t), annual_payment * (1 - real_fraction),  "nominal"))
        return cls(flows)

    @classmethod
    def custom(
        cls,
        times:   list[float],
        amounts: list[float],
        kinds:   list[Literal["nominal", "real"]],
    ) -> LiabilitySchedule:
        """Build from explicit lists."""
        return cls([CashFlow(t, a, k) for t, a, k in zip(times, amounts, kinds)])

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @property
    def max_maturity(self) -> float:
        return max(cf.time for cf in self.cash_flows)

    def __len__(self) -> int:
        return len(self.cash_flows)


# ===========================================================================
# Liability model
# ===========================================================================

class LiabilityModel:
    """
    Values a LiabilitySchedule under a given MacroState.

    Discounting uses the full Diebold-Li (Nelson-Siegel) yield curve built from
    ``scenarios.engine.YieldCurve``, so all three curve factors (level, slope,
    curvature) affect the present value.  The PV formula is:

        PV = Σ_i  amount_i × DF(time_i, kind_i)

    where ``DF(τ, "nominal") = exp(−r_nom(τ) · τ)``
    and   ``DF(τ, "real")    = exp(−r_real(τ) · τ)``.

    Sensitivity metrics (duration, inflation PV01) are computed via finite-
    difference bumps so they automatically reflect the full curve shape.

    Parameters
    ----------
    schedule : LiabilitySchedule
        The stream of future obligations to be valued.
    lambda_  : float
        Nelson-Siegel shape parameter (years).  Controls where the curvature
        loading peaks: peak maturity ≈ λ · ln 2 ≈ 0.693 · λ.
        Must match the ``lambda_`` used in asset sleeves if duration matching
        is required.  Default 5.0 yr.
    """

    def __init__(
        self,
        schedule: LiabilitySchedule,
        lambda_:  float = 5.0,
    ) -> None:
        self.schedule = schedule
        self.lambda_  = lambda_

    # ------------------------------------------------------------------
    # Valuation
    # ------------------------------------------------------------------

    def present_value(self, state: MacroState) -> float:
        """Present value of all liability cash flows under ``state``."""
        curve = YieldCurve(state, self.lambda_)
        return sum(
            cf.amount * curve.discount_factor(cf.time, cf.kind)
            for cf in self.schedule.cash_flows
        )

    # ------------------------------------------------------------------
    # Sensitivities (bump-and-reprice)
    # ------------------------------------------------------------------

    def duration(self, state: MacroState, bump: float = 1e-4) -> float:
        """
        Modified duration of the liability (years).

        Defined as −(∂PV/∂r) / PV for a parallel shift in both nominal and
        real yield curves (all three Nelson-Siegel factors shifted equally).
        """
        pv0 = self.present_value(state)
        if pv0 == 0.0:
            return 0.0
        shocked = MacroState(
            short_rate    = state.short_rate    + bump,
            long_rate     = state.long_rate     + bump,
            real_rate     = state.real_rate     + bump,
            inflation     = state.inflation,
            growth        = state.growth,
            credit_spread = state.credit_spread,
            curvature     = state.curvature,          # shape held fixed
        )
        pv1 = self.present_value(shocked)
        return -(pv1 - pv0) / (bump * pv0)

    def curvature_pv01(self, state: MacroState, bump: float = 1e-4) -> float:
        """
        Curvature sensitivity: % change in PV per 1 bp increase in β₂.

        A positive value means the liability becomes more expensive when the
        curve humps (typical for liabilities concentrated at medium maturities).
        Long-duration pension liabilities are generally insensitive to curvature
        because the Nelson-Siegel curvature loading tends to zero at long maturities.
        """
        pv0 = self.present_value(state)
        if pv0 == 0.0:
            return 0.0
        shocked = MacroState(
            short_rate    = state.short_rate,
            long_rate     = state.long_rate,
            real_rate     = state.real_rate,
            inflation     = state.inflation,
            growth        = state.growth,
            credit_spread = state.credit_spread,
            curvature     = state.curvature + bump,
        )
        pv1 = self.present_value(shocked)
        return (pv1 - pv0) / (bump * pv0)

    def inflation_pv01(self, state: MacroState, bump: float = 1e-4) -> float:
        """
        Inflation sensitivity: % change in PV per 1 bp increase in breakeven
        inflation (i.e. real rate falls by ``bump``, nominal rate unchanged).
        """
        pv0 = self.present_value(state)
        if pv0 == 0.0:
            return 0.0
        shocked = MacroState(
            short_rate    = state.short_rate,
            long_rate     = state.long_rate,
            real_rate     = state.real_rate   - bump,   # lower real → higher breakeven
            inflation     = state.inflation   + bump,
            growth        = state.growth,
            credit_spread = state.credit_spread,
            curvature     = state.curvature,
        )
        pv1 = self.present_value(shocked)
        return (pv1 - pv0) / (bump * pv0)

    def cashflow_pv_breakdown(self, state: MacroState) -> list[dict]:
        """Return per-cash-flow PV breakdown (useful for debugging / reporting)."""
        curve = YieldCurve(state, self.lambda_)
        return [
            {
                "time":   cf.time,
                "kind":   cf.kind,
                "amount": cf.amount,
                "df":     curve.discount_factor(cf.time, cf.kind),
                "pv":     cf.amount * curve.discount_factor(cf.time, cf.kind),
            }
            for cf in self.schedule.cash_flows
        ]
