"""
ALM Simulation — Fund-Level Demo
==================================
Demonstrates the full fund-level pipeline:

  1.  MacroScenarioEngine  — VAR(1) generates 1 000 correlated macro paths.
  2.  LiabilityModel       — 30-year blended (60% CPI-linked) annuity liability.
  3.  Portfolio            — LHP (long bonds + linkers) + RSP (equity + real assets).
                            hedge_ratio = 60 % in LHP, 40 % in RSP.
  4.  FXModel              — currency overlay on RSP sleeves (13 currencies, EUR base).
  5.  SimulationEngine     — evolves portfolio and liability through each path.
  6.  Analytics            — fan chart of funding ratio + stress scenario comparison.

Run from the project root::

    MPLBACKEND=Agg python -u main.py

Output
------
  - Console: liability stats, funding ratio at years 5, 10, 20, stress results.
  - funding_ratio_fan_chart.png
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from scenarios.engine import (
    MacroState, VARParams, MacroScenarioEngine, StressScenario,
)
from liabilities.model import LiabilitySchedule, LiabilityModel
from assets.cash import CashSleeve
from assets.bonds import NominalBondSleeve, CreditBondSleeve
from assets.linkers import LinkerSleeve
from assets.growth import EquitySleeve, RealAssetSleeve, CommoditySleeve
from assets.fx import FXModel
from portfolio.portfolio import Portfolio, SleeveSpec
from simulation.engine import SimulationEngine
from analytics.metrics import (
    funding_ratio_stats, fan_chart_data, compute_var_cvar, period_return_stats,
)


# ===========================================================================
# Configuration
# ===========================================================================

N_SCENARIOS      = 1_000
N_STEPS          = 20            # annual steps
INITIAL_FUND     = 180_000_000   # €180 M starting portfolio value
HEDGE_RATIO      = 0.60          # 60 % LHP, 40 % RSP
SEED             = 42


# ===========================================================================
# Building blocks
# ===========================================================================

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
    params = VARParams()
    return MacroScenarioEngine(params, initial, dt=1.0, seed=seed)


def build_liability() -> LiabilityModel:
    """30-year blended annuity: €10 M/yr, 60 % CPI-linked, 40 % nominal."""
    schedule = LiabilitySchedule.blended_annuity(
        annual_payment = 10_000_000,
        n_years        = 30,
        real_fraction  = 0.60,
    )
    return LiabilityModel(schedule, lambda_=5.0)


def build_lhp_specs() -> list[SleeveSpec]:
    """LHP: 50 % long nominal govts, 40 % ILGs, 10 % cash."""
    return [
        SleeveSpec(NominalBondSleeve("LongGovt", duration=20.0, maturity=25.0), weight=0.50),
        SleeveSpec(LinkerSleeve(     "ILG",       real_duration=18.0, maturity=22.0), weight=0.40),
        SleeveSpec(CashSleeve(       "LHPCash"),                                      weight=0.10),
    ]


def build_rsp_specs() -> list[SleeveSpec]:
    """RSP: 50 % global equity, 25 % real assets, 15 % IG credit, 10 % commodities.

    FX exposures represent *unhedged* fractions after hedge ratio.
    The FXModel overlay is applied by SubPortfolio; LHP has no FX exposure.
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
    # MSCI World: ~70 % USD, ~10 % GBP, ~7 % JPY gross; 50 % hedge on USD/GBP
    eq.fx_exposures = {"USD": 0.35, "GBP": 0.05, "JPY": 0.07, "CHF": 0.02,
                       "CNY": 0.03, "TWD": 0.01, "KRW": 0.01}

    ra = RealAssetSleeve(
        "RealAssets",
        growth_beta=0.30, inflation_beta=0.70, idio_vol=0.10,
        seed=SEED + 2,
        initial_cap_rate=0.055, risk_premium=0.010,
        cap_rate_reversion=0.20, implied_duration=15.0,
    )
    ra.fx_exposures = {"USD": 0.15}

    cr = CreditBondSleeve("IG_Credit", duration=7.0, maturity=8.0, seed=SEED + 4)
    cr.fx_exposures = {"USD": 0.05}

    co = CommoditySleeve(
        "Commodities",
        idio_vol=0.25, roll_yield=-0.010,
        geo_intensity=0.10, geo_jump_mean=0.08,
        seed=SEED + 3,
    )
    co.fx_exposures = {"USD": 0.40}

    return [
        SleeveSpec(eq, weight=0.50),
        SleeveSpec(ra, weight=0.25),
        SleeveSpec(cr, weight=0.15),
        SleeveSpec(co, weight=0.10),
    ]


def make_portfolio_factory(base_seed: int = SEED):
    """Return a factory callable that produces a fresh Portfolio per scenario.

    Each call increments an internal counter so the FXModel gets a unique seed,
    giving each scenario its own independent FX idiosyncratic draws while keeping
    the simulation fully reproducible given the same base_seed.
    """
    _count = [0]

    def _factory() -> Portfolio:
        fx_model = FXModel.default(seed=base_seed + 1_000 + _count[0])
        _count[0] += 1
        return Portfolio(
            lhp_specs           = build_lhp_specs(),
            rsp_specs           = build_rsp_specs(),
            initial_value       = INITIAL_FUND,
            hedge_ratio         = HEDGE_RATIO,
            rebalance_frequency = 1,
            fx_model            = fx_model,
        )

    return _factory


