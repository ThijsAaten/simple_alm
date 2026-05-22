"""
Growth / Return-Seeking Asset Sleeves
======================================
Return model (factor + noise), with optional valuation mean-reversion:

Base factor model (all sleeves):

    r ≈ μ·dt  +  β_g·(g − ḡ)·dt  +  β_π·π·dt  +  σ·√dt·ε

where
    μ      = long-run annualised total return
    β_g    = sensitivity to growth deviation from trend (positive = pro-cyclical)
    β_π    = inflation beta (negative for nominal equity, positive for real assets)
    g      = state_t.growth         (realised growth)
    ḡ      = long_run_growth        (calibrated trend)
    π      = state_t.inflation      (realised inflation level)
    σ      = annualised idiosyncratic volatility
    ε      ~ N(0, 1)               (drawn fresh each call)

Valuation extensions
--------------------
EquitySleeve — CAPE mean-reversion:

    r ≈ [factor model]  −  β_val · log(CAPE / CAPE_fair) · dt

    CAPE tracks price-to-earnings mechanically each step:
        log(CAPE_{t+1}) = log(CAPE_t) + (r − div_yield·dt) − LR_earnings_growth·dt

RealAssetSleeve — cap-rate mean-reversion:

    income   = cap_rate · dt
    cap_gain = −D_impl · Δcap_rate

    Δcap_rate = −κ · (cap_rate − cap_fair) · dt
              + φ · Δlong_rate              (rate pass-through)
              + σ_cr · √dt · ε₁             (idiosyncratic repricing noise)

    r = income + cap_gain + β_g·(g−ḡ)·dt + β_π·π·dt + σ·√dt·ε₂

    where  cap_fair = long_rate + risk_premium

CommoditySleeve — GSCI-consistent decomposition with geopolitical jump risk:

    r = collateral + excess + roll + jump

    collateral = short_rate · dt              T-bill return on posted futures margin
    excess     = β_g·(g−ḡ)·dt + β_π·(π−π̄)·dt + σ·√dt·ε
    roll       = roll_yield · dt              contango drag (typically −1 % to −3 %/yr)
    jump       = Σᵢ Jᵢ,  Jᵢ ~ Exp(μ_geo),  N ~ Poisson(λ_geo·dt)

    excess return uses *deviations* from long-run for both growth and inflation so
    the unconditional expected excess return is zero — consistent with the empirical
    finding that GSCI long-run total return ≈ T-bill collateral return.

Three sleeves:
  - ``EquitySleeve``      — global equities (CAPE valuation mean-reversion)
  - ``RealAssetSleeve``   — infrastructure / property (cap-rate income + repricing)
  - ``CommoditySleeve``   — commodities (GSCI decomposition + geopolitical spikes)

Extension points
----------------
- Add correlation between idiosyncratic shocks across sleeves.
- Replace the additive factor model with a log-normal GBM for option pricing.
- Replace the proxy cap rate with a separate VAR state variable (requires 8D VAR).
- Model backwardation/contango as a time-varying state variable driven by inventory levels.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from scenarios.engine import MacroState
from assets.base import AssetSleeve


# ===========================================================================
# Shared base
# ===========================================================================

class _FactorAssetSleeve(AssetSleeve):
    """Base class: stores parameters and exposes _factor_return() helper."""

    def __init__(
        self,
        name: str,
        drift: float,
        growth_beta: float,
        inflation_beta: float,
        idio_vol: float,
        long_run_growth: float,
        seed: Optional[int],
    ) -> None:
        super().__init__(name)
        self.drift           = drift
        self.growth_beta     = growth_beta
        self.inflation_beta  = inflation_beta
        self.idio_vol        = idio_vol
        self.long_run_growth = long_run_growth
        self.rng             = np.random.default_rng(seed)

    def _factor_return(self, state_t: MacroState, dt: float) -> float:
        """Systematic factor return + one idiosyncratic draw."""
        growth_dev  = state_t.growth - self.long_run_growth
        systematic  = (
            self.drift            * dt
            + self.growth_beta    * growth_dev        * dt
            + self.inflation_beta * state_t.inflation * dt
        )
        return systematic + self.idio_vol * np.sqrt(dt) * self.rng.standard_normal()

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        return self._factor_return(state_t, dt)


# ===========================================================================
# Equity sleeve — CAPE mean-reversion
# ===========================================================================

class EquitySleeve(_FactorAssetSleeve):
    """
    Global equity sleeve with CAPE-based valuation mean-reversion.

    The base return follows the factor model (drift + growth cycle + inflation
    sensitivity + idiosyncratic noise).  A valuation adjustment is added:

        val_drag = −valuation_beta · log(CAPE / cape_fair) · dt

    When CAPE > cape_fair (expensive), expected return is reduced; when CAPE <
    cape_fair (cheap), it is boosted.  CAPE is updated each step from the
    realised price return and a calibrated long-run earnings growth rate,
    so it rises in bull markets and falls when earnings outpace prices.

    Parameters
    ----------
    drift            : long-run nominal total return p.a.          (default 7 %)
    growth_beta      : sensitivity to growth deviation             (default 0.6)
    inflation_beta   : inflation sensitivity (negative for equities)(default −0.3)
    idio_vol         : annualised idiosyncratic volatility         (default 15 %)
    long_run_growth  : trend growth for deviation calculation      (default 2.5 %)
    cape             : starting CAPE ratio                         (default 25)
    cape_fair        : long-run fair CAPE (equilibrium anchor)     (default 20)
    valuation_beta   : return drag per unit of log(CAPE/cape_fair) (default 0.05)
    payout_ratio     : dividend payout ratio (for yield calculation)(default 0.50)
    long_run_earnings_growth : LR nominal earnings growth rate     (default 4 %)
    """

    def __init__(
        self,
        name: str                        = "Equity",
        drift: float                     = 0.07,
        growth_beta: float               = 0.60,
        inflation_beta: float            = -0.30,
        idio_vol: float                  = 0.15,
        long_run_growth: float           = 0.025,
        seed: Optional[int]              = None,
        # --- valuation ---
        cape: float                      = 25.0,
        cape_fair: float                 = 20.0,
        valuation_beta: float            = 0.05,
        payout_ratio: float              = 0.50,
        long_run_earnings_growth: float  = 0.04,
    ) -> None:
        super().__init__(name, drift, growth_beta, inflation_beta, idio_vol,
                         long_run_growth, seed)
        self._cape                       = float(cape)
        self._cape_fair                  = float(cape_fair)
        self._valuation_beta             = float(valuation_beta)
        self._payout_ratio               = float(payout_ratio)
        self._long_run_earnings_growth   = float(long_run_earnings_growth)

    @property
    def cape(self) -> float:
        """Current CAPE ratio (updated each period_return call)."""
        return self._cape

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        # Valuation drag / boost
        log_gap  = np.log(self._cape / self._cape_fair)
        val_drag = -self._valuation_beta * log_gap * dt

        r = self._factor_return(state_t, dt) + val_drag

        # Update CAPE: price grows at (r − dividend yield); earnings at LR rate
        div_yield  = self._payout_ratio / self._cape
        price_ret  = r - div_yield * dt
        d_log_cape = price_ret - self._long_run_earnings_growth * dt
        self._cape = float(np.clip(self._cape * np.exp(d_log_cape), 5.0, 100.0))

        return r


# ===========================================================================
# Real asset sleeve — cap-rate mean-reversion
# ===========================================================================

class RealAssetSleeve(_FactorAssetSleeve):
    """
    Real assets sleeve (infrastructure, direct property) with cap-rate-based
    valuation and income modelling.

    Return decomposition:

        r = income + cap_gain + cycle + inflation + idio

        income   = cap_rate · dt
        cap_gain = −implied_duration · Δcap_rate
        cycle    = growth_beta · (g − ḡ) · dt
        inflation= inflation_beta · π · dt
        idio     = idio_vol · √dt · ε

    Cap-rate dynamics (Ornstein-Uhlenbeck with rate pass-through):

        Δcap_rate = −cap_rate_reversion · (cap_rate − cap_fair) · dt
                  + cap_rate_pass_through · Δlong_rate
                  + cap_rate_vol · √dt · ε_cr

        cap_fair  = long_rate + risk_premium

    A rising cap rate (repricing cheaper) causes a capital loss via the
    implied_duration term; the income yield rises over subsequent periods.
    A falling cap rate causes a capital gain with lower future income.

    Note: the ``drift`` parameter is superseded by the dynamic cap-rate income
    and is ignored in period_return.  It is retained only for API compatibility.

    Parameters
    ----------
    drift               : unused (superseded by cap-rate income)    (default 6 %)
    growth_beta         : pro-cyclical growth sensitivity           (default 0.3)
    inflation_beta      : direct inflation pass-through             (default 0.7)
    idio_vol            : return idiosyncratic vol (not cap-rate)   (default 10 %)
    initial_cap_rate    : starting cap rate (income yield)          (default 5.5 %)
    risk_premium        : spread of fair cap rate over long bond    (default 1.0 %)
    cap_rate_reversion  : O-U mean-reversion speed (yr⁻¹)          (default 0.20)
    cap_rate_pass_through: fraction of long-rate change in cap rate (default 0.50)
    cap_rate_vol        : annualised cap-rate innovation vol        (default 0.8 %)
    implied_duration    : price sensitivity to cap-rate (years)     (default 15)
    """

    def __init__(
        self,
        name: str                   = "RealAssets",
        drift: float                = 0.06,
        growth_beta: float          = 0.30,
        inflation_beta: float       = 0.70,
        idio_vol: float             = 0.10,
        long_run_growth: float      = 0.025,
        seed: Optional[int]         = None,
        # --- cap-rate valuation ---
        initial_cap_rate: float     = 0.055,
        risk_premium: float         = 0.010,
        cap_rate_reversion: float   = 0.20,
        cap_rate_pass_through: float= 0.50,
        cap_rate_vol: float         = 0.008,
        implied_duration: float     = 15.0,
    ) -> None:
        super().__init__(name, drift, growth_beta, inflation_beta, idio_vol,
                         long_run_growth, seed)
        self._cap_rate              = float(initial_cap_rate)
        self._risk_premium          = float(risk_premium)
        self._cap_rate_reversion    = float(cap_rate_reversion)
        self._cap_rate_pass_through = float(cap_rate_pass_through)
        self._cap_rate_vol          = float(cap_rate_vol)
        self._implied_duration      = float(implied_duration)

    @property
    def cap_rate(self) -> float:
        """Current cap rate (updated each period_return call)."""
        return self._cap_rate

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        fair_cap_rate     = state_t.long_rate + self._risk_premium
        long_rate_change  = state_t1.long_rate - state_t.long_rate

        # Cap rate evolution: O-U reversion + rate pass-through + noise
        cap_rate_change = (
            -self._cap_rate_reversion    * (self._cap_rate - fair_cap_rate) * dt
            + self._cap_rate_pass_through * long_rate_change
            + self._cap_rate_vol          * np.sqrt(dt) * self.rng.standard_normal()
        )

        # Return components
        income   = self._cap_rate * dt
        cap_gain = -self._implied_duration * cap_rate_change
        cycle    = self.growth_beta    * (state_t.growth - self.long_run_growth) * dt
        infl     = self.inflation_beta * state_t.inflation * dt
        idio     = self.idio_vol       * np.sqrt(dt) * self.rng.standard_normal()

        r = income + cap_gain + cycle + infl + idio

        # Update cap rate (soft floor 0.5 %, ceiling 20 %)
        self._cap_rate = float(np.clip(self._cap_rate + cap_rate_change, 0.005, 0.20))

        return r


# ===========================================================================
# Commodity sleeve — GSCI-consistent decomposition with geopolitical jumps
# ===========================================================================

class CommoditySleeve(_FactorAssetSleeve):
    """
    Commodity sleeve using a GSCI-consistent three-component decomposition plus
    a geopolitical supply-shock jump process.

    Return decomposition:

        r = collateral + excess_return + roll + jump

        collateral    = short_rate · dt
        excess_return = β_g · (g − ḡ) · dt  +  β_π · (π − π̄) · dt  +  σ · √dt · ε
        roll          = roll_yield · dt
        jump          = Σᵢ Jᵢ,   Jᵢ ~ Exp(geo_jump_mean),   N ~ Poisson(geo_intensity · dt)

    The ``collateral`` term reflects the T-bill return earned on the cash posted
    as margin for futures positions.  The ``excess_return`` uses *deviations* from
    long-run targets for both growth and inflation, so the unconditional excess
    return is zero — consistent with the empirical finding that GSCI total return
    ≈ collateral yield over long horizons.

    The ``roll`` term captures the structural contango drag (most commodity futures
    markets spend more time in contango than backwardation, creating a negative
    roll yield for passive long investors).

    The ``jump`` term models geopolitical supply shocks (e.g. Middle East conflicts,
    Russia-Ukraine, OPEC cuts).  Jump sizes are exponentially distributed — always
    positive (price spikes, not compressions) — and the arrival rate is fixed rather
    than state-dependent, because geopolitics arrive exogenously.

    Note: ``drift`` is ignored at runtime (superseded by the collateral + roll
    decomposition).  It is retained only for API compatibility.

    Parameters
    ----------
    drift              : ignored — superseded by collateral + roll   (default 0.0)
    growth_beta        : pro-cyclical demand sensitivity             (default 0.4)
    inflation_beta     : inflation sensitivity (deviation from LR)   (default 1.2)
    idio_vol           : annualised idiosyncratic vol                (default 25 %)
    long_run_growth    : trend growth for deviation calculation      (default 2.5 %)
    long_run_inflation : trend inflation for deviation calculation   (default 2.5 %)
    roll_yield         : annual contango drag (negative = cost)      (default −1.0 %)
    geo_intensity      : geopolitical jumps per year                 (default 0.10)
    geo_jump_mean      : mean commodity return per jump (Exp scale)  (default 8.0 %)
    """

    def __init__(
        self,
        name: str                   = "Commodities",
        drift: float                = 0.0,
        growth_beta: float          = 0.40,
        inflation_beta: float       = 1.20,
        idio_vol: float             = 0.25,
        long_run_growth: float      = 0.025,
        seed: Optional[int]         = None,
        # --- GSCI decomposition ---
        long_run_inflation: float   = 0.025,
        roll_yield: float           = -0.010,
        # --- geopolitical jump ---
        geo_intensity: float        = 0.10,
        geo_jump_mean: float        = 0.08,
    ) -> None:
        super().__init__(name, drift, growth_beta, inflation_beta, idio_vol,
                         long_run_growth, seed)
        self._long_run_inflation = long_run_inflation
        self._roll_yield         = roll_yield
        self._geo_intensity      = geo_intensity
        self._geo_jump_mean      = geo_jump_mean

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        # 1. Collateral yield — T-bill return on posted margin
        collateral = state_t.short_rate * dt

        # 2. Excess return — factor deviations only (zero in equilibrium)
        growth_dev = state_t.growth     - self.long_run_growth
        inf_dev    = state_t.inflation  - self._long_run_inflation
        excess = (
            self.growth_beta    * growth_dev * dt
            + self.inflation_beta * inf_dev    * dt
            + self.idio_vol * np.sqrt(dt) * self.rng.standard_normal()
        )

        # 3. Roll yield (contango drag)
        roll = self._roll_yield * dt

        # 4. Geopolitical supply-shock jump (one-sided: price spikes only)
        n_jumps  = int(self.rng.poisson(self._geo_intensity * dt))
        jump_ret = (
            float(self.rng.exponential(self._geo_jump_mean, size=n_jumps).sum())
            if n_jumps > 0 else 0.0
        )

        return collateral + excess + roll + jump_ret
