"""
Example: bond-side attribution under baseline vs EUR financial repression.

Nested attribution, each step adding one decision:
    (i)   Current      — ACWI-like equity + EUR-only LHP
    (ii)  +Re-anchor   — Asia ~40% equity, China UNCAPPED + EUR-only LHP
    (iii) +China cap   — Proposed A equity (China 6%) + EUR-only LHP
    (iv)  +Bond side   — Proposed A equity + 80/10/10 unrepressed LHP

Each step is run under two explicit worlds on the SAME paths (Option C):
    BASELINE     — no repression
    REPRESSION   — EUR real rate pinned to -1.5%, inflation 3.5% over a sustained
                   late-accumulation window; the low-beta overlay sleeves stay
                   unrepressed by construction (and a weaker EUR hands the
                   unhedged overlay an FX tailwind via the FX model).

Run from the repo root:
    python -m examples.run_attribution            # default 400 scenarios
    python -m examples.run_attribution 800
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
from examples.run_equity_only import rsp_specs_with_mosaic, cpi_at_retirement
from allocations import CURRENT_EQUITY, PROPOSED_EQUITY, build_overlay_specs

# Attribution waypoint: Asia re-anchored (~43% incl Japan) but China still at its
# (uncapped) cap-weighted share ~11%; step (iii) disciplines it to 6%, moving the
# 5% into the cheaper/younger EM-Asia tilt. NOT a recommended allocation — an
# attribution intermediate only.
REANCHOR_EQUITY = {
    "USA": 0.37, "Europe": 0.20, "Japan": 0.12, "China": 0.11,
    "Korea": 0.05, "India": 0.05, "Taiwan": 0.045, "Indonesia": 0.035,
    "Vietnam": 0.01, "Singapore": 0.01,
}


def build_lhp_with_overlay(dev=0.10, em=0.10, china=0.0):
    """EUR core (residual plug) + unhedged unrepressed/managed overlay."""
    overlay = build_overlay_specs(dev, em, china)
    eur_w = 1.0 - sum(s.weight for s in overlay)
    eur_core = [SleeveSpec(s.sleeve, weight=s.weight * eur_w) for s in mp.build_lhp_specs()]
    out = eur_core + overlay
    assert abs(sum(s.weight for s in out) - 1.0) < 1e-9
    return out


def cfg(equity, lhp_specs):
    c = mp.build_base_config()
    return dataclasses.replace(c, rsp_specs=rsp_specs_with_mosaic(equity), lhp_specs=lhp_specs)


def repress(path, start=25, duration=12, real=-0.015, infl=0.035, slope=0.010):
    """Repressed copy of a macro path: over [start, start+duration) pin EUR
    real_rate and inflation and rebuild the nominal curve so the long real yield
    is negative (nominal long = real + breakeven ~ inflation)."""
    out = []
    for i, s in enumerate(path):
        if start <= i < start + duration:
            long_rate = real + infl
            s = dataclasses.replace(s, real_rate=real, inflation=infl,
                                    long_rate=long_rate, short_rate=long_rate - slope)
        out.append(s)
    return out


def _pot_p50(paths, cpi, equity, lhp_specs, wy):
    res = mp._run_batch(paths, cfg(equity, lhp_specs))
    pot = np.array([r.pot_path[wy] for r in res]) / cpi
    return np.percentile(pot, 50)


def main(n_scenarios=None):
    n = n_scenarios or 400
    wy = mp.RETIREMENT_AGE - mp.ENTRY_AGE
    base_paths = mp.build_scenario_engine(mp.build_initial_state()).simulate(
        n_steps=mp.N_STEPS, n_scenarios=n)
    rep_paths = [repress(p) for p in base_paths]
    base_cpi = np.array([cpi_at_retirement(p, wy) for p in base_paths])
    rep_cpi = np.array([cpi_at_retirement(p, wy) for p in rep_paths])

    steps = [
        ("(i)   Current",    CURRENT_EQUITY,  mp.build_lhp_specs()),
        ("(ii)  +Re-anchor", REANCHOR_EQUITY, mp.build_lhp_specs()),
        ("(iii) +China cap", PROPOSED_EQUITY, mp.build_lhp_specs()),
        ("(iv)  +Bond side", PROPOSED_EQUITY, build_lhp_with_overlay()),
    ]

    print(f"NESTED ATTRIBUTION — real pension pot p50 (entry-year EUR) | {n} paths")
    print("Repression: EUR real -1.5%, inflation 3.5%, 12y late-accumulation window\n")
    hdr = f"{'Step':<20}{'BASELINE':>12}{'Δ':>8}{'REPRESSION':>13}{'Δ':>8}"
    print(hdr); print("-" * len(hdr))
    pb = pr = None
    for tag, eq, lhp in steps:
        b = _pot_p50(base_paths, base_cpi, eq, lhp, wy)
        r = _pot_p50(rep_paths, rep_cpi, eq, lhp, wy)
        db = "" if pb is None else f"{(b-pb)/1e3:+.0f}k"
        dr = "" if pr is None else f"{(r-pr)/1e3:+.0f}k"
        print(f"{tag:<20}{b/1e3:>11.0f}k{db:>8}{r/1e3:>12.0f}k{dr:>8}")
        pb, pr = b, r
    print("\nΔ = marginal contribution. The bond-side step adds little at baseline and "
          "materially more under repression — its conditional value.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
