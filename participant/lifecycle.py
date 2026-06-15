"""
participant/lifecycle.py — Dutch WTP-style individual participant lifecycle model.

Design
------
Each participant is simulated through a single macro path produced by
MacroScenarioEngine (or RegimeSwitchingEngine).  The lifecycle is split into:

  Accumulation (entry → retirement_age):
    - Annual contribution = contribution_rate × nominal_salary
    - Pot grows at the cohort return, which is a levered blend of RSP and LHP returns
    - RSP and LHP returns come from the actual asset sleeve models (EquitySleeve, etc.)
    - Leverage cost = leverage_fraction × short_rate × dt  (deducted each period)

  Decumulation (retirement_age → death_age):
    - Pot is (partially) converted to variabel pensioen at retirement
    - Annual pension = pot / annuity_factor(age, yield_curve)
    - Actual pension is adjusted annually: compare target vs actual, smooth over 3 years
    - Adjustment floored at -3 % p.a., no explicit cap (upside shared with solidarity pool)

Cohort allocation table (Dutch WTP-style, 10-year age bands, actual asset weights):

  Age band   RSP %   LHP %   Total %   Leverage %
  25–34      120     0       120       20
  35–44      100     0       100        0
  45–54       80     20      100        0
  55–64       70     30      100        0
  65–74       50     50      100        0
  75–84       20     80      100        0
  85–94       20     80      100        0
  95–104      20     80      100        0

At-retirement options (stubs — values default to no adjustment):
  - lump_sum_fraction   : fraction of pot taken as cash at retirement (0–1)
  - high_low_option     : high-then-low pension conversion (bool placeholder)
  - partner_exchange_fraction : fraction exchanged for partner's pension

Usage::

    from scenarios.engine import MacroScenarioEngine, MacroState, VARParams, YieldCurve
    from participant.salary import SalaryProfile
    from participant.lifecycle import ParticipantConfig, LifecycleSimulator, default_cohort_allocations

    config = ParticipantConfig(
        entry_age=25, retirement_age=68, death_age=90,
        lhp_specs=build_lhp_specs(), rsp_specs=build_rsp_specs(),
    )
    sim = LifecycleSimulator(config)
    path = engine.simulate(n_steps=65, n_scenarios=1)[0]   # single path
    result = sim.run(path)
    print(result.final_pot, result.pension_at_retirement)
"""

from __future__ import annotations

import copy
import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from scenarios.engine import MacroState, YieldCurve
from participant.salary import SalaryProfile
from portfolio.portfolio import SubPortfolio, SleeveSpec
from assets.fx import FXModel


# ---------------------------------------------------------------------------
# Cohort allocation
# ---------------------------------------------------------------------------

@dataclass
class CohortAllocation:
    """Return and LHP weights for one 10-year age band.

    All fractions are expressed as decimals (e.g. 1.20 = 120%).
    leverage_fraction = rsp_fraction + lhp_fraction - 1.0  (if > 0).
    """

    age_from: int
    age_to:   int
    rsp_fraction: float   # e.g. 1.20
    lhp_fraction: float   # e.g. 0.00


    @property
    def leverage_fraction(self) -> float:
        return max(0.0, self.rsp_fraction + self.lhp_fraction - 1.0)


def default_cohort_allocations() -> list[CohortAllocation]:
    """Return the Dutch-WTP asset-weight glide path.

    Weights are actual portfolio asset weights.  LHP = max(0, 100% − RSP) so
    allocations sum to 100% except in the 25–34 band (120% RSP → 20% leverage).
    """
    return [
        CohortAllocation(25, 34,  rsp_fraction=1.20, lhp_fraction=0.00),
        CohortAllocation(35, 44,  rsp_fraction=1.00, lhp_fraction=0.00),
        CohortAllocation(45, 54,  rsp_fraction=0.80, lhp_fraction=0.20),
        CohortAllocation(55, 64,  rsp_fraction=0.70, lhp_fraction=0.30),
        CohortAllocation(65, 74,  rsp_fraction=0.50, lhp_fraction=0.50),
        CohortAllocation(75, 84,  rsp_fraction=0.20, lhp_fraction=0.80),
        CohortAllocation(85, 94,  rsp_fraction=0.20, lhp_fraction=0.80),
        CohortAllocation(95, 104, rsp_fraction=0.20, lhp_fraction=0.80),
    ]


