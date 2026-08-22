#!/usr/bin/env python3
"""
build_exhibit6_participant_wealth.py — Exhibit 6 for the Asia pension article.

Two panels:
  (a) value bridge: median real pot built up Current -> +Re-anchor -> +China cap
      -> +Bond side, baseline vs EUR financial repression.
  (b) distributions: Current vs Proposed A (p5-p95 whisker, p25-p75 box, median),
      in each world.

This exhibit is generated FROM THE MODEL (unlike the data-pickle exhibits), so it
re-renders automatically when the allocations in simple_alm/allocations change.

Requires the model repo `simple_alm` (github.com/ThijsAaten/simple_alm). It is
located via, in order: $SIMPLE_ALM, ../simple_alm relative to the bundle,
~/simple_alm. Output: exhibit6_participant_wealth.{pdf,png} in the current dir
(so it sits beside the article .md at build time, like the other exhibits).

    python3 build_exhibit6_participant_wealth.py            # 1000 scenarios
    SIMPLE_ALM=/path/to/simple_alm python3 build_exhibit6_participant_wealth.py 2000
"""
import os, sys
from pathlib import Path

# --- output location (2026-08-22) -----------------------------------------
# This script is deliberately kept in TWO places, byte-identical:
#   * simple_alm/build_exhibit6_participant_wealth.py   — so the exhibit can be
#     rebuilt from the public model repo alone, without the private article project
#   * <article>/exhibits/scripts/                       — beside the other exhibit
#     builders, which write into <article>/exhibits/
# One rule serves both, so the copies never need to differ:
#   1. $EXHIBIT_OUT if set
#   2. else ../ if this file sits in .../exhibits/scripts/  (the article layout)
#   3. else the current directory                          (the standalone layout)
from pathlib import Path as _P

def _out_dir() -> _P:
    import os as _os
    if _os.environ.get("EXHIBIT_OUT"):
        return _P(_os.environ["EXHIBIT_OUT"]).expanduser().resolve()
    here = _P(__file__).resolve()
    if here.parent.name == "scripts" and here.parents[1].name == "exhibits":
        return here.parents[1]
    return _P.cwd()

_OUT = _out_dir()
# --------------------------------------------------------------------------



def _find_simple_alm() -> Path:
    here = Path(__file__).resolve()
    cands = []
    if os.environ.get("SIMPLE_ALM"):
        cands.append(Path(os.environ["SIMPLE_ALM"]))
    cands += [
        here.parents[2] / "simple_alm",   # repo sibling of the bundle root
        here.parents[1] / "simple_alm",
        Path.home() / "simple_alm",
    ]
    for c in cands:
        if (c / "main_participant.py").exists():
            return c
    raise SystemExit("simple_alm not found. Set SIMPLE_ALM=/path/to/simple_alm "
                     "(github.com/ThijsAaten/simple_alm).")


SA = _find_simple_alm()
sys.path.insert(0, str(SA))
sys.path.insert(0, str(SA / "examples"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch

import main_participant as mp
from examples.run_attribution import REANCHOR_EQUITY, build_lhp_with_overlay, cfg, repress
from examples.run_equity_only import cpi_at_retirement
from allocations import CURRENT_EQUITY, PROPOSED_EQUITY

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.labelsize"] = 10

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
wy = mp.RETIREMENT_AGE - mp.ENTRY_AGE
base_paths = mp.build_scenario_engine(mp.build_initial_state()).simulate(
    n_steps=mp.N_STEPS, n_scenarios=N)
rep_paths = [repress(p) for p in base_paths]
base_cpi = np.array([cpi_at_retirement(p, wy) for p in base_paths])
rep_cpi = np.array([cpi_at_retirement(p, wy) for p in rep_paths])

STEPS = [
    ("Current",    CURRENT_EQUITY,  mp.build_lhp_specs()),
    ("+Re-anchor", REANCHOR_EQUITY, mp.build_lhp_specs()),
    ("+China cap", PROPOSED_EQUITY, mp.build_lhp_specs()),
    ("+Bond side", PROPOSED_EQUITY, build_lhp_with_overlay()),
]

def run(paths, cpi, eq, lhp):
    res = mp._run_batch(paths, cfg(eq, lhp))
    return np.array([r.pot_path[wy] for r in res]) / cpi / 1e3

base = [run(base_paths, base_cpi, eq, lhp) for _, eq, lhp in STEPS]
rep  = [run(rep_paths,  rep_cpi,  eq, lhp) for _, eq, lhp in STEPS]
base_med = [np.percentile(a, 50) for a in base]
rep_med  = [np.percentile(a, 50) for a in rep]

WHITE, GREY = "white", "0.62"
fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.2, 4.9))

