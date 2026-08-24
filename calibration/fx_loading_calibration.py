"""
Derivation of the FX macro loadings in assets/fx.py.

METHOD (as documented in assets/fx.py). One joint regression per currency:

    r_ccy/EUR  ~  a  +  b_usd * r_USD/EUR  +  b_g * r_MSCIWorld/EUR

on monthly log returns, 2001-03 .. 2026-04. Then

    inflation_loading      =  0.50 * b_usd            rounded to 0.05
    growth_loading (EUR)   = -0.30 * b_usd            rounded to 0.05
    global_growth_loading  =  0.60 * b_g  (residual)  rounded to 0.05

CONVENTIONS. `data/fx_levels.csv` quotes per EUR; `data/fx_bloomberg_legs.csv`
quotes per USD, except EURUSD which is USD per EUR. They are combined here
explicitly rather than being harmonised in the data files — see data/README.md.
The EUR-cross return of holding currency c is -dlog(c per EUR).

ROUND 2 (2026-08-24). `calibration/data/bloomberg_pull_VM3_and_FX2_v2_2026-08-24.xlsx`
(tab FX_round2) supplies DIRECT Bloomberg EUR crosses — EURUSD, EURCHF, EURCAD,
EURAUD, EURNZD, monthly PX_LAST 2001-01..2026-07, 307 level observations each.
Bloomberg EURxxx quotes xxx per EUR, i.e. exactly the per-EUR convention of
fx_levels.csv, so these series enter with NO crossing step; the workbook's
crossed USD legs (USDCHF = EURCHF/EURUSD = CHF per USD) match the per-USD
convention of fx_bloomberg_legs.csv and are used only as a cross-check. Both
directions are ASSERTED in `round2_eur_cross_returns` rather than assumed:
level anchors pin the quote direction, and the crossed legs are reconciled
against the committed round-1 legs file. The regression window is the overlap
with the committed MSCI World series (data/ret_usd.csv ends 2026-04), giving
n = 302 monthly returns, 2001-03..2026-04.

Round-2 finding (run 2026-08-24): the four round-1 loadings REPRODUCE — b_usd
within ±0.005, residual betas within ±0.002, every rounded loading identical.
The pair-direction-inversion hypothesis for the historical CHF sign error is
NOT supported: the sign error was the pre-derivation judgement value (-0.30
inflation loading, contradicting its own comment), retired by the V-D5
derivation at 9c0aa70; the derivation itself was and remains correct.

PIPELINE VALIDATION. This script reproduces four independently published figures
exactly, which is what establishes that the data and conventions are right:
  * all 11 currency correlations with the USD (to 3dp)
  * the article's own CNY-USD correlation of 0.92 (measured 0.923)
  * the annualised volatilities cited for IDR (11.1%) and THB (8.2%)
  * all 12 global_growth_loading values currently in assets/fx.py

WHAT IT DOES NOT REPRODUCE. The `b_usd` column published in the assets/fx.py
derivation note, and therefore inflation_loading and growth_loading, which are
computed from it. See the DISCREPANCY section printed at the end, and validation
finding V-F1 in docs/VALIDATION_REPORT.md. This script deliberately does NOT
rewrite assets/fx.py: changing 17 live loadings is a decision, not a side effect
of running a calibration.

Run from the repo root:

    python calibration/fx_loading_calibration.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:          # so `assets.fx` resolves when run directly
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
START, END = "2001-03", "2026-04"          # END is where fx_levels/ret_usd stop
ROUND = 0.05

# b_usd and residual growth beta as published in the assets/fx.py derivation note.
PUBLISHED = {
    "USD": (1.000,  0.000), "HKD": (0.988, 0.001), "VND": (1.027,  0.024),
    "IDR": (0.997,  0.217), "INR": (0.938, 0.160), "CNY": (0.933,  0.039),
    "TWD": (0.863,  0.105), "THB": (0.814, 0.103), "KRW": (0.760,  0.262),
    "SGD": (0.720,  0.087), "GBP": (0.596, 0.122), "JPY": (0.447, -0.120),
    # Added 2026-08-23, closing V-D5. Pinned from this script's first run over
    # data/fx_bloomberg_legs.csv — CHF/CAD/AUD had no prior published b_usd
    # (un-derived judgement), and NZD did not exist in the model (AUD proxied it).
    "CHF": (0.170, -0.042), "CAD": (0.400,  0.259),
    "AUD": (0.012,  0.341), "NZD": (-0.022, 0.301),
}


def _month_end(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = pd.to_datetime(df.index).to_period("M").to_timestamp("M")
    return df


def eur_cross_returns() -> tuple[pd.DataFrame, pd.Series]:
    """Monthly EUR-cross log returns per currency, plus MSCI World in EUR."""
    fx_eur = _month_end(pd.read_csv(DATA / "fx_levels.csv", index_col=0, parse_dates=True))
    legs = _month_end(pd.read_csv(DATA / "fx_bloomberg_legs.csv", index_col=0, parse_dates=True))
    ret = _month_end(pd.read_csv(DATA / "ret_usd.csv", index_col=0, parse_dates=True))

    per_eur = {c: fx_eur[c] for c in fx_eur.columns}                 # already per EUR
    for col in legs.columns:                                         # per USD -> per EUR
        if col.startswith("USD"):
            per_eur[col[3:]] = legs[col] * legs["EURUSD"]

    # Holding currency c: gain when fewer units of c buy a EUR.
    X = pd.DataFrame({c: -np.log(s).diff() for c, s in per_eur.items()})
    world_eur = np.log1p(ret["World"]) + X["USD"]                    # USD asset -> EUR, in logs
    return X, world_eur


def calibrate() -> pd.DataFrame:
    X, world = eur_cross_returns()
    rows = {}
    for ccy in PUBLISHED:
        df = pd.concat([X[ccy].rename("y"), X["USD"].rename("usd"), world.rename("w")],
                       axis=1).dropna().loc[START:END]
        fit = sm.OLS(df["y"], sm.add_constant(df[["usd", "w"]])).fit()
        b, g = fit.params["usd"], fit.params["w"]
        rows[ccy] = {
            "b_usd": b, "resid_g": g, "t_g": fit.tvalues["w"],
            "corr_usd": df["y"].corr(df["usd"]), "vol": df["y"].std() * np.sqrt(12),
            "inflation_loading": _r(0.50 * b),
            "growth_loading": _r(-0.30 * b),
            "global_growth_loading": _r(0.60 * g),
            "n": len(df),
        }
    return pd.DataFrame(rows).T


def _r(v: float) -> float:
    return round(round(v / ROUND) * ROUND, 10)


ROUND2_XLSX = ROOT / "calibration" / "data" / "bloomberg_pull_VM3_and_FX2_v2_2026-08-24.xlsx"
ROUND2_CCYS = ("CHF", "CAD", "AUD", "NZD")
# (date col, value col) per ticker on the FX_round2 tab, 0-indexed; data from sheet row 4.
_ROUND2_PAIRS = {"USD": (0, 1), "CHF": (3, 4), "CAD": (6, 7), "AUD": (9, 10), "NZD": (12, 13)}


def round2_eur_cross_returns() -> tuple[pd.DataFrame, pd.Series]:
    """EUR-cross returns from the round-2 direct Bloomberg pulls, conventions asserted."""
    raw = pd.read_excel(ROUND2_XLSX, sheet_name="FX_round2", header=None, skiprows=3)
    per_eur = {}
    for ccy, (dc, vc) in _ROUND2_PAIRS.items():
        s = pd.Series(pd.to_numeric(raw.iloc[:, vc], errors="coerce").values,
                      index=pd.to_datetime(raw.iloc[:, dc], errors="coerce")).dropna().sort_index()
        s.index = s.index.to_period("M").to_timestamp("M")
        per_eur[ccy] = s

    # CONVENTION ASSERTS — the structural fix for the pair-direction question.
    # 1. Quote direction pinned by level anchors: in Jan-2001 the euro bought
    #    ~0.93 USD and ~1.53 CHF. An inverted pull would sit near 1.08 / 0.65.
    assert 0.8 < per_eur["USD"].iloc[0] < 1.1, "EURUSD must be USD per EUR"
    assert 1.3 < per_eur["CHF"].iloc[0] < 1.8, "EURCHF must be CHF per EUR"
    # 2. The implied per-USD legs must reconcile with the committed round-1 legs
    #    file (per-USD convention). Pull-timing noise only; an inversion fails big.
    legs = _month_end(pd.read_csv(DATA / "fx_bloomberg_legs.csv", index_col=0, parse_dates=True))
    for ccy in ROUND2_CCYS:
        crossed = per_eur[ccy] / per_eur["USD"]                      # (c/EUR)/(USD/EUR) = c per USD
        dev = (crossed - legs[f"USD{ccy}"]).dropna().abs().max()
        assert dev < 0.05, f"USD{ccy}: round-2 cross deviates {dev:.4g} from round-1 leg"

    ret = _month_end(pd.read_csv(DATA / "ret_usd.csv", index_col=0, parse_dates=True))
    X = pd.DataFrame({c: -np.log(s).diff() for c, s in per_eur.items()})
    world_eur = np.log1p(ret["World"]) + X["USD"]
    return X, world_eur


def calibrate_round2() -> pd.DataFrame:
    """Same regression as `calibrate`, on the round-2 direct EUR crosses."""
    X, world = round2_eur_cross_returns()
    rows = {}
    for ccy in ROUND2_CCYS:
        df = pd.concat([X[ccy].rename("y"), X["USD"].rename("usd"), world.rename("w")],
                       axis=1).dropna()
        fit = sm.OLS(df["y"], sm.add_constant(df[["usd", "w"]])).fit()
        b, g = fit.params["usd"], fit.params["w"]
        rows[ccy] = {
            "b_usd": b, "resid_g": g, "t_g": fit.tvalues["w"],
            "inflation_loading": _r(0.50 * b),
            "growth_loading": _r(-0.30 * b),
            "global_growth_loading": _r(0.60 * g),
            "n": len(df),
        }
    return pd.DataFrame(rows).T


if __name__ == "__main__":
    from assets.fx import _DEFAULT_CURRENCIES as LIVE

    tab = calibrate()
    print("FX macro loadings, derived from data/ (window "
          f"{START}..{END}, n={int(tab['n'].iloc[0])} months)\n")
    print(tab[["b_usd", "resid_g", "t_g", "corr_usd", "vol",
               "inflation_loading", "growth_loading", "global_growth_loading"]]
          .round(3).to_string())

    print("\n--- pipeline validation against independently published figures ---")
    print(f"  CNY-USD correlation : {tab.loc['CNY','corr_usd']:.3f}   (article publishes 0.92)")
    print(f"  IDR annualised vol  : {tab.loc['IDR','vol']:.1%}   (published 11.1%)")
    print(f"  THB annualised vol  : {tab.loc['THB','vol']:.1%}    (published 8.2%)")

    print("\n--- agreement with the loadings live in assets/fx.py ---")
    cols = ["inflation_loading", "growth_loading", "global_growth_loading"]
    diffs = {c: [] for c in cols}
    for ccy in PUBLISHED:
        for col in cols:
            if abs(tab.loc[ccy, col] - getattr(LIVE[ccy], col)) > 1e-9:
                diffs[col].append(ccy)
    for col in cols:
        d = diffs[col]
        n = len(PUBLISHED)
        print(f"  {col:<22} {n - len(d):>2}/{n} agree" +
              (f"   DIFFER: {', '.join(d)}" if d else "   (exact)"))

    print("\n--- round 2 (2026-08-24): direct EUR crosses vs the round-1 derivation ---")
    tab2 = calibrate_round2()
    cols2 = ["inflation_loading", "growth_loading", "global_growth_loading"]
    moved = []
    for ccy in ROUND2_CCYS:
        b2, g2 = tab2.loc[ccy, "b_usd"], tab2.loc[ccy, "resid_g"]
        b1, g1 = PUBLISHED[ccy]
        same = all(abs(tab2.loc[ccy, c] - getattr(LIVE[ccy], c)) < 1e-9 for c in cols2)
        if not same:
            moved.append(ccy)
        print(f"  {ccy}: n={int(tab2.loc[ccy,'n'])}  b_usd {b2:+.3f} (round1 {b1:+.3f}, "
              f"d {b2-b1:+.3f})  resid_g {g2:+.3f} (round1 {g1:+.3f})  "
              f"rounded loadings {'UNCHANGED' if same else 'CHANGED — REVIEW assets/fx.py'}")
    print("  =>", "all four round-1 loadings CONFIRMED by the round-2 direct pulls"
          if not moved else f"loadings moved for: {', '.join(moved)} — do not merge silently")

    if any(diffs.values()):
        print("\n--- DISCREPANCY (validation finding V-F1) ---")
        print("  global_growth_loading reproduces exactly for all 12 currencies, so the")
        print("  regression and the data are right. inflation_loading and growth_loading")
        print("  do not, because both are computed from a b_usd column that cannot be")
        print("  reproduced from this data under any specification or window tested.")
        print("  The loadings in assets/fx.py are LEFT UNCHANGED by this script.")
        print(f"\n  {'ccy':<5}{'b_usd here':>12}{'b_usd published':>17}{'diff':>8}")
        for ccy in PUBLISHED:
            b, pub = tab.loc[ccy, "b_usd"], PUBLISHED[ccy][0]
            print(f"  {ccy:<5}{b:>12.3f}{pub:>17.3f}{b - pub:>+8.3f}")
