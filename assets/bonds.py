"""
Nominal Bond Sleeves
====================
Return model (duration approximation with Diebold-Li yield at bond maturity):

    r_bond ≈ y(τ)·dt  −  D_mod·Δy(τ)  +  ½·C·(Δy(τ))²

where
    y(τ)   = Nelson-Siegel nominal spot rate at the bond's average maturity τ
    D_mod  = modified duration (years)
    C      = convexity ≈ D²   (par-bond approximation)
    Δy(τ)  = y_t1(τ) − y_t(τ)  — yield change at maturity τ

Because the yield is read from the full Diebold-Li curve rather than from
``state.long_rate`` alone, non-parallel curve moves (steepening, flattening,
hump) are correctly reflected in the bond's carry and price change.

Two sleeves are provided:

NominalBondSleeve
    Plain government bond; repriced at its maturity on the Nelson-Siegel curve.

CreditBondSleeve
    Extends NominalBondSleeve with:
      - Credit spread in carry and spread-duration repricing.
      - Poisson compound-jump component on the credit spread.

Poisson jump model (CreditBondSleeve)
--------------------------------------
Within each period a random number of spread-widening events arrive:

    N(dt) ~ Poisson(λ(state_t) · dt)       number of jumps
    J_i   ~ N(μ_J, σ_J²)                   size of each jump (default μ_J=50bps, σ_J=40bps)
    total jump spread = Σ_i J_i

Jump intensity λ is a function of the current macro state:

    λ = λ_base
      + λ_cs  · max(0, cs − cs_normal)     elevated when spreads are already wide
      + λ_rec · max(0, −g)                 elevated in recessions

This captures the empirical observation that credit dislocations are rare in
Goldilocks periods and cluster in stressed regimes (recession, stagflation)
without requiring explicit regime labels — the macro state itself drives the
intensity.  Per-regime effective intensities (using default long-run means):

  Regime            cs      g      λ_eff  P(≥1 jump/yr)
  Def. Boom         0.8 %  3.5 %   0.05     ~5 %
  Def. Bust         2.0 % −0.5 %   0.16    ~15 %
  Inf. Boom         1.2 %  3.0 %   0.07     ~7 %
  Inf. Bust         3.0 % −1.0 %   0.27    ~24 %

Extension points
----------------
- Replace the single-maturity proxy with a full key-rate duration vector so
  that each cash flow is discounted separately.
- Model the credit spread as an additional VAR state variable (requires 8D VAR)
  for richer co-movement with macro factors.
- Use exponential jump sizes (always positive) for a more conservative model.
"""

from __future__ import annotations

import numpy as np

from scenarios.engine import MacroState, YieldCurve
from assets.base import AssetSleeve


# ===========================================================================
# Nominal government bond
# ===========================================================================

class NominalBondSleeve(AssetSleeve):
    """
    Nominal government bond sleeve.

    The yield used for carry and repricing is the Diebold-Li Nelson-Siegel
    spot rate at ``maturity`` years, so the bond is correctly priced when the
    yield curve steepens, flattens, or humps — not just when it shifts in
    parallel.

    Parameters
    ----------
    duration : float
        Modified duration (years).  Typical long-bond: 15–25 yr.
    maturity : float or None
        Average maturity of the bond (years) used to look up the yield on the
        Nelson-Siegel curve.  If ``None``, ``duration`` is used as a proxy
        (exact for a zero-coupon bond; slightly underestimates for coupon bonds).
    convexity : float or None
        Convexity (yr²).  If ``None`` the par-bond approximation D² is used.
    lambda_  : float
        Nelson-Siegel shape parameter — must match the value used in
        ``LiabilityModel`` if duration-matching is required.  Default 5.0 yr.
    """

    def __init__(
        self,
        name:      str              = "NominalBond",
        duration:  float            = 15.0,
        maturity:  float | None     = None,
        convexity: float | None     = None,
        lambda_:   float            = 5.0,
    ) -> None:
        super().__init__(name)
        self.duration   = duration
        self.maturity   = maturity if maturity is not None else duration
        self._convexity = convexity
        self.lambda_    = lambda_

    @property
    def convexity(self) -> float:
        return self._convexity if self._convexity is not None else self.duration ** 2

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        # Read the yield at this bond's maturity from the full Nelson-Siegel curve
        y0 = YieldCurve(state_t,  self.lambda_).nominal_rate(self.maturity)
        y1 = YieldCurve(state_t1, self.lambda_).nominal_rate(self.maturity)
        dy = y1 - y0

        carry     = y0 * dt
        price_chg = -self.duration * dy + 0.5 * self.convexity * dy ** 2
        return carry + price_chg