# ===========================================================================
# Plotting
# ===========================================================================

def plot_fan_chart(
    fan,
    stress_paths: dict[str, list[float]] | None = None,
    title: str = "Funding Ratio — Monte Carlo Fan Chart",
    save_path: str = "funding_ratio_fan_chart.png",
) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.fill_between(fan["step"], fan["p5"],  fan["p95"], alpha=0.12,
                    color="steelblue", label="5th–95th percentile")
    ax.fill_between(fan["step"], fan["p25"], fan["p75"], alpha=0.28,
                    color="steelblue", label="25th–75th percentile")
    ax.plot(fan["step"], fan["p50"],  color="steelblue", lw=2.2, label="Median")
    ax.plot(fan["step"], fan["mean"], color="darkorange", lw=1.6,
            linestyle="--", label="Mean")

    if stress_paths:
        colors = ["crimson", "darkgreen", "purple"]
        for (name, path), col in zip(stress_paths.items(), colors):
            ax.plot(range(len(path)), path, lw=1.8, linestyle=":", color=col, label=name)

    ax.axhline(1.0, color="red", lw=1.2, ls=":", label="Fully funded (FR = 1)")
    ax.set_xlabel("Year",          fontsize=12)
    ax.set_ylabel("Funding Ratio", fontsize=12)
    ax.set_title(title,            fontsize=13)
    ax.legend(loc="upper left",    fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, fan["step"].max())
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {save_path}")


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    import pandas as pd

    initial = build_initial_state()

    # -----------------------------------------------------------------------
    # 1. Liability
    # -----------------------------------------------------------------------
    liability = build_liability()
    pv0       = liability.present_value(initial)
    dur       = liability.duration(initial)
    inf_sens  = liability.inflation_pv01(initial)

    print(f"\n{'='*60}")
    print("LIABILITY")
    print(f"{'='*60}")
    print(f"  Initial PV           : €{pv0:>15,.0f}")
    print(f"  Implied duration     : {dur:.1f} years")
    print(f"  Inflation PV01       : {inf_sens:.4f}  (% PV per 1 bp)")
    print(f"  Initial fund value   : €{INITIAL_FUND:>15,.0f}")
    print(f"  Initial funding ratio: {INITIAL_FUND / pv0:.2%}")

    # -----------------------------------------------------------------------
    # 2. Stochastic simulation
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"SIMULATION: {N_SCENARIOS} scenarios × {N_STEPS} years")
    print(f"{'='*60}")

    engine = build_scenario_engine(initial)
    paths  = engine.simulate(n_steps=N_STEPS, n_scenarios=N_SCENARIOS)

    sim = SimulationEngine(
        liability_model   = liability,
        portfolio_factory = make_portfolio_factory(SEED),
        dt                = 1.0,
    )
    results = sim.run_all(paths, verbose=True)

    for yr in [5, 10, 20]:
        print(f"\n{funding_ratio_stats(results, step=yr)}")
        var, cvar = compute_var_cvar(results, step=yr, confidence=0.95)
        print(f"  VaR(95%) FR        : {var:.2%}")
        print(f"  CVaR(95%) FR       : {cvar:.2%}")

    print("\nPeriod-return summary (all scenarios, all steps):")
    print(period_return_stats(results).to_string(index=False))

    # -----------------------------------------------------------------------
    # 3. Stress scenarios
    # -----------------------------------------------------------------------
    stress_scenarios = [
        StressScenario.parallel_rate_shock(initial, N_STEPS, shock_bps=200),
        StressScenario.stagflation(initial, N_STEPS),
        StressScenario.deflation(initial, N_STEPS),
    ]

    stress_sim = SimulationEngine(
        liability_model   = liability,
        portfolio_factory = make_portfolio_factory(SEED + 9_000),
        dt                = 1.0,
    )

    stress_fr_paths: dict[str, list[float]] = {}
    print(f"\n{'='*60}")
    print("STRESS SCENARIOS")
    print(f"{'='*60}")
    for stress in stress_scenarios:
        r = stress_sim.run_stress(stress)
        stress_fr_paths[stress.name] = r.funding_ratios
        print(f"\n  {stress.name}")
        print(f"    FR after  1yr : {r.funding_ratios[1]:.2%}")
        print(f"    FR after  5yr : {r.funding_ratios[5]:.2%}")
        print(f"    FR after 20yr : {r.funding_ratios[-1]:.2%}")

    # -----------------------------------------------------------------------
    # 4. Plot
    # -----------------------------------------------------------------------
    fan = fan_chart_data(results)
    plot_fan_chart(fan, stress_paths=stress_fr_paths)

    try:
        plt.show()
    except Exception:
        pass


if __name__ == "__main__":
    main()
