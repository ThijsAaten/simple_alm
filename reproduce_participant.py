#!/usr/bin/env python3
"""
reproduce_participant.py — one-command driver for the participant-wealth results.

Runs the lifecycle Monte Carlo for all four article allocations on a single
shared set of macro paths (common random numbers, so the comparison is paired)
and prints the real-pension-pot distribution and replacement ratio for each.

    python reproduce_participant.py            # default 500 scenarios
    python reproduce_participant.py 200        # faster

This covers the in-repo ALM model. Regenerating the article's CAPE / Markowitz /
fiscal exhibits is documented separately in docs/REPRODUCE.md (those scripts read
the data workbook and are part of the article working bundle, not this model).
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np

import main_participant as mp
from allocations import (
    CURRENT_EQUITY, PROPOSED_EQUITY, PROPOSED_CONSERVATIVE, PROPOSED_TIGHT_CHINA,
)
from examples.run_equity_only import config_with, cpi_at_retirement

ALLOCATIONS = [
    ("Current (ACWI-like)",        CURRENT_EQUITY),
    ("Proposed A (China 6%)",      PROPOSED_EQUITY),
    ("Proposed C (conservative)",  PROPOSED_CONSERVATIVE),
    ("Proposed D (China 3%)",      PROPOSED_TIGHT_CHINA),
]


def main(n_scenarios=None):
    n = n_scenarios or mp.N_SCENARIOS
    wy = mp.RETIREMENT_AGE - mp.ENTRY_AGE
    paths = mp.build_scenario_engine(mp.build_initial_state()).simulate(
        n_steps=mp.N_STEPS, n_scenarios=n)
    cpi = np.array([cpi_at_retirement(p, wy) for p in paths])

    print(f"PARTICIPANT WEALTH — {n} scenarios, equity-only mosaic (bonds fixed)")
    print(f"  entry {mp.ENTRY_AGE} -> retire {mp.RETIREMENT_AGE} -> death {mp.DEATH_AGE}, "
          f"ambition RR {mp.AMBITION_RR:.0%}, RR basis = wage-indexed middelloon\n")
    hdr = f"{'Allocation':<28}{'real pot p5':>13}{'p50':>9}{'p95':>9}{'RR p50':>9}{'P(RR<70%)':>11}"
    print(hdr); print("-" * len(hdr))

    base_p50 = None
    for tag, w in ALLOCATIONS:
        res = mp._run_batch(paths, config_with(w))
        rr = np.array([r.replacement_ratio for r in res])
        real_pot = np.array([r.pot_path[wy] for r in res]) / cpi
        p50 = np.percentile(real_pot, 50)
        if base_p50 is None:
            base_p50 = p50
        delta = "" if tag.startswith("Current") else f"  ({(p50/base_p50-1)*100:+.1f}% vs Current)"
        print(f"{tag:<28}{np.percentile(real_pot,5)/1e3:>12.0f}k{p50/1e3:>8.0f}k"
              f"{np.percentile(real_pot,95)/1e3:>8.0f}k{np.percentile(rr,50):>8.1%}"
              f"{(rr<mp.AMBITION_RR).mean():>11.1%}{delta}")
    print("\nReal pot = nominal pot at retirement deflated by each path's cumulative CPI (entry-year EUR).")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
