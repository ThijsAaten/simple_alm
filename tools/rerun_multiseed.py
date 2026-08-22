"""Multi-seed re-run of the nested attribution and the CGB dial.

Reproduces the row format of output/validated_attribution.csv and
output/validated_cgb_dial.csv so a post-recalibration run diffs directly
against the frozen validation record. Added 2026-08-22 for V-M3; the harness
that produced the original validated CSVs was not committed.

Usage:  python tools/rerun_multiseed.py [N] [tag]
Writes: output/<tag>_attribution.csv, output/<tag>_cgb_dial.csv,
        output/<tag>_pot_distributions.csv
"""
from __future__ import annotations
import csv, subprocess, sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "examples"))

import main_participant as mp                                   # noqa: E402
import run_attribution as ra                                    # noqa: E402
import run_cgb_dial as rc                                       # noqa: E402
from run_attribution import repress, cpi_at_retirement          # noqa: E402

ATTR_SEEDS = [42, 137, 271, 314, 577]
DIAL_SEEDS = [42, 137, 271]
DIAL_WEIGHTS = rc.CGB_WEIGHTS


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _worlds(seed: int, n: int, wy: int):
    base = mp.build_scenario_engine(mp.build_initial_state(), seed=seed).simulate(
        n_steps=mp.N_STEPS, n_scenarios=n)
    rep = [repress(p) for p in base]
    return {
        "baseline":   (base, np.array([cpi_at_retirement(p, wy) for p in base])),
        "repression": (rep,  np.array([cpi_at_retirement(p, wy) for p in rep])),
    }


def _pots(paths, cpi, equity, lhp, wy, seed):
    res = mp._run_batch(paths, ra.cfg(equity, lhp), seed_base=seed)
    return np.array([r.pot_path[wy] for r in res]) / cpi


def main(n: int = 1000, tag: str = "vm3") -> None:
    wy = mp.RETIREMENT_AGE - mp.ENTRY_AGE
    out = ROOT / "output"; out.mkdir(exist_ok=True)
    hdr_meta = f"commit {_commit()} | N={n}"

    steps = [
        ("(i)   Current",    ra.CURRENT_EQUITY,  mp.build_lhp_specs),
        ("(ii)  +Re-anchor", ra.REANCHOR_EQUITY, mp.build_lhp_specs),
        ("(iii) +China cap", ra.PROPOSED_EQUITY, mp.build_lhp_specs),
        ("(iv)  +Bond side", ra.PROPOSED_EQUITY, ra.build_lhp_with_overlay),
    ]

    # ---- attribution --------------------------------------------------------
    attr_rows, dist_rows = [], []
    for seed in ATTR_SEEDS:
        worlds = _worlds(seed, n, wy)
        for world, (paths, cpi) in worlds.items():
            prev = None
            for tag_s, eq, lhp_fn in steps:
                pots = _pots(paths, cpi, eq, lhp_fn(), wy, seed)
                lvl = float(np.percentile(pots, 50)) / 1e3
                attr_rows.append({"step": tag_s, "world": world, "seed": seed,
                                  "level": round(lvl, 3),
                                  "marginal_delta": "" if prev is None else round(lvl - prev, 3)})
                dist_rows.append({"step": tag_s, "world": world, "seed": seed,
                                  **{f"p{q}": round(float(np.percentile(pots, q)) / 1e3, 3)
                                     for q in (5, 25, 50, 75, 95)},
                                  "sd": round(float(pots.std()) / 1e3, 3)})
                prev = lvl
                print(f"[attr] seed {seed} {world:10s} {tag_s:<20s} {lvl:8.1f}k", flush=True)

    with open(out / f"{tag}_attribution.csv", "w", newline="") as fh:
        fh.write(f"# Nested attribution, per seed (EUR000 real pot at retirement) | {hdr_meta} "
                 f"| seeds={ATTR_SEEDS} | post V-M3 bond-volatility recalibration\n")
        w = csv.DictWriter(fh, fieldnames=["step", "world", "seed", "level", "marginal_delta"])
        w.writeheader(); w.writerows(attr_rows)
    with open(out / f"{tag}_pot_distributions.csv", "w", newline="") as fh:
        fh.write(f"# Pot distribution percentiles per step/world/seed (EUR000) | {hdr_meta}\n")
        w = csv.DictWriter(fh, fieldnames=list(dist_rows[0].keys()))
        w.writeheader(); w.writerows(dist_rows)

    # ---- CGB dial -----------------------------------------------------------
    dial_rows = []
    for seed in DIAL_SEEDS:
        worlds = _worlds(seed, n, wy)
        for world, (paths, cpi) in worlds.items():
            zero = None
            for cw in DIAL_WEIGHTS:
                lhp = rc.lhp_specs_for(cw)
                rec = rc._LHPRecorder(lhp)
                with rec.capture():
                    res = mp._run_batch(paths, ra.cfg(ra.PROPOSED_EQUITY, lhp), seed_base=seed)
                pots = np.array([r.pot_path[wy] for r in res]) / cpi
                vol, rr = rec.stats(cpi, wy)
                med = float(np.percentile(pots, 50))
                zero = med if zero is None else zero
                dial_rows.append({"calibration": "reverting_1.8_to_2.3", "world": world, "seed": seed,
                                  "cgb_weight": cw, "median": round(med / 1e3, 3),
                                  "delta_vs_zero": round((med - zero) / 1e3, 3),
                                  **{f"p{q}": round(float(np.percentile(pots, q)) / 1e3, 3)
                                     for q in (5, 25, 75, 95)},
                                  "lhp_vol": round(float(vol), 6), "lhp_real_return": round(float(rr), 6)})
                print(f"[dial] seed {seed} {world:10s} w={cw:.0%} {med/1e3:8.1f}k "
                      f"Δ={(med-zero)/1e3:+.1f}k vol={vol:.2%}", flush=True)

    with open(out / f"{tag}_cgb_dial.csv", "w", newline="") as fh:
        fh.write(f"# CGB dial sweep, per seed (EUR000 real pot at retirement) | {hdr_meta} "
                 f"| seeds={DIAL_SEEDS} | post V-M3 bond-volatility recalibration\n")
        w = csv.DictWriter(fh, fieldnames=list(dial_rows[0].keys()))
        w.writeheader(); w.writerows(dial_rows)
    print("done", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1000,
         sys.argv[2] if len(sys.argv) > 2 else "vm3")
