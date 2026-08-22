"""
Sensitivity: full-sample vs post-2017 FX inflation loadings.

`assets/fx.py` calibrates `inflation_loading` from EUR-cross monthly log changes
over 2001-03..2026-04 (loading = 0.50 x beta vs USD). Post-2017 those
correlations fall sharply — CNY 0.92 -> 0.71, TWD 0.80 -> 0.60, JPY 0.56 -> 0.25,
while HKD holds at 0.99 as a hard peg should. The full sample is the headline
because 112 months is thin for currency betas, but the choice is load-bearing
and is reported rather than buried.

The choice is NOT self-serving: post-2017 puts CNY at 0.30 rather than 0.45,
which WEAKENS the CGB repression case this repo otherwise argues for.

Only the four post-2017 loadings that were actually derived are applied
(CNY/THB/IDR/HKD); the rest keep their full-sample value. Loading cannot be
recovered from correlation alone — scaling CNY's full-sample loading by its
correlation ratio predicts 0.35 where the measured post-2017 value is 0.30 —
so TWD and JPY are deliberately left unchanged rather than guessed.

Run from the repo root:
    python -m examples.run_fx_loading_sensitivity          # 1000 scenarios
    python -m examples.run_fx_loading_sensitivity 200
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from contextlib import contextmanager

import numpy as np

import main_participant as mp
from assets.fx import FXModel, POST_2017_INFLATION_LOADINGS
from allocations import CURRENT_EQUITY, PROPOSED_EQUITY
from examples.run_equity_only import cpi_at_retirement
from examples.run_attribution import (
    build_lhp_with_overlay, cfg, repress, REANCHOR_EQUITY)
from examples.run_cgb_dial import lhp_specs_for, DEV_WEIGHT, EM_WEIGHT


@contextmanager
def post_2017_loadings():
    """Swap FXModel.default for the post-2017 variant for the duration.

    LifecycleSimulator.run calls FXModel.default(seed=...) directly, so this is
    the least invasive way to run the whole pipeline on an alternative table.
    """
    orig = FXModel.default
    FXModel.default = FXModel.post_2017
    try:
        yield
    finally:
        FXModel.default = orig


def _p50(paths, cpi, equity, lhp_specs, wy):
    res = mp._run_batch(paths, cfg(equity, lhp_specs))
    return float(np.percentile(np.array([r.pot_path[wy] for r in res]) / cpi, 50))


def main(n_scenarios=None):
    n = n_scenarios or 1000
    wy = mp.RETIREMENT_AGE - mp.ENTRY_AGE
    base = mp.build_scenario_engine(mp.build_initial_state()).simulate(
        n_steps=mp.N_STEPS, n_scenarios=n)
    rep = [repress(p) for p in base]
    worlds = {"BASELINE": (base, np.array([cpi_at_retirement(p, wy) for p in base])),
              "REPRESSION": (rep, np.array([cpi_at_retirement(p, wy) for p in rep]))}

    steps = [
        ("(i)   Current",    CURRENT_EQUITY,  mp.build_lhp_specs()),
        ("(ii)  +Re-anchor", REANCHOR_EQUITY, mp.build_lhp_specs()),
        ("(iii) +China cap", PROPOSED_EQUITY, mp.build_lhp_specs()),
        ("(iv)  +Bond side", PROPOSED_EQUITY, build_lhp_with_overlay()),
    ]

    print(f"FX LOADING SENSITIVITY — full-sample vs post-2017 | {n} paths")
    print(f"Overridden post-2017: {POST_2017_INFLATION_LOADINGS}")
    print("All other currencies keep their full-sample loading.\n")

    def attribution():
        return {w: [_p50(p, c, eq, lhp, wy) for _t, eq, lhp in steps]
                for w, (p, c) in worlds.items()}

    full = attribution()
    with post_2017_loadings():
        post = attribution()

    for w in worlds:
        print(f"── {w}")
        hdr = f"{'Step':<20}{'full-sample':>13}{'post-2017':>12}{'diff':>10}"
        print(hdr); print("-" * len(hdr))
        for i, (tag, _e, _l) in enumerate(steps):
            a, b = full[w][i], post[w][i]
            print(f"{tag:<20}{a/1e3:>12.0f}k{b/1e3:>11.0f}k{(b-a)/1e3:>+9.1f}k")
        # marginal contributions matter more than levels
        da = np.diff(full[w]) / 1e3
        db = np.diff(post[w]) / 1e3
        print(f"{'  marginal Δ':<20}"
              + "  ".join(f"{x:+.0f}k->{y:+.0f}k" for x, y in zip(da, db)))
        print()

    # CGB dial: does the repression case survive the weaker CNY loading?
    print("CGB dial — Δ(5% vs 0%) on median real pot")
    hdr = f"{'World':<14}{'full-sample':>13}{'post-2017':>12}{'diff':>10}"
    print(hdr); print("-" * len(hdr))
    for w, (paths, cpi) in worlds.items():
        vals = []
        for use_post in (False, True):
            ctx = post_2017_loadings() if use_post else None
            if ctx:
                with ctx:
                    z = _p50(paths, cpi, PROPOSED_EQUITY, lhp_specs_for(0.0), wy)
                    f = _p50(paths, cpi, PROPOSED_EQUITY, lhp_specs_for(0.05), wy)
            else:
                z = _p50(paths, cpi, PROPOSED_EQUITY, lhp_specs_for(0.0), wy)
                f = _p50(paths, cpi, PROPOSED_EQUITY, lhp_specs_for(0.05), wy)
            vals.append((f - z) / 1e3)
        print(f"{w:<14}{vals[0]:>+12.1f}k{vals[1]:>+11.1f}k{vals[1]-vals[0]:>+9.1f}k")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