# ---- Panel (a): value bridge ----
labels = ["Current", "+Re-anchor", "+China cap", "+Bond side"]
x = np.arange(4); w = 0.36; FLOOR = 820

def bridge(ax, med, xoff, face):
    ax.bar(x[0] + xoff, med[0] - FLOOR, width=w, bottom=FLOOR,
           facecolor=face, edgecolor="black", lw=1.1, zorder=3)
    for k in range(1, 4):
        lo, hi = min(med[k-1], med[k]), max(med[k-1], med[k])
        ax.bar(x[k] + xoff, hi - lo, width=w, bottom=lo,
               facecolor=face, edgecolor="black", lw=1.1, zorder=3)
        ax.plot([x[k-1] + xoff + w/2, x[k] + xoff - w/2], [med[k-1]]*2,
                color="0.5", lw=0.8, ls=(0, (3, 2)), zorder=2)
        ax.annotate(f"{med[k]-med[k-1]:+.0f}", (x[k] + xoff, hi + 4),
                    ha="center", va="bottom", fontsize=7)
    ax.annotate(f"{med[0]:.0f}", (x[0] + xoff, med[0] + 4), ha="center", va="bottom", fontsize=7)
    ax.annotate(f"{med[3]:.0f}", (x[3] + xoff, max(med[2], med[3]) + 22),
                ha="center", va="bottom", fontsize=7.5, fontweight="bold")

bridge(axA, base_med, -w/2 - 0.02, WHITE)
bridge(axA, rep_med,  +w/2 + 0.02, GREY)
axA.set_xticks(x); axA.set_xticklabels(labels, fontsize=8.5)
axA.set_ylim(FLOOR, 1470)
axA.set_ylabel("Median real pension pot at retirement (\u20ac000, entry-year)")
axA.set_title("(a) Attribution of the median real pot", fontsize=10.5, pad=6)
axA.grid(True, axis="y", alpha=0.25, lw=0.5, zorder=0); axA.set_axisbelow(True)

# ---- Panel (b): distributions ----
def box(ax, arr, xc, face, bw=0.30):
    p5, p25, p50, p75, p95 = np.percentile(arr, [5, 25, 50, 75, 95])
    ax.plot([xc, xc], [p5, p95], color="black", lw=1.0, zorder=2)
    for yv in (p5, p95):
        ax.plot([xc - bw/4, xc + bw/4], [yv, yv], color="black", lw=1.0, zorder=2)
    ax.add_patch(Rectangle((xc - bw/2, p25), bw, p75 - p25,
                           facecolor=face, edgecolor="black", lw=1.1, zorder=3))
    ax.plot([xc - bw/2, xc + bw/2], [p50, p50], color="black", lw=1.7, zorder=4)

pos = {"cur_b": 0.82, "cur_r": 1.18, "pro_b": 2.02, "pro_r": 2.38}
box(axB, base[0], pos["cur_b"], WHITE); box(axB, rep[0], pos["cur_r"], GREY)
box(axB, base[3], pos["pro_b"], WHITE); box(axB, rep[3], pos["pro_r"], GREY)
axB.set_xticks([1.0, 2.2]); axB.set_xticklabels(["Current", "Proposed A"], fontsize=9.5)
axB.set_xlim(0.4, 2.8)
axB.set_ylabel("Real pension pot at retirement (\u20ac000, entry-year)")
axB.set_title("(b) Pot distribution (p5\u2013p95, box p25\u2013p75, median)", fontsize=10.5, pad=6)
axB.grid(True, axis="y", alpha=0.25, lw=0.5, zorder=0); axB.set_axisbelow(True)
axB.legend(handles=[Patch(facecolor=WHITE, edgecolor="black", label="Baseline (no repression)"),
                    Patch(facecolor=GREY, edgecolor="black", label="EUR financial repression")],
           loc="upper left", fontsize=8.5, frameon=False)

plt.tight_layout()
for ext in ("pdf", "png"):
    plt.savefig(str(_OUT / f"exhibit6_participant_wealth.{ext}"),
                bbox_inches="tight", dpi=170 if ext == "png" else None)
print(f"[simple_alm: {SA}]  N={N}")
print("baseline medians:", [f"{m:.0f}" for m in base_med])
print("repression medians:", [f"{m:.0f}" for m in rep_med])
print(f"Exhibit 6 written to {_OUT}/exhibit6_participant_wealth.{{pdf,png}}")
