"""
ALM Simulation — Participant Lifecycle Demo (Dutch WTP style)
=============================================================
Tracks performance against the Dutch pension fund ambition of ~70 %
of career-average (middelloon) pensionable pay.

Analytics produced
------------------
Base (500 scenarios × 65 years, death_age = 90)
  1. Replacement ratio distribution vs 70 % ambition
  2. Pension stability: cut frequency, average size, YoY vol
  3. Real purchasing power of pension (entry-year €)
  4. Pot path and nominal/real pension fan charts
  5. Annual adjustment factor fan chart

Extended analytics
  6. Pot exhaustion probability (P(pot = 0 before death_age))
  7. Longevity sensitivity — RR at death_age 90 / 95 / 100
  8. Cut recovery time — years to recover after a −3 % floor event
  9. Contribution rate sensitivity curve — P(RR < 70 %) vs contribution_rate
 10. Cohort vintage spread — P95 / P5 of RR (intergenerational fairness)
 11. Stress scenarios — stagflation and deflation lifecycle overlay

Run from the project root::

    python main_participant.py
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from scenarios.engine import (
    MacroState, VARParams, MacroScenarioEngine, StressScenario,
)
from participant.salary import SalaryProfile
from participant.lifecycle import (
    ParticipantConfig, LifecycleSimulator, ParticipantResult,
    default_cohort_allocations, RetirementOptions,
)
from assets.cash import CashSleeve
from assets.bonds import NominalBondSleeve, CreditBondSleeve
from assets.linkers import LinkerSleeve
from assets.growth import EquitySleeve, RealAssetSleeve, CommoditySleeve
from portfolio.portfolio import SleeveSpec


# ===========================================================================
# Configuration
# ===========================================================================

N_SCENARIOS    = 500
N_SCENARIOS_EX = 200   # extended / sensitivity analyses
SEED           = 42
ENTRY_AGE      = 25
RETIREMENT_AGE = 68
DEATH_AGE      = 90
N_STEPS        = DEATH_AGE - ENTRY_AGE         # 65 years for base run
N_STEPS_LONG   = 100 - ENTRY_AGE              # 75 years — covers death_age 100
AMBITION_RR    = 0.70


# ===========================================================================
# Building blocks
# ===========================================================================

def build_lhp_specs() -> list[SleeveSpec]:
    """Liability-hedging sub-portfolio — intra-LHP weights must sum to 1.0."""
    return [
        SleeveSpec(NominalBondSleeve("LongGovt", duration=20.0, maturity=25.0), weight=0.50),
        SleeveSpec(LinkerSleeve(     "ILG",       real_duration=18.0, maturity=22.0), weight=0.40),
        SleeveSpec(CashSleeve(       "LHPCash"),                                weight=0.10),
    ]


def build_rsp_specs() -> list[SleeveSpec]:
    """Return-seeking sub-portfolio — intra-RSP weights must sum to 1.0.

    Asset mix:
      50 % global equity    (MSCI World; currency exposures set via fx_exposures)
      25 % real assets      (infrastructure, RE; USD + minor exposure)
      15 % IG credit        (EUR-hedged; minimal FX)
      10 % commodities      (USD-priced; significant unhedged USD)

    FX exposures represent *unhedged* fractions after accounting for hedge ratio.
    Currency overlay is applied by the FXModel in SubPortfolio.step().
    """
    eq = EquitySleeve(
        "GlobalEquity",
        drift=0.07, growth_beta=0.60,
        inflation_beta=-0.30, idio_vol=0.15,
        seed=SEED + 1,
        cape=25.0, cape_fair=20.0,
        valuation_beta=0.05,
        long_run_earnings_growth=0.04,
    )
    # MSCI World: ~70 % USD, ~10 % GBP, ~7 % JPY gross; 50 % hedge on USD/GBP, leave JPY unhedged
    eq.fx_exposures = {"USD": 0.35, "GBP": 0.05, "JPY": 0.07, "CHF": 0.02,
                       "CNY": 0.03, "TWD": 0.01, "KRW": 0.01}

    ra = RealAssetSleeve(
        "RealAssets",
        growth_beta=0.30, inflation_beta=0.70, idio_vol=0.10,
        seed=SEED + 2,
        initial_cap_rate=0.055, risk_premium=0.010,
        cap_rate_reversion=0.20, implied_duration=15.0,
    )
    # Mostly EUR / global real assets; some unhedged USD from US RE / infra
    ra.fx_exposures = {"USD": 0.15}

    cr = CreditBondSleeve("IG_Credit", duration=7.0, maturity=8.0, seed=SEED + 4)
    # EUR-denominated credit; residual small unhedged USD
    cr.fx_exposures = {"USD": 0.05}

    co = CommoditySleeve(
        "Commodities",
        idio_vol=0.25, roll_yield=-0.010,
        geo_intensity=0.10, geo_jump_mean=0.08,
        seed=SEED + 3,
    )
    # Commodities priced in USD; no explicit hedge → significant unhedged USD
    co.fx_exposures = {"USD": 0.40}

    return [
        SleeveSpec(eq, weight=0.50),
        SleeveSpec(ra, weight=0.25),
        SleeveSpec(cr, weight=0.15),
        SleeveSpec(co, weight=0.10),
    ]


def build_initial_state() -> MacroState:
    return MacroState(
        short_rate    = 0.040,
        long_rate     = 0.045,
        real_rate     = 0.015,
        inflation     = 0.025,
        growth        = 0.025,
        credit_spread = 0.012,
        curvature     = 0.010,
    )


def build_scenario_engine(initial: MacroState, seed: int = SEED) -> MacroScenarioEngine:
    return MacroScenarioEngine(VARParams(), initial, dt=1.0, seed=seed)


def build_base_config() -> ParticipantConfig:
    return ParticipantConfig(
        entry_age      = ENTRY_AGE,
        retirement_age = RETIREMENT_AGE,
        death_age      = DEATH_AGE,
        contribution_rate = 0.20,
        salary_profile = SalaryProfile(
            base_salary     = 50_000,
            real_growth     = 0.005,
            promotion_jumps = {30: 0.15, 40: 0.20},
        ),
        cohort_allocations = default_cohort_allocations(),
        retirement_options = RetirementOptions(),
        lhp_specs = build_lhp_specs(),
        rsp_specs  = build_rsp_specs(),
        lambda_    = 5.0,
        adjustment_smoothing_years = 3,
        adjustment_floor           = -0.03,
        solidarity_reserve_rate    = 0.05,
    )


def _run_batch(paths: list, config: ParticipantConfig, seed_base: int = SEED) -> list[ParticipantResult]:
    """Run one LifecycleSimulator per path; each gets a distinct sleeve RNG seed."""
    sim = LifecycleSimulator(config)
    return [sim.run(path, run_seed=seed_base + i) for i, path in enumerate(paths)]


# ===========================================================================
# Analytics helpers
# ===========================================================================

def _pct(arr: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "p5":   np.percentile(arr, 5,  axis=0),
        "p25":  np.percentile(arr, 25, axis=0),
        "p50":  np.percentile(arr, 50, axis=0),
        "p75":  np.percentile(arr, 75, axis=0),
        "p95":  np.percentile(arr, 95, axis=0),
        "mean": arr.mean(axis=0),
    }


def pension_stability_stats(results: list[ParticipantResult]) -> dict:
    all_cuts:      list[float] = []
    all_increases: list[float] = []
    all_floor_hits: list[bool] = []
    per_scenario_vols: list[float] = []
    floor = 1.0 - 0.03

    for r in results:
        adj    = np.array(r.adjustment_path)
        pension = np.array(r.pension_path)
        cuts      = adj[adj < 1.0 - 1e-6]
        increases = adj[adj > 1.0 + 1e-6]
        all_cuts.extend((1.0 - cuts).tolist())
        all_increases.extend((increases - 1.0).tolist())
        all_floor_hits.extend((adj < floor + 1e-4).tolist())
        if len(pension) > 1:
            log_changes = np.diff(np.log(np.maximum(pension, 1.0)))
            per_scenario_vols.append(float(np.std(log_changes)))

    n_total = sum(len(r.adjustment_path) for r in results)
    n_any_cut = sum(any(a < 1.0 - 1e-6 for a in r.adjustment_path) for r in results)

    return {
        "pct_years_cut":         len(all_cuts) / n_total if n_total else 0.0,
        "pct_years_floor":       sum(all_floor_hits) / n_total if n_total else 0.0,
        "avg_cut_pct":           float(np.mean(all_cuts))      if all_cuts      else 0.0,
        "avg_increase_pct":      float(np.mean(all_increases)) if all_increases else 0.0,
        "pension_yoy_vol":       float(np.median(per_scenario_vols)) if per_scenario_vols else 0.0,
        "pct_scenarios_any_cut": n_any_cut / len(results) if results else 0.0,
    }


def pot_exhaustion_stats(results: list[ParticipantResult], retirement_age: int) -> dict:
    """Probability and timing of pot exhaustion."""
    exhausted = [r for r in results if r.pot_exhausted_at is not None]
    ages = [retirement_age + r.pot_exhausted_at for r in exhausted]
    return {
        "prob_exhaustion":     len(exhausted) / len(results),
        "median_exhaust_age":  float(np.median(ages)) if ages else None,
        "p5_exhaust_age":      float(np.percentile(ages, 5))  if ages else None,
        "p95_exhaust_age":     float(np.percentile(ages, 95)) if ages else None,
    }


def cut_recovery_stats(results: list[ParticipantResult]) -> dict:
    """Years to recover to pre-cut pension level after a −3 % floor event."""
    floor = 1.0 - 0.03
    recovery_times: list[int] = []
    never_recovered: int = 0

    for r in results:
        adj    = np.array(r.adjustment_path)
        pension = np.array(r.pension_path)
        i = 0
        while i < len(adj):
            if adj[i] <= floor + 1e-4:
                # Pension level just before the floor event
                pre_cut = pension[i - 1] if i > 0 else pension[0]
                j = i + 1
                while j < len(pension) and pension[j] < pre_cut * (1.0 - 1e-3):
                    j += 1
                if j < len(pension):
                    recovery_times.append(j - i)
                    i = j
                else:
                    never_recovered += 1
                    break
            else:
                i += 1

    total_events = len(recovery_times) + never_recovered
    return {
        "median_recovery_years": float(np.median(recovery_times)) if recovery_times else None,
        "p75_recovery_years":    float(np.percentile(recovery_times, 75)) if recovery_times else None,
        "pct_never_recovered":   never_recovered / total_events if total_events else 0.0,
        "n_events":              total_events,
    }


# ===========================================================================
# Plotting helpers
# ===========================================================================

def _save(fig: plt.Figure, path: str) -> None:
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved: {path}")


def plot_fan(
    x: np.ndarray,
    pct: dict[str, np.ndarray],
    ylabel: str,
    title: str,
    save_path: str,
    yscale: float = 1.0,
    yunit: str = "",
    vline: int | None = None,
    hline: float | None = None,
    hline_label: str = "",
    color: str = "steelblue",
) -> None:
    p = {k: v / yscale for k, v in pct.items()}
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.fill_between(x, p["p5"],  p["p95"], alpha=0.12, color=color, label="5th–95th %ile")
    ax.fill_between(x, p["p25"], p["p75"], alpha=0.28, color=color, label="25th–75th %ile")
    ax.plot(x, p["p50"],  color=color,       lw=2.2, label="Median")
    ax.plot(x, p["mean"], color="darkorange", lw=1.6, linestyle="--", label="Mean")
    if vline is not None:
        ax.axvline(vline, color="red", lw=1.2, ls=":", label=f"Retirement (age {vline})")
    if hline is not None:
        ax.axhline(hline / yscale, color="green", lw=1.4, ls="--", label=hline_label)
    ax.set_xlabel("Age", fontsize=12)
    ax.set_ylabel(f"{ylabel}{' (' + yunit + ')' if yunit else ''}", fontsize=12)
    ax.set_title(title, fontsize=13)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save(fig, save_path)


def plot_replacement_ratio_dist(
    rr: np.ndarray,
    ambition: float,
    title: str,
    save_path: str,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    bins = np.linspace(0, max(rr.max() * 1.05, ambition * 2.5), 60)
    ax.hist(rr, bins=bins, color="steelblue", edgecolor="white", alpha=0.85, label="Simulated RR")
    ax.axvline(ambition, color="green", lw=2.0, ls="--", label=f"Ambition ({ambition:.0%})")
    ax.axvspan(0, ambition, alpha=0.08, color="red", label="Below ambition")
    pct_below = (rr < ambition).mean()
    ymax = ax.get_ylim()[1]
    ax.text(ambition * 0.02, ymax * 0.85,
            f"P(RR < {ambition:.0%}) = {pct_below:.1%}", color="red", fontsize=10)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.set_xlabel("Replacement ratio (pension / career-average salary)", fontsize=12)
    ax.set_ylabel("Scenarios", fontsize=12)
    ax.set_title(title, fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    _save(fig, save_path)


def plot_adj_factor_fan(
    ages: np.ndarray,
    adj_matrix: np.ndarray,
    save_path: str,
) -> None:
    pct = _pct(adj_matrix)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.fill_between(ages, pct["p5"],  pct["p95"], alpha=0.12, color="darkorange",
                    label="5th–95th %ile")
    ax.fill_between(ages, pct["p25"], pct["p75"], alpha=0.28, color="darkorange",
                    label="25th–75th %ile")
    ax.plot(ages, pct["p50"], color="darkorange", lw=2.2, label="Median")
    ax.axhline(1.0,        color="grey", lw=1.0, ls="--", label="No change")
    ax.axhline(1.0 - 0.03, color="red",  lw=1.2, ls=":",  label="−3% floor")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.set_xlabel("Age", fontsize=12)
    ax.set_ylabel("Annual adjustment factor", fontsize=12)
    ax.set_title("Pension adjustment fan chart (variabel pensioen)", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save(fig, ax.get_figure().get_label() if False else save_path)


def plot_contribution_sensitivity(
    rates: list[float],
    shortfall_probs: list[float],
    base_rate: float,
    save_path: str,
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot([r * 100 for r in rates], [p * 100 for p in shortfall_probs],
            "o-", color="steelblue", lw=2.0, ms=7)
    ax.axhline(5.0,  color="green", lw=1.2, ls="--", label="5 % shortfall threshold")
    ax.axhline(10.0, color="orange", lw=1.2, ls="--", label="10 % shortfall threshold")
    ax.axvline(base_rate * 100, color="red", lw=1.2, ls=":", label=f"Base rate ({base_rate:.0%})")
    ax.set_xlabel("Contribution rate (%)", fontsize=12)
    ax.set_ylabel("P(RR < 70%) (%)", fontsize=12)
    ax.set_title("Contribution rate sensitivity — shortfall probability vs 70% ambition", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save(fig, save_path)


def plot_longevity_rr(
    rrs_by_age: dict[int, np.ndarray],
    ambition: float,
    save_path: str,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = {90: "steelblue", 95: "darkorange", 100: "crimson"}
    for death_age, rr in sorted(rrs_by_age.items()):
        color = colors.get(death_age, "grey")
        ax.hist(rr, bins=50, alpha=0.40, color=color, edgecolor="white",
                label=f"death_age={death_age}  median={np.median(rr):.0%}")
    ax.axvline(ambition, color="green", lw=2.0, ls="--", label=f"Ambition ({ambition:.0%})")
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.set_xlabel("Replacement ratio", fontsize=12)
    ax.set_ylabel("Scenarios", fontsize=12)
    ax.set_title("Longevity sensitivity — replacement ratio at death ages 90 / 95 / 100", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    _save(fig, save_path)


def plot_stress_overlay(
    ages_ret: np.ndarray,
    base_pct:      dict[str, np.ndarray],
    stress_medians: dict[str, np.ndarray],
    save_path: str,
) -> None:
    """Nominal pension fan chart with stress scenario median overlays."""
    fig, ax = plt.subplots(figsize=(12, 6))
    p = {k: v / 1e3 for k, v in base_pct.items()}
    ax.fill_between(ages_ret, p["p5"],  p["p95"], alpha=0.10, color="steelblue")
    ax.fill_between(ages_ret, p["p25"], p["p75"], alpha=0.25, color="steelblue")
    ax.plot(ages_ret, p["p50"], color="steelblue", lw=2.0, label="Base median")

    colors = {"stagflation": "crimson", "deflation": "purple"}
    for name, median_path in stress_medians.items():
        ax.plot(ages_ret, median_path / 1e3, lw=2.0, ls="--",
                color=colors.get(name, "grey"), label=f"{name} median")

    ax.set_xlabel("Age", fontsize=12)
    ax.set_ylabel("Annual pension (€k)", fontsize=12)
    ax.set_title("Stress scenario overlay — nominal pension during decumulation", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save(fig, save_path)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    initial = build_initial_state()
    engine  = build_scenario_engine(initial)
    config  = build_base_config()

    print(f"\n{'='*60}")
    print(f"PARTICIPANT LIFECYCLE — {N_SCENARIOS} scenarios × {N_STEPS} years")
    print(f"  Entry: {ENTRY_AGE}  |  Retirement: {RETIREMENT_AGE}  |  Death: {DEATH_AGE}")
    print(f"  Contribution rate : {config.contribution_rate:.0%}")
    print(f"  Ambition          : {AMBITION_RR:.0%} of career-average salary (middelloon)")
    print(f"{'='*60}")

    # -----------------------------------------------------------------------
    # BASE RUN — 500 scenarios × 65 years
    # -----------------------------------------------------------------------
    paths   = engine.simulate(n_steps=N_STEPS, n_scenarios=N_SCENARIOS)
    results = _run_batch(paths, config)

    rr             = np.array([r.replacement_ratio     for r in results])
    pension_at_ret = np.array([r.pension_at_retirement for r in results])
    career_avg_sal = np.array([r.career_avg_salary     for r in results])

    # -----------------------------------------------------------------------
    # 1. Replacement ratio vs ambition
    # -----------------------------------------------------------------------
    print(f"\n── 1. REPLACEMENT RATIO (pension / career-average salary, middelloon) ──")
    for p in [5, 25, 50, 75, 95]:
        print(f"  {p:3d}th pct : {np.percentile(rr, p):.1%}")
    print(f"  Mean     : {rr.mean():.1%}")
    print(f"\n  Shortfall probabilities:")
    for thresh in [0.50, 0.60, AMBITION_RR, 0.80]:
        tag = " ← ambition" if thresh == AMBITION_RR else ""
        print(f"    P(RR < {thresh:.0%}) : {(rr < thresh).mean():.1%}{tag}")
    print(f"\n  Median career-average salary : €{np.median(career_avg_sal):>10,.0f}")
    print(f"  Median pension at retirement : €{np.median(pension_at_ret):>10,.0f}")

    # 10. Cohort vintage spread (intergenerational fairness)
    p95, p5 = np.percentile(rr, 95), np.percentile(rr, 5)
    print(f"\n── 10. COHORT VINTAGE SPREAD ──")
    print(f"  P95 / P5 of RR : {p95:.1%} / {p5:.1%}  → spread ratio {p95/p5:.1f}×")
    print(f"  Inter-quartile : {np.percentile(rr,75):.1%} / {np.percentile(rr,25):.1%}")

    # -----------------------------------------------------------------------
    # 2. Stability
    # -----------------------------------------------------------------------
    stab = pension_stability_stats(results)
    print(f"\n── 2. PENSION STABILITY ──")
    print(f"  Years with cut          : {stab['pct_years_cut']:.1%}")
    print(f"  Years at −3% floor      : {stab['pct_years_floor']:.1%}")
    print(f"  Avg cut (if cut)        : {stab['avg_cut_pct']:.2%}")
    print(f"  Avg increase (if up)    : {stab['avg_increase_pct']:.2%}")
    print(f"  Scenarios with any cut  : {stab['pct_scenarios_any_cut']:.1%}")
    print(f"  YoY pension vol (median): {stab['pension_yoy_vol']:.2%}")

    # 8. Cut recovery time
    crec = cut_recovery_stats(results)
    print(f"\n── 8. CUT RECOVERY TIME ──")
    print(f"  Total floor events     : {crec['n_events']}")
    if crec['median_recovery_years'] is not None:
        print(f"  Median recovery        : {crec['median_recovery_years']:.0f} years")
        print(f"  75th pct recovery      : {crec['p75_recovery_years']:.0f} years")
    print(f"  Never recovered        : {crec['pct_never_recovered']:.1%} of events")

    # -----------------------------------------------------------------------
    # 3. Real purchasing power
    # -----------------------------------------------------------------------
    real_pen_matrix = np.array([r.real_pension_path for r in results]) / 1e3
    ages_ret        = np.arange(RETIREMENT_AGE + 1, DEATH_AGE + 1)
    print(f"\n── 3. REAL PURCHASING POWER (entry-year €) ──")
    for check_age in [RETIREMENT_AGE + 1, 75, 80, 85, DEATH_AGE]:
        idx = check_age - RETIREMENT_AGE - 1
        if 0 <= idx < real_pen_matrix.shape[1]:
            print(f"  Age {check_age}: €{np.median(real_pen_matrix[:, idx]):>6.1f}k")

    # -----------------------------------------------------------------------
    # 6. Pot exhaustion probability
    # -----------------------------------------------------------------------
    exh = pot_exhaustion_stats(results, RETIREMENT_AGE)
    print(f"\n── 6. POT EXHAUSTION PROBABILITY ──")
    print(f"  P(pot exhausted before age {DEATH_AGE}) : {exh['prob_exhaustion']:.1%}")
    if exh['median_exhaust_age'] is not None:
        print(f"  Median exhaustion age            : {exh['median_exhaust_age']:.0f}")
        print(f"  5th–95th pct exhaust age         : {exh['p5_exhaust_age']:.0f}–{exh['p95_exhaust_age']:.0f}")

    # -----------------------------------------------------------------------
    # 9. Contribution rate sensitivity
    # -----------------------------------------------------------------------
    print(f"\n── 9. CONTRIBUTION RATE SENSITIVITY (using base {N_SCENARIOS} paths) ──")
    contrib_rates  = [0.10, 0.13, 0.16, 0.18, 0.20, 0.22, 0.25]
    shortfall_probs: list[float] = []
    for rate in contrib_rates:
        cfg_r   = replace(config, contribution_rate=rate)
        res_r   = _run_batch(paths, cfg_r, seed_base=SEED + 1000)
        rr_r    = np.array([r.replacement_ratio for r in res_r])
        sp      = float((rr_r < AMBITION_RR).mean())
        shortfall_probs.append(sp)
        print(f"  Rate {rate:.0%}  →  P(RR < 70%) = {sp:.1%}")

    # -----------------------------------------------------------------------
    # 7. Longevity sensitivity (200 scenarios × 75 years)
    # -----------------------------------------------------------------------
    print(f"\n── 7. LONGEVITY SENSITIVITY (death_age = 90 / 95 / 100) ──")
    paths_long = engine.simulate(n_steps=N_STEPS_LONG, n_scenarios=N_SCENARIOS_EX)
    rrs_by_age: dict[int, np.ndarray] = {}
    for da in [90, 95, 100]:
        cfg_da = replace(config, death_age=da)
        res_da = _run_batch(paths_long, cfg_da, seed_base=SEED + 2000)
        rr_da  = np.array([r.replacement_ratio for r in res_da])
        rrs_by_age[da] = rr_da
        print(f"  death_age={da}:  median RR = {np.median(rr_da):.1%}  "
              f"P(RR<70%) = {(rr_da < 0.70).mean():.1%}  "
              f"P(exhausted) = {sum(r.pot_exhausted_at is not None for r in res_da)/len(res_da):.1%}")

    # -----------------------------------------------------------------------
    # 11. Stress scenarios (200 scenarios per stress, same RSP noise)
    # -----------------------------------------------------------------------
    print(f"\n── 11. STRESS SCENARIOS ──")
    stress_medians: dict[str, np.ndarray] = {}
    stress_defs = {
        "stagflation": StressScenario.stagflation(initial, N_STEPS),
        "deflation":   StressScenario.deflation(initial,   N_STEPS),
    }
    for stress_name, stress in stress_defs.items():
        stress_path = stress.states   # list[MacroState], length = N_STEPS + 1
        sim_stress  = LifecycleSimulator(config)
        res_stress  = [
            sim_stress.run(stress_path, run_seed=SEED + 3000 + i)
            for i in range(N_SCENARIOS_EX)
        ]
        rr_stress    = np.array([r.replacement_ratio for r in res_stress])
        pension_mat  = np.array([r.pension_path for r in res_stress])
        stress_medians[stress_name] = np.median(pension_mat, axis=0)
        exh_s = sum(r.pot_exhausted_at is not None for r in res_stress) / len(res_stress)
        print(f"  {stress_name:12s}:  median RR = {np.median(rr_stress):.1%}  "
              f"P(RR<70%) = {(rr_stress < 0.70).mean():.1%}  "
              f"P(exhausted) = {exh_s:.1%}")

    # -----------------------------------------------------------------------
    # Charts
    # -----------------------------------------------------------------------
    ages_all   = np.arange(ENTRY_AGE, DEATH_AGE + 1)
    pot_matrix = np.array([r.pot_path[:N_STEPS + 1] for r in results])

    plot_fan(ages_all, _pct(pot_matrix),
             ylabel="Pension pot", yunit="€M", yscale=1e6,
             title="Individual Participant — Pension Pot Fan Chart",
             save_path="participant_pot_fan_chart.png", vline=RETIREMENT_AGE)

    pension_matrix = np.array([r.pension_path for r in results])
    plot_fan(ages_ret, _pct(pension_matrix),
             ylabel="Annual pension", yunit="€k", yscale=1e3,
             title="Individual Participant — Nominal Pension Fan Chart",
             save_path="participant_pension_fan_chart.png")

    pct_real = _pct(real_pen_matrix)
    plot_fan(ages_ret, pct_real,
             ylabel="Real pension (entry-year €)", yunit="€k", yscale=1.0,
             title="Individual Participant — Real Pension Fan Chart (entry-year €)",
             save_path="participant_real_pension_fan_chart.png",
             hline=float(np.median(real_pen_matrix[:, 0])),
             hline_label="Real pension at retirement (median)")

    plot_replacement_ratio_dist(rr, AMBITION_RR,
                                title="Replacement ratio distribution vs 70% ambition",
                                save_path="participant_replacement_ratio.png")

    adj_matrix = np.array([r.adjustment_path for r in results])
    plot_adj_factor_fan(ages_ret, adj_matrix, "participant_adj_factor_fan.png")

    plot_contribution_sensitivity(contrib_rates, shortfall_probs,
                                  base_rate=config.contribution_rate,
                                  save_path="participant_contribution_sensitivity.png")

    plot_longevity_rr(rrs_by_age, AMBITION_RR,
                      save_path="participant_longevity_rr.png")

    plot_stress_overlay(ages_ret, _pct(pension_matrix), stress_medians,
                        save_path="participant_stress_overlay.png")

    plt.show()


if __name__ == "__main__":
    main()