# ===========================================================================
# Investment-grade credit bond (with Poisson spread jumps)
# ===========================================================================

class CreditBondSleeve(AssetSleeve):
    """
    Investment-grade credit bond sleeve with Poisson compound-jump risk.

    Extends ``NominalBondSleeve`` by including:

    1. Credit spread carry and spread-duration repricing (as before).
    2. A Poisson compound-jump process on the credit spread: a random number
       of spread-widening events arrive within each period, each drawn from a
       normal distribution.  The total jump spread widens the period's
       effective spread change, causing an additional capital loss.

    Jump intensity is state-dependent — it rises when spreads are already
    elevated and when growth is negative — so jumps are naturally more frequent
    in stressed macro regimes (recession, stagflation) than in calm ones.

    Parameters
    ----------
    duration        : float  — modified rate duration (years)
    maturity        : float or None  — average maturity for NS curve lookup;
                                       defaults to ``duration``
    spread_duration : float or None  — modified spread duration; defaults to ``duration``
    convexity       : float or None  — if None uses D²
    lambda_         : float  — Nelson-Siegel shape parameter (default 5.0 yr)
    seed            : int or None    — RNG seed for reproducible jump draws
    base_intensity  : float  — baseline jumps/yr at normal spread/growth (default 0.05)
    spread_loading  : float  — intensity per unit excess spread above spread_normal
                               (default 10.0; i.e. +1% excess spread → +0.10 jumps/yr)
    recession_loading : float — intensity per unit of negative growth
                               (default 2.0; i.e. −1% growth → +0.02 jumps/yr)
    spread_normal   : float  — "normal" credit spread used for excess calculation
                               (default 1.0 % = 0.010)
    jump_mean       : float  — mean spread widening per jump (default 50 bps = 0.005)
    jump_vol        : float  — std dev of jump size (default 40 bps = 0.004)
    """

    def __init__(
        self,
        name:              str              = "CreditBond",
        duration:          float            = 10.0,
        maturity:          float | None     = None,
        spread_duration:   float | None     = None,
        convexity:         float | None     = None,
        lambda_:           float            = 5.0,
        seed:              int | None       = None,
        # --- Poisson jump parameters ---
        base_intensity:    float            = 0.05,
        spread_loading:    float            = 10.0,
        recession_loading: float            = 2.0,
        spread_normal:     float            = 0.010,
        jump_mean:         float            = 0.005,
        jump_vol:          float            = 0.004,
    ) -> None:
        super().__init__(name)
        self.duration        = duration
        self.maturity        = maturity if maturity is not None else duration
        self.spread_duration = spread_duration if spread_duration is not None else duration
        self._convexity      = convexity
        self.lambda_         = lambda_
        self._rng            = np.random.default_rng(seed)
        # jump calibration
        self._base_intensity    = base_intensity
        self._spread_loading    = spread_loading
        self._recession_loading = recession_loading
        self._spread_normal     = spread_normal
        self._jump_mean         = jump_mean
        self._jump_vol          = jump_vol

    @property
    def convexity(self) -> float:
        return self._convexity if self._convexity is not None else self.duration ** 2

    def _jump_intensity(self, state: MacroState) -> float:
        """State-dependent Poisson intensity (jumps per year)."""
        excess_spread = max(0.0, state.credit_spread - self._spread_normal)
        recession     = max(0.0, -state.growth)
        return (self._base_intensity
                + self._spread_loading    * excess_spread
                + self._recession_loading * recession)

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        gov_t  = YieldCurve(state_t,  self.lambda_).nominal_rate(self.maturity)
        gov_t1 = YieldCurve(state_t1, self.lambda_).nominal_rate(self.maturity)

        yield_t   = gov_t + state_t.credit_spread
        dy_rate   = gov_t1 - gov_t
        dy_spread = state_t1.credit_spread - state_t.credit_spread

        carry    = yield_t * dt
        rate_chg = -self.duration * dy_rate + 0.5 * self.convexity * dy_rate ** 2

        # Poisson compound jump: N jumps each of size ~ N(μ_J, σ_J²)
        intensity = self._jump_intensity(state_t)
        n_jumps   = int(self._rng.poisson(intensity * dt))
        jump_spread = (
            float(self._rng.normal(self._jump_mean, self._jump_vol, size=n_jumps).sum())
            if n_jumps > 0 else 0.0
        )

        # Smooth VAR spread change + jump treated as a single effective spread move
        total_dy_spread = dy_spread + jump_spread
        spread_chg = (-self.spread_duration * total_dy_spread
                      + 0.5 * self.convexity * total_dy_spread ** 2)

        return carry + rate_chg + spread_chg
