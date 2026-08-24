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
  USD, GBP, CAD, AUD, NZD, CHF, JPY, CNY, HKD, TWD, KRW, SGD, THB, IDR, VND, INR

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
        #   b_usd 0.355   residual growth beta +0.119 (t +4.7)
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.30 -> +0.20, growth_loading -0.20 -> -0.10
        #   superseded b_usd 0.596 -> 0.355; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.20,   # 0.50 x b_usd
        growth_loading        =  -0.10,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.05,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,
        initial_ppp_gap    = -0.05,    # slight undervaluation post-Brexit
        idio_vol           =  0.09,
    ),
    "CAD": CurrencyParams(
        carry_spread       =  0.005,
        fx_drift           =  0.000,   # commodity-linked; roughly neutral trend
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.400   residual growth beta +0.259 (t +10.4)
        # DERIVED 2026-08-23 (V-D5). The old judgement pair was HALF right: 0.20
        # inflation matches the measurement exactly, but the +0.10 growth loading
        # was global-cycle exposure sitting in the euro-growth column — the same
        # defect the 2026-08 rounds fixed everywhere else. The oil/risk-on
        # exposure the old comment described now lives where it belongs.
        inflation_loading     =   0.20,   # 0.50 x b_usd
        growth_loading        =  -0.10,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.15,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.08,
    ),
    "AUD": CurrencyParams(
        carry_spread       =  0.010,   # RBA historically above ECB
        fx_drift           =  0.000,
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.012   residual growth beta +0.341 (t +11.4)
        # DERIVED 2026-08-23 (V-D5). From a EUR base the Australian dollar is a
        # PURE global-cycle currency: essentially zero dollar-tracking
        # (corr 0.095) and the largest residual cycle beta in the panel. The old
        # judgement (+0.10 inflation, +0.20 euro-growth) had the magnitude about
        # right and both columns wrong.
        inflation_loading     =   0.00,   # 0.50 x b_usd
        growth_loading        =   0.00,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.20,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.11,
    ),
    # ── New Zealand dollar ──────────────────────────────────────────────────
    # ADDED 2026-08-23 (V-D5), retiring the AUD-proxies-NZD substitution — the
    # last FX proxy in the model. The measurement retroactively judges the proxy
    # KIND: AUD and NZD have near-identical profiles from a EUR base (both zero
    # dollar-beta, both ~+0.20 global-cycle), so the substitution was benign —
    # but that is now measured rather than assumed.
    "NZD": CurrencyParams(
        carry_spread       =  0.012,   # JUDGEMENT: RBNZ historically above RBA's spread to ECB
        fx_drift           =  0.000,   # JUDGEMENT: commodity currency, neutral trend
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd -0.022   residual growth beta +0.301 (t +8.8)
        inflation_loading     =   0.00,   # 0.50 x b_usd
        growth_loading        =   0.00,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.20,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,    # JUDGEMENT
        initial_ppp_gap    =  0.00,    # JUDGEMENT
        idio_vol           =  0.094,   # MEASURED: 9.4% annualised, same sample
    ),
    "CHF": CurrencyParams(
        carry_spread       = -0.005,   # SNB yields below ECB; negative carry
        fx_drift           =  0.005,   # structural appreciation (current-account surplus)
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.170   residual growth beta -0.042 (t -1.8)
        # DERIVED 2026-08-23 (V-D5), calibration/fx_loading_calibration.py.
        # This retires the LAST NEGATIVE inflation loading in the table: the old
        # -0.30 contradicted its own comment ("EUR inflation -> EUR weakens ->
        # CHF gains"), and the data agrees with the comment, not the number —
        # positive, but small, because the SNB manages CHF against the EUR and
        # its EUR cross barely tracks the dollar (corr 0.245, vol 6.0%, the
        # lowest of the panel). The safe-haven bid survives where JPY's does: a
        # NEGATIVE global-cycle loading.
        inflation_loading     =   0.10,   # 0.50 x b_usd
        growth_loading        =  -0.05,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =  -0.05,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.10,
        initial_ppp_gap    =  0.00,
        idio_vol           =  0.08,
    ),
    # ── Japanese yen ────────────────────────────────────────────────────────
    "JPY": CurrencyParams(
        carry_spread       = -0.008,   # BOJ rates deeply negative / near-zero vs ECB
        fx_drift           =  0.003,   # long-run appreciation bias despite low carry
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.686   residual growth beta -0.123 (t -3.4)
        # NEGATIVE cycle beta: the safe-haven bid, measured
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.20 -> +0.35, growth_loading -0.15 -> -0.20
        #   superseded b_usd 0.447 -> 0.686; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.35,   # 0.50 x b_usd
        growth_loading        =  -0.20,   # -0.30 x b_usd  (EURO growth)
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
        #   b_usd 0.856   residual growth beta +0.038 (t +2.8)
        # significant but tiny: 0.039*0.60 rounds to zero
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.45 -> +0.45, growth_loading -0.30 -> -0.25
        #   superseded b_usd 0.933 -> 0.856; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.45,   # 0.50 x b_usd
        growth_loading        =  -0.25,   # -0.30 x b_usd  (EURO growth)
        global_growth_loading =   0.00,   # 0.60 x residual  (GLOBAL growth)
        ppp_reversion      =  0.12,
        initial_ppp_gap    = -0.20,    # Balassa-Samuelson undervaluation in rapidly developing economy
        idio_vol           =  0.05,    # PBOC suppresses FX volatility (~5 %)
    ),
    "HKD": CurrencyParams(
        carry_spread       =  0.015,   # currency board pegged to USD; USD carry passes through
        fx_drift           =  0.000,   # peg → no secular trend vs USD; vs EUR tracks USD drift
        # joint regression on [USD EUR-cross, MSCI World EUR], 2001-2026:
        #   b_usd 0.985   residual growth beta +0.001 (t +0.3)
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
        #   b_usd 0.655   residual growth beta +0.102 (t +5.7)
        # semiconductor cycle, now in the right column
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.45 -> +0.35, growth_loading -0.25 -> -0.20
        #   superseded b_usd 0.863 -> 0.655; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.35,   # 0.50 x b_usd
        growth_loading        =  -0.20,   # -0.30 x b_usd  (EURO growth)
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
        #   b_usd 0.240   residual growth beta +0.258 (t +8.4)
        # largest independent cycle in the set (t=8.4)
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.40 -> +0.10, growth_loading -0.25 -> -0.05
        #   superseded b_usd 0.760 -> 0.240; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.10,   # 0.50 x b_usd
        growth_loading        =  -0.05,   # -0.30 x b_usd  (EURO growth)
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
        #   b_usd 0.547   residual growth beta +0.085 (t +5.9)
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.35 -> +0.25, growth_loading -0.20 -> -0.15
        #   superseded b_usd 0.720 -> 0.547; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.25,   # 0.50 x b_usd
        growth_loading        =  -0.15,   # -0.30 x b_usd  (EURO growth)
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
        #   b_usd 0.610   residual growth beta +0.100 (t +4.4)
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.40 -> +0.30, growth_loading -0.25 -> -0.20
        #   superseded b_usd 0.814 -> 0.610; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.30,   # 0.50 x b_usd
        growth_loading        =  -0.20,   # -0.30 x b_usd  (EURO growth)
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
        #   b_usd 0.565   residual growth beta +0.218 (t +5.9)
        # commodity exporter; strong independent cycle
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.50 -> +0.30, growth_loading -0.30 -> -0.15
        #   superseded b_usd 0.997 -> 0.565; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.30,   # 0.50 x b_usd
        growth_loading        =  -0.15,   # -0.30 x b_usd  (EURO growth)
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
        #   b_usd 0.981   residual growth beta +0.024 (t +2.0)
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
        #   b_usd 0.621   residual growth beta +0.158 (t +6.4)
        # DERIVED 2026-08-22, calibration/fx_loading_calibration.py.
        #   inflation_loading +0.45 -> +0.30, growth_loading -0.30 -> -0.20
        #   superseded b_usd 0.938 -> 0.621; the old value's
        #   origin is not recoverable (V-F1).
        inflation_loading     =   0.30,   # 0.50 x b_usd
        growth_loading        =  -0.20,   # -0.30 x b_usd  (EURO growth)
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
#   ccy  b_usd  resid_g     t    corr    infl   growth  global   (was infl/grow)
#   USD  1.000  +0.000    —    1.000   0.50   -0.30   +0.00
#   HKD  0.985  +0.001   +0.3  0.997   0.50   -0.30   +0.00
#   VND  0.981  +0.024   +2.0  0.951   0.50   -0.30   +0.00
#   IDR  0.565  +0.218   +5.9  0.510   0.30   -0.15   +0.15   (0.50/-0.30)
#   INR  0.621  +0.158   +6.4  0.686   0.30   -0.20   +0.10   (0.45/-0.30)
#   CNY  0.856  +0.038   +2.8  0.923   0.45   -0.25   +0.00   (0.45/-0.30)
#   TWD  0.655  +0.102   +5.7  0.804   0.35   -0.20   +0.05   (0.45/-0.25)
#   THB  0.610  +0.100   +4.4  0.713   0.30   -0.20   +0.05   (0.40/-0.25)
#   KRW  0.240  +0.258   +8.4  0.313   0.10   -0.05   +0.15   (0.40/-0.25)
#   SGD  0.547  +0.085   +5.9  0.813   0.25   -0.15   +0.05   (0.35/-0.20)
#   GBP  0.355  +0.119   +4.7  0.483   0.20   -0.10   +0.05   (0.30/-0.20)
#   JPY  0.686  -0.123   -3.4  0.559   0.35   -0.20   -0.05   (0.20/-0.15)
#   --- added 2026-08-23, closing V-D5 (previously un-derived / absent): ---
#   CHF  0.170  -0.042   -1.8  0.245   0.10   -0.05   -0.05   (was -0.30/-0.50)
#   CAD  0.400  +0.259  +10.4  0.512   0.20   -0.10   +0.15   (was  0.20/+0.10)
#   AUD  0.012  +0.341  +11.4  0.095   0.00    0.00   +0.20   (was  0.10/+0.20)
#   NZD -0.022  +0.301   +8.8  0.046   0.00    0.00   +0.20   (new; retires the AUD proxy)
#
#   CONFIRMED 2026-08-24 (FX round 2): the four V-D5 rows re-derived from
#   direct Bloomberg EUR crosses (EURCHF/EURCAD/EURAUD/EURNZD, 2001-01..2026-07,
#   n=302 regression months) reproduce b_usd within +/-0.005 and every rounded
#   loading exactly. calibration/fx_loading_calibration.py, round-2 section;
#   data in calibration/data/bloomberg_pull_VM3_and_FX2_v2_2026-08-24.xlsx.
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
# PROVENANCE OF THIS TABLE (rewritten 2026-08-22, validation finding V-F1).
# Every value above is now produced by calibration/fx_loading_calibration.py from
# data/fx_levels.csv, data/fx_bloomberg_legs.csv and data/ret_usd.csv. Run it and
# it reproduces this table to three decimals; a test asserts that it does.
#
# It replaces a b_usd column whose origin could not be recovered. That column was
# searched for across the repository, the full git history including dangling
# objects, and the laptop: the values 0.760 / 0.997 / 0.447 appear nowhere except
# in the simple_alm files that recorded them. No script, notebook or intermediate
# artefact produced them. They were also inconsistent with the ROUND-3 univariate
# column measured on the same data and window — that column reproduces exactly
# here (KRW 0.300, IDR 0.615, CNY 0.865) while the superseded round-4 table
# claimed 0.760, 0.997 and 0.933 for the same three currencies, both described as
# a beta against the USD.
#
# 17 loadings changed (8 inflation, 9 growth). global_growth_loading did NOT
# change for any currency — it derives from the residual growth beta of the same
# regression and already reproduced exactly, which is what established that the
# data and specification were right and only b_usd was wrong.
#
# MEASURED EFFECT: none beyond seed noise. Every attribution waypoint and the CGB
# dial moved inside one seed standard deviation. See
# output/fx_loadings_rerun_summary.md.
#
# CONVENTION CHECKS the table must satisfy (enforced in tests/test_invariants.py):
#   * every inflation_loading  > 0   (euro-specific debasement lifts all others)
#   * every growth_loading     < 0   (euro growth strengthens the EUR)
#   * global_growth_loading is SIGNED and is the ONLY cyclical channel
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
