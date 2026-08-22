"""
Comparison: which growth cycle should equity betas load on?

`assets/growth.py` applies `growth_beta` to `state.growth`, which is EURO-AREA
growth. But `allocations/country_inputs.py` carries India at 0.75, China 0.70 and
Korea 0.70 against Europe's 0.60 and Japan's 0.55. Indian equities cannot
plausibly respond more strongly to euro-area growth than European equities do.
That ordering is only coherent against a GLOBAL cycle — i.e. the equity side
likely carries the same defect the FX side did before `global_growth` existed.

This script does NOT change the default. It runs the three options side by side
so the decision can be made on the size of the effect:

    euro    the current wiring (whole beta on euro growth)
    split   beta divided between the cycles by mosaic.EURO_CYCLE_SHARE,
            preserving each country's TOTAL growth sensitivity
    global  whole beta on global growth

Run from the repo root:
    python -m examples.run_equity_growth_mode            # 1000 scenarios
    python -m examples.run_equity_growth_mode 300
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import dataclasses

import numpy as np

import main_participant as mp
from portfolio.portfolio import SleeveSpec
from allocations import CURRENT_EQUITY, PROPOSED_EQUITY, build_equity_specs
from allocations.mosaic import GROWTH_MODES
from examples.run_equity_only import cpi_at_retirement, EQUITY_RSP_WEIGHT
from examples.run_attribution import (
    build_lhp_with_overlay, repress, REANCHOR_EQUITY)
from examples.run_cgb_dial import lhp_specs_for


def config_for(equity_weights, lhp_specs, growth_mode):
    eq = build_equity_specs(equity_weights, seed=mp.SEED + 1, growth_mode=growth_mode)
    mosaic = [SleeveSpec(s.sleeve, weight=s.weight * EQUITY_RSP_WEIGHT) for s in eq]
    rsp = mosaic + list(mp.build_rsp_specs()[1:])
    return dataclasses.replace(mp.build_base_config(), rsp_specs=rsp, lhp_specs=lhp_specs)


def _p50(paths, cpi, equity, lhp_specs, wy, mode):
    res = mp._run_batch(paths, config_for(equity, lhp_specs, mode))
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

    print(f"EQUITY GROWTH-CYCLE COMPARISON | {n} paths")
    print("euro = current wiring (no published number changes). "
          "split/global reallocate the SAME total beta.\n")

    res = {m: {w: [_p50(p, c, eq, lhp, wy, m) for _t, eq, lhp in steps]
               for w, (p, c) in worlds.items()} for m in GROWTH_MODES}

    for w in worlds:
        print(f"── {w} — median real pot, €000")
        hdr = f"{'Step':<20}" + "".join(f"{m:>12}" for m in GROWTH_MODES)
        print(hdr); print("-" * len(hdr))
        for i, (tag, _e, _l) in enumerate(steps):
            print(f"{tag:<20}" + "".join(f"{res[m][w][i]/1e3:>11.0f}k" for m in GROWTH_MODES))
        print(f"{'  marginal Δ':<20}")
        for i, (tag, _e, _l) in enumerate(steps):
            if i == 0:
                continue
            d = {m: (res[m][w][i] - res[m][w][i-1]) / 1e3 for m in GROWTH_MODES}
            print(f"  {tag.strip():<18}" + "".join(f"{d[m]:>+11.0f}k" for m in GROWTH_MODES))
        print()

    print("CGB dial — Δ(5% vs 0%) on median real pot, €000")
    hdr = f"{'World':<14}" + "".join(f"{m:>12}" for m in GROWTH_MODES)
    print(hdr); print("-" * len(hdr))
    for w, (paths, cpi) in worlds.items():
        row = f"{w:<14}"
        for m in GROWTH_MODES:
            z = _p50(paths, cpi, PROPOSED_EQUITY, lhp_specs_for(0.0), wy, m)
            f = _p50(paths, cpi, PROPOSED_EQUITY, lhp_specs_for(0.05), wy, m)
            row += f"{(f - z)/1e3:>+11.1f}k"
        print(row)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
