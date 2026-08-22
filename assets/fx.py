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

  macro_betas    = inflation_loading      × (π − π̄) × dt
                 + growth_loading         × (g − ḡ) × dt
                 + global_growth_loading  × (G − Ḡ) × dt

                   THREE CONVENTIONS, ALL EXPLICIT:

                   (1) inflation_loading — EUR inflation above target → EUR
                       weakens → foreign gains. POSITIVE for every currency.

                   (2) growth_loading — EURO-AREA growth above trend → EUR
                       strengthens → foreign loses. NEGATIVE for every
                       currency. `g` is state.growth, which is euro growth.

                   (3) global_growth_loading — WORLD growth above trend → risk
                       appetite rises → cyclical exporters gain, safe havens
                       lose. SIGNED: positive for KRW/IDR/INR, negative for
                       JPY, zero where dollar-tracking explains everything.
                       `G` is state.global_growth (added 2026-08).

                   (2) and (3) exist separately because they were previously
                   confounded. The table used to carry POSITIVE growth loadings
                   for CNY/TWD/KRW/CAD/AUD justified by comments about "global
                   growth" and "risk-on" — a factor the model did not have.
                   Those values were wrong against convention (2) while the
                   economics the comments described was real and measurable.
                   Adding (3) puts that economics where it belongs instead of
                   flipping signs and losing it.

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
  USD, GBP, CAD, AUD, CHF, JPY, CNY, HKD, TWD, KRW, SGD, THB, IDR, VND, INR

Asian undervaluation thesis
----------------------------
Asian currencies (JPY, CNY, TWD, KRW, SGD, THB, IDR, VND, INR) carry a negative
``initial_ppp_gap``, encoding the view that they are structurally cheap
relative to EUR on purchasing-power-parity terms.  As these gaps close over
a 5–12 year horizon the positions generate a real FX tailwind that diversifies
against European financial-repression scenarios.

