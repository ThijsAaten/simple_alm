"""
EM / Developing-Market Government Bond Sleeves
===============================================
Government bonds from developing and managed markets that require their own
yield-curve dynamics rather than inheriting the EUR Diebold-Li curve used in
``assets/bonds.py``.

Each sleeve models the *local-currency* total return.  Currency translation to
EUR is applied separately via the FXModel overlay (to be wired in a future
update).

Return decomposition
--------------------
For each sleeve:

    r = carry  +  price_change

    carry        = cgb_yield_t × dt

    price_change = −D_mod × Δy  +  ½ × C × (Δy)²

    Δy           = (mean-reversion pull)
                 + (global rate pass-through)
                 + (idiosyncratic shock)

Yield dynamics (Ornstein-Uhlenbeck with global co-movement)
-----------------------------------------------------------

    Δy = −κ × (y_t − ȳ) × dt
       + β_global × Δy_EUR × dt          (pass-through from EUR/global rates)
       + σ × √dt × ε,   ε ~ N(0,1)

where
    κ           = mean-reversion speed (yr⁻¹)
    ȳ           = long-run CGB yield
    β_global    = sensitivity to changes in EUR long rate
    σ           = annualised idiosyncratic yield volatility

PBOC management (ChinaGovernmentBondSleeve)
-------------------------------------------
The PBOC actively manages the yield curve, resulting in:
  - Higher mean-reversion speed (κ ≈ 0.25) vs western bonds (κ ≈ 0.10–0.15)
  - Lower idiosyncratic vol (σ ≈ 50 bp/yr) vs western bonds (~100 bp/yr)
  - Partial but imperfect co-movement with global rates (β ≈ 0.20–0.30)

Extension points
----------------
Future sleeves that fit naturally in this module:
  - IndiaGovernmentBondSleeve  (RBI-managed, higher nominal yields, rupee exposure)
  - KoreaTreasurySleeve        (more open, higher β_global)
  - BrazilGovernmentBondSleeve (very high nominal yields, BRL volatility)
"""

from __future__ import annotations

import math

import numpy as np

from scenarios.engine import MacroState, YieldCurve
from assets.base import AssetSleeve


class ChinaGovernmentBondSleeve(AssetSleeve):
    """
    China central government bond (CGB) in local currency (CNY).

    The CGB yield follows an O-U process with PBOC-managed parameters:
    fast mean-reversion to a structurally low long-run yield and low
    idiosyncratic volatility relative to western government bonds.

    Local-currency return only.  Apply FXModel CNY/EUR overlay separately.

    Parameters
    ----------
    name : str
        Identifier used in reports.
    duration : float
        Modified duration (years).  10Y CGB ≈ 7–8 yr.
    maturity : float or None
        Average maturity used to determine initial yield; defaults to
        ``duration`` if None.
    convexity : float or None
        Convexity (yr²).  If None, uses the par-bond approximation D².
    initial_yield : float
        Starting CGB yield (annualised).  ~2.3 % for 10Y CGB in 2024–25.
    long_run_yield : float
        Equilibrium CGB yield the O-U process reverts to.
        ~2.5 % consistent with PBOC inflation target of 2–3 % and low
        neutral real rates in a high-savings economy.
    yield_reversion : float
        O-U mean-reversion speed κ (yr⁻¹).  0.25 ≈ 4-year half-life,
        reflecting active PBOC yield-curve management (vs ~0.10 for EUR).
    global_rate_beta : float
        Sensitivity to changes in the EUR long rate (Δlong_rate_EUR).
        0.25 reflects partial but imperfect integration with global bond
        markets due to capital controls and PBOC intervention.
    idio_yield_vol : float
        Annualised idiosyncratic yield volatility (σ).  ~50 bp for CGBs
        (vs ~100 bp for EUR govts) due to PBOC suppression of volatility.
    lambda_ : float
        Nelson-Siegel shape parameter for EUR curve (used only to compute
        Δlong_rate_EUR for the pass-through term).  Default 5.0.
    seed : int or None
        RNG seed for reproducibility.
    """

    def __init__(
        self,
        name:             str        = "CGB",
        duration:         float      = 7.0,
        maturity:         float | None = None,
        convexity:        float | None = None,
        initial_yield:    float      = 0.023,
        long_run_yield:   float      = 0.025,
        yield_reversion:  float      = 0.25,
        global_rate_beta: float      = 0.25,
        idio_yield_vol:   float      = 0.005,
        lambda_:          float      = 5.0,
        seed:             int | None = None,
    ) -> None:
        super().__init__(name)
        self.duration         = duration
        self.maturity         = maturity if maturity is not None else duration
        self._convexity       = convexity
        self.long_run_yield   = long_run_yield
        self.yield_reversion  = yield_reversion
        self.global_rate_beta = global_rate_beta
        self.idio_yield_vol   = idio_yield_vol
        self.lambda_          = lambda_
        self._cgb_yield       = initial_yield
        self._rng             = np.random.default_rng(seed)

    @property
    def convexity(self) -> float:
        return self._convexity if self._convexity is not None else self.duration ** 2

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        # Change in EUR long rate (global pass-through reference)
        eur_long_t  = YieldCurve(state_t,  self.lambda_).nominal_rate(self.maturity)
        eur_long_t1 = YieldCurve(state_t1, self.lambda_).nominal_rate(self.maturity)
        d_eur = eur_long_t1 - eur_long_t

        # O-U yield dynamics: mean-reversion + global pass-through + idio shock
        mean_pull   = -self.yield_reversion * (self._cgb_yield - self.long_run_yield) * dt
        global_pull = self.global_rate_beta * d_eur
        idio_shock  = self.idio_yield_vol * math.sqrt(dt) * self._rng.standard_normal()
        d_cgb = mean_pull + global_pull + idio_shock

        carry     = self._cgb_yield * dt
        price_chg = -self.duration * d_cgb + 0.5 * self.convexity * d_cgb ** 2

        self._cgb_yield = max(0.0, self._cgb_yield + d_cgb)

        return carry + price_chg