def _cohort_for_age(age: int, cohorts: list[CohortAllocation]) -> CohortAllocation:
    for c in cohorts:
        if c.age_from <= age <= c.age_to:
            return c
    return cohorts[-1]   # clamp to oldest band


# ---------------------------------------------------------------------------
# At-retirement options (placeholders)
# ---------------------------------------------------------------------------

@dataclass
class RetirementOptions:
    """At-retirement conversion choices — all default to neutral (no adjustment)."""

    lump_sum_fraction: float = 0.0
    """Fraction of pot taken as tax-free cash at retirement (0–1)."""

    high_low_option: bool = False
    """If True, convert to high-then-low pension (higher before 80, lower after)."""

    partner_exchange_fraction: float = 0.0
    """Fraction of own pension exchanged for a partner's survivor pension."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ParticipantConfig:
    """Full specification for one participant's lifecycle simulation.

    Parameters
    ----------
    entry_age:
        Age at which participant enters the scheme.
    retirement_age:
        Age at which accumulation ends and decumulation begins.
    death_age:
        Age at which the pension obligation ends (deterministic for now).
    contribution_rate:
        Annual pension contribution as fraction of pensionable salary (e.g. 0.20).
    salary_profile:
        SalaryProfile instance.
    cohort_allocations:
        List of CohortAllocation entries (10-year bands).
    retirement_options:
        At-retirement conversion choices.
    lhp_specs:
        Asset sleeves for the liability-hedging sub-portfolio (intra-LHP weights
        must sum to 1.0).  Deepcopied at the start of each run() call so that
        sleeve state (e.g. CAPE, cap-rate) does not leak across scenarios.
    rsp_specs:
        Asset sleeves for the return-seeking sub-portfolio (intra-RSP weights
        must sum to 1.0).  Deepcopied at the start of each run() call.
    lambda_:
        Diebold-Li decay parameter for the annuity factor yield curve read.
    adjustment_smoothing_years:
        Number of years over which pension adjustments are spread.
    adjustment_floor:
        Minimum annual pension adjustment (negative = cut), e.g. -0.03.
    solidarity_reserve_rate:
        Fraction of positive adjustment ceded to solidarity reserve each year.
    """

    entry_age:              int   = 25
    retirement_age:         int   = 68
    death_age:              int   = 90

    contribution_rate:      float = 0.20
    salary_profile:         SalaryProfile = field(default_factory=SalaryProfile)
    cohort_allocations:     list[CohortAllocation] = field(default_factory=default_cohort_allocations)
    retirement_options:     RetirementOptions = field(default_factory=RetirementOptions)

    # Asset sleeve models — intra-sub-portfolio weights must sum to 1.0
    lhp_specs:              list[SleeveSpec] = field(default_factory=list)
    rsp_specs:              list[SleeveSpec] = field(default_factory=list)

    # Diebold-Li parameter for the annuity factor computation
    lambda_:                float = 5.0

    # Annual adjustment mechanism
    adjustment_smoothing_years: int   = 3
    adjustment_floor:           float = -0.03
    solidarity_reserve_rate:    float = 0.05   # 5% of gains go to solidarity reserve

    # Career-average (middelloon) revaluation basis for the replacement ratio.
    #   "wage"  : revalue each past year's pensionable salary to retirement-year
    #             terms by economy-wide nominal wage growth = realised price
    #             inflation x structural real-wage drift (salary_profile.
    #             real_growth). Excludes the individual's promotion jumps, which
    #             are personal career progression rather than the indexation
    #             series. This is the conventional geindexeerd middelloon and is
    #             the default.
    #   "price" : revalue by realised CPI only (price-indexed middelloon).
    #   "none"  : raw nominal average (legacy behaviour; understates the
    #             denominator and so overstates the replacement ratio).
    career_average_indexation:  str   = "wage"

    @property
    def working_years(self) -> int:
        return self.retirement_age - self.entry_age

    @property
    def retirement_years(self) -> int:
        return self.death_age - self.retirement_age


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ParticipantResult:
    """Outputs from a single lifecycle simulation path.

    Attributes
    ----------
    pot_path:
        Pension pot (€) at each annual step from entry to death.
        Length = working_years + retirement_years + 1 (includes step 0).
    pension_path:
        Annual pension payment (€) during decumulation.  Length = retirement_years.
        Zero during accumulation.
    contribution_path:
        Annual contribution (€) during accumulation.  Length = working_years.
    adjustment_path:
        Annual pension adjustment factor applied each decumulation year.
        1.0 = no change; 0.97 = cut of 3%; >1.0 = increase.
    real_pension_path:
        Pension (€) deflated back to entry-year purchasing power (÷ cumulative CPI
        at each decumulation step). Shows whether the pension maintains real value.
    final_pot:
        Pot value at death_age (residual after decumulation).
    pension_at_retirement:
        Initial annual pension set at retirement (nominal €).
    career_avg_salary:
        Career-average pensionable salary, revalued to retirement-year terms
        per ParticipantConfig.career_average_indexation (the middelloon
        denominator of the replacement ratio).
    replacement_ratio:
        pension_at_retirement / career_avg_salary — the Dutch middelloon
        benchmark (ambition = 70 %), on a revalued (geindexeerd) basis.
    solidarity_reserve_path:
        Cumulative contributions to the solidarity reserve.
    """

    pot_path:              list[float]
    pension_path:          list[float]
    real_pension_path:     list[float]   # pension deflated to entry-year €
    contribution_path:     list[float]
    adjustment_path:       list[float]
    solidarity_reserve_path: list[float]
    final_pot:             float
    pension_at_retirement: float
    career_avg_salary:     float   # career-average pensionable salary, revalued to retirement-year terms (see ParticipantConfig.career_average_indexation)
    career_avg_salary_nominal: float   # raw un-revalued nominal average (transparency)
    replacement_ratio:     float   # pension_at_retirement / career_avg_salary (middelloon)
    pot_exhausted_at:      int | None  # 0-indexed decumulation step when pot first hits 0; None if pot survives


# ---------------------------------------------------------------------------
# Helper — annuity factor
# ---------------------------------------------------------------------------

def _annuity_factor(
    current_age: int,
    death_age:   int,
    yield_curve: YieldCurve,
) -> float:
    """Present value of €1/year from current_age to death_age using NS real yield.

    Uses the real yield curve so that the pension obligation is valued in
    real terms (consistent with variabel pensioen that can be indexed).
    """
    factor = 0.0
    for t in range(1, death_age - current_age + 1):
        r = yield_curve.real_rate(float(t))
        r = max(r, 1e-6)   # floor to avoid division by zero at negative rates
        factor += math.exp(-r * t)
    return max(factor, 0.1)   # numerical floor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stable_offset(name: str, modulo: int = 100_000) -> int:
    """Deterministic, process-stable name -> offset.

    Python's built-in hash() is salted per process via PYTHONHASHSEED, so using
    it here made sleeve RNG seeds differ between runs and broke cross-run
    reproducibility. A fixed digest keeps the offset identical across processes.
    """
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulo


def _reseed_specs(specs: list[SleeveSpec], base_seed: int) -> None:
    """Re-seed each sleeve's internal RNG using a name-derived offset.

    Called after deepcopy so that repeated runs on the same macro path
    (e.g. stress scenario replications) produce distinct idiosyncratic draws
    while remaining deterministic given the same base_seed.
    """
    for spec in specs:
        if hasattr(spec.sleeve, "_rng"):
            sleeve_offset = _stable_offset(spec.sleeve.name)
            spec.sleeve._rng = np.random.default_rng(base_seed + sleeve_offset)


# ---------------------------------------------------------------------------
# Main simulator
# ---------------------------------------------------------------------------

class LifecycleSimulator:
    """Simulates a single participant's lifecycle over a given macro path.

    The macro path must span at least (death_age - entry_age) annual steps.
    Each row of *path* is a MacroState.  The simulator reads ``short_rate``,
    ``long_rate``, ``real_rate``, ``inflation``, and ``growth`` at each step.

    RSP and LHP returns are generated by the actual asset sleeve models
    (EquitySleeve, RealAssetSleeve, LinkerSleeve, etc.) via SubPortfolio.
    The sleeve specs are deepcopied at the start of each run() call so that
    stateful sleeve properties (CAPE, cap-rate) do not leak across scenarios.

    Parameters
    ----------
    config:
        ParticipantConfig describing the participant.  Must include non-empty
        lhp_specs and rsp_specs.
    """

    def __init__(self, config: ParticipantConfig) -> None:
        if not config.lhp_specs:
            raise ValueError("ParticipantConfig.lhp_specs must be non-empty")
        if not config.rsp_specs:
            raise ValueError("ParticipantConfig.rsp_specs must be non-empty")
        self._cfg = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, path: list[MacroState], run_seed: int | None = None) -> ParticipantResult:
        """Simulate the full lifecycle over *path* and return results.

        Parameters
        ----------
        path:
            List of MacroState objects, one per annual step.  Must have
            at least (death_age - entry_age) entries after step 0.
        run_seed:
            If provided, re-seeds every sleeve's internal RNG after deepcopy
            so that repeated calls on the same macro path (e.g. stress scenario
            replications) produce distinct idiosyncratic draws.
        """
        cfg = self._cfg
        n_total = cfg.working_years + cfg.retirement_years
        if len(path) < n_total + 1:
            raise ValueError(
                f"path has {len(path)} steps, need at least {n_total + 1} "
                f"(working={cfg.working_years} + retirement={cfg.retirement_years} + 1)"
            )

        # Fresh sleeve instances per run — prevents CAPE/cap-rate state leakage
        rsp_specs = copy.deepcopy(cfg.rsp_specs)
        lhp_specs = copy.deepcopy(cfg.lhp_specs)

        if run_seed is not None:
            _reseed_specs(rsp_specs, base_seed=run_seed)
            _reseed_specs(lhp_specs, base_seed=run_seed + 10_000)

        # One FXModel per run: single RNG draw per currency per period ensures
        # all sleeves see the same exchange-rate move in each period.
        fx_seed = (run_seed + 20_000) if run_seed is not None else None
        fx_model = FXModel.default(seed=fx_seed)

        rsp_sub = SubPortfolio(rsp_specs, initial_value=1.0, fx_model=fx_model)
        # LHP also takes the FX model: the liability hedge may now hold unhedged
        # foreign-currency govvies (unrepressed-curve sleeves). EUR-only sleeves
        # carry no fx_exposures, so this is a no-op for them.
        lhp_sub = SubPortfolio(lhp_specs, initial_value=1.0, fx_model=fx_model)

        pot_path:          list[float] = [0.0] * (n_total + 1)
        contribution_path: list[float] = []
        pension_path:      list[float] = []
        adjustment_path:   list[float] = []
        solidarity_path:   list[float] = []

        pot = 0.0
        cumulative_inflation = 0.0
        cumulative_solidarity = 0.0
        salary_sum = 0.0   # raw nominal career-average (middelloon) accumulator
        # Wage-revaluation accumulator: each year's salary is divided by a running
        # wage index, so that multiplying the total by the retirement-year index
        # expresses every year's pay in retirement-year terms. See
        # cfg.career_average_indexation.
        revalued_salary_sum = 0.0
        wage_index = 1.0
        _real_wage_drift = cfg.salary_profile.real_growth

        # ----------------------------------------------------------------
        # Accumulation phase
        # ----------------------------------------------------------------
        for step in range(cfg.working_years):
            state_t  = path[step]
            state_t1 = path[step + 1]
            age      = cfg.entry_age + step

            # Salary and contribution
            nominal_salary = cfg.salary_profile.nominal_salary_at(
                age, cfg.entry_age, cumulative_inflation
            )
            salary_sum += nominal_salary
            revalued_salary_sum += nominal_salary / wage_index
            contribution = cfg.contribution_rate * nominal_salary
            contribution_path.append(contribution)
            pot += contribution

            # Cohort allocation
            cohort   = _cohort_for_age(age, cfg.cohort_allocations)
            rsp_w    = cohort.rsp_fraction
            lhp_w    = cohort.lhp_fraction
            leverage = cohort.leverage_fraction

            # RSP and LHP returns from actual asset sleeve models
            rsp_return = rsp_sub.step(state_t, state_t1, dt=1.0)
            lhp_return = lhp_sub.step(state_t, state_t1, dt=1.0)

            leverage_cost = leverage * state_t.short_rate
            period_return = rsp_w * rsp_return + lhp_w * lhp_return - leverage_cost

            pot *= (1.0 + period_return)
            pot_path[step + 1] = pot

            rsp_sub.rebalance()
            lhp_sub.rebalance()

            # Update cumulative CPI and the wage-revaluation index in lock-step,
            # so both reflect realised inflation through the same step.
            cumulative_inflation = (1.0 + cumulative_inflation) * (1.0 + state_t.inflation) - 1.0
            if cfg.career_average_indexation == "wage":
                wage_index *= (1.0 + state_t.inflation) * (1.0 + _real_wage_drift)
            elif cfg.career_average_indexation == "price":
                wage_index *= (1.0 + state_t.inflation)
            # "none": wage_index stays 1.0, so revalued_salary_sum == salary_sum

        # ----------------------------------------------------------------
        # Retirement conversion
        # ----------------------------------------------------------------
        retirement_step  = cfg.working_years
        state_retirement = path[retirement_step]
        yc_ret           = YieldCurve(state_retirement, lambda_=cfg.lambda_)

        # At-retirement options
        opts = cfg.retirement_options
        converted_pot = pot * (1.0 - opts.lump_sum_fraction)
        # high_low_option and partner_exchange_fraction are stubs — apply trivially

        annuity_f = _annuity_factor(cfg.retirement_age, cfg.death_age, yc_ret)
        initial_pension = converted_pot / annuity_f
        pension_at_retirement = initial_pension

        # Career-average salary (middelloon) and replacement ratio.
        # career_avg_salary is revalued to retirement-year terms per
        # cfg.career_average_indexation; career_avg_salary_nominal is the raw
        # un-revalued average, retained for transparency/audit.
        wy = cfg.working_years
        career_avg_salary_nominal = (salary_sum / wy) if wy > 0 else 0.0
        if wy > 0:
            # revalued_salary_sum = Sum_t (salary_t / wage_index_t); multiplying by
            # the retirement-year index expresses each year in retirement-year terms.
            career_avg_salary = (revalued_salary_sum * wage_index) / wy
        else:
            career_avg_salary = 0.0
        replacement_ratio = (initial_pension / career_avg_salary) if career_avg_salary > 0 else 0.0

        # CPI at retirement (used to deflate decumulation pension to entry-year €)
        cpi_at_retirement = 1.0 + cumulative_inflation

        # ----------------------------------------------------------------
        # Decumulation phase — variabel pensioen with annual adjustment
        # ----------------------------------------------------------------
        current_pension    = initial_pension
        real_pension_path: list[float] = []
        pending_adj_queue: list[float] = []   # smoothed adjustment amounts waiting to be applied
        cumulative_cpi_defl = cpi_at_retirement   # grows as CPI continues post-retirement
        pot_exhausted_at: int | None = None

        for step in range(cfg.retirement_years):
            state_t  = path[retirement_step + step]
            state_t1 = path[retirement_step + step + 1]
            age      = cfg.retirement_age + step

            # Cohort allocation (post-retirement — 80/20 LHP/RSP, no leverage)
            cohort   = _cohort_for_age(age, cfg.cohort_allocations)
            rsp_w    = cohort.rsp_fraction
            lhp_w    = cohort.lhp_fraction
            leverage = cohort.leverage_fraction   # 0.0 post-retirement

            # RSP and LHP returns from actual asset sleeve models
            rsp_return = rsp_sub.step(state_t, state_t1, dt=1.0)
            lhp_return = lhp_sub.step(state_t, state_t1, dt=1.0)

            leverage_cost = leverage * state_t.short_rate
            period_return = rsp_w * rsp_return + lhp_w * lhp_return - leverage_cost

            pot *= (1.0 + period_return)

            # Deduct annual pension payment
            pot -= current_pension
            if pot < 0 and pot_exhausted_at is None:
                pot_exhausted_at = step
            pot = max(pot, 0.0)

            rsp_sub.rebalance()
            lhp_sub.rebalance()

            # Annual adjustment mechanism
            if pot > 0 and (cfg.retirement_age + step + 1) < cfg.death_age:
                yc_next     = YieldCurve(state_t1, lambda_=cfg.lambda_)
                annuity_new = _annuity_factor(age + 1, cfg.death_age, yc_next)
                target_pension = pot / annuity_new

                raw_adj = (target_pension - current_pension) / current_pension

                # Solidarity reserve: cede a fraction of positive adjustments
                if raw_adj > 0.0:
                    solidarity_contribution = cfg.solidarity_reserve_rate * raw_adj * current_pension
                    cumulative_solidarity  += solidarity_contribution
                    raw_adj -= cfg.solidarity_reserve_rate * raw_adj   # reduce by ceded share

                # Smooth over adjustment_smoothing_years
                annual_slice = raw_adj / cfg.adjustment_smoothing_years
                pending_adj_queue.append(annual_slice)
                applied_adj = sum(pending_adj_queue[-cfg.adjustment_smoothing_years:])
                applied_adj = max(applied_adj, cfg.adjustment_floor)   # floor at -3%

                new_pension    = current_pension * (1.0 + applied_adj)
                new_pension    = max(new_pension, 0.0)
                adjustment_factor = new_pension / current_pension if current_pension > 0 else 1.0
                current_pension   = new_pension
            else:
                adjustment_factor = 1.0

            # Real pension: deflate nominal pension back to entry-year €
            cumulative_cpi_defl *= (1.0 + state_t.inflation)
            real_pension_path.append(current_pension / cumulative_cpi_defl)

            pension_path.append(current_pension)
            adjustment_path.append(adjustment_factor)
            solidarity_path.append(cumulative_solidarity)
            pot_path[retirement_step + step + 1] = pot

        return ParticipantResult(
            pot_path              = pot_path,
            pension_path          = pension_path,
            real_pension_path     = real_pension_path,
            contribution_path     = contribution_path,
            adjustment_path       = adjustment_path,
            solidarity_reserve_path = solidarity_path,
            final_pot             = pot,
            pension_at_retirement = pension_at_retirement,
            career_avg_salary     = career_avg_salary,
            career_avg_salary_nominal = career_avg_salary_nominal,
            replacement_ratio     = replacement_ratio,
            pot_exhausted_at      = pot_exhausted_at,
        )
