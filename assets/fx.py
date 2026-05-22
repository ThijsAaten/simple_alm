"""
FX Overlay — Currency Return Model
====================================
``FXModel`` is a shared simulation utility, not an asset sleeve.  It is
attached to a ``SubPortfolio`` and computes one period's return for every
tracked currency in a single call.  The ``SubPortfolio`` then scales each
sleeve's local return by its unhedged currency exposures.

Return decomposition per currency (annual)
------------------------------------------

  r = carry + fx_drift + macro_betas + ppp_correction + idio

  carry          = carry_spread × dt
                   (foreign short rate − EUR short rate)

  fx_drift       = fx_drift × dt
                   Secular trend: negative for debasement / EM inflation
                   erosion, positive for structural appreciation (CHF, SGD).

  macro_betas    = inflation_loading × (π − π̄) × dt
                 + growth_loading    × (g − ḡ) × dt
                   EUR inflation above target → EUR weakens → foreign gains.
                   EUR growth above trend    → EUR strengthens → foreign loses.

  ppp_correction = −ppp_reversion × ppp_gap × dt
                   Slow mean-reversion toward PPP equilibrium.

  idio           = idio_vol × √dt × ε,  ε ~ N(0,1)

PPP gap dynamics
----------------
  ppp_gap_{t+1} = (1 − ppp_reversion × dt) × ppp_gap_t  +  idio_t

  initial_ppp_gap < 0  →  foreign currency undervalued vs EUR on PPP terms
                          (expect a tailwind as gap closes toward zero).
  initial_ppp_gap > 0  →  overvalued (headwind).

Usage pattern
-------------
  fx = FXModel.default(seed=42)          # all 13 currencies pre-calibrated

  # Per sleeve (set once in build_rsp_specs / build_lhp_specs):
  eq_sleeve.fx_exposures = {"USD": 0.35, "JPY": 0.05, "GBP": 0.05}

  # Pass to SubPortfolio:
  rsp_sub = SubPortfolio(rsp_specs, initial_value=1.0, fx_model=fx)

  # SubPortfolio.step() calls fx.step() once per period and distributes.

Supported currencies (EUR is the domestic base)
------------------------------------------------
  USD, GBP, CAD, AUD, CHF, JPY, CNY, HKD, TWD, KRW, SGD, THB, INR

Asian undervaluation thesis
----------------------------
Asian currencies (JPY, CNY, TWD, KRW, SGD, THB, INR) carry a negative
``initial_ppp_gap``, encoding the view that they are structurally cheap
relative to EUR on purchasing-power-parity terms.  As these gaps close over
a 5–12 year horizon the positions generate a real FX tailwind that diversifies
against European financial-repression and dollar-debasement scenarios.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from scenarios.engine import MacroState


@dataclass
class CurrencyParams:
    """
    Calibration parameters for a single foreign currency vs EUR.

    All rates are annualised decimals (e.g. 0.015 = 1.5 %).

    Parameters
    ----------
    carry_spread      : foreign short rate − EUR short rate.
    fx_drift          : secular trend vs EUR (neg = depreciation).
    inflation_loading : return per 1 pp of EUR inflation above long-run level.
                        Positive: EUR inflation → EUR weakens → foreign gains.
    growth_loading    : return per 1 pp of EUR growth above long-run trend.
                        Negative for USD (EUR growth → EUR strengthens).
    ppp_reversion     : O-U mean-reversion speed (yr⁻¹).  0.10 ≈ 7-yr ½-life.
    initial_ppp_gap   : starting deviation from PPP.
                        Negative = foreign currency undervalued (tailwind).
    idio_vol          : annual FX volatility.
    long_run_inflation: neutral CPI (must match VAR calibration).
    long_run_growth   : neutral GDP growth (must match VAR calibration).
    """
    carry_spread:        float
    fx_drift:            float
    inflation_loading:   float
    growth_loading:      float
    ppp_reversion:       float
    initial_ppp_gap:     float = 0.0
    idio_vol:            float = 0.10
    long_run_inflation:  float = 0.025
    long_run_growth:     float = 0.025


# ---------------------------------------------------------------------------
# Default calibration for all 13 supported currencies
# ---------------------------------------------------------------------------

_DEFAULT_CURRENCIES: dict[str, CurrencyParams] = {
    # ── G10 majors ──────────────────────────────────────────────────────────
    "USD": CurrencyParams(
        carry_spread       =  0.015,   # Fed ~150 bp above ECB on average
        fx_drift           = -0.010,   # dollar debasement / US twin-deficit
        inflation_loading  =  0.50,    # EUR inflation → EUR weakens → USD gains
        growth_loading     = -0.30,    # EUR growth → EUR strengthens → USD loses
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.10,    # EUR/USD 10-yr realised vol ≈ 8–10 %
    ),
    "GBP": CurrencyParams(
        carry_spread       =  0.005,   # BoE slightly above ECB on average
        fx_drift           = -0.005,   # mild depreciation bias (post-Brexit structural damage)
        inflation_loading  =  0.30,
        growth_loading     = -0.20,
        ppp_reversion      =  0.10,
        initial_ppp_gap    = -0.05,    # slight undervaluation post-Brexit
        idio_vol           =  0.09,
    ),
    "CAD": CurrencyParams(
        carry_spread       =  0.005,
        fx_drift           =  0.000,   # commodity-linked; roughly neutral trend
        inflation_loading  =  0.20,
        growth_loading     =  0.10,    # positive: oil-exporter benefits from global growth
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.08,
    ),
    "AUD": CurrencyParams(
        carry_spread       =  0.010,   # RBA historically above ECB
        fx_drift           =  0.000,
        inflation_loading  =  0.10,
        growth_loading     =  0.20,    # growth-positive; iron ore & resource exposure
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.11,
    ),
    "CHF": CurrencyParams(
        carry_spread       = -0.005,   # SNB yields below ECB; negative carry
        fx_drift           =  0.005,   # structural appreciation (current-account surplus)
        inflation_loading  = -0.30,    # EUR inflation → EUR weakens → CHF gains in EUR terms
        growth_loading     = -0.50,    # risk-off / EUR slowdown → CHF safe-haven rally
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.08,
    ),
    # ── Japanese yen ────────────────────────────────────────────────────────
    "JPY": CurrencyParams(
        carry_spread       = -0.008,   # BOJ rates deeply negative / near-zero vs ECB
        fx_drift           =  0.003,   # long-run appreciation bias despite low carry
        inflation_loading  = -0.20,    # safe-haven; gains when EUR weakens
        growth_loading     = -0.40,    # risk-off flight → JPY rallies
        ppp_reversion      =  0.08,    # BOJ intervention slows PPP convergence
        initial_ppp_gap    = -0.25,    # JPY historically ~25 % undervalued vs EUR on PPP
        idio_vol           =  0.09,
    ),
    # ── Chinese renminbi ────────────────────────────────────────────────────
    "CNY": CurrencyParams(
        carry_spread       =  0.005,   # PBOC policy rate ≈ EUR neutral in long run
        fx_drift           =  0.005,   # managed appreciation as China moves up value chain
        inflation_loading  =  0.10,
        growth_loading     =  0.30,    # strong global growth → risk-on → CNY gains
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.20,    # Balassa-Samuelson undervaluation in rapidly developing economy
        idio_vol           =  0.05,    # PBOC suppresses FX volatility (~5 %)
    ),
    "HKD": CurrencyParams(
        carry_spread       =  0.015,   # currency board pegged to USD; USD carry passes through
        fx_drift           =  0.000,   # peg → no secular trend vs USD; vs EUR tracks USD drift
        inflation_loading  =  0.10,
        growth_loading     = -0.10,
        ppp_reversion      =  0.15,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.03,    # near-zero idio vol due to currency board
    ),
    # ── Taiwan dollar ────────────────────────────────────────────────────────
    "TWD": CurrencyParams(
        carry_spread       =  0.005,
        fx_drift           =  0.005,   # persistent current-account surplus → appreciation
        inflation_loading  =  0.10,
        growth_loading     =  0.40,    # semiconductor cycle dominates; global growth positive
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.20,    # structural undervaluation; government manages pace
        idio_vol           =  0.07,
    ),
    # ── Korean won ──────────────────────────────────────────────────────────
    "KRW": CurrencyParams(
        carry_spread       =  0.015,
        fx_drift           =  0.003,
        inflation_loading  = -0.10,
        growth_loading     =  0.30,    # export economy; global growth positive
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.15,    # moderate undervaluation; more open than CNY/TWD
        idio_vol           =  0.10,    # more volatile; open capital account
    ),
    # ── Singapore dollar ────────────────────────────────────────────────────
    "SGD": CurrencyParams(
        carry_spread       =  0.005,
        fx_drift           =  0.005,   # MAS uses managed appreciation as monetary policy tool
        inflation_loading  = -0.20,    # partial safe-haven characteristics in Asia
        growth_loading     =  0.20,
        ppp_reversion      =  0.10,
        initial_ppp_gap    = -0.10,
        idio_vol           =  0.06,    # MAS actively damps FX volatility
    ),
    # ── Thai baht ───────────────────────────────────────────────────────────
    "THB": CurrencyParams(
        carry_spread       =  0.010,
        fx_drift           =  0.000,
        inflation_loading  = -0.10,
        growth_loading     =  0.30,    # tourism + manufacturing; growth-positive
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.15,
        idio_vol           =  0.12,    # more volatile; tourism income swings
    ),
    # ── Indian rupee ────────────────────────────────────────────────────────
    "INR": CurrencyParams(
        carry_spread       =  0.030,   # RBI rates well above ECB
        fx_drift           = -0.015,   # nominal depreciation trend (higher domestic inflation)
        inflation_loading  =  0.20,
        growth_loading     =  0.40,    # high-growth domestic story; growth-positive
        ppp_reversion      =  0.15,
        initial_ppp_gap    = -0.10,    # undervalued in real terms despite nominal depreciation
        idio_vol           =  0.07,    # RBI manages vol; lower than raw EM peers
    ),
}


class FXModel:
    """
    Shared currency-return simulator for a set of named foreign currencies.

    One ``FXModel`` instance is attached to a ``SubPortfolio`` and generates
    returns for all currencies in a single ``step()`` call, ensuring:
      - One RNG draw per currency per period (consistent across sleeves).
      - One PPP-gap update per currency per period.

    Parameters
    ----------
    currencies : dict[str, CurrencyParams]
        Mapping from currency code to calibration parameters.
        EUR is the implicit domestic base; do not include it here.
    seed : int or None
        RNG seed.  Pass a per-replication seed to get variance across runs.
    """

    def __init__(
        self,
        currencies: dict[str, CurrencyParams],
        seed: int | None = None,
    ) -> None:
        self._params   = currencies
        self._ppp_gaps = {name: p.initial_ppp_gap for name, p in currencies.items()}
        self._rng      = np.random.default_rng(seed)

    @property
    def currencies(self) -> list[str]:
        """Names of the currencies tracked by this model."""
        return list(self._params.keys())

    def step(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> dict[str, float]:
        """
        Compute one period's return for every currency and advance PPP gaps.

        Returns
        -------
        returns : dict[str, float]
            Total return (decimal) for each currency vs EUR.
        """
        returns: dict[str, float] = {}
        for name, p in self._params.items():
            gap   = self._ppp_gaps[name]
            carry = p.carry_spread * dt
            drift = p.fx_drift * dt

            infl_excess   = state_t.inflation - p.long_run_inflation
            growth_excess = state_t.growth    - p.long_run_growth
            macro = (p.inflation_loading * infl_excess
                     + p.growth_loading * growth_excess) * dt

            ppp_correction = -p.ppp_reversion * gap * dt
            idio           = p.idio_vol * math.sqrt(dt) * self._rng.standard_normal()

            returns[name]        = carry + drift + macro + ppp_correction + idio
            self._ppp_gaps[name] = (1.0 - p.ppp_reversion * dt) * gap + idio

        return returns

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def default(cls, seed: int | None = None) -> "FXModel":
        """Return an FXModel with all 13 pre-calibrated currencies."""
        return cls(_DEFAULT_CURRENCIES, seed=seed)

    @classmethod
    def subset(
        cls,
        currencies: list[str],
        seed: int | None = None,
    ) -> "FXModel":
        """Return an FXModel containing only the listed currencies."""
        unknown = set(currencies) - _DEFAULT_CURRENCIES.keys()
        if unknown:
            raise ValueError(f"Unknown currencies: {unknown}.  "
                             f"Available: {list(_DEFAULT_CURRENCIES)}")
        return cls({c: _DEFAULT_CURRENCIES[c] for c in currencies}, seed=seed)

    def __repr__(self) -> str:
        return f"FXModel(currencies={self.currencies})"
