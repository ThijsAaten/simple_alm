"""
Example: what does the CGB dial cost at its 0% default?

`allocations.bond_inputs` carries China (CGB) in a separate MANAGED block, held
as a capped dial with a DEFAULT WEIGHT OF ZERO. The nested attribution in
`examples.run_attribution` therefore never reports what the line would
contribute. This script prices it.

Sweep
-----
CGB weight in {0%, 1%, 2%, 3%, 5%} of the TOTAL LHP. The weight is taken from
the EUR core: the unrepressed developed (10%) and EM (10%) overlay blocks are
held FIXED, so each step trades EUR-core duration for CGB and the comparison is
CGB *against the repressed base*, not against the other overlay sleeves.

Worlds (same construction as `examples.run_attribution`, on the SAME paths)
--------------------------------------------------------------------------
    BASELINE     — no repression
    REPRESSION   — EUR real rate pinned to -1.5%, inflation 3.5%, over a 12y
                   late-accumulation window. CGB's global_rate_beta of 0.10 is
                   the whole rationale for the line: the episode should not pass
                   through into the CGB curve, and a weaker EUR hands the
                   unhedged CNY exposure an FX tailwind.

Equity is held at PROPOSED_EQUITY throughout — this is a marginal on top of
step (iv) of the attribution, not a re-run of the equity decisions.

Reported metrics
----------------
Per world, per weight: median real pension pot at retirement (entry-year EUR,
€000), its delta vs the 0% default, p5/p25/p75/p95, plus the LHP's own
annualised volatility and annualised real return.

NOTE ON THE LHP RETURN SERIES. `ParticipantResult` exposes only pot / pension /
contribution / adjustment paths — no sub-portfolio return series, so LHP vol is
NOT directly exposed by the model. Rather than approximate it from the pot path
(which mixes in the RSP and the age-varying cohort weights), this script records
the LHP return *from inside the real run* by instrumenting `SubPortfolio.step`
(see `_LHPRecorder`). The numbers are therefore the exact annual LHP returns the
pot experienced, not a reconstruction. Both statistics are measured over the
accumulation window only (entry -> retirement), which is the window the headline
pot metric is formed over.

Nothing in `allocations/bond_inputs.py` is modified: the dial stays 0% by
default and is overridden locally, per call.

Downside sensitivity
--------------------
`bond_inputs.py` calibrates CGB at 1.8% initial reverting toward a 2.3% long-run
yield. `--flat-lr` re-prices the whole sweep with the long-run yield pinned at
1.8% — i.e. the old "today's cyclical low is permanent" assumption — so the
result can be read against the reversion assumption it now depends on.

Run from the repo root:
    python -m examples.run_cgb_dial              # default 1000 scenarios
    python -m examples.run_cgb_dial 200          # faster, fewer scenarios
    python -m examples.run_cgb_dial --flat-lr    # 1.8% flat long-run downside
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import csv
from contextlib import contextmanager

import numpy as np

import main_participant as mp
from portfolio.portfolio import SubPortfolio, SleeveSpec
from assets.em_bonds import GovernmentBondSleeve
from allocations import PROPOSED_EQUITY, BOND_INPUTS
from examples.run_equity_only import cpi_at_retirement
from examples.run_attribution import build_lhp_with_overlay, cfg, repress

# CGB weights as a share of the TOTAL LHP.
CGB_WEIGHTS = (0.00, 0.01, 0.02, 0.03, 0.05)
# Unrepressed overlay blocks, held fixed across the sweep.
DEV_WEIGHT, EM_WEIGHT = 0.10, 0.10

N_DEFAULT = 1000
OUT_DIR = _REPO_ROOT / "output"
OUT_CSV = OUT_DIR / "cgb_dial_sweep.csv"
OUT_CSV_FLAT = OUT_DIR / "cgb_dial_sweep_flat_lr.csv"


def lhp_specs_for(china_weight, flat_lr=False):
    """LHP for this sweep point.

    `flat_lr` rebuilds the China sleeve with its long-run yield pinned to the
    initial 1.8% (no reversion pull) — the downside sensitivity. Everything else,
    including the seed, matches what `build_overlay_specs` would have produced,
    so the two sweeps differ in exactly one parameter. `bond_inputs.py` is never
    mutated: the override is constructed locally, per call.
    """
    specs = build_lhp_with_overlay(DEV_WEIGHT, EM_WEIGHT, china_weight)
    if not flat_lr:
        return specs
    inp = BOND_INPUTS["China"]
    out = []
    for s in specs:
        if s.sleeve.name == "China":
            sl = GovernmentBondSleeve(
                name="China", duration=inp["dur"],
                initial_yield=inp["yld"], long_run_yield=inp["yld"],
                yield_reversion=0.20, global_rate_beta=inp["beta"],
                idio_yield_vol=inp["idio"], fx_key=inp["fx"],
                seed=7 + list(BOND_INPUTS).index("China"),
            )
            out.append(SleeveSpec(sl, weight=s.weight))
        else:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# LHP return capture
# ---------------------------------------------------------------------------

class _LHPRecorder:
    """Capture the LHP sub-portfolio's annual returns from inside a real run.

    `LifecycleSimulator.run` builds one RSP and one LHP `SubPortfolio` per path
    and never surfaces their returns. We patch `SubPortfolio.__init__`/`.step`
    for the duration of a batch and keep the returns of the sub-portfolio whose
    sleeve-name set matches the LHP specs. Name-set matching (not creation
    order) is used because the equity mosaic contains sleeves named "China",
    "India", "Korea", "Indonesia" that collide with the bond overlay names —
    the full sets are still unambiguous.
    """

    def __init__(self, lhp_specs):
        self._names = frozenset(s.sleeve.name for s in lhp_specs)
        self.runs: list[list[float]] = []

    @contextmanager
    def capture(self):
        orig_init, orig_step = SubPortfolio.__init__, SubPortfolio.step
        rec = self

        def init(self, specs, initial_value, fx_model=None):
            orig_init(self, specs, initial_value, fx_model)
            if frozenset(s.sleeve.name for s in specs) == rec._names:
                self._lhp_returns = []
                rec.runs.append(self._lhp_returns)

        def step(self, state_t, state_t1, dt=1.0, fx_returns=None):
            r = orig_step(self, state_t, state_t1, dt, fx_returns)
            if hasattr(self, "_lhp_returns"):
                self._lhp_returns.append(r)
            return r

        SubPortfolio.__init__, SubPortfolio.step = init, step
        try:
            yield self
        finally:
            SubPortfolio.__init__, SubPortfolio.step = orig_init, orig_step

    def stats(self, cpi, working_years):
        """Annualised LHP vol and real return over the accumulation window.

        vol  — per-path stdev of annual LHP total returns, median across paths
               (same convention as main_participant.pension_stability_stats).
        real — per-path geometric annual return net of realised CPI to
               retirement, median across paths.
        """
        if not self.runs:
            return float("nan"), float("nan")
        r = np.array([run[:working_years] for run in self.runs])
        vol = float(np.median(r.std(axis=1, ddof=1)))
        growth = np.prod(1.0 + r, axis=1)
        real = float(np.median((growth / cpi) ** (1.0 / working_years) - 1.0))
        return vol, real


# ---------------------------------------------------------------------------
# One (world, weight) cell
# ---------------------------------------------------------------------------

def run_cell(paths, cpi, china_weight, working_years, flat_lr=False):
    """Run the sweep point and return its summary dict."""
    lhp_specs = lhp_specs_for(china_weight, flat_lr)
    rec = _LHPRecorder(lhp_specs)
    with rec.capture():
        results = mp._run_batch(paths, cfg(PROPOSED_EQUITY, lhp_specs))
    pot = np.array([r.pot_path[working_years] for r in results]) / cpi
    vol, real = rec.stats(cpi, working_years)
    return dict(
        cgb_weight=china_weight,
        median_pot=float(np.percentile(pot, 50)),
        p5=float(np.percentile(pot, 5)),
        p25=float(np.percentile(pot, 25)),
        p75=float(np.percentile(pot, 75)),
        p95=float(np.percentile(pot, 95)),
        lhp_vol=vol,
        lhp_real_return=real,
    )


def main(n_scenarios=None, flat_lr=False):
    n = n_scenarios or N_DEFAULT
    wy = mp.RETIREMENT_AGE - mp.ENTRY_AGE

    # Same seeding as examples.run_attribution: engine seed mp.SEED, and
    # _run_batch's default seed_base=mp.SEED. Both worlds share the paths.
    base_paths = mp.build_scenario_engine(mp.build_initial_state()).simulate(
        n_steps=mp.N_STEPS, n_scenarios=n)
    rep_paths = [repress(p) for p in base_paths]
    worlds = {
        "baseline":   (base_paths, np.array([cpi_at_retirement(p, wy) for p in base_paths])),
        "repression": (rep_paths,  np.array([cpi_at_retirement(p, wy) for p in rep_paths])),
    }

    lr = BOND_INPUTS["China"]["yld"] if flat_lr else BOND_INPUTS["China"].get(
        "lr", BOND_INPUTS["China"]["yld"])
    print(f"CGB DIAL SWEEP — marginal contribution of the managed CGB line | {n} paths")
    print(f"CGB: {BOND_INPUTS['China']['yld']:.1%} initial -> {lr:.1%} long-run, "
          f"beta {BOND_INPUTS['China']['beta']:.2f}"
          f"{'   [DOWNSIDE SENSITIVITY: flat long-run]' if flat_lr else ''}")
    print(f"Weight taken from the EUR core; dev {DEV_WEIGHT:.0%} / EM {EM_WEIGHT:.0%} "
          f"overlay held fixed. Equity: PROPOSED A.")
    print("Repression: EUR real -1.5%, inflation 3.5%, 12y late-accumulation window.")
    print("Pot = real pension pot at retirement, entry-year EUR (€000).\n")

    rows = []
    hdr = (f"{'CGB w':>7}{'median':>10}{'Δ vs 0%':>10}{'p5':>9}{'p25':>9}"
           f"{'p75':>9}{'p95':>9}{'LHP vol':>10}{'LHP real':>10}")
    for world, (paths, cpi) in worlds.items():
        print(f"── {world.upper()} " + "─" * (len(hdr) - len(world) - 4))
        print(hdr); print("-" * len(hdr))
        zero = None
        for w in CGB_WEIGHTS:
            s = run_cell(paths, cpi, w, wy, flat_lr)
            if zero is None:
                zero = s["median_pot"]
            s["world"] = world
            s["delta_vs_zero"] = s["median_pot"] - zero
            rows.append(s)
            d = "" if w == CGB_WEIGHTS[0] else f"{s['delta_vs_zero']/1e3:+.1f}k"
            print(f"{w:>6.0%}{s['median_pot']/1e3:>9.0f}k{d:>10}"
                  f"{s['p5']/1e3:>8.0f}k{s['p25']/1e3:>8.0f}k{s['p75']/1e3:>8.0f}k"
                  f"{s['p95']/1e3:>8.0f}k{s['lhp_vol']:>9.2%}{s['lhp_real_return']:>10.2%}")
        print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_CSV_FLAT if flat_lr else OUT_CSV
    cols = ["world", "cgb_weight", "median_pot", "delta_vs_zero",
            "p5", "p25", "p75", "p95", "lhp_vol", "lhp_real_return"]
    with open(out_csv, "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=cols)
        wtr.writeheader()
        for r in rows:
            # Pot figures in €000 entry-year, matching the printed table;
            # lhp_vol / lhp_real_return are decimals.
            out = {k: r[k] for k in cols}
            for k in ("median_pot", "delta_vs_zero", "p5", "p25", "p75", "p95"):
                out[k] = round(out[k] / 1e3, 3)
            for k in ("lhp_vol", "lhp_real_return"):
                out[k] = round(out[k], 6)
            wtr.writerow(out)
    print(f"Wrote {out_csv.relative_to(_REPO_ROOT)} "
          f"(pot columns in €000 entry-year; vol/real as decimals)")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if a != "--flat-lr"]
    main(int(argv[0]) if argv else None, flat_lr="--flat-lr" in sys.argv)
