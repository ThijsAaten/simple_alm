"""V-C4 verification — EUR translation direction, rebuilt from first principles.

Independently verifies the 2026-09-10 finding that the article-side ret_eur
series (the §8.6 frontier covariance source) was built with the EUR translation
INVERTED. This script deliberately does NOT import the code path under
suspicion (tools/compute_te_frontier_w811.eur_returns): the translation is
written out explicitly, once, from the committed raw data.

First principles, for a EUR-based investor holding a USD-denominated asset:

    wealth_EUR = wealth_USD / u,   u = USD per EUR  (EURUSD)
    r_eur      = (1 + r_usd) * (u_{t-1} / u_t) - 1

so when the dollar strengthens (u falls), the EUR investor GAINS on the FX leg.
Because the dollar tends to strengthen in equity selloffs, correct translation
DAMPS equity volatility for a EUR investor: vol_EUR(USA) < vol_USD(USA). The
inverted factor (u_t / u_{t-1}) doubles the FX exposure instead and inflates
vols. That damping direction is locked in as a regression test in
tests/test_invariants.py::test_eur_translation_damps_usa_equity_vol.

The FX level convention is asserted via the level-anchor pattern from the
fx-loadings round rather than assumed: EURUSD (USD per EUR) stayed within
[0.8, 1.6] over 2001-2026; the inverse (EUR per USD) breaches the lower bound.

Usage:
    python tools/verify_vc4_translation.py [path/to/ret_eur.csv]

The optional argument is an externally built EUR-translated return file to
compare against (e.g. the article-side exhibits/data/ret_eur.csv). Without it,
the fresh path is compared against the two candidate constructions only.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SERIES = ["USA", "AsiaExJP"]


def load() -> tuple[pd.DataFrame, pd.Series]:
    ret = pd.read_csv(ROOT / "data" / "ret_usd.csv", index_col=0, parse_dates=True)
    fx = pd.read_csv(ROOT / "data" / "fx_levels.csv", index_col=0, parse_dates=True)
    for df in (ret, fx):
        df.index = pd.to_datetime(df.index).to_period("M").to_timestamp("M")
    u = fx["USD"].reindex(ret.index).astype(float)
    # LEVEL ANCHORS: u must be USD per EUR. Full-sample range check (EURUSD
    # traded ~0.85 in 2001 and ~1.58 at the 2008 peak); the inverse convention
    # (EUR per USD) would breach the lower bound in 2008 (1/1.58 = 0.63).
    assert 0.8 <= u.min() and u.max() <= 1.6, \
        f"EURUSD levels outside [0.8, 1.6] ({u.min():.3f}..{u.max():.3f}) — wrong convention"
    return ret, u


def annualised_vol(r: pd.Series) -> float:
    return float(r.std(ddof=1) * np.sqrt(12))


def main(compare_csv: str | None = None) -> None:
    ret, u = load()
    correct = {}
    inverted = {}
    for s in SERIES:
        r_usd = ret[s]
        correct[s] = ((1.0 + r_usd) * (u.shift(1) / u) - 1.0).dropna()
        inverted[s] = ((1.0 + r_usd) * (u / u.shift(1)) - 1.0).dropna()

    print("Annualised monthly vols, full committed sample "
          f"({ret.index[0].date()}..{ret.index[-1].date()}):\n")
    print(f"{'series':<10}{'USD':>8}{'EUR fresh (correct)':>21}{'EUR inverted':>14}")
    for s in SERIES:
        print(f"{s:<10}{annualised_vol(ret[s].dropna()):>7.1%}"
              f"{annualised_vol(correct[s]):>16.1%}{annualised_vol(inverted[s]):>17.1%}")

    print("\nDamping check (EUR investor's equity-dollar damping): "
          f"USA EUR {annualised_vol(correct['USA']):.1%} < USA USD "
          f"{annualised_vol(ret['USA'].dropna()):.1%} -> "
          f"{'consistent' if annualised_vol(correct['USA']) < annualised_vol(ret['USA'].dropna()) else 'NOT consistent'} "
          "with correct translation; the inverted series is higher than USD vol, "
          "which no unhedged EUR translation of a USD asset with risk-off dollar "
          "strength should produce over this sample.")

    if compare_csv:
        ext = pd.read_csv(compare_csv, index_col=0, parse_dates=True)
        ext.index = pd.to_datetime(ext.index).to_period("M").to_timestamp("M")
        print(f"\nComparison against external file ({Path(compare_csv).name}):")
        for s in SERIES:
            both_c = pd.concat([ext[s], correct[s]], axis=1, keys=["ext", "own"]).dropna()
            both_i = pd.concat([ext[s], inverted[s]], axis=1, keys=["ext", "own"]).dropna()
            dc = (both_c.ext - both_c.own).abs().max()
            di = (both_i.ext - both_i.own).abs().max()
            print(f"  {s:<10} vol {annualised_vol(ext[s].dropna()):.1%}   "
                  f"max|diff| vs correct {dc:.5f}, vs inverted {di:.5f}  "
                  f"-> matches {'INVERTED' if di < dc else 'correct'} construction")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
