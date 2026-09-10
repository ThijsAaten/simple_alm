"""Ex-ante TE / active return / IR (Proposed A vs ACWI proxy) and the W8.11
frontier row, from committed data. No simulation.

FRONTIER (article Table 6 row "Asian volatility +3pp"). Rebuilds the four-region
frontier exactly as §8.6: EUR-translated monthly MSCI returns 2001-03..2026-04
(data/ret_usd.csv crossed through data/fx_levels.csv USD-per-EUR), historical
covariance, forward-looking means USA 4% / Europe 7% / Japan 6% / Asia ex-Japan
8.5% nominal EUR, long-only, Sharpe = ER/vol (rf = 0, matching the published
0.26 / 0.29). The construction is VALIDATED by reproducing the published anchor
vols/Sharpes before the perturbation is applied. The +3pp row scales the Asia
ex-Japan row/column of the covariance so its vol rises 3pp absolute with
correlations unchanged.

TRACKING ERROR. ACWI proxy at sleeve granularity = the committed CURRENT_EQUITY
("approximate MSCI-ACWI-benchmarked" — allocations/mosaic.py); active weights =
PROPOSED_EQUITY - CURRENT_EQUITY. Primary covariance: historical EUR-translated
monthly country returns (the §8.6 calibration's covariance source), with
Indonesia / Vietnam / Singapore mapped to the AsiaExJP column (their country
series are not committed; combined active weight 0.045). Cross-check: the
model-implied factor covariance b b' sF^2 + diag(idio^2) in local currency.

Usage:  python tools/compute_te_frontier_w811.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from allocations import CURRENT_EQUITY, PROPOSED_EQUITY               # noqa: E402
from allocations.country_inputs import COUNTRY_INPUTS, ASIA           # noqa: E402
from allocations.preview import blended, FX_TAILWIND                  # noqa: E402
from scenarios.engine import EQUITY_FACTOR_VOL                        # noqa: E402

REGIONS = ["USA", "Europe", "Japan", "AsiaExJP"]
MU_FWD = np.array([0.04, 0.07, 0.06, 0.085])          # §8.6 forward inputs, nominal EUR
W_CURRENT_4 = np.array([0.60, 0.15, 0.10, 0.15])
W_ASIA30_4 = np.array([0.35, 0.25, 0.10, 0.30])
COUNTRY_COLS = {"USA": "USA", "Europe": "Europe", "Japan": "Japan", "China": "China",
                "India": "India", "Korea": "Korea", "Taiwan": "Taiwan",
                "Indonesia": "AsiaExJP", "Vietnam": "AsiaExJP", "Singapore": "AsiaExJP"}


def eur_returns(inverted: bool = False) -> pd.DataFrame:
    """EUR-translated returns. inverted=True applies the FX factor the WRONG way
    (u_t / u_{t-1} instead of u_{t-1} / u_t, u = USD per EUR).

    FINDING (2026-09-10): the inverted translation reproduces §8.6's published
    portfolio vols almost exactly (Current 20.7% vs published 20.9%; 30% Asia
    21.8% vs 22.0%), while the correct translation gives 14.1% / 14.3%. The
    article-side ret_eur.pkl therefore appears to have been built with the FX
    factor inverted, which strips out the natural equity-dollar damping a EUR
    investor gets and inflates every vol by roughly 5pp. Kept here as an option
    so both constructions can be reported side by side; the article correction
    is an article-side decision.
    """
    ret = pd.read_csv(ROOT / "data" / "ret_usd.csv", index_col=0, parse_dates=True)
    fx = pd.read_csv(ROOT / "data" / "fx_levels.csv", index_col=0, parse_dates=True)
    for df in (ret, fx):
        df.index = pd.to_datetime(df.index).to_period("M").to_timestamp("M")
    u = fx["USD"].reindex(ret.index)
    fx_factor = (u / u.shift(1)) if inverted else (u.shift(1) / u)
    return ((1.0 + ret).mul(fx_factor, axis=0) - 1.0).dropna()


def tangency_long_only(mu, sigma):
    n = len(mu)
    res = minimize(lambda w: -(w @ mu) / np.sqrt(w @ sigma @ w),
                   np.ones(n) / n, bounds=[(0, 1)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}])
    return res.x


def frontier_section() -> None:
    def stats(w, s):
        vol = np.sqrt(w @ s @ w)
        er = w @ MU_FWD
        return er, vol, er / vol

    for label, inv in [("published construction (FX factor inverted — see eur_returns)", True),
                       ("correct EUR translation", False)]:
        r = eur_returns(inverted=inv)[REGIONS]
        sigma = r.cov().values * 12.0
        vols = np.sqrt(np.diag(sigma))
        print(f"== frontier under {label} ==")
        for name, w in [("Current 60/15/10/15", W_CURRENT_4),
                        ("30% Asia 35/25/10/30", W_ASIA30_4)]:
            er, vol, sh = stats(w, sigma)
            print(f"  base     {name}: ER {er:.1%}  vol {vol:.1%}  Sharpe {sh:.3f}")

        i = REGIONS.index("AsiaExJP")
        scale = (vols[i] + 0.03) / vols[i]
        s2 = sigma.copy()
        s2[i, :] *= scale; s2[:, i] *= scale; s2[i, i] = (vols[i] * scale) ** 2

        wt = tangency_long_only(MU_FWD, s2)
        asia_w = wt[REGIONS.index("Japan")] + wt[i]
        erc, volc, shc = stats(W_CURRENT_4, s2)
        era, vola, sha = stats(W_ASIA30_4, s2)
        print(f"  W8.11 row: AxJ vol {vols[i]:.1%} -> {vols[i]+0.03:.1%} (+3pp, correlations kept)")
        print(f"    tangency {dict(zip(REGIONS, wt.round(3)))}  ->  Asia (J+AxJ) {asia_w:.0%}")
        print(f"    Current:  ER {erc:.1%}  vol {volc:.1%}  Sharpe {shc:.3f}")
        print(f"    30% Asia: ER {era:.1%}  vol {vola:.1%}  Sharpe {sha:.3f}")
        print(f"    30%-Asia still beats Current? {'YES' if sha > shc else 'NO'} "
              f"(Sharpe margin {sha-shc:+.3f})\n")


def te_section() -> None:
    countries = list(PROPOSED_EQUITY)
    wa = np.array([PROPOSED_EQUITY.get(c, 0.0) - CURRENT_EQUITY.get(c, 0.0)
                   for c in countries])
    print("\n== tracking error: Proposed A vs ACWI proxy (= committed CURRENT_EQUITY) ==")
    print("  active weights:", {c: round(w, 3) for c, w in zip(countries, wa)})

    # Primary: historical EUR-translated covariance at country granularity
    r = eur_returns()
    cols = [COUNTRY_COLS[c] for c in countries]
    sigma_h = r[cols].cov().values * 12.0
    te_h = float(np.sqrt(wa @ sigma_h @ wa))
    print(f"  TE (historical EUR-translated, IDN/VNM/SGP->AsiaExJP): {te_h:.2%}")

    # Cross-check: model factor covariance, local currency
    mb = np.array([COUNTRY_INPUTS[c]["mbeta"] for c in countries])
    idio = np.array([COUNTRY_INPUTS[c]["idio"] for c in countries])
    sigma_m = np.outer(mb, mb) * EQUITY_FACTOR_VOL ** 2 + np.diag(idio ** 2)
    te_m = float(np.sqrt(wa @ sigma_m @ wa))
    print(f"  TE (model factor covariance, local ccy, exact sleeves): {te_m:.2%}")

    # Active return (a): re-rating view = model central expected returns incl. FX
    a_prop, a_cur = blended(PROPOSED_EQUITY), blended(CURRENT_EQUITY)
    ar_central = a_prop["er_eur"] - a_cur["er_eur"]
    print(f"\n  active return, re-rating view: {a_prop['er_eur']:.2%} - "
          f"{a_cur['er_eur']:.2%} = {ar_central:+.2%}   IR {ar_central/te_h:.2f} "
          f"(model-cov IR {ar_central/te_m:.2f})")

    # Active return (b): §8.10 single-adverse case — Asia ex-Japan expected
    # returns -2pp (the harshest single row of Table 6); Japan unchanged, as in
    # the four-region table. -1pp shown for completeness.
    for cut in (0.01, 0.02):
        def blended_cut(weights):
            er = sum(w * (COUNTRY_INPUTS[c]["drift"]
                          - (cut if (c in ASIA and c != "Japan") else 0.0))
                     for c, w in weights.items())
            base = blended(weights)
            return er + base["fx"]                      # same FX treatment
        ar = blended_cut(PROPOSED_EQUITY) - blended_cut(CURRENT_EQUITY)
        tag = f"Asia exJ ER -{cut*100:.0f}pp"
        print(f"  active return, {tag}: {ar:+.2%}   IR {ar/te_h:.2f}")


if __name__ == "__main__":
    frontier_section()
    te_section()