Note the limit of that claim for the RMB.  CNY's ``inflation_loading`` of 0.45
is USD's 0.50 scaled by the ~0.92 RMB-USD correlation the article measures from
a EUR base.  A currency that inherits 90% of the dollar's behaviour against the
euro diversifies well against EUR repression and poorly against USD debasement —
the same correlation gives both results, and the second should not be claimed.
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
    growth_loading    : return per 1 pp of EURO-AREA growth above long-run trend.
                        NEGATIVE FOR EVERY CURRENCY by the convention above:
                        euro growth above trend strengthens the EUR, so the
                        foreign currency loses. Magnitude scales with how much
                        the currency tracks the dollar.
    global_growth_loading : return per 1 pp of GLOBAL growth above world trend.
                        POSITIVE for cyclical exporters (KRW, IDR, INR),
                        NEGATIVE for safe havens (JPY), ZERO for currencies
                        whose behaviour is fully explained by dollar-tracking
                        (HKD, VND, CNY). This is where cyclical exposure lives;
                        it must NOT be smuggled into growth_loading.
    ppp_reversion     : O-U mean-reversion speed (yr⁻¹).  0.10 ≈ 7-yr ½-life.
    initial_ppp_gap   : starting deviation from PPP.
                        Negative = foreign currency undervalued (tailwind).
    idio_vol          : annual FX volatility.
    long_run_inflation: neutral CPI (must match VAR calibration).
    long_run_growth   : neutral EURO-AREA GDP growth (must match VAR calibration).
    long_run_global_growth : neutral WORLD GDP growth (must match
                        VARParams.long_run_mean[7] = 0.030).
    """
    carry_spread:        float
    fx_drift:            float
    inflation_loading:   float
    growth_loading:      float
    global_growth_loading: float = 0.0
    ppp_reversion:       float = 0.10
    initial_ppp_gap:     float = 0.0
    idio_vol:            float = 0.10
    long_run_inflation:  float = 0.025
    long_run_growth:     float = 0.025   # euro-area trend
    long_run_global_growth: float = 0.030  # world trend; must match
                                           # VARParams.long_run_mean[7]


# ---------------------------------------------------------------------------
# Default calibration for all 13 supported currencies
# ---------------------------------------------------------------------------

_DEFAULT_CURRENCIES: dict[str, CurrencyParams] = {
    # ── G10 majors ──────────────────────────────────────────────────────────
    "USD": CurrencyParams(
        carry_spread       =  0.015,   # Fed ~150 bp above ECB on average
        fx_drift           = -0.010,   # dollar debasement / US twin-deficit
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 1.000   residual growth beta +0.000 (t   —)
        # anchor by construction
        inflation_loading     =   0.50,   # 0.50 x b_usd
        growth_loading        =  -0.30,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.00,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.10,    # EUR/USD 10-yr realised vol ≈ 8–10 %
    ),
    "GBP": CurrencyParams(
        carry_spread       =  0.005,   # BoE slightly above ECB on average
        fx_drift           = -0.005,   # mild depreciation bias (post-Brexit structural damage)
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.596   residual growth beta +0.122 (t +4.8)
        inflation_loading     =   0.30,   # 0.50 x b_usd
        growth_loading        =  -0.20,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.05,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,
        initial_ppp_gap    = -0.05,    # slight undervaluation post-Brexit
        idio_vol           =  0.09,
    ),
    # TODO(un-derived): CAD is absent from the FX dataset, so no joint
    #       regression exists for it. commodity currency; growth_loading +0.10 is positive, so it is wrong
    #       under convention (2) — that +0.10 is global-cycle exposure sitting in the
    #       euro-growth column, exactly the defect this change fixes elsewhere.
    #       LEFT AS-IS DELIBERATELY — see the un-derived note below the table.
    "CAD": CurrencyParams(
        carry_spread       =  0.005,
        fx_drift           =  0.000,   # commodity-linked; roughly neutral trend
        inflation_loading  =  0.20,
        growth_loading     =  0.10,    # positive: oil-exporter benefits from global growth
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.08,
    ),
    # TODO(un-derived): AUD is absent from the FX dataset, so no joint
    #       regression exists for it. same defect as CAD: growth_loading +0.20 is global-cycle exposure in
    #       the euro-growth column. Its +0.10 inflation_loading also looks like the
    #       old unreasoned block default.
    #       LEFT AS-IS DELIBERATELY — see the un-derived note below the table.
    "AUD": CurrencyParams(
        carry_spread       =  0.010,   # RBA historically above ECB
        fx_drift           =  0.000,
        inflation_loading  =  0.10,
        growth_loading     =  0.20,    # growth-positive; iron ore & resource exposure
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.11,
    ),
    # TODO(un-derived): CHF is absent from the FX dataset, so no joint
    #       regression exists for it. PRIORITY. inflation_loading -0.30 contradicts its own comment below
    #       (which describes CHF GAINING when the EUR weakens) and violates the
    #       no-negative-loading rule. growth_loading -0.50 is, by contrast, CORRECT
    #       under convention (2) for a safe haven. Cannot be fixed without a beta.
    #       LEFT AS-IS DELIBERATELY — see the un-derived note below the table.
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
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.447   residual growth beta -0.120 (t -3.3)
        # NEGATIVE cycle beta: the safe-haven bid, measured
        inflation_loading     =   0.20,   # 0.50 x b_usd
        growth_loading        =  -0.15,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =  -0.05,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.08,    # BOJ intervention slows PPP convergence
        initial_ppp_gap    = -0.25,    # JPY historically ~25 % undervalued vs EUR on PPP
        idio_vol           =  0.09,
    ),
    # ── Chinese renminbi ────────────────────────────────────────────────────
    "CNY": CurrencyParams(
        carry_spread       =  0.005,   # PBOC policy rate ≈ EUR neutral in long run
        fx_drift           =  0.005,   # managed appreciation as China moves up value chain
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.933   residual growth beta +0.039 (t +2.9)
        # significant but tiny: 0.039*0.60 rounds to zero
        inflation_loading     =   0.45,   # 0.50 x b_usd
        growth_loading        =  -0.30,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.00,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.20,    # Balassa-Samuelson undervaluation in rapidly developing economy
        idio_vol           =  0.05,    # PBOC suppresses FX volatility (~5 %)
    ),
    "HKD": CurrencyParams(
        carry_spread       =  0.015,   # currency board pegged to USD; USD carry passes through
        fx_drift           =  0.000,   # peg → no secular trend vs USD; vs EUR tracks USD drift
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.988   residual growth beta +0.001 (t +0.4)
        # currency board: zero independent cycle, as it should be
        inflation_loading     =   0.50,   # 0.50 x b_usd
        growth_loading        =  -0.30,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.00,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.15,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.03,    # near-zero idio vol due to currency board
    ),
    # ── Taiwan dollar ────────────────────────────────────────────────────────
    "TWD": CurrencyParams(
        carry_spread       =  0.005,
        fx_drift           =  0.005,   # persistent current-account surplus → appreciation
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.863   residual growth beta +0.105 (t +5.8)
        # semiconductor cycle, now in the right column
        inflation_loading     =   0.45,   # 0.50 x b_usd
        growth_loading        =  -0.25,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.05,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.20,    # structural undervaluation; government manages pace
        idio_vol           =  0.07,
    ),
    # ── Korean won ──────────────────────────────────────────────────────────
    "KRW": CurrencyParams(
        carry_spread       =  0.015,
        fx_drift           =  0.003,
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.760   residual growth beta +0.262 (t +8.4)
        # largest independent cycle in the set (t=8.4)
        inflation_loading     =   0.40,   # 0.50 x b_usd
        growth_loading        =  -0.25,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.15,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.15,    # moderate undervaluation; more open than CNY/TWD
        idio_vol           =  0.10,    # more volatile; open capital account
    ),
    # ── Singapore dollar ────────────────────────────────────────────────────
    "SGD": CurrencyParams(
        carry_spread       =  0.005,
        fx_drift           =  0.005,   # MAS uses managed appreciation as monetary policy tool
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.720   residual growth beta +0.087 (t +6.0)
        inflation_loading     =   0.35,   # 0.50 x b_usd
        growth_loading        =  -0.20,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.05,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,
        initial_ppp_gap    = -0.10,
        idio_vol           =  0.06,    # MAS actively damps FX volatility
    ),
    # ── Thai baht ───────────────────────────────────────────────────────────
    "THB": CurrencyParams(
        carry_spread       =  0.010,
        fx_drift           =  0.000,
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.814   residual growth beta +0.103 (t +4.5)
        inflation_loading     =   0.40,   # 0.50 x b_usd
        growth_loading        =  -0.25,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.05,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.15,
        idio_vol           =  0.12,    # more volatile; tourism income swings
    ),
    # ── Indonesian rupiah ───────────────────────────────────────────────────
    # ADDED 2026-08, retiring the THB-proxies-IDR substitution. IDR is now
    # derived directly from its own EUR-cross history, not stood in for.
    "IDR": CurrencyParams(
        carry_spread       =  0.035,   # JUDGEMENT: BI policy rate persistently well
                                       # above ECB; set just above INR's 0.030
        fx_drift           = -0.020,   # JUDGEMENT: persistent nominal depreciation on
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.997   residual growth beta +0.217 (t +5.8)
        # commodity exporter; strong independent cycle
        inflation_loading     =   0.50,   # 0.50 x b_usd
        growth_loading        =  -0.30,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.15,   # 0.60 x residual  (GLOBAL growth)
                                       # an inflation differential wider than India's
        ppp_reversion      =  0.12,    # JUDGEMENT
        initial_ppp_gap    = -0.15,    # JUDGEMENT
        idio_vol           =  0.111,   # MEASURED: 11.1% annualised, same sample
    ),
    # ── Vietnamese dong ─────────────────────────────────────────────────────
    "VND": CurrencyParams(
        carry_spread       =  0.030,   # JUDGEMENT: SBV rates above ECB
        fx_drift           = -0.020,   # JUDGEMENT: managed crawling depreciation
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 1.027   residual growth beta +0.024 (t +1.9)
        # t=1.9, not significant -> 0.00; a managed peg, see below
        inflation_loading     =   0.50,   # 0.50 x b_usd
        growth_loading        =  -0.30,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.00,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,    # JUDGEMENT: managed, slow convergence
        initial_ppp_gap    = -0.20,    # JUDGEMENT: Balassa-Samuelson undervaluation
        idio_vol           =  0.040,   # JUDGEMENT: crawling band suppresses vol; set
                                       # between HKD's hard-peg 0.03 and CNY's 0.05
    ),
    # ── Indian rupee ────────────────────────────────────────────────────────
    "INR": CurrencyParams(
        carry_spread       =  0.030,   # RBI rates well above ECB
        fx_drift           = -0.015,   # nominal depreciation trend (higher domestic inflation)
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.938   residual growth beta +0.160 (t +6.4)
        inflation_loading     =   0.45,   # 0.50 x b_usd
        growth_loading        =  -0.30,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.10,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.15,
        initial_ppp_gap    = -0.10,    # undervalued in real terms despite nominal depreciation
        idio_vol           =  0.07,    # RBI manages vol; lower than raw EM peers
    ),
}

# ---------------------------------------------------------------------------
# LOADING DERIVATION  (2026-08, joint estimation — supersedes the univariate run)
# ---------------------------------------------------------------------------
# METHOD. All three macro loadings come from ONE regression per currency:
#
#     r_ccy/EUR  ~  b_usd * r_USD/EUR  +  b_g * r_MSCIWorld/EUR      (2001-2026, monthly)
#
#     inflation_loading      =  0.50 x b_usd            rounded to 0.05
#     growth_loading (EUR)   = -0.30 x b_usd            rounded to 0.05
#     global_growth_loading  =  0.60 x b_g (residual)   rounded to 0.05
#
#   ccy  b_usd  resid_g     t    infl   growth  global
#   USD  1.000   0.000     —     0.50   -0.30    0.00
#   HKD  0.988   0.001    0.4    0.50   -0.30    0.00
#   VND  1.027   0.024    1.9    0.50   -0.30    0.00
#   IDR  0.997   0.217    5.8    0.50   -0.30    0.15
#   INR  0.938   0.160    6.4    0.45   -0.30    0.10
#   CNY  0.933   0.039    2.9    0.45   -0.30    0.00
#   TWD  0.863   0.105    5.8    0.45   -0.25    0.05
#   THB  0.814   0.103    4.5    0.40   -0.25    0.05
#   KRW  0.760   0.262    8.4    0.40   -0.25    0.15
#   SGD  0.720   0.087    6.0    0.35   -0.20    0.05
#   GBP  0.596   0.122    4.8    0.30   -0.20    0.05
#   JPY  0.447  -0.120   -3.3    0.20   -0.15   -0.05
#
# THE 0.60 CONVERSION IS THE WEAKEST LINK. b_g is an EQUITY-RETURN beta; the
# model needs a GROWTH-DEVIATION loading. 0.60 is EquitySleeve's growth_beta,
# used as the conversion factor, so the chain is:
#     1 pp global growth deviation -> 0.60 units of equity return -> b_g * that
# in currency return. That borrows a coefficient calibrated for a different
# purpose. If the true equity-to-growth sensitivity is 0.4 or 0.9 rather than
# 0.6, every global_growth_loading scales with it. The RANKING across currencies
# is robust (it comes straight from b_g); the LEVEL is not. Treat the global
# column as ordinally reliable and cardinally soft.
#
# WHY JOINT ESTIMATION MATTERS — this supersedes the univariate loadings applied
# in the previous round. Those regressed only on the USD, so shared global-cycle
# exposure was absorbed into b_usd. Controlling for growth moves several
# materially: KRW 0.15 -> 0.40, IDR 0.30 -> 0.50, TWD 0.35 -> 0.45, JPY 0.35 ->
# 0.20. The two columns HAVE to be estimated together, and the fact that they
# could contradict each other at all — CNY tracking the dollar at 0.93 for
# inflation while opposing it at +0.30 for growth — is a direct consequence of
# their having been set independently, by argument rather than by measurement.
#
# CONVENTION CHECKS the table must satisfy (enforced in tests/test_invariants.py):
#   * every inflation_loading  > 0   (euro-specific debasement lifts all others)
#   * every growth_loading     < 0   (euro growth strengthens the EUR)
#   * global_growth_loading is SIGNED and is the ONLY cyclical channel
#
# ---------------------------------------------------------------------------
# UN-DERIVED — CHF, CAD, AUD  (flagged, deliberately unchanged)
# ---------------------------------------------------------------------------
# These three are absent from the FX dataset, so no joint regression exists.
# Each carries at least one value that is wrong by the conventions above:
#
#   CHF  inflation_loading -0.30  WRONG (only negative left; contradicts its own
#                                 comment, which describes CHF gaining as the EUR
#                                 weakens). growth_loading -0.50 is CORRECT.
#   CAD  growth_loading    +0.10  WRONG sign under (2); it is global-cycle
#                                 exposure sitting in the euro-growth column.
#   AUD  growth_loading    +0.20  same defect; inflation_loading +0.10 also looks
#                                 like the old unreasoned block default.
#
# They are left alone because correcting them without a measured beta would
# substitute one assertion for another — the precise failure mode this whole
# exercise exists to remove. CHF is the priority: it appears at 2% weight in
# main_participant.build_rsp_specs' GlobalEquity sleeve, so it affects the
# headline participant charts (NOT the attribution or CGB runs, which swap that
# sleeve for the country mosaic). CAD and AUD: AUD carries the NZD proxy for the
# bond overlay, so its loadings reach the LHP.
#
# ---------------------------------------------------------------------------
# SAMPLE-PERIOD CHOICE
# ---------------------------------------------------------------------------
# Post-2017 the dollar-tracking correlations fall sharply, mirroring the equity
# decoupling in §13: CNY 0.92 -> 0.71, TWD 0.80 -> 0.60, JPY 0.56 -> 0.25; HKD
# holds at 0.99 as a hard peg should. The full sample is the headline because
# 112 months is thin for currency betas. The choice is not self-serving:
# post-2017 puts CNY at 0.30 rather than 0.45, which WEAKENS the CGB repression
# case this repo otherwise argues for.
#
# DATA CAUTION for anyone re-deriving. The Bloomberg pull was specified with a
# future end date, so observations after 2026-08 are the last value carried
# forward. The derivation truncates at 2026-07. A re-run that does not truncate
# will silently dilute every estimate with a run of zero returns.
# ---------------------------------------------------------------------------

# Post-2017 loadings, for the documented sensitivity.
#
# CAVEAT: these four values were derived under the UNIVARIATE method (regression
# on the USD alone) and have NOT been re-estimated jointly with the growth
# factor. They are therefore on a different footing from the headline table
# above and are not strictly comparable to it — a joint post-2017 re-estimation
# would likely move them the same way it moved the full-sample figures. They are
# retained because a stale sensitivity is more informative than none, but the
# sensitivity should be read as indicative only, and the global_growth_loading
# column is NOT varied at all.
#
# Only the four values the derivation supplied directly are listed; TWD and JPY
# post-2017 correlations are known (0.60, 0.25) but their betas are not, and
# loading cannot be recovered from correlation alone — scaling CNY's full-sample
# loading by its correlation ratio predicts 0.35 where the actual post-2017 value
# is 0.30. Currencies absent here keep their full-sample loading.
POST_2017_INFLATION_LOADINGS: dict[str, float] = {
    "CNY": 0.30,
    "THB": 0.13,
    "IDR": 0.33,
    "HKD": 0.50,   # unchanged; the peg holds
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
            growth_excess = state_t.growth    - p.long_run_growth          # EURO growth
            global_excess = state_t.global_growth - p.long_run_global_growth
            macro = (p.inflation_loading * infl_excess
                     + p.growth_loading * growth_excess
                     + p.global_growth_loading * global_excess) * dt

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
    def post_2017(cls, seed: int | None = None) -> "FXModel":
        """FXModel with POST_2017_INFLATION_LOADINGS applied — the documented
        sample-period sensitivity, not the headline calibration.

        Only the currencies for which a post-2017 loading was actually derived
        are overridden; the rest keep their full-sample value.  See the
        SAMPLE-PERIOD CHOICE note above for why the full sample is the headline.
        """
        import dataclasses as _dc
        params = {
            name: (_dc.replace(p, inflation_loading=POST_2017_INFLATION_LOADINGS[name])
                   if name in POST_2017_INFLATION_LOADINGS else p)
            for name, p in _DEFAULT_CURRENCIES.items()
        }
        return cls(params, seed=seed)

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
