"""
Calibration of the global equity market factor for simple_alm (closes V-C3).

The model gave equity sleeves only macro exposures plus idiosyncratic noise, so simulated
cross-country correlation was +0.01 against 0.5-0.9 observed. This derives a single global
equity factor: market_beta per country and the residual idio_vol that reproduces observed
total volatility.

Returns are converted to LOCAL currency first (MSCI USD series un-crossed through the USD
legs in fx_levels.csv), because the model handles currency separately via FXModel. Using
EUR or USD returns would fold a common currency term into the equity factor structure.

Run from the repo root:

    python calibration/equity_factor_calibration.py

Reproduces the market_beta / idio_vol table in allocations/country_inputs.py and the 15.5%
factor volatility in scenarios/engine.py, to the three decimals those files state.
"""
import pandas as pd, numpy as np, statsmodels.api as sm
from pathlib import Path

# Repo-relative since 2026-08-22. Previously an absolute path outside the
# repository, which made this derivation unreproducible from a clean clone; the
# source is now CSV under data/ (see calibration/convert_source_data.py for why
# CSV rather than the original pickles).
U = Path(__file__).resolve().parents[1] / "data"
MAP = {"Japan": "JPY", "China": "CNY", "India": "INR", "Korea": "KRW", "Taiwan": "TWD"}


def local_returns():
    r = pd.read_csv(U / "ret_usd.csv", index_col=0, parse_dates=True)
    r.index = pd.to_datetime(r.index).to_period("M").to_timestamp("M")
    fx = pd.read_csv(U / "fx_levels.csv", index_col=0, parse_dates=True)
    fx.index = pd.to_datetime(fx.index).to_period("M").to_timestamp("M")
    per_usd = pd.DataFrame({c: fx[c] / fx["USD"] for c in MAP.values()})
    out = {m: (1 + r[m]) * (1 + per_usd[c].pct_change()) - 1 for m, c in MAP.items()}
    out["USA"] = r["USA"]
    out["Europe"] = (1 + r["Europe"]) * (1 - fx["USD"].pct_change()) - 1
    return pd.DataFrame(out).dropna().loc[:"2025-12-31"], r["World"]


def calibrate():
    L, F = local_returns()
    F = F.reindex(L.index)
    rows = {}
    for c in L.columns:
        m = sm.OLS(L[c], sm.add_constant(F)).fit()
        rows[c] = {"market_beta": m.params["World"],
                   "idio_vol": m.resid.std() * np.sqrt(12),
                   "total_vol": L[c].std() * np.sqrt(12),
                   "R2": m.rsquared}
    return pd.DataFrame(rows).T, L, F


def implied_corr(tab, F):
    fv = F.var()
    cols = list(tab.index)
    out = pd.DataFrame(index=cols, columns=cols, dtype=float)
    for i in cols:
        for j in cols:
            bi, ii = tab.loc[i, "market_beta"], tab.loc[i, "idio_vol"] / np.sqrt(12)
            bj, ij = tab.loc[j, "market_beta"], tab.loc[j, "idio_vol"] / np.sqrt(12)
            out.loc[i, j] = (bi * bj * fv) / np.sqrt((bi**2 * fv + ii**2) * (bj**2 * fv + ij**2))
    return out


if __name__ == "__main__":
    tab, L, F = calibrate()
    tab["check_total"] = np.sqrt((tab.market_beta**2) * F.var() * 12 + tab.idio_vol**2)
    print(tab.round(3).to_string())
    print(f"\nfactor vol {F.std()*np.sqrt(12)*100:.1f}%/yr")
    obs, imp = L.corr(), implied_corr(tab, F)
    m = ~np.eye(len(obs), dtype=bool)
    print(f"observed mean corr {obs.values[m].mean():.2f} | implied {imp.values[m].mean():.2f} "
          f"| max abs diff {np.abs(obs.values - imp.values)[m].max():.2f}")
    print("\nworst-fitting pairs:")
    d = (obs - imp).abs().where(m)
    print(d.stack().sort_values(ascending=False).head(4).round(2).to_string())
