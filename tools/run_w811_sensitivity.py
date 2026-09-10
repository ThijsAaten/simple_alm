"""W8.11 sensitivity variant — all Asian equity sleeve volatilities +3pp.

Referee-facing robustness row (article Table 6 / tracker W8.11): rerun the
participant simulation with every Asian equity sleeve's TOTAL volatility raised
by 3 percentage points (absolute), everything else at committed calibration.

The perturbation is a RUN-CONFIG OVERRIDE, not a calibration edit: sleeves are
built from the committed COUNTRY_INPUTS and then each Asian sleeve's `idio_vol`
is raised on the constructed instance so that

    sqrt((mbeta * EQUITY_FACTOR_VOL)^2 + idio_new^2) = total_committed + 0.03.

Raising idio (rather than mbeta) adds the 3pp orthogonally: market betas, and
therefore absolute cross-sleeve covariances, are unchanged; correlation
coefficients fall slightly because total vol rises. "Asian" = the committed
ASIA set (incl. Japan). The committed calibration is hash-guarded: the bytes of
the calibration modules are hashed before and after the run and must match
(also enforced in tests/test_invariants.py).

Runs step (i) Current (reference mix) and step (iv) Proposed A + bond side
(the headline allocation), 5 seeds x N x both worlds, in the row format of the
committed attribution records so it diffs directly against output/fxr2_*.

Usage:  python tools/run_w811_sensitivity.py [N]     (default 1000)
Writes: output/w811_asia_vol3pp_attribution.csv
"""
from __future__ import annotations
import csv, hashlib, subprocess, sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "examples"))

import main_participant as mp                                   # noqa: E402
import run_attribution as ra                                    # noqa: E402
from run_attribution import repress, cpi_at_retirement          # noqa: E402
from run_equity_only import rsp_specs_with_mosaic               # noqa: E402
from allocations.country_inputs import ASIA, COUNTRY_INPUTS     # noqa: E402
from scenarios.engine import EQUITY_FACTOR_VOL                  # noqa: E402
import dataclasses                                              # noqa: E402

SEEDS = [42, 137, 271, 314, 577]
VOL_BUMP = 0.03          # absolute, on TOTAL sleeve volatility
CALIB_FILES = [ROOT / "allocations" / "country_inputs.py",
               ROOT / "scenarios" / "engine.py",
               ROOT / "assets" / "growth.py"]


def calib_hash() -> str:
    h = hashlib.sha256()
    for f in CALIB_FILES:
        h.update(f.read_bytes())
    # runtime dict too, so an in-process mutation is caught even without a file edit
    h.update(repr(sorted((k, sorted(v.items())) for k, v in COUNTRY_INPUTS.items()
                         if isinstance(v, dict))).encode())
    return h.hexdigest()


def bump_asian_vol(specs, bump: float = VOL_BUMP):
    """Raise each Asian sleeve's total vol by `bump`, via idio, on the instances."""
    for s in specs:
        name = getattr(s.sleeve, "name", None)
        if name in ASIA:
            mkt = s.sleeve.market_beta * EQUITY_FACTOR_VOL
            total = np.sqrt(mkt ** 2 + s.sleeve.idio_vol ** 2)
            s.sleeve.idio_vol = float(np.sqrt((total + bump) ** 2 - mkt ** 2))
    return specs


def cfg_variant(equity_weights, lhp_specs):
    c = mp.build_base_config()
    rsp = bump_asian_vol(rsp_specs_with_mosaic(equity_weights))
    return dataclasses.replace(c, rsp_specs=rsp, lhp_specs=lhp_specs)


def main(n: int = 1000) -> None:
    h0 = calib_hash()
    wy = mp.RETIREMENT_AGE - mp.ENTRY_AGE
    out = ROOT / "output"; out.mkdir(exist_ok=True)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                         cwd=ROOT, text=True).strip()
    except Exception:
        commit = "unknown"

    steps = [
        ("(i)   Current",    ra.CURRENT_EQUITY,  mp.build_lhp_specs),
        ("(iv)  +Bond side", ra.PROPOSED_EQUITY, ra.build_lhp_with_overlay),
    ]
    rows = []
    for seed in SEEDS:
        base = mp.build_scenario_engine(mp.build_initial_state(), seed=seed).simulate(
            n_steps=mp.N_STEPS, n_scenarios=n)
        rep = [repress(p) for p in base]
        worlds = {
            "baseline":   (base, np.array([cpi_at_retirement(p, wy) for p in base])),
            "repression": (rep,  np.array([cpi_at_retirement(p, wy) for p in rep])),
        }
        for world, (paths, cpi) in worlds.items():
            for tag, eq, lhp in steps:
                res = mp._run_batch(paths, cfg_variant(eq, lhp()), seed_base=seed)
                pot = np.array([r.pot_path[wy] for r in res]) / cpi
                p50 = float(np.percentile(pot, 50))
                rows.append((tag, world, seed, round(p50 / 1e3, 3)))
                print(f"[w811] seed {seed} {world:<10} {tag:<18} {p50/1e3:8.1f}k")

    assert calib_hash() == h0, "committed calibration mutated during the run"
    print("calibration hash unchanged:", h0[:16])

    path = out / "w811_asia_vol3pp_attribution.csv"
    with path.open("w", newline="") as f:
        f.write(f"# W8.11 variant: Asian equity sleeve total vol +3pp (idio override; "
                f"ASIA set incl. Japan) | commit {commit} | N={n} | seeds={SEEDS} | "
                f"calib sha256 {h0[:16]} unchanged\n")
        w = csv.writer(f)
        w.writerow(["step", "world", "seed", "level"])
        w.writerows(rows)
    print("wrote", path)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
