"""
plot_allocations.py — Visualise the current cohort allocation glide path.

Run from the project root::

    python plot_allocations.py
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from participant.lifecycle import default_cohort_allocations

cohorts = default_cohort_allocations()

# ── Console table ────────────────────────────────────────────────────────────
print(f"\n{'Age band':>10}  {'RSP %':>7}  {'LHP %':>7}  {'Total %':>8}  {'Leverage %':>11}  {'Equity %':>9}")
print("─" * 62)
for c in cohorts:
    equity_pct = c.rsp_fraction + c.lhp_fraction   # just the sum label
    print(f"{c.age_from:>4}–{c.age_to:<4}    {c.rsp_fraction*100:>5.0f}     {c.lhp_fraction*100:>5.0f}     "
          f"{(c.rsp_fraction+c.lhp_fraction)*100:>6.0f}      {c.leverage_fraction*100:>8.0f}     "
          f"{(c.rsp_fraction+c.lhp_fraction)*100:>6.0f}")
print()

# ── Chart ────────────────────────────────────────────────────────────────────
# Use age-band midpoints for the x-axis
midpoints   = [(c.age_from + c.age_to) / 2 for c in cohorts]
rsp_vals    = [c.rsp_fraction    * 100 for c in cohorts]
lhp_vals    = [c.lhp_fraction    * 100 for c in cohorts]
lev_vals    = [c.leverage_fraction * 100 for c in cohorts]
total_vals  = [(c.rsp_fraction + c.lhp_fraction) * 100 for c in cohorts]

fig, ax = plt.subplots(figsize=(11, 6))

# Stacked bars: LHP (bottom) + RSP above it, split at the 100% line
bar_width = 8.5

# 1. LHP slice (dark blue)
ax.bar(midpoints, lhp_vals, width=bar_width,
       color="#1f77b4", alpha=0.85, label="LHP allocation")

# 2. RSP slice up to 100% (orange, stacked on LHP)
rsp_to_100 = [min(r, 100 - l) for r, l in zip(rsp_vals, lhp_vals)]
ax.bar(midpoints, rsp_to_100, width=bar_width, bottom=lhp_vals,
       color="#ff7f0e", alpha=0.85, label="RSP allocation (unlevered)")

# 3. Leverage slice above 100% (red hatching)
ax.bar(midpoints, lev_vals, width=bar_width,
       bottom=[100.0] * len(midpoints),
       color="#d62728", alpha=0.45, hatch="///", label="Leverage (above 100%)")

# Reference lines
ax.axhline(100, color="black", lw=1.4, ls="--", label="100% = no leverage")

# Labels on each bar: RSP / LHP
for mid, r, l, tot in zip(midpoints, rsp_vals, lhp_vals, total_vals):
    ax.text(mid, tot + 2.5, f"{tot:.0f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.text(mid, l / 2,        f"LHP\n{l:.0f}%",  ha="center", va="center", fontsize=8, color="white")
    if r > 10:
        ax.text(mid, l + rsp_to_100[midpoints.index(mid)] / 2,
                f"RSP\n{r:.0f}%", ha="center", va="center", fontsize=8, color="white")

ax.set_xlim(20, 110)
ax.set_ylim(0, 175)
ax.set_xticks(midpoints)
ax.set_xticklabels([f"{c.age_from}–{c.age_to}" for c in cohorts], fontsize=10)
ax.set_xlabel("Age band", fontsize=12)
ax.set_ylabel("Allocation (%)", fontsize=12)
ax.set_title("Cohort allocation glide path — current settings\n"
             "(actual asset weights)", fontsize=13)
ax.legend(loc="upper right", fontsize=10)
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig("cohort_allocations.png", dpi=150, bbox_inches="tight")
print("Saved: cohort_allocations.png")
plt.show()
