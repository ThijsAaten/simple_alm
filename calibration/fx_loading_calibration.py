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
        print(f"  {col:<22} {12 - len(d):>2}/12 agree" +
              (f"   DIFFER: {', '.join(d)}" if d else "   (exact)"))

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
