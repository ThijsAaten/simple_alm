"""
Example: equity-only pipeline validation — CURRENT vs PROPOSED A.

Swaps ONLY the global-equity block of the RSP for the country mosaic
(allocations.build_equity_specs), scaled to that block's RSP weight. Real assets
/ IG credit / commodities are held FIXED — the "equity-only first, bonds fixed"
validation step. Both allocations run on the SAME macro paths (common random
numbers), so differences reflect equity composition, not scenario luck.

Headline: real pension pot at retirement (entry-year EUR) + replacement ratio
(now on a conventional, wage-revalued middelloon basis).

Run from the repo root:
    python -m examples.run_equity_only            # default 500 scenarios
    python -m examples.run_equity_only 200        # faster, fewer scenarios
"""
import sys
from pathlib import Path

# Portable bootstrap: put the repo root (this file's parent's parent) on the
# path, so `main_participant`, `assets`, `allocations`, ... resolve regardless of
# the caller's working directory. Replaces the old hard-coded /home/claude path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import dataclasses
import numpy as np

import main_participant as mp
from portfolio.portfolio import SleeveSpec
from allocations import build_equity_specs, CURRENT_EQUITY, PROPOSED_EQUITY

# Weight of the single global-equity sleeve inside the base RSP (build_rsp_specs).
EQUITY_RSP_WEIGHT = 0.50


def rsp_specs_with_mosaic(weights, seed=mp.SEED):
    """Base RSP, but the single equity sleeve replaced by the country mosaic
    (each country weight x the equity block's RSP weight). ra/cr/co unchanged."""
    base = mp.build_rsp_specs()
    non_equity = base[1:]                       # real assets / credit / commodities
    eq_specs = build_equity_specs(weights, seed=seed + 1)
    mosaic = [SleeveSpec(s.sleeve, weight=s.weight * EQUITY_RSP_WEIGHT) for s in eq_specs]
    out = mosaic + list(non_equity)
    tot = sum(s.weight for s in out)
    assert abs(tot - 1.0) < 1e-9, f"RSP weights sum to {tot}"
    return out


def config_with(weights):
    cfg = mp.build_base_config()
    new_specs = rsp_specs_with_mosaic(weights)
    try:
        cfg.rsp_specs = new_specs
    except dataclasses.FrozenInstanceError:
        cfg = dataclasses.replace(cfg, rsp_specs=new_specs)
    return cfg


def cpi_at_retirement(path, working_years):
    cpi = 1.0
    for step in range(working_years):
        cpi *= (1.0 + path[step].inflation)
    return cpi


def summarise(results, paths, working_years):
    rr = np.array([r.replacement_ratio for r in results])
    nom = np.array([r.pot_path[working_years] for r in results])
    cpi = np.array([cpi_at_retirement(p, working_years) for p in paths])
    real_pot = nom / cpi
    return dict(
        rr_p50=np.percentile(rr, 50),
        pot_p5=np.percentile(real_pot, 5),
        pot_p50=np.percentile(real_pot, 50),
        pot_p95=np.percentile(real_pot, 95),
        pot_mean=real_pot.mean(),
        p_short=(rr < mp.AMBITION_RR).mean(),
    )


def main(n_scenarios=None):
    n_scenarios = n_scenarios or mp.N_SCENARIOS
    engine = mp.build_scenario_engine(mp.build_initial_state())
    working_years = mp.RETIREMENT_AGE - mp.ENTRY_AGE
    paths = engine.simulate(n_steps=mp.N_STEPS, n_scenarios=n_scenarios)
    print(f"Paths: {n_scenarios} scenarios x {mp.N_STEPS}y | "
          f"entry {mp.ENTRY_AGE} -> retire {mp.RETIREMENT_AGE} -> death {mp.DEATH_AGE}")

    out = {}
    for tag, w in [("CURRENT (ACWI-like)", CURRENT_EQUITY),
                   ("PROPOSED A (Asia ~40, China 6%)", PROPOSED_EQUITY)]:
        out[tag] = summarise(mp._run_batch(paths, config_with(w)), paths, working_years)

    print(f"\n{'='*72}\nEQUITY-ONLY VALIDATION — real pension pot at retirement (entry-year EUR)\n{'='*72}")
    hdr = f"{'Allocation':<34}{'pot p5':>10}{'pot p50':>10}{'pot p95':>10}{'RR p50':>9}{'P(RR<70%)':>11}"
    print(hdr); print("-"*len(hdr))
    for tag, s in out.items():
        print(f"{tag:<34}{s['pot_p5']/1e3:>9.0f}k{s['pot_p50']/1e3:>9.0f}k{s['pot_p95']/1e3:>9.0f}k"
              f"{s['rr_p50']:>8.1%}{s['p_short']:>11.1%}")
    c, p = out["CURRENT (ACWI-like)"], out["PROPOSED A (Asia ~40, China 6%)"]
    print(f"\nProposed A vs Current (median real pot): {(p['pot_p50']/c['pot_p50']-1)*100:+.1f}%")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(n)
