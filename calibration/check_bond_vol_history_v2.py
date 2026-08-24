"""V-M3 provenance check, v2 — realised annual-change volatility of long euro yields.

Reads the round-2 Bloomberg pull workbook (tab `Bund_yields`) and recomputes the
statistics the sheet shows, independently, so the provenance line in
docs/INPUT_PROVENANCE.md rests on committed data and a committed script rather
than on a spreadsheet cell. The independent out-of-repo recomputation of the
same figures is committed alongside as calibration/vm3_fx2_verification_2026-08-24.md.

v2 differences from check_bond_vol_history.py (23 Aug chat download, never
committed): the v2 workbook stores each ticker as its own (date, value) BDH pair
— 10y in A/B, 30y in D/E, IG OAS in G/H, real 10y linker in J/K — instead of one
shared date column; OAS is stored in percentage points, not bp; the gap-ridden
linker series is differenced only across consecutive-year pairs; and the two
secondary series are printed as recorded observations, not adjudicated (V-M3's
pre-registered band covers the 30y only).

Usage:  python calibration/check_bond_vol_history_v2.py \
            calibration/data/bloomberg_pull_VM3_and_FX2_v2_2026-08-24.xlsx

Pass criterion (set 2026-08-22 with the recalibration, before any data was
seen): sd of year-end-to-year-end changes in the 30y Bund yield within 60-80bp.
The model's `long_rate` innovation is 70bp, giving an analytic annual-change sd
of 73bp for the level factor and 69bp for the 25y yield.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_LONG_RATE_CHANGE_SD_BP = 73   # from (Phi, Sigma) at commit 8f01503
MODEL_REAL_RATE_INNOV_BP = 65
MODEL_SPREAD_CHANGE_SD_BP = 49      # 45bp innovation at phi = 0.65
BAND_30Y = (60, 80)
NEAR_BOUNDARY_BP = 1.0              # flag a pass this close to a band edge

# (date column, value column) per series, 0-indexed; data starts on sheet row 4.
PAIRS = {"10y": (0, 1), "30y": (3, 4), "oas": (6, 7), "real": (9, 10)}


def load(path: str) -> dict[str, pd.Series]:
    raw = pd.read_excel(path, sheet_name="Bund_yields", header=None, skiprows=3)
    out = {}
    for name, (dc, vc) in PAIRS.items():
        dates = pd.to_datetime(raw.iloc[:, dc], errors="coerce")
        vals = pd.to_numeric(raw.iloc[:, vc], errors="coerce")
        s = pd.Series(vals.values, index=dates).dropna().sort_index()
        out[name] = s[~s.index.duplicated()]
    return out


def sd_annual_changes(s: pd.Series, bp_mult: float,
                      exclude_years: tuple[int, ...] = (),
                      consecutive_only: bool = False) -> tuple[float, int]:
    """sd of year-on-year changes in bp; change indexed by the later year-end."""
    d = (s.diff() * bp_mult).dropna()
    if consecutive_only:
        year_gap = pd.Series(s.index.year, index=s.index).diff().reindex(d.index)
        d = d[year_gap == 1]
    d = d[~d.index.year.isin(exclude_years)]
    return (float(d.std(ddof=1)), int(len(d))) if len(d) >= 3 else (float("nan"), int(len(d)))


def main(path: str) -> int:
    s = load(path)
    rows = [
        ("10y Bund, incl. 2022", *sd_annual_changes(s["10y"], 100), "noted band 70-95 (not pre-registered)"),
        ("10y Bund, excl. 2022", *sd_annual_changes(s["10y"], 100, (2022,)), "—"),
        ("30y Bund, incl. 2022", *sd_annual_changes(s["30y"], 100),
         f"model {MODEL_LONG_RATE_CHANGE_SD_BP}bp; PRE-REGISTERED band {BAND_30Y[0]}-{BAND_30Y[1]}"),
        ("30y Bund, excl. 2022", *sd_annual_changes(s["30y"], 100, (2022,)), "—"),
        # Secondary observations: recorded, not adjudicated. No band was
        # pre-registered for either; V-M3 closed on the long rate.
        ("IG OAS (pp -> bp)", *sd_annual_changes(s["oas"], 100),
         f"model annual-change ~{MODEL_SPREAD_CHANGE_SD_BP}bp (observation)"),
        ("IG OAS, ex-2008-09", *sd_annual_changes(s["oas"], 100, (2008, 2009)), "—"),
        ("10y real, consec. pairs", *sd_annual_changes(s["real"], 100, consecutive_only=True),
         f"model innovation {MODEL_REAL_RATE_INNOV_BP}bp (observation; gap-ridden series)"),
    ]
    print(f"{'series':26s}{'sd (bp)':>9s}{'n':>5s}   comparison")
    for name, sd, n, cmp in rows:
        print(f"{name:26s}{sd:9.2f}{n:5d}   {cmp}")

    sd30, _ = sd_annual_changes(s["30y"], 100)
    sd30x, _ = sd_annual_changes(s["30y"], 100, (2022,))
    ok = BAND_30Y[0] <= sd30 <= BAND_30Y[1]
    near = min(sd30 - BAND_30Y[0], BAND_30Y[1] - sd30)
    print()
    print("VERDICT:", "PASS — long_rate 70bp innovation is sourced" if ok
          else f"REVISIT — 30y annual-change sd {sd30:.2f}bp outside {BAND_30Y}")
    if ok and near <= NEAR_BOUNDARY_BP:
        print(f"  (near-boundary: {near:.2f}bp inside the band edge — a pass, recorded as such)")
    print()
    print("Provenance line for docs/INPUT_PROVENANCE.md:")
    yrs = s["30y"].index.year
    print(f"  long_rate | 0.0070 | Sourced: sd of year-end changes in GDBR30 Index "
          f"{yrs.min()}-{yrs.max()} = {sd30:.2f}bp incl-2022 / {sd30x:.2f}bp excl-2022, "
          f"pre-registered band {BAND_30Y[0]}-{BAND_30Y[1]}bp "
          f"(10y {sd_annual_changes(s['10y'], 100)[0]:.2f}bp); file {Path(path).name}, "
          f"script calibration/check_bond_vol_history_v2.py")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else
                  "calibration/data/bloomberg_pull_VM3_and_FX2_v2_2026-08-24.xlsx"))
