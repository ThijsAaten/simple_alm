# simple_alm — Asset-Liability Management Simulation Framework

A modular Python framework for quantitative ALM modelling. It generates correlated macro scenarios, values a liability cash-flow stream, simulates a portfolio split between a Liability-Hedging Portfolio (LHP) and a Return-Seeking Portfolio (RSP), and tracks the funding ratio over time.

---

## Table of Contents

1. [How to Use](#1-how-to-use)
   - [1.1 Installation](#11-installation)
   - [1.2 Quick Start](#12-quick-start)
   - [1.3 Choosing a Scenario Engine](#13-choosing-a-scenario-engine)
   - [1.4 Defining Liabilities](#14-defining-liabilities)
   - [1.5 Building a Portfolio](#15-building-a-portfolio)
   - [1.6 Running the Simulation](#16-running-the-simulation)
   - [1.7 Stress Testing](#17-stress-testing)
   - [1.8 Regime-Aware Analytics](#18-regime-aware-analytics)
   - [1.9 Full Working Example](#19-full-working-example)
2. [Documentation](#2-documentation)
   - [2.1 Project Structure](#21-project-structure)
   - [2.2 Macro State](#22-macro-state-scenariosenginepy)
   - [2.3 VAR(1) Scenario Engine](#23-var1-scenario-engine-scenariosenginepy)
   - [2.4 Regime-Switching Engine](#24-regime-switching-engine-scenariosregimespy)
   - [2.5 Stress Scenarios](#25-stress-scenarios-scenariosenginepy)
   - [2.6 Liability Model](#26-liability-model-liabilitiesmodelpy)
   - [2.7 Asset Sleeves](#27-asset-sleeves-assets)
   - [2.8 Portfolio Construction](#28-portfolio-construction-portfolioportfoliopy)
   - [2.9 Simulation Engine](#29-simulation-engine-simulationenginepy)
   - [2.10 Analytics](#210-analytics-analyticsmetricspy)
   - [2.11 Return Models — Mathematical Reference](#211-return-models--mathematical-reference)
   - [2.12 Extension Points](#212-extension-points)
   - [2.13 Participant Lifecycle Model](#213-participant-lifecycle-model-participant)
   - [2.14 Country Mosaic — Asia Re-anchoring](#214-country-mosaic--asia-re-anchoring-allocations)

---

# 1. How to Use

## 1.1 Installation

```bash
pip install -r requirements.txt
```

**Requirements:** `numpy >= 1.26`, `pandas >= 2.2`, `matplotlib >= 3.8`

Run all scripts from the `simple_alm/` project root so that package imports resolve correctly:

```bash
cd simple_alm/
python main.py
```

---

## 1.2 Quick Start

```python
from scenarios.engine import MacroState, VARParams, MacroScenarioEngine
from liabilities.model import LiabilitySchedule, LiabilityModel
from assets.bonds   import NominalBondSleeve
from assets.linkers import LinkerSleeve
from assets.cash    import CashSleeve
from assets.growth  import EquitySleeve, RealAssetSleeve
from portfolio.portfolio import Portfolio, SleeveSpec
from simulation.engine   import SimulationEngine
from analytics.metrics   import funding_ratio_stats, fan_chart_data

# 1. Define the starting macro environment
initial = MacroState(
    short_rate=0.04, long_rate=0.045, real_rate=0.015,
    inflation=0.025, growth=0.025, credit_spread=0.012,
    curvature=0.010,    # Diebold-Li β₂: slight positive hump
)

# 2. Generate 1 000 correlated macro paths (20 annual steps)
engine = MacroScenarioEngine(VARParams(), initial, seed=42)
paths  = engine.simulate(n_steps=20, n_scenarios=1_000)

# 3. Define the liability — 30-year blended annuity (60 % CPI-linked)
schedule  = LiabilitySchedule.blended_annuity(10_000_000, n_years=30, real_fraction=0.6)
liability = LiabilityModel(schedule)

# 4. Build the portfolio factory (called once per scenario)
def make_portfolio():
    return Portfolio(
        lhp_specs=[
            SleeveSpec(NominalBondSleeve("LongGovt", duration=20.0, maturity=25.0), weight=0.50),
            SleeveSpec(LinkerSleeve("ILG", real_duration=18.0, maturity=22.0),      weight=0.40),
            SleeveSpec(CashSleeve("LHPCash"),                                        weight=0.10),
        ],
        rsp_specs=[
            SleeveSpec(EquitySleeve("Equity",     seed=1, cape=25.0, cape_fair=20.0), weight=0.65),
            SleeveSpec(RealAssetSleeve("RealAssets", seed=2, initial_cap_rate=0.055), weight=0.35),
        ],
        initial_value=180_000_000,
        hedge_ratio=0.60,          # 60 % LHP, 40 % RSP
    )

# 5. Run the simulation
sim     = SimulationEngine(liability, make_portfolio)
results = sim.run_all(paths)      # returns a tidy pandas DataFrame

# 6. Inspect results
print(funding_ratio_stats(results, step=10))
fan = fan_chart_data(results)
```

---

## 1.3 Choosing a Scenario Engine

Two scenario engines are available. Both expose the same `simulate()` interface so they are interchangeable downstream.

### VAR(1) engine — single-regime

```python
from scenarios.engine import MacroState, VARParams, MacroScenarioEngine

engine = MacroScenarioEngine(VARParams(), initial_state, dt=1.0, seed=42)
paths  = engine.simulate(n_steps=20, n_scenarios=1_000)
```

Override specific parameters without replacing the full `VARParams`:

```python
import numpy as np
params = VARParams()
params.long_run_mean[4] = 0.03    # raise long-run growth to 3 %
engine = MacroScenarioEngine(params, initial_state, seed=42)
```

### Regime-switching engine — four macro quadrants

```python
from scenarios.regimes import (
    RegimeLabel, RegimeSwitchingEngine, default_regime_spec,
)

spec   = default_regime_spec()
engine = RegimeSwitchingEngine(
    spec,
    initial_state,
    initial_regime=RegimeLabel.DEFLATIONARY_BOOM,
    seed=42,
)

# Drop-in usage (regime labels discarded)
paths = engine.simulate(n_steps=20, n_scenarios=1_000)

# Extended usage (keeps regime labels for analytics)
paths, regime_paths = engine.simulate_with_regimes(n_steps=20, n_scenarios=1_000)
```

---

## 1.4 Defining Liabilities

### Pre-built schedules

```python
from liabilities.model import LiabilitySchedule, LiabilityModel

# Pure nominal annuity
schedule = LiabilitySchedule.level_annuity(10_000_000, n_years=30, kind="nominal")

# Pure CPI-linked annuity
schedule = LiabilitySchedule.level_annuity(10_000_000, n_years=30, kind="real")

# Mixed — 60 % CPI-linked, 40 % nominal (most common for UK pension funds)
schedule = LiabilitySchedule.blended_annuity(10_000_000, n_years=30, real_fraction=0.6)

# Fully custom schedule (e.g. lump sums or irregular cash flows)
schedule = LiabilitySchedule.custom(
    times   = [5.0, 10.0, 20.0, 30.0],
    amounts = [5e6, 8e6, 12e6, 20e6],
    kinds   = ["nominal", "real", "real", "nominal"],
)
```

### Valuation and sensitivities

```python
liability = LiabilityModel(schedule, lambda_=5.0)   # lambda_ = Nelson-Siegel shape (years)

pv       = liability.present_value(macro_state)     # € present value
duration = liability.duration(macro_state)          # modified duration (years)
inf_pv01 = liability.inflation_pv01(macro_state)    # % PV change per 1 bp breakeven move

# Per-cash-flow PV breakdown (returns list of dicts)
breakdown = liability.cashflow_pv_breakdown(macro_state)
```

---

## 1.5 Building a Portfolio

The portfolio has a two-level weight structure:

```
Total portfolio
├── LHP  (hedge_ratio of total)
│   ├── NominalBondSleeve  (weight within LHP)
│   ├── LinkerSleeve
│   └── CashSleeve
└── RSP  (1 − hedge_ratio of total)
    ├── EquitySleeve       (weight within RSP)
    ├── RealAssetSleeve
    ├── CreditBondSleeve
    └── CommoditySleeve
```

```python
from portfolio.portfolio import Portfolio, SleeveSpec
from assets.bonds   import NominalBondSleeve, CreditBondSleeve
from assets.linkers import LinkerSleeve
from assets.cash    import CashSleeve
from assets.growth  import EquitySleeve, RealAssetSleeve, CommoditySleeve

portfolio = Portfolio(
    lhp_specs=[
        SleeveSpec(NominalBondSleeve("LongGovt",  duration=20.0, maturity=25.0), weight=0.50),
        SleeveSpec(LinkerSleeve(     "ILG",   real_duration=18.0, maturity=22.0), weight=0.40),
        SleeveSpec(CashSleeve(       "LHPCash"),                                  weight=0.10),
    ],
    rsp_specs=[
        SleeveSpec(EquitySleeve(    "Equity",
                                    drift=0.07, seed=1,
                                    cape=25.0, cape_fair=20.0,
                                    valuation_beta=0.05),              weight=0.50),
        SleeveSpec(RealAssetSleeve( "RealAssets",
                                    seed=2,
                                    initial_cap_rate=0.055,
                                    risk_premium=0.010,
                                    implied_duration=15.0),            weight=0.25),
        SleeveSpec(CreditBondSleeve("IGCredit",   duration=7.0, maturity=8.0),   weight=0.15),
        SleeveSpec(CommoditySleeve( "Commod",     seed=3),                       weight=0.10),
    ],
    initial_value=180_000_000,
    hedge_ratio=0.60,           # 60 % in LHP
    rebalance_frequency=1,      # rebalance every step; 0 = never
)
```

Weights within each sub-portfolio must sum to 1.0. The `hedge_ratio` is independent of those weights.

---

## 1.6 Running the Simulation

```python
from simulation.engine import SimulationEngine

sim = SimulationEngine(
    liability_model   = liability,
    portfolio_factory = make_portfolio,    # callable that returns a fresh Portfolio
    dt                = 1.0,              # time step in years
    # optional: inject cash flows at specific steps
    contribution_schedule = {5: 10_000_000},   # €10 M contribution at year 5
)

# Run all scenarios → tidy long-format DataFrame
results = sim.run_all(paths, verbose=True)
```

The output DataFrame has one row per `(scenario, step)` with columns:

| Column | Description |
| -------- | ------------- |
| `scenario` | Scenario index |
| `step` | Time step index (0 = initial) |
| `portfolio_value` | Total fund market value |
| `liability_pv` | Liability present value |
| `funding_ratio` | `portfolio_value / liability_pv` |
| `period_return` | Portfolio total return for the period (`NaN` at step 0) |
| `short_rate` | Macro state variables … |
| `long_rate`, `real_rate`, `inflation`, `growth`, `credit_spread`, `curvature` | … at this step |
| `regime` | Regime label (only when `regime_paths` is passed) |
| `regime_id` | Integer regime index (0–3) |

---

## 1.7 Stress Testing

```python
from scenarios.engine import StressScenario

# Named stress constructors
stress_rate   = StressScenario.parallel_rate_shock(initial, n_steps=20, shock_bps=200)
stress_stagfl = StressScenario.stagflation(initial, n_steps=20)
stress_defl   = StressScenario.deflation(initial, n_steps=20)

# Run a single stress path
result = sim.run_stress(stress_rate)       # returns ScenarioResult
print(f"FR after 1yr: {result.funding_ratios[1]:.2%}")

# Convert to DataFrame for further analysis
df_stress = result.to_dataframe()
```

---

## 1.8 Regime-Aware Analytics

When using the regime-switching engine, pass `regime_paths` through the simulation to unlock per-regime analytics:

```python
from analytics.metrics import (
    funding_ratio_by_regime,
    regime_transition_heatmap_data,
    fan_chart_by_regime,
)

paths, regime_paths = engine.simulate_with_regimes(n_steps=20, n_scenarios=1_000)
results = sim.run_all(paths, regime_paths=regime_paths)

# Funding ratio breakdown by regime at year 10
print(funding_ratio_by_regime(results, step=10))

# Validate empirical transition matrix matches specification
print(regime_transition_heatmap_data(results))

# Separate fan chart data per regime (for colour-coded plots)
fans = fan_chart_by_regime(results)   # dict: regime label → fan DataFrame

# Verify simulated regime frequencies vs theoretical stationary distribution
print(engine.regime_frequency(regime_paths))
```

---

## 1.9 Full Working Example

Run `main.py` from the project root for a complete end-to-end demonstration:

```bash
python main.py
```

This runs 1 000 scenarios × 20 years through a blended 60/40 LHP/RSP portfolio, prints funding ratio statistics at years 5, 10, and 20, overlays three stress paths, and saves a fan chart to `funding_ratio_fan_chart.png`.

---

# 2. Documentation

## 2.1 Project Structure

```
simple_alm/
├── scenarios/
│   ├── engine.py        # MacroState, VARParams, YieldCurve, MacroScenarioEngine, StressScenario
│   └── regimes.py       # RegimeLabel, RegimeSpec, RegimeSwitchingEngine
├── liabilities/
│   └── model.py         # CashFlow, LiabilitySchedule, LiabilityModel
├── assets/
│   ├── base.py          # AssetSleeve (abstract base class)
│   ├── cash.py          # CashSleeve
│   ├── bonds.py         # NominalBondSleeve, CreditBondSleeve
│   ├── linkers.py       # LinkerSleeve
│   ├── growth.py        # EquitySleeve, RealAssetSleeve, CommoditySleeve
│   ├── fx.py            # FXModel, CurrencyParams (13-currency overlay)
│   └── em_bonds.py      # ChinaGovernmentBondSleeve (extensible EM bond module)
├── portfolio/
│   └── portfolio.py     # SleeveSpec, SubPortfolio, Portfolio
├── simulation/
│   └── engine.py        # ScenarioResult, SimulationEngine
├── analytics/
│   └── metrics.py       # FundingRatioStats and all analytics functions
├── participant/
│   ├── salary.py        # SalaryProfile
│   └── lifecycle.py     # CohortAllocation, ParticipantConfig, LifecycleSimulator, ParticipantResult
├── allocations/
│   ├── __init__.py      # lazy-export façade
│   ├── country_inputs.py # COUNTRY_INPUTS: per-market drift/CAPE/FX, sourced from §3.1 Table 1a
│   ├── mosaic.py        # build_equity_specs(), four canonical allocations (CURRENT/PROPOSED/…)
│   └── preview.py       # static allocation-preview table (no Monte Carlo)
├── examples/
│   └── run_equity_only.py  # CURRENT vs PROPOSED A equity-only validation
├── tests/
│   └── test_invariants.py  # 8 load-bearing invariants (pytest or python -m)
├── docs/
│   ├── REPRODUCE.md     # one-command reproduce runbook
│   └── INPUT_PROVENANCE.md # maps every input figure to its §3.1/§13.6 source
├── reproduce_participant.py # driver: all four allocations on shared paths
├── main.py              # Fund-level ALM demo
├── main_participant.py  # Dutch WTP individual lifecycle demo
└── requirements.txt
```

Each package is independent at the class level. The dependency graph is acyclic:

```
scenarios   → (nothing)
liabilities → scenarios
assets      → scenarios
portfolio   → assets, scenarios
simulation  → scenarios, liabilities, portfolio
analytics   → (nothing — operates on DataFrames)
participant → scenarios, assets, portfolio
```

---

## 2.2 Macro State (`scenarios/engine.py`)

### `MacroState`

A snapshot of the macro environment at a single point in time. All rates are annualised decimals (e.g. `0.04` = 4 %).

```python
@dataclass
class MacroState:
    short_rate:    float   # short-term nominal risk-free rate
    long_rate:     float   # long-term nominal yield (e.g. 30yr government)
    real_rate:     float   # long-term real yield (e.g. 30yr index-linked gilt)
    inflation:     float   # realised / expected CPI inflation
    growth:        float   # real GDP growth
    credit_spread: float   # IG credit spread over government bonds
    curvature:     float   # Diebold-Li β₂: hump / inversion factor (positive = hump, negative = inverted)
```

**Derived property:**

| Property | Formula |
| ---------- | --------- |
| `breakeven_inflation` | `long_rate − real_rate` |

**Methods:**

| Method | Description |
| -------- | ------------- |
| `to_array() → np.ndarray` | Returns a 7-element array in field order |
| `from_array(arr) → MacroState` | Class method; inverse of `to_array` |

---

## 2.3 VAR(1) Scenario Engine (`scenarios/engine.py`)

### `VARParams`

Holds all parameters for the VAR(1) process. Every field has a calibrated default so only the fields you want to change need to be specified.

```python
@dataclass
class VARParams:
    long_run_mean: np.ndarray   # shape (7,)  — equilibrium values of X
    phi:           np.ndarray   # shape (7,7) — persistence / mean-reversion matrix
    sigma:         np.ndarray   # shape (7,7) — annualised innovation covariance
    floors:        dict[str, float]  # soft lower bounds per variable
```

**Default long-run means** (annualised):

| Variable | Default |
| ---------- | --------- |
| `short_rate` | 3.5 % |
| `long_rate` | 4.5 % |
| `real_rate` | 1.5 % |
| `inflation` | 2.5 % |
| `growth` | 2.5 % |
| `credit_spread` | 1.0 % |
| `curvature` | 0.5 % |

The default `phi` is a sparse 7×7 matrix where the diagonal captures per-variable mean-reversion speed (ranging from 0.50 for growth to 0.80 for long rates). Off-diagonal terms capture cross-variable spillovers: inflation feeds into short rates, and slope and inflation feed weakly into curvature (inverted curves tend to appear when inflation is high and the curve is steep).

The default `sigma` is built from empirical volatilities and a 7×7 correlation structure where rates are positively correlated with each other, curvature is negatively correlated with rates (a parallel rate rise tends to flatten the curve), and growth is negatively correlated with credit spreads.

---

### `MacroScenarioEngine`

Generates correlated macro paths using the discrete-time VAR(1) process:

```
X(t+1) = X̄ + Φ · (X(t) − X̄) + chol(Σ · dt) · ε,    ε ~ N(0, I)
```

**Constructor:**

```python
MacroScenarioEngine(
    params:        VARParams,
    initial_state: MacroState,
    dt:            float = 1.0,    # time step in years
    seed:          int | None = None,
)
```

**Methods:**

| Method | Signature | Description |
| -------- | ----------- | ------------- |
| `step` | `(state) → MacroState` | Advance one step |
| `simulate` | `(n_steps, n_scenarios=1) → list[list[MacroState]]` | Generate all paths |
| `to_dataframe` | `(paths) → pd.DataFrame` | Flatten paths to tidy format |

`simulate` returns `paths[scenario][step]`. Step 0 is always `initial_state`.

---

## 2.4 Regime-Switching Engine (`scenarios/regimes.py`)

Extends the VAR(1) engine with a Markov regime layer. The four regimes form a 2×2 quadrant:

```
                   Inflation LOW      Inflation HIGH
  Growth HIGH  │  Deflationary Boom  │  Inflationary Boom  │
  Growth LOW   │  Deflationary Bust  │  Inflationary Bust  │
```

At every step, the regime is sampled from the Markov chain, and the new regime's VAR parameters are used to advance the macro state. Each regime has distinct equilibrium values, reversion speeds, and shock volatilities.

### `RegimeLabel`

```python
class RegimeLabel(IntEnum):
    DEFLATIONARY_BOOM = 0   # "Goldilocks": high growth, low inflation
    DEFLATIONARY_BUST = 1   # Recession:   low growth,  low inflation
    INFLATIONARY_BOOM = 2   # Overheating: high growth, high inflation
    INFLATIONARY_BUST = 3   # Stagflation: low growth,  high inflation
```

**Properties:** `growth_level` (`"high"` / `"low"`), `inflation_level` (`"high"` / `"low"`), `label` (human-readable string).

---

### Per-regime calibration

| Variable | Def. Boom | Def. Bust | Inf. Boom | Inf. Bust |
| ---------- | ----------- | ----------- | ----------- | ----------- |
| short_rate (LR) | 3.0 % | 1.0 % | 4.5 % | 5.5 % |
| long_rate (LR) | 4.0 % | 2.5 % | 5.5 % | 6.0 % |
| real_rate (LR) | 2.5 % | 1.5 % | 2.0 % | 0.5 % |
| inflation (LR) | 1.5 % | 0.5 % | 3.5 % | 5.0 % |
| growth (LR) | 3.5 % | −0.5 % | 3.0 % | −1.0 % |
| credit_spread (LR) | 0.8 % | 2.0 % | 1.2 % | 3.0 % |
| curvature (LR) | +0.5 % | −0.5 % | +1.0 % | −1.0 % |
| Φ diag (approx) | ~0.65 | ~0.80 | ~0.70 | ~0.82 |
| Growth vol | 1.8 % | 3.0 % | 2.5 % | 3.5 % |

Bust and stagflation regimes have higher persistence (Φ) and higher innovation volatility (Σ). The inflationary bust is the stickiest and noisiest regime, and has the most negative curvature equilibrium (inverted curves from aggressive central bank tightening). The inflationary boom has the strongest positive hump (markets pricing in future hikes but CB still behind the curve).

---

### Default transition matrix (annual probabilities)

|  | → Def. Boom | → Def. Bust | → Inf. Boom | → Inf. Bust |
| -- | ------------- | ------------- | ------------- | ------------- |
| **Def. Boom** | 0.70 | 0.10 | 0.15 | 0.05 |
| **Def. Bust** | 0.25 | 0.60 | 0.03 | 0.12 |
| **Inf. Boom** | 0.08 | 0.05 | 0.65 | 0.22 |
| **Inf. Bust** | 0.05 | 0.25 | 0.10 | 0.60 |

**Stationary distribution** (long-run fraction of time in each regime):

| Regime | Freq. | Expected duration |
| -------- | ------- | ------------------- |
| Deflationary Boom | ~30 % | 3.3 years |
| Deflationary Bust | ~25 % | 2.5 years |
| Inflationary Boom | ~22 % | 2.9 years |
| Inflationary Bust | ~23 % | 2.5 years |

---

### `RegimeSpec`

```python
@dataclass
class RegimeSpec:
    params_by_regime:  dict[RegimeLabel, VARParams]
    transition_matrix: np.ndarray   # shape (4, 4), row-stochastic
```

| Method | Description |
| -------- | ------------- |
| `stationary_distribution() → np.ndarray` | Long-run regime frequencies (left eigenvector) |
| `expected_regime_duration() → dict[RegimeLabel, float]` | Mean duration = 1 / (1 − p_ii) |

Use `default_regime_spec()` to instantiate with calibrated defaults.

---

### `RegimeSwitchingEngine`

Drop-in replacement for `MacroScenarioEngine`. The transition at each step is:

1. Sample `regime_{t+1} ~ Categorical(T[regime_t, :])` from the transition matrix.
2. Draw macro shock from `regime_{t+1}`'s VAR: `X_{t+1} = X̄_r + Φ_r · (X_t − X̄_r) + chol(Σ_r · dt) · ε`.

**Constructor:**

```python
RegimeSwitchingEngine(
    spec:           RegimeSpec,
    initial_state:  MacroState,
    initial_regime: RegimeLabel = RegimeLabel.DEFLATIONARY_BOOM,
    dt:             float = 1.0,
    seed:           int | None = None,
)
```

**Methods:**

| Method | Signature | Description |
| -------- | ----------- | ------------- |
| `simulate` | `(n_steps, n_scenarios) → list[list[MacroState]]` | Drop-in interface, regime labels discarded |
| `simulate_with_regimes` | `(n_steps, n_scenarios) → (paths, regime_paths)` | Full output with regime labels |
| `step` | `(state, regime) → (MacroState, RegimeLabel)` | Single-step transition |
| `to_dataframe` | `(paths, regime_paths=None) → pd.DataFrame` | Adds `regime` and `regime_id` columns when `regime_paths` is provided |
| `regime_frequency` | `(regime_paths) → pd.DataFrame` | Empirical vs theoretical regime frequencies |

---

## 2.5 Stress Scenarios (`scenarios/engine.py`)

### `StressScenario`

A hand-crafted deterministic macro path for tail risk analysis.

```python
@dataclass
class StressScenario:
    name:   str
    states: list[MacroState]   # states[0] = initial state (t=0)
```

**Named constructors:**

| Constructor | Parameters | Description |
| ------------- | ------------ | ------------- |
| `parallel_rate_shock` | `initial, n_steps, shock_bps=200, ramp_steps=1` | Parallel yield curve shift |
| `stagflation` | `initial, n_steps, inflation_shock=0.04, growth_shock=-0.03` | High inflation + low growth |
| `deflation` | `initial, n_steps, inflation_shock=-0.03, growth_shock=-0.04` | Deflationary recession |

Run a stress scenario through the simulation with `sim.run_stress(stress)`.

---

## 2.6 Liability Model (`liabilities/model.py`)

### `CashFlow`

```python
@dataclass
class CashFlow:
    time:   float                        # years from valuation date
    amount: float                        # base amount (nominal € or today's real €)
    kind:   Literal["nominal", "real"]   # determines which yield curve is used
```

---

### `LiabilitySchedule`

**Named constructors:**

| Constructor | Parameters | Description |
| ------------- | ------------ | ------------- |
| `level_annuity` | `annual_payment, n_years, kind="nominal"` | Uniform annual payments, all one type |
| `blended_annuity` | `annual_payment, n_years, real_fraction=0.5` | Split between CPI-linked and nominal |
| `custom` | `times, amounts, kinds` | Arbitrary cash flows from explicit lists |

**Properties:** `max_maturity` (years), `len()` (number of cash flows).

---

### `YieldCurve` (`scenarios/engine.py`)

A full three-factor Diebold-Li / dynamic Nelson-Siegel yield curve built from a `MacroState`. Both asset sleeves and the liability model import `YieldCurve` from `scenarios.engine`.

**Nominal spot rate at maturity τ:**

```
r_nominal(τ) = L + S · f(τ) + C · g(τ)

where  L = long_rate                            (level  / β₀)
       S = short_rate − long_rate               (slope  / β₁)
       C = curvature                            (hump   / β₂)

       f(τ) = (1 − e^{−τ/λ}) / (τ/λ)          (slope loading)
       g(τ) = f(τ) − e^{−τ/λ}                 (curvature loading, peaks at τ ≈ λ·ln 2)

Limits:  r_nominal(0) = L + S = short_rate
         r_nominal(∞) = L     = long_rate
```

**Real spot rate:**

```
r_real(τ) = r_nominal(τ) + (real_rate − long_rate)
```

The real curve has the same Diebold-Li shape as the nominal curve, shifted by the long-end real/nominal spread. This preserves `r_real(∞) = real_rate`.

**Discount factor:**

```
DF(τ, kind) = exp(−r(τ) · τ)
```

**`lambda_`** (default 5 years): the Nelson-Siegel shape parameter. Controls where the curvature loading `g(τ)` peaks — peak maturity ≈ λ·ln 2 ≈ 3.5 years at λ = 5. Must be the same value across `LiabilityModel`, `NominalBondSleeve`, `CreditBondSleeve`, and `LinkerSleeve` for duration matching to be internally consistent.

**Methods:**

| Method | Signature | Description |
| -------- | ----------- | ------------- |
| `nominal_rate` | `(tau) → float` | NS nominal spot rate at maturity τ |
| `real_rate` | `(tau) → float` | NS real spot rate at maturity τ |
| `discount_factor` | `(tau, kind) → float` | Continuous-compounding DF |
| `spot_curve` | `(maturities, kind="nominal") → np.ndarray` | Vectorised spot rates |

---

### `LiabilityModel`

```python
LiabilityModel(schedule: LiabilitySchedule, lambda_: float = 5.0)
```

**Methods:**

| Method | Signature | Description |
| -------- | ----------- | ------------- |
| `present_value` | `(state) → float` | PV of all cash flows |
| `duration` | `(state, bump=1e-4) → float` | Modified duration (years) via bump-and-reprice |
| `inflation_pv01` | `(state, bump=1e-4) → float` | % PV change per 1 bp breakeven move |
| `curvature_pv01` | `(state, bump=1e-4) → float` | % PV change per 1 bp increase in β₂ |
| `cashflow_pv_breakdown` | `(state) → list[dict]` | Per-flow PV decomposition |

`duration` applies a parallel shift to both nominal and real yield curves. `inflation_pv01` lowers the real rate by `bump` while raising inflation by `bump` (holding nominal rates fixed), which increases the breakeven and therefore raises the PV of real liabilities. `curvature_pv01` bumps the `curvature` state variable; for long-duration pension liabilities this is typically small and negative because the curvature loading `g(τ) → 0` at long maturities.

---

## 2.7 Asset Sleeves (`assets/`)

All sleeves inherit from `AssetSleeve` and implement a single method:

```python
def period_return(state_t: MacroState, state_t1: MacroState, dt: float = 1.0) -> float
```

which returns the total return earned over the period `[t, t+dt]`.

---

### `CashSleeve` (`assets/cash.py`)

```python
CashSleeve(name="Cash")
```

**Return model:**

```
r_cash = r_short(t) · dt
```

No duration risk. Earns the short rate at the start of the period.

---

### `NominalBondSleeve` (`assets/bonds.py`)

```python
NominalBondSleeve(
    name="NominalBond",
    duration=15.0,           # modified duration (years)
    maturity=None,           # average maturity for NS curve lookup; defaults to duration
    convexity=None,          # if None, uses duration² (par-bond approximation)
    lambda_=5.0,             # Nelson-Siegel shape parameter (must match LiabilityModel)
)
```

**Return model:**

```
r_bond = y(τ, t)·dt  −  D_mod·Δy(τ)  +  ½·C·(Δy(τ))²

where  y(τ, t) = YieldCurve(state_t).nominal_rate(maturity)   — full Diebold-Li NS rate
       Δy(τ)   = y(τ, t+1) − y(τ, t)                          — yield change at maturity τ
```

Using the full 3-factor NS rate means non-parallel moves (steepening, flattening, hump changes) are correctly reflected in the bond's carry and price change.

---

### `CreditBondSleeve` (`assets/bonds.py`)

```python
CreditBondSleeve(
    name="CreditBond",
    duration=10.0,
    maturity=None,            # average maturity for NS curve lookup; defaults to duration
    spread_duration=None,     # defaults to duration
    convexity=None,
    lambda_=5.0,
    seed=None,
    # --- Poisson jump parameters ---
    base_intensity=0.05,      # baseline jumps/yr at normal conditions
    spread_loading=10.0,      # intensity per unit excess spread above spread_normal
    recession_loading=2.0,    # intensity per unit of negative growth
    spread_normal=0.010,      # normal spread level (1.0 %) for excess calculation
    jump_mean=0.005,          # mean spread widening per jump (50 bps = 0.005)
    jump_vol=0.004,           # std dev of jump size (40 bps = 0.004)
)
```

**Return model:**

```
r_credit = carry + rate_repricing + spread_repricing + jump_impact

carry           = (y(τ) + cs) · dt
rate_repricing  = −D · Δy(τ) + ½ · C · (Δy(τ))²
spread_repricing= −D_s · (Δcs_VAR + Δcs_jump) + ½ · C · (Δcs_VAR + Δcs_jump)²

where  y(τ) = YieldCurve(state_t).nominal_rate(maturity)   — full Diebold-Li NS rate
       Δcs_VAR  = state_t1.credit_spread − state_t.credit_spread   — smooth VAR change
       Δcs_jump = Σᵢ Jᵢ,   Jᵢ ~ N(μ_J, σ_J²),   N ~ Poisson(λ · dt)
```

**Poisson jump intensity (state-dependent):**

```
λ(state) = λ_base
          + λ_cs  · max(0, cs − cs_normal)
          + λ_rec · max(0, −g)
```

Jumps are rare in calm markets and cluster in stressed regimes without requiring explicit regime labels — the macro state drives intensity automatically:

| Regime | cs | g | λ_eff | P(≥ 1 jump/yr) |
| -------- | ---- | --- | ------- | ---------------- |
| Def. Boom | 0.8 % | 3.5 % | 0.05 | ~5 % |
| Def. Bust | 2.0 % | −0.5 % | 0.16 | ~15 % |
| Inf. Boom | 1.2 % | 3.0 % | 0.07 | ~7 % |
| Inf. Bust | 3.0 % | −1.0 % | 0.27 | ~24 % |

At 7yr spread duration and 50bps mean jump, a single typical event costs ~3.5% return; a 2σ event (~130bps) costs ~9%. The method `sleeve._jump_intensity(state)` returns the current intensity for inspection.

---

### `LinkerSleeve` (`assets/linkers.py`)

```python
LinkerSleeve(
    name="Linker",
    real_duration=18.0,
    maturity=None,           # average maturity for NS real-curve lookup; defaults to real_duration
    real_convexity=None,     # if None, uses real_duration²
    lambda_=5.0,
)
```

**Return model:**

```
r_linker = r_real(τ, t)·dt  +  π(t)·dt  −  D_real·Δr_real(τ)  +  ½·C_real·(Δr_real(τ))²

where  r_real(τ, t) = YieldCurve(state_t).real_rate(maturity)   — full Diebold-Li real NS rate
       Δr_real(τ)   = r_real(τ, t+1) − r_real(τ, t)             — real yield change at maturity τ
       π             = state_t.inflation                          — CPI accrual
```

Reading the real yield from the full NS real curve (rather than just `state.real_rate`) means that steepening or humping of the real curve is correctly priced — this is most material for short-to-medium maturity linkers.

---

### `EquitySleeve` (`assets/growth.py`)

```python
EquitySleeve(
    name="Equity",
    drift=0.07,                      # long-run nominal total return p.a.
    growth_beta=0.60,                # sensitivity to growth deviation from trend
    inflation_beta=-0.30,            # negative: unexpected inflation hurts equities
    idio_vol=0.15,                   # annualised idiosyncratic volatility
    long_run_growth=0.025,           # trend growth for deviation calculation
    seed=None,
    # --- CAPE valuation mean-reversion ---
    cape=25.0,                       # starting CAPE ratio
    cape_fair=20.0,                  # long-run fair/equilibrium CAPE
    valuation_beta=0.05,             # return drag per unit of log(CAPE/cape_fair)
    payout_ratio=0.50,               # dividend payout ratio (for yield calculation)
    long_run_earnings_growth=0.04,   # LR nominal earnings growth rate
)
```

**Return model:**

```
r_equity = μ·dt  +  β_g·(g − ḡ)·dt  +  β_π·π·dt  +  σ·√dt·ε
         − β_val · log(CAPE / cape_fair) · dt

β_val > 0: expensive (CAPE > fair) → lower expected return; cheap → higher
```

**CAPE update (each period):**

```
price_return   = r − (payout_ratio / CAPE) · dt     [total return minus dividends]
log(CAPE_{t+1}) = log(CAPE_t) + price_return − LR_earnings_growth · dt
```

CAPE is clipped to [5, 100]. The property `sleeve.cape` returns the current value.

---

### `RealAssetSleeve` (`assets/growth.py`)

Real assets (infrastructure, direct property) modelled via dynamic cap-rate income and mean-reverting repricing. The `drift` parameter is superseded by the cap-rate income and is ignored at runtime.

```python
RealAssetSleeve(
    name="RealAssets",
    drift=0.06,                  # ignored — income comes from cap rate
    growth_beta=0.30,            # pro-cyclical demand sensitivity
    inflation_beta=0.70,         # direct CPI pass-through (rental growth etc.)
    idio_vol=0.10,               # return idiosyncratic vol (asset-specific)
    long_run_growth=0.025,
    seed=None,
    # --- cap-rate valuation ---
    initial_cap_rate=0.055,      # starting income yield (5.5 %)
    risk_premium=0.010,          # fair cap rate spread over long bond (1.0 %)
    cap_rate_reversion=0.20,     # O-U mean-reversion speed (yr⁻¹; ~5yr half-life)
    cap_rate_pass_through=0.50,  # fraction of long-rate change that flows into cap rate
    cap_rate_vol=0.008,          # annualised cap-rate innovation vol (80 bps)
    implied_duration=15.0,       # price sensitivity to 1 pp cap-rate move (years)
)
```

**Return decomposition:**

```
r = income + cap_gain + cycle + inflation + idio

income   = cap_rate · dt
cap_gain = −implied_duration · Δcap_rate
cycle    = growth_beta · (g − ḡ) · dt
inflation= inflation_beta · π · dt
idio     = idio_vol · √dt · ε
```

**Cap-rate dynamics:**

```
Δcap_rate = −κ · (cap_rate − cap_fair) · dt
          + φ · Δlong_rate
          + σ_cr · √dt · ε_cr

cap_fair  = long_rate + risk_premium
```

A rising cap rate → immediate capital loss (`−D · Δcap`) + higher future income. Cap rate is clipped to [0.5 %, 20 %]. The property `sleeve.cap_rate` returns the current value.

---

### `CommoditySleeve` (`assets/growth.py`)

Commodity futures modelled with a GSCI-consistent three-component decomposition plus a geopolitical supply-shock jump process.

```python
CommoditySleeve(
    name="Commodities",
    drift=0.0,                   # ignored — superseded by collateral + roll
    growth_beta=0.40,            # pro-cyclical demand sensitivity
    inflation_beta=1.20,         # very high — commodities often cause inflation
    idio_vol=0.25,               # annualised idiosyncratic vol
    long_run_growth=0.025,
    seed=None,
    # --- GSCI decomposition ---
    long_run_inflation=0.025,    # trend inflation for computing inflation deviation
    roll_yield=-0.010,           # contango drag (−1 % default; −3 % for crude oil)
    # --- geopolitical jump ---
    geo_intensity=0.10,          # geopolitical events per year (~1 per decade)
    geo_jump_mean=0.08,          # mean index return per event (8 %); Exp-distributed
)
```

**Return decomposition:**

```
r = collateral + excess + roll + jump

collateral = short_rate · dt               T-bill on posted futures margin
excess     = β_g·(g − ḡ)·dt  +  β_π·(π − π̄)·dt  +  σ·√dt·ε
roll       = roll_yield · dt               contango drag
jump       = Σᵢ Jᵢ,  Jᵢ ~ Exp(μ_geo),  N ~ Poisson(λ_geo·dt)
```

Key properties:
- **Long-run total return ≈ T-bill**: excess uses *deviations* from trend for both growth and inflation, so `E[excess] = 0` in equilibrium — consistent with the GSCI empirical finding that the long-run commodity futures return equals the collateral yield.
- **Stagflation hedge**: when `π > π̄` and `g < ḡ` (inflationary bust), the inflation term dominates and commodities deliver a positive return above the T-bill.
- **Deflation drag**: when `π < π̄` and `g < ḡ`, both factors are negative — commodities lose even on a T-bill-relative basis.
- **Geopolitical spikes**: one-sided positive jumps with exponential size distribution. A `geo_intensity=0.10` event (one per ~10 years) with `geo_jump_mean=0.08` (8%) models energy-supply shocks from Middle East conflicts, OPEC cuts, etc. Expected jump contribution: `λ × μ = 0.10 × 8% = 0.8%/yr`.

Typical regime outcomes (3 000-scenario average):

| Regime | Mean return | Driver |
| -------- | ------------- | -------- |
| Def. Boom (g=3.5%, π=1.5%) | ~3.5 % | collateral + small growth boost |
| Def. Bust (g=−0.5%, π=0.5%) | ~0 % | growth/inflation drag offset by collateral |
| Inf. Boom (g=3.0%, π=3.5%) | ~7 % | inflation deviation + growth + collateral |
| Inf. Bust (g=−1.0%, π=5.0%) | ~8 % | inflation overwhelms growth drag |

---

### `FXModel` (`assets/fx.py`) — Currency Overlay

Currency exposure is modelled as an **overlay**, not a separate asset sleeve.  Each sleeve carries an `fx_exposures` dict specifying the *unhedged* fraction of each currency after accounting for any hedging decision.  A single shared `FXModel` draws one return per currency per period and distributes the P&L across all sleeves.

**Architecture:**

```text
Sleeve.fx_exposures = {"USD": 0.35, "JPY": 0.07}   # unhedged fractions (user sets, hedge already deducted)

FXModel.step(state_t, state_t1)  →  {"USD": r_usd, "JPY": r_jpy, ...}   # one draw per currency

SubPortfolio: total_return(sleeve) = local_return + Σ exposure_i × fx_return_i
```

**Why overlay, not sleeve:** In reality a USD-denominated equity holding already earns the equity return; the currency effect is a property of that holding's denomination, not a separate asset. Modelling it as an overlay correctly separates the local asset return from the currency P&L and avoids double-counting.

**Return model per currency:**

```text
r = carry + fx_drift + macro_betas + ppp_correction + idio

carry          = carry_spread × dt
fx_drift       = fx_drift × dt
macro_betas    = inflation_loading × (π − π̄) × dt
               + growth_loading    × (g − ḡ) × dt
ppp_correction = −ppp_reversion × ppp_gap × dt
idio           = idio_vol × √dt × ε

ppp_gap_{t+1}  = (1 − ppp_reversion × dt) × ppp_gap_t  +  idio_t
```

`ppp_gap < 0` means the foreign currency is currently **undervalued** vs EUR (tailwind as the gap closes).

**Pre-calibrated currencies** (`FXModel.default()`):

| Code | carry | drift | ppp_gap₀ | idio_vol | Notes |
| --- | --- | --- | --- | --- | --- |
| USD | +1.5 % | −1.0 % | 0 % | 10 % | Dollar-debasement bias |
| GBP | +0.5 % | −0.5 % | −5 % | 9 % | Slight post-Brexit undervaluation |
| CAD | +0.5 % | 0 % | 0 % | 8 % | Commodity-linked |
| AUD | +1.0 % | 0 % | 0 % | 11 % | Growth-positive, resource exporter |
| CHF | −0.5 % | +0.5 % | 0 % | 8 % | Safe haven; risk-off rally |
| JPY | −0.8 % | +0.3 % | −25 % | 9 % | BOJ-managed; deeply undervalued vs PPP |
| CNY | +0.5 % | +0.5 % | −20 % | 5 % | PBOC-managed; structural appreciation |
| HKD | +1.5 % | 0 % | 0 % | 3 % | USD peg → near-zero idio vol |
| TWD | +0.5 % | +0.5 % | −20 % | 7 % | CA surplus; semiconductor cycle |
| KRW | +1.5 % | +0.3 % | −15 % | 10 % | Export economy; open capital account |
| SGD | +0.5 % | +0.5 % | −10 % | 6 % | MAS managed appreciation |
| THB | +1.0 % | 0 % | −15 % | 12 % | Tourism + manufacturing |
| INR | +3.0 % | −1.5 % | −10 % | 7 % | High carry; RBI-managed vol |

**Asian undervaluation thesis:** JPY, CNY, TWD, KRW, SGD, THB, and INR all carry a negative `initial_ppp_gap`, encoding the view that they are structurally cheap relative to EUR on PPP terms.  Diversification into Asian assets therefore benefits from both local asset returns and slow (5–12 year) real currency appreciation.

**Usage:**

```python
from assets.fx import FXModel

# FXModel is created automatically in LifecycleSimulator.run() — no manual wiring needed.
# Set unhedged exposures on each sleeve when building specs:

eq = EquitySleeve("GlobalEquity", ...)
# MSCI World: 70 % USD gross, 50 % hedge → 35 % unhedged; JPY fully unhedged at 7 %
eq.fx_exposures = {"USD": 0.35, "JPY": 0.07, "GBP": 0.05, "CNY": 0.03, "TWD": 0.01}

co = CommoditySleeve("Commodities", ...)
co.fx_exposures = {"USD": 0.40}   # commodities priced in USD; no hedge

# Fully EUR-hedged sleeve — just leave fx_exposures empty (default):
cr = CreditBondSleeve("IG_Credit", ...)   # no fx_exposures needed

# Use a subset of currencies if you only need a few:
fx = FXModel.subset(["USD", "JPY", "GBP"], seed=42)
```

To model a **fully currency-hedged** portfolio, leave all `fx_exposures` dicts empty (the default).

---

### `ChinaGovernmentBondSleeve` (`assets/em_bonds.py`)

Models **local-currency total return** on China central government bonds (CGBs), with yield dynamics calibrated to PBOC-managed market conditions.  Currency translation from CNY to EUR is applied separately via the FXModel overlay (planned).

```python
from assets.em_bonds import ChinaGovernmentBondSleeve

ChinaGovernmentBondSleeve(
    name="CGB",
    duration=7.0,            # modified duration; 10Y CGB ≈ 7–8 yr
    initial_yield=0.023,     # starting yield; ~2.3 % for 10Y CGB in 2024–25
    long_run_yield=0.025,    # O-U equilibrium; consistent with PBOC 2–3 % inflation target
    yield_reversion=0.25,    # κ = 0.25 → ~4-yr half-life (faster than EUR at κ ≈ 0.10)
    global_rate_beta=0.25,   # pass-through from EUR long rate (partial; capital controls)
    idio_yield_vol=0.005,    # ~50 bp/yr idio vol (vs ~100 bp for EUR govts)
    seed=None,
)
```

**Yield dynamics (O-U with global pass-through):**

```text
Δy = −κ × (y_t − ȳ) × dt
   + β_global × Δy_EUR × dt
   + σ × √dt × ε

r  = y_t × dt  −  D × Δy  +  ½ × C × Δy²
```

| Parameter | CGB (PBOC-managed) | EUR Govt (ECB) | Rationale |
| --------- | ------------------ | -------------- | --------- |
| κ (reversion) | 0.25 (4-yr ½-life) | ~0.10 (7-yr ½-life) | PBOC active curve management |
| σ (idio vol) | 50 bp/yr | ~100 bp/yr | Suppressed volatility regime |
| β_global | 0.25 | 1.0 (by construction) | Partial integration via capital controls |
| Long-run yield ȳ | 2.5 % | driven by VAR | High savings, structural low rates |

**Asian undervaluation thesis:**  CGBs provide real-yield exposure to an economy where nominal yields (~2.3%) approximate real yields given near-zero inflation — a structurally different profile from EUR or USD bonds.  Combined with a CNY appreciation overlay (via FXModel), they offer diversification against European financial repression scenarios.

**No default allocation** is set in the current configs; include in `rsp_specs` or `lhp_specs` when ready:

```python
SleeveSpec(ChinaGovernmentBondSleeve("CGB", seed=42), weight=0.05)
```

**Extension:**  `assets/em_bonds.py` is designed to be extended.  Future additions — `IndiaGovernmentBondSleeve`, `KoreaTreasurySleeve`, `BrazilGovernmentBondSleeve` — follow the same O-U + global-pass-through pattern with market-specific κ and σ calibrations.

---

## 2.8 Portfolio Construction (`portfolio/portfolio.py`)

### `SleeveSpec`

```python
@dataclass
class SleeveSpec:
    sleeve: AssetSleeve
    weight: float           # intra-sub-portfolio weight; must sum to 1.0 per sub-portfolio
```

---

### `SubPortfolio`

Holds a list of `SleeveSpec` objects and tracks their individual values. Not constructed directly — use `Portfolio`.

**Methods:**

| Method | Description |
| -------- | ------------- |
| `step(state_t, state_t1, dt) → float` | Advance all sleeves; returns value-weighted return |
| `rebalance(target_value=None)` | Reset sleeve values to target weights |
| `sleeve_weights() → dict` | Current (possibly drifted) weights |

---

### `Portfolio`

```python
Portfolio(
    lhp_specs:           list[SleeveSpec],
    rsp_specs:           list[SleeveSpec],
    initial_value:       float,
    hedge_ratio:         float = 0.60,    # fraction of total in LHP; [0, 1]
    rebalance_frequency: int   = 1,       # rebalance every N steps; 0 = never
)
```

**Properties:**

| Property | Description |
| ---------- | ------------- |
| `total_value` | Combined market value |
| `lhp_value` | LHP sub-portfolio value |
| `rsp_value` | RSP sub-portfolio value |
| `effective_hedge_ratio` | Current LHP / total (drifts between rebalances) |

**Methods:**

| Method | Signature | Description |
| -------- | ----------- | ------------- |
| `step` | `(state_t, state_t1, dt) → float` | Advance one period; returns portfolio return |
| `summary` | `() → dict` | Snapshot of all values and weights |

At each `rebalance_frequency` step, the portfolio resets to `hedge_ratio` between LHP and RSP, and each sub-portfolio resets to its `SleeveSpec` weights.

---

## 2.9 Simulation Engine (`simulation/engine.py`)

### `ScenarioResult`

Stores the full time series for one simulated path.

```python
@dataclass
class ScenarioResult:
    scenario_id:      int
    steps:            list[int]
    macro_states:     list[MacroState]
    portfolio_values: list[float]
    liability_pvs:    list[float]
    funding_ratios:   list[float]
    period_returns:   list[float]   # length n_steps; NaN prepended at t=0
    regime_labels:    list | None   # list[RegimeLabel] if regime_paths was passed
```

`to_dataframe()` flattens to a tidy DataFrame with all fields as columns.

---

### `SimulationEngine`

```python
SimulationEngine(
    liability_model:       LiabilityModel,
    portfolio_factory:     Callable[[], Portfolio],
    dt:                    float = 1.0,
    contribution_schedule: dict[int, float] | None = None,
)
```

The `portfolio_factory` is called once per scenario, ensuring each scenario starts from an identical, independent portfolio with no state leakage between scenarios.

The `contribution_schedule` maps step indices to cash amounts. Positive values add assets (contributions), negative values remove them (benefit payments). The adjustment is applied proportionally across LHP and RSP before the step's return is computed.

**Methods:**

| Method | Signature | Description |
| -------- | ----------- | ------------- |
| `run_scenario` | `(path, scenario_id=0, regime_path=None) → ScenarioResult` | Single path |
| `run_stress` | `(stress: StressScenario) → ScenarioResult` | Convenience wrapper |
| `run_all` | `(paths, regime_paths=None, verbose=False) → pd.DataFrame` | All paths → concatenated DataFrame |

---

## 2.10 Analytics (`analytics/metrics.py`)

All functions operate on the tidy `pd.DataFrame` produced by `SimulationEngine.run_all`.

---

### `FundingRatioStats`

```python
@dataclass
class FundingRatioStats:
    step:               int
    n_scenarios:        int
    mean:               float
    median:             float
    std:                float
    p5:                 float     # 5th percentile
    p25:                float
    p75:                float
    p95:                float     # 95th percentile
    prob_deficit:       float     # P(FR < 1)
    prob_fully_funded:  float     # P(FR ≥ 1)
    expected_shortfall: float     # E[FR | FR < 1]
```

`print(stats)` produces a formatted multi-line summary.

---

### Aggregation functions

| Function | Signature | Description |
| ---------- | ----------- | ------------- |
| `funding_ratio_stats` | `(df, step) → FundingRatioStats` | Cross-sectional FR summary at one step |
| `fan_chart_data` | `(df, steps=None, percentiles=(5,25,50,75,95)) → pd.DataFrame` | Percentile bands over time |
| `compute_var_cvar` | `(df, step, column="funding_ratio", confidence=0.95) → (var, cvar)` | Left-tail VaR and CVaR |
| `duration_gap` | `(liab_dur, port_dur, liab_pv, port_val) → float` | Interest rate hedge gap (years) |
| `period_return_stats` | `(df) → pd.DataFrame` | Mean, std, skew, kurtosis of period returns |

**`fan_chart_data` output columns:** `step, mean, p5, p25, p50, p75, p95`

**`duration_gap`:**

```
gap = D_assets × (A/L) − D_liabilities
```

A gap of zero means rate risk is fully hedged. A positive gap means the portfolio is longer than the liability (benefits from rising rates).

---

### Regime-aware analytics (require `regime` column in DataFrame)

| Function | Signature | Description |
| ---------- | ----------- | ------------- |
| `funding_ratio_by_regime` | `(df, step) → pd.DataFrame` | FR stats split by regime at one step |
| `regime_transition_heatmap_data` | `(df) → pd.DataFrame` | Empirical transition frequencies (pivot table) |
| `fan_chart_by_regime` | `(df, steps=None) → dict[str, pd.DataFrame]` | Fan chart data per regime |

These raise `ValueError` if the `regime` column is absent. The column is only present when `run_all` is called with `regime_paths` from a `RegimeSwitchingEngine`.

---

## 2.11 Return Models — Mathematical Reference

### State vector

All asset return models reference the seven-dimensional macro state:

```
X = [short_rate, long_rate, real_rate, inflation, growth, credit_spread, curvature]
```

### Cash

```
r_cash = r_s · dt
```

### Yield curve (Diebold-Li Nelson-Siegel)

```
r_nominal(τ) = L + S · f(τ) + C · g(τ)

L = long_rate,   S = short_rate − long_rate,   C = curvature (β₂)
f(τ) = (1 − e^{−τ/λ}) / (τ/λ)
g(τ) = f(τ) − e^{−τ/λ}

r_real(τ) = r_nominal(τ) + (real_rate − long_rate)
```

### Nominal bond

```
r_bond = y(τ) · dt  −  D · Δy(τ)  +  ½ · C_conv · (Δy(τ))²

y(τ)  = YieldCurve.nominal_rate(maturity)   — full 3-factor NS rate
Δy(τ) = yield change at maturity τ over period
D     = modified duration
C_conv = convexity  (≈ D² for par bond)
```

### Credit bond (with Poisson spread jumps)

```
r_credit = (y(τ) + cs) · dt  −  D · Δy(τ)  −  D_s · Δcs_total  +  convexity terms

Δcs_total = Δcs_VAR + Δcs_jump

Δcs_VAR  = state_t1.credit_spread − state_t.credit_spread   — smooth VAR change
Δcs_jump = Σᵢ Jᵢ,   Jᵢ ~ N(μ_J, σ_J²),   N ~ Poisson(λ · dt)

λ(state) = λ_base  +  λ_cs · max(0, cs − cs_normal)  +  λ_rec · max(0, −g)
```

### Inflation-linked bond

```
r_linker = r_real(τ) · dt  +  π · dt  −  D_real · Δr_real(τ)  +  ½ · C_real · (Δr_real(τ))²

r_real(τ) = YieldCurve.real_rate(maturity)   — full 3-factor NS real rate
π          = realised inflation (state_t.inflation)
D_real     = real modified duration
Δr_real(τ) = real yield change at maturity τ
```

### Equity (with CAPE mean-reversion)

```
r_equity = μ · dt  +  β_g · (g − ḡ) · dt  +  β_π · π · dt  +  σ · √dt · ε
         − β_val · log(CAPE / CAPE_fair) · dt

μ      = long-run drift
β_val  = valuation sensitivity (return drag when CAPE > fair, boost when cheap)
```

CAPE update each period:

```
d log(CAPE) = (r − payout_ratio / CAPE · dt) − LR_earnings_growth · dt
            = price_return − earnings_growth
```

### Real assets (with cap-rate mean-reversion)

```
r_real = income + cap_gain + cycle + inflation + idio

income    = cap_rate · dt
cap_gain  = −D_impl · Δcap_rate
cycle     = β_g · (g − ḡ) · dt
inflation = β_π · π · dt
idio      = σ · √dt · ε

Δcap_rate = −κ · (cap_rate − cap_fair) · dt  +  φ · Δlong_rate  +  σ_cr · √dt · ε_cr
cap_fair  = long_rate + risk_premium

D_impl    = implied duration (price sensitivity to cap rate, years)
κ         = cap_rate mean-reversion speed
φ         = cap_rate pass-through from long-rate moves
```

### Commodities (GSCI decomposition + geopolitical jumps)

```
r = collateral + excess + roll + jump

collateral = r_s · dt                                        T-bill on margin
excess     = β_g · (g − ḡ) · dt  +  β_π · (π − π̄) · dt  +  σ · √dt · ε
roll       = roll_yield · dt                                 contango drag
jump       = Σᵢ Jᵢ,  Jᵢ ~ Exp(μ_geo),  N ~ Poisson(λ_geo · dt)

π̄ = long_run_inflation   (excess uses deviations, so E[excess] = 0 in equilibrium)
```

Long-run `E[r] ≈ r_s + roll + λ_geo · μ_geo` — total return ≈ T-bill plus jump risk
premium minus contango drag, consistent with GSCI empirical evidence.

### Liability present value

```
PV = Σ_i  amount_i · DF(τ_i, kind_i)

DF(τ, "nominal") = exp(−r_nominal(τ) · τ)
DF(τ, "real")    = exp(−r_real(τ)    · τ)

r_nominal(τ) and r_real(τ) use the full Diebold-Li NS formula above,
so all three curve factors (level, slope, curvature) affect the PV.
```

### VAR(1) transition

```
X(t+1) = X̄ + Φ · (X(t) − X̄) + L · ε(t+1)

L = chol(Σ · dt)
ε ~ N(0, I)
```

For the regime-switching model, `X̄`, `Φ`, and `Σ` all depend on the regime active at `t+1`:

```
regime(t+1) ~ Categorical(T[regime(t), :])
X(t+1)      = X̄_{r(t+1)} + Φ_{r(t+1)} · (X(t) − X̄_{r(t+1)}) + L_{r(t+1)} · ε
```

---

## 2.12 Extension Points

The framework is designed to be extended one layer at a time without touching the other layers.

### Add a new asset class

Subclass `AssetSleeve` in `assets/` and implement `period_return`. Then include it in `lhp_specs` or `rsp_specs` when constructing a `Portfolio`.

```python
from assets.base import AssetSleeve
from scenarios.engine import MacroState

class FXSleeve(AssetSleeve):
    def period_return(self, state_t, state_t1, dt=1.0):
        ...
```

### Add a new stress scenario

Add a class method to `StressScenario` following the pattern of `parallel_rate_shock`, `stagflation`, or `deflation`.

### Add a fifth regime

Add a new `RegimeLabel` integer, add its `VARParams` to `params_by_regime`, and extend the transition matrix to 5×5.

### Add glide-path / dynamic de-risking logic

`SimulationEngine.run_scenario` has access to the portfolio's `effective_hedge_ratio` at every step. A funding-ratio-triggered glide path — raising `hedge_ratio` as the FR crosses threshold levels — can be wired in there without touching any other module.

```python
# Sketch: inside a custom run_scenario
if portfolio.effective_hedge_ratio < 0.80 and fr > 0.95:
    portfolio.lhp.rebalance(target_value=portfolio.total_value * 0.80)
    portfolio.rsp.rebalance(target_value=portfolio.total_value * 0.20)
```

### Add stochastic credit spreads with jump risk

The current `CreditBondSleeve` uses the smooth VAR credit spread. Real IG spreads exhibit jumps (2008, 2020). Add a Poisson jump term with per-regime intensity and size calibrated to the regime — the inflationary bust regime gets the fattest jump distribution.

### Add mortality / longevity risk

`LiabilitySchedule` uses fixed cash flows. To model uncertain payment timing, add a `longevity_shock` state variable to `MacroState` (weakly correlated with growth) and apply it as a multiplicative adjustment to cash flow amounts in `LiabilityModel.present_value`. This is the largest unmodelled risk for most DB pension schemes.

### Calibrate to historical data

Replace the hardcoded `VARParams` defaults by fitting a VAR(1) to your time series:

```python
# Example using statsmodels
from statsmodels.tsa.vector_ar.var_model import VAR
model  = VAR(historical_df[list(MacroState._FIELDS)])   # 7-column DataFrame
result = model.fit(maxlags=1)

params = VARParams(
    long_run_mean = result.coefs_exog.squeeze(),
    phi           = result.coefs[0],
    sigma         = result.sigma_u,
)
```

For regime-switching, use the EM algorithm (Hamilton 1989) to estimate per-regime VARs and the transition matrix jointly from historical data.  For `EquitySleeve`, calibrate `cape_fair` and `valuation_beta` from a long-run Shiller CAPE regression; for `RealAssetSleeve`, calibrate `risk_premium` and `cap_rate_reversion` from MSCI Real Estate or NCREIF data; for `CommoditySleeve`, calibrate `roll_yield` from historical GSCI roll return series and `geo_intensity`/`geo_jump_mean` from a catalogue of supply-shock events.

### Use sub-annual time steps

Set `dt` consistently across the engine and the simulation:

```python
engine = MacroScenarioEngine(params, initial, dt=1/12)   # monthly
sim    = SimulationEngine(liability, make_portfolio, dt=1/12)
paths  = engine.simulate(n_steps=240, n_scenarios=1_000)  # 20 years × 12
```

Asset return models scale automatically via the `dt` parameter.

---

## 2.13 Participant Lifecycle Model (`participant/`)

Implements a Dutch WTP-style individual lifecycle pension model. Each participant is simulated through a single macro path and proceeds through:

- **Accumulation** (entry → retirement): contributions grow in a levered cohort portfolio.
- **Decumulation** (retirement → death): a *variabel pensioen* with annual adjustments and a solidarity reserve.

Run the demo:

```bash
python main_participant.py
```

---

### `SalaryProfile` (`participant/salary.py`)

Projects pensionable pay over a working life.

| Parameter | Default | Description |
| ----------- | --------- | ------------- |
| `base_salary` | 50 000 | Salary at entry age (real, today's €) |
| `real_growth` | 0.005 | Annual real productivity growth |
| `promotion_jumps` | `{30: 0.15, 40: 0.20}` | One-off multiplicative salary jumps at specified ages |

```python
profile = SalaryProfile(base_salary=50_000, real_growth=0.005,
                        promotion_jumps={30: 0.15, 40: 0.20})
nominal = profile.nominal_salary_at(age=40, entry_age=25,
                                    cumulative_inflation=0.25)
```

---

### `CohortAllocation` and `default_cohort_allocations()` (`participant/lifecycle.py`)

Defines the Dutch WTP asset-weight glide path. Weights are **actual portfolio asset weights** (not return-allocation weights). Each 10-year age band specifies the RSP and LHP fractions; anything above 100 % combined is funded by leverage.

| Age band | RSP | LHP | Total | Leverage |
| -------- | --- | --- | ----- | -------- |
| 25–34 | 120 % | 0 % | 120 % | 20 % |
| 35–44 | 100 % | 0 % | 100 % | 0 % |
| 45–54 | 80 % | 20 % | 100 % | 0 % |
| 55–64 | 70 % | 30 % | 100 % | 0 % |
| 65–74 | 50 % | 50 % | 100 % | 0 % |
| 75–84 | 20 % | 80 % | 100 % | 0 % |
| 85–94 | 20 % | 80 % | 100 % | 0 % |
| 95–104 | 20 % | 80 % | 100 % | 0 % |

**Leverage cost** = `leverage_fraction × short_rate × dt` is deducted from the period return each step.

---

### `RetirementOptions` (`participant/lifecycle.py`)

At-retirement conversion choices. All currently default to no adjustment (stubs for future implementation):

| Parameter | Default | Description |
| ----------- | --------- | ------------- |
| `lump_sum_fraction` | 0.0 | Fraction of pot taken as cash at retirement |
| `high_low_option` | False | High-then-low pension conversion |
| `partner_exchange_fraction` | 0.0 | Fraction exchanged for partner's survivor pension |

---

### `ParticipantConfig` (`participant/lifecycle.py`)

Full specification for one participant's lifecycle.

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `entry_age` | 25 | Age at scheme entry |
| `retirement_age` | 68 | Age at retirement (accumulation ends) |
| `death_age` | 90 | Age at death (deterministic) |
| `contribution_rate` | 0.20 | Annual contribution as fraction of pensionable salary |
| `salary_profile` | `SalaryProfile()` | See above |
| `cohort_allocations` | `default_cohort_allocations()` | Glide-path table |
| `retirement_options` | `RetirementOptions()` | At-retirement choices |
| `lhp_specs` | `[]` | `list[SleeveSpec]` for the LHP sub-portfolio; intra-weights must sum to 1.0 |
| `rsp_specs` | `[]` | `list[SleeveSpec]` for the RSP sub-portfolio; intra-weights must sum to 1.0 |
| `lambda_` | 5.0 | Diebold-Li shape parameter used in the annuity factor computation |
| `adjustment_smoothing_years` | 3 | Years over which pension adjustments are spread |
| `adjustment_floor` | −0.03 | Minimum annual pension adjustment (−3 %) |
| `solidarity_reserve_rate` | 0.05 | Fraction of upward adjustments ceded to solidarity pool |
| `career_average_indexation` | `"wage"` | Middelloon revaluation basis: `"wage"` (CPI × real-wage drift — *geïndexeerd middelloon*, default), `"price"` (CPI only), `"none"` (raw nominal average — legacy, overstates RR) |

Both `lhp_specs` and `rsp_specs` must be provided (non-empty) before calling `run()`.  Sleeve specs are **deepcopied** at the start of each `run()` call so that stateful sleeve properties (CAPE, cap-rate, PPP gap) do not leak between scenarios.

---

### `LifecycleSimulator` (`participant/lifecycle.py`)

Runs a single participant through a macro path. The same simulator instance can be reused across many paths — sleeve state is isolated per `run()` call via deepcopy.

```python
from participant.lifecycle import ParticipantConfig, LifecycleSimulator, default_cohort_allocations
from main_participant import build_lhp_specs, build_rsp_specs

config = ParticipantConfig(
    entry_age=25, retirement_age=68, death_age=90,
    lhp_specs=build_lhp_specs(),
    rsp_specs=build_rsp_specs(),
)
sim    = LifecycleSimulator(config)
result = sim.run(path)             # path is a list[MacroState] of length ≥ 66
result = sim.run(path, run_seed=42)  # optional: re-seeds sleeve RNGs for this run

print(f"Replacement ratio : {result.replacement_ratio:.1%}")
print(f"Pot at retirement : €{result.pot_path[43]:,.0f}")
```

The optional `run_seed` parameter re-seeds every sleeve's internal RNG after deepcopy using a name-derived offset computed with a **fixed SHA-256 digest** (`_stable_offset()`), ensuring bit-for-bit reproducibility across processes and machines regardless of `PYTHONHASHSEED`. (Earlier versions used Python's built-in `hash()`, which is process-salted and caused ~0.3 % run-to-run drift.)

**`ParticipantResult` fields:**

| Attribute | Description |
| --------- | ----------- |
| `pot_path` | Pension pot (€) at each annual step, length = total years + 1 |
| `pension_path` | Annual pension (€) paid each decumulation year |
| `real_pension_path` | Pension deflated to entry-year € (÷ cumulative CPI) — shows real purchasing power |
| `contribution_path` | Annual contribution (€) paid each accumulation year |
| `adjustment_path` | Annual adjustment factor applied each decumulation year (1.0 = no change) |
| `solidarity_reserve_path` | Cumulative solidarity pool contributions (€) |
| `final_pot` | Residual pot at `death_age` |
| `pension_at_retirement` | Initial annual pension set at the point of retirement |
| `career_avg_salary` | Career-average pensionable salary revalued to retirement-year terms per `career_average_indexation` (the *geïndexeerd middelloon* denominator) |
| `career_avg_salary_nominal` | Raw un-revalued nominal average — retained for audit / transparency |
| `replacement_ratio` | `pension_at_retirement / career_avg_salary` — the Dutch 70 % ambition benchmark, on a wage-indexed basis by default |
| `pot_exhausted_at` | 0-indexed decumulation step when pot first hits zero; `None` if pot survives to `death_age` |

---

### Annual adjustment mechanism

Each decumulation year the simulator computes:

```
target_pension  = pot / annuity_factor(current_age, yield_curve)
raw_adj         = (target_pension − current_pension) / current_pension
annual_slice    = raw_adj / adjustment_smoothing_years
applied_adj     = sum(last 3 slices)          # capped at floor = −3 %
solidarity_cont = solidarity_reserve_rate × max(0, raw_adj) × current_pension
current_pension = current_pension × (1 + applied_adj)
```

The **annuity factor** discounts €1/year at the live real Diebold-Li yield curve, so both rising rates (lower factor → higher pension) and falling rates (higher factor → lower pension) feed through automatically.

---

### Mathematical summary — lifecycle returns

RSP and LHP returns are generated by the same asset sleeve models used in the fund-level simulation (see §2.7 and §2.11). The lifecycle model applies a two-level weight structure:

**Period return (accumulation and decumulation):**

```
r_pot = rsp_w · r_RSP + lhp_w · r_LHP − leverage_fraction · short_rate

r_RSP = SubPortfolio(rsp_specs).step(state_t, state_t1)   — weighted return across all RSP sleeves
r_LHP = SubPortfolio(lhp_specs).step(state_t, state_t1)   — weighted return across all LHP sleeves
```

The default RSP composition (intra-RSP weights):

| Sleeve | Weight | Key return driver |
| ------ | ------ | ----------------- |
| GlobalEquity | 50 % | CAPE mean-reversion + macro betas + FX overlay (USD 35 %, JPY 7 %, GBP 5 %, CNY 3 %, …) |
| RealAssets | 25 % | Cap-rate income + inflation pass-through + FX overlay (USD 15 %) |
| IG Credit | 15 % | Carry + Poisson spread jumps + FX overlay (USD 5 %) |
| Commodities | 10 % | Collateral + inflation deviation + geo jumps + FX overlay (USD 40 %) |

The default LHP composition (intra-LHP weights):

| Sleeve | Weight | Key return driver |
| ------ | ------ | ----------------- |
| LongGovt | 50 % | 20yr nominal bond (Diebold-Li NS) |
| ILG | 40 % | 18yr real-duration linker + CPI accrual |
| LHPCash | 10 % | Short rate |

Each sleeve's internal state (CAPE, cap-rate, PPP gap) is **deepcopied** per `run()` call and optionally re-seeded via `run_seed`, so scenarios are fully independent.

**Annuity factor** (Diebold-Li real yield, deterministic survival):

```
A(t, T) = Σ_{s=1}^{T−t} exp(−r_real(s) · s)

r_real(s) = YieldCurve(state_t, lambda_=5.0).real_rate(s)
```

Rising real rates → smaller annuity factor → higher pension per € of pot; falling real rates → reverse.

**Pension at retirement:** `P₀ = pot_T / A(T, death_age)`

**Middelloon replacement ratio:** `RR = P₀ / career_avg_salary`  (Dutch 70 % ambition benchmark)

**Solidarity reserve cession:** `s_t = ρ · max(0, ΔP/P) · P_t`,  `ρ = solidarity_reserve_rate`

---

## 2.14 Country Mosaic — Asia Re-anchoring (`allocations/`)

The `allocations/` package implements a **bottom-up, country-level equity sleeve** that replaces the single cap-weighted `GlobalEquity` block with per-country `EquitySleeve` instances, each carrying its own §3.1 drift/CAPE calibration and FX overlay exposure.

### Motivation

A EUR-based pension fund that holds MSCI-ACWI-like equities (~60 % USA) has concentrated exposure to US valuation risk (CAPE ~40 vs fair value ~27.5) and dollar-debasement drift. The Asia re-anchoring proposal tilts toward markets that are demographically young, institutionally reforming, and structurally cheap on CAPE terms — while explicitly capping China at 6 % (governance discount) and leaving Asian FX unhedged to capture the PPP undervaluation tailwind documented in the FX model.

### `country_inputs.py` — per-market calibration

Each country entry provides the inputs to `EquitySleeve` and the FXModel:

| Market | drift (§3.1 r_nom) | CAPE now | CAPE anchor | FX key | Data |
| --- | ---: | ---: | ---: | --- | --- |
| USA | 4.0 % | 40.1 | 27.5 | USD | §3.1 Table 1a |
| Europe | 7.0 % | 17.0 | 17.0 | — (EUR base) | §3.1 Table 1a |
| Japan | 6.0 % | 24.0 | 22.0 | JPY | §3.1; ROE-convergence upside |
| China | 8.4 % | 11.0 | 14.0 | CNY | §3.1 |
| India | 6.4 % | 28.0 | 24.0 | INR | §3.1 |
| Korea | 7.1 % | 12.0 | 16.0 | KRW | §3.1; Value-Up re-rating |
| Taiwan | 5.6 % | 21.0 | 19.0 | TWD | §3.1 |
| Indonesia | 8.8 % | 17.0 | 18.0 | THB* | §3.1 |
| Vietnam† | 9.0 % | 13.0 | 16.0 | THB* | Proxy — illustrative |
| Singapore† | 6.0 % | 14.0 | 15.0 | SGD | Proxy — illustrative |

`*` FXModel has no IDR or VND; THB is used as the nearest managed-float ASEAN proxy.
`†` Proxy markets (`real=False`); not in §3.1. Use `proxy_markets()` to list them.

`drift` is the **local-currency** nominal expected return. FX appreciation is handled separately by the FXModel overlay (the `fx` key), never folded into `drift`.

### `mosaic.py` — sleeve builder and canonical allocations

```python
from allocations import build_equity_specs, PROPOSED_EQUITY

# Returns list[SleeveSpec] — drop straight into the RSP equity block
specs = build_equity_specs(PROPOSED_EQUITY, seed=1, hedge_developed=0.5)
```

`hedge_developed=0.5` hedges 50 % of USD exposure; Asian FX is left fully unhedged (the PPP-undervaluation thesis). JPY is 85 % unhedged (deeply undervalued, BOJ normalisation).

**Four canonical allocations:**

| Name | Asia (incl. Japan) | China | USA | Notes |
| --- | ---: | ---: | ---: | --- |
| `CURRENT_EQUITY` | ~25 % | 5.5 % | 60 % | MSCI ACWI-like benchmark |
| `PROPOSED_EQUITY` | ~40 % | 6.0 % | 37 % | Article §13.6 anchor |
| `PROPOSED_CONSERVATIVE` | ~35 % | 5.0 % | 42 % | Reviewer robustness check |
| `PROPOSED_TIGHT_CHINA` | ~40 % | 3.0 % | 36 % | China cap tightened to 3 % |

### Running the comparison

```bash
# All four allocations on shared macro paths (paired comparison):
python reproduce_participant.py

# Equity-only Current vs Proposed A validation:
python -m examples.run_equity_only

# Static allocation preview (no Monte Carlo):
python -m allocations.preview

# Invariant tests:
pytest tests/                        # or: python -m tests.test_invariants
```

### Wiring into the RSP

`examples/run_equity_only.py` shows the standard pattern: swap only the equity block, hold real assets / credit / commodities fixed.

```python
from allocations import build_equity_specs, PROPOSED_EQUITY
from examples.run_equity_only import config_with

cfg = config_with(PROPOSED_EQUITY)   # ParticipantConfig with mosaic equity
results = sim.run(path, run_seed=42)
```

See `docs/REPRODUCE.md` for a full reproduce runbook and `docs/INPUT_PROVENANCE.md` for the source mapping of every input figure.
