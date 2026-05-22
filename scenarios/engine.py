"""
Macro Scenario Engine
=====================
Generates correlated macro scenarios via a Vector Auto-Regression (VAR(1)) process.

State vector  X = [short_rate, long_rate, real_rate, inflation, growth,
                   credit_spread, curvature]

The seventh variable, ``curvature``, is the β₂ factor from the Diebold-Li
(2006) dynamic Nelson-Siegel model.  It controls the hump (or inversion) of
the yield curve at medium maturities and is simulated jointly with all other
macro variables so that curve-shape risk is captured in scenarios.

VAR(1) transition:

    X(t+1) = X̄ + Φ·(X(t) − X̄) + chol(Σ·dt)·ε,    ε ~ N(0, I)

Where
  X̄   long-run mean (equilibrium)
  Φ    persistence / mean-reversion matrix (eigenvalues < 1 for stationarity)
  Σ    annualised innovation covariance matrix

Yield curve (Diebold-Li / Nelson-Siegel):

    r(τ) = L + S·f(τ) + C·g(τ)

    f(τ) = (1 − e^{−τ/λ}) / (τ/λ)          — slope loading
    g(τ) = f(τ) − e^{−τ/λ}                  — curvature loading

    L = long_rate   (level:     lim_{τ→∞} r(τ))
    S = short_rate − long_rate  (slope:   lim_{τ→0} r(τ) − L)
    C = curvature               (hump/inversion at medium maturities)

The ``YieldCurve`` class (defined here, used by both liabilities and asset
sleeves) builds the full nominal and real term structure from a MacroState.

Extension points
----------------
- Add more state variables (e.g. FX, commodity price index)
- Replace VAR with a regime-switching model (see scenarios/regimes.py)
- Provide alternative StressScenario paths for deterministic shocks
- Calibrate Φ and Σ from historical data via OLS / maximum likelihood
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ===========================================================================
# Macro state
# ===========================================================================

@dataclass
class MacroState:
    """
    Snapshot of the macro environment at a single point in time.

    All rates are annualised decimals (e.g. 0.04 = 4 %).
    ``curvature`` is the Diebold-Li β₂ factor: positive values create a hump
    at medium maturities; negative values create an inversion.
    """

    short_rate:    float   # short-term nominal risk-free rate
    long_rate:     float   # long-term nominal yield (e.g. 30yr government)
    real_rate:     float   # long-term real yield    (e.g. 30yr index-linked)
    inflation:     float   # realised / expected CPI inflation
    growth:        float   # real GDP growth
    credit_spread: float   # IG credit spread over government bonds
    curvature:     float   # Diebold-Li β₂: yield-curve hump/inversion factor

    # ------------------------------------------------------------------
    # Derived quantities
    # ------------------------------------------------------------------

    @property
    def breakeven_inflation(self) -> float:
        """Implied breakeven inflation: long_rate − real_rate."""
        return self.long_rate - self.real_rate

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    _FIELDS = (
        "short_rate", "long_rate", "real_rate",
        "inflation", "growth", "credit_spread", "curvature",
    )

    def to_array(self) -> np.ndarray:
        return np.array([getattr(self, f) for f in self._FIELDS])

    @classmethod
    def from_array(cls, arr: np.ndarray) -> MacroState:
        return cls(**dict(zip(cls._FIELDS, arr)))

    def __repr__(self) -> str:
        lines = [f"  {f}: {getattr(self, f):.4f}" for f in self._FIELDS]
        return "MacroState(\n" + "\n".join(lines) + "\n)"


# ===========================================================================
# Diebold-Li yield curve
# ===========================================================================

class YieldCurve:
    """
    Full Diebold-Li (dynamic Nelson-Siegel) yield curve built from a MacroState.

    Nominal spot rate at maturity τ years:

        r_nom(τ) = L  +  S · f(τ)  +  C · g(τ)

        f(τ) = (1 − e^{−τ/λ}) / (τ/λ)      — slope loading
        g(τ) = f(τ) − e^{−τ/λ}              — curvature loading (peaks ≈ τ = λ·ln 2)

    where
        L = state.long_rate           (level factor — long-run limit of the curve)
        S = state.short_rate − L      (slope factor — determines curve steepness)
        C = state.curvature           (curvature factor — hump or inversion)

    Real spot rate at maturity τ:

        r_real(τ) = r_nom(τ) + (state.real_rate − state.long_rate)

    This preserves the long-end real yield (state.real_rate) while applying
    the same Nelson-Siegel shape as the nominal curve.

    Parameters
    ----------
    state   : MacroState
        Provides the three Nelson-Siegel factors (L, S, C) plus the real rate.
    lambda_ : float
        Shape parameter in years.  Controls where the curvature loading peaks:
        peak maturity ≈ λ · ln 2 ≈ 0.693 · λ.
        Default 5.0 yr → peak at ≈ 3.5 yr (appropriate for most pension curves).
    """

    def __init__(self, state: MacroState, lambda_: float = 5.0) -> None:
        self.state   = state
        self.lambda_ = lambda_
        # Nelson-Siegel factors
        self._L = state.long_rate
        self._S = state.short_rate - state.long_rate
        self._C = state.curvature

    # ------------------------------------------------------------------

    def _loadings(self, tau: float) -> tuple[float, float]:
        """Return (slope_loading f(τ), curvature_loading g(τ))."""
        if tau <= 1e-8:
            return 1.0, 0.0          # lim_{τ→0}: f→1, g→0
        x   = tau / self.lambda_
        exp = np.exp(-x)
        f   = (1.0 - exp) / x
        g   = f - exp
        return f, g

    def nominal_rate(self, tau: float) -> float:
        """Continuously compounded nominal spot rate for maturity ``tau`` years."""
        f, g = self._loadings(tau)
        return self._L + self._S * f + self._C * g

    def real_rate(self, tau: float) -> float:
        """
        Continuously compounded real spot rate for maturity ``tau`` years.

        The real spread at the long end (state.real_rate − state.long_rate) is
        applied uniformly across all maturities, preserving the Diebold-Li shape.
        """
        long_spread = self.state.real_rate - self.state.long_rate
        return self.nominal_rate(tau) + long_spread

    def discount_factor(self, tau: float, kind: str = "nominal") -> float:
        """Zero-coupon discount factor exp(−r · τ)."""
        r = self.real_rate(tau) if kind == "real" else self.nominal_rate(tau)
        return float(np.exp(-r * tau))

    def spot_curve(
        self,
        maturities: np.ndarray,
        kind: str = "nominal",
    ) -> np.ndarray:
        """Return spot rates at an array of maturities (vectorised convenience)."""
        fn = self.real_rate if kind == "real" else self.nominal_rate
        return np.array([fn(tau) for tau in maturities])


# ===========================================================================
# VAR(1) parameters
# ===========================================================================
#
# State vector order (must match MacroState._FIELDS):
#   [0] short_rate
#   [1] long_rate
#   [2] real_rate
#   [3] inflation
#   [4] growth
#   [5] credit_spread
#   [6] curvature          ← Diebold-Li β₂ (NEW)

def _default_long_run_mean() -> np.ndarray:
    # Equilibrium (long-run mean) values for each state variable.
    # curvature ≈ 0.005 (mild positive hump) in the unconditional distribution.
    return np.array([0.035, 0.045, 0.015, 0.025, 0.025, 0.010, 0.005])


def _default_phi() -> np.ndarray:
    """
    7×7 persistence matrix.

    Diagonal entries: per-variable mean-reversion speed.
    Off-diagonal entries: cross-variable spillovers.

    Curvature (row/col 6) responds to slope deviations (col 1) — when the
    curve steepens the hump tends to build — and persists moderately on its own.
    Other variables are not directly driven by curvature deviations.
    """
    return np.array([
        #  r_s   r_l   r_r   π     g     cs    C
        [0.70, 0.10, 0.00, 0.05, 0.00, 0.00, 0.00],  # short_rate
        [0.05, 0.80, 0.00, 0.05, 0.00, 0.00, 0.00],  # long_rate
        [0.00, 0.00, 0.75, 0.05, 0.00, 0.00, 0.00],  # real_rate
        [0.05, 0.05, 0.00, 0.60, 0.00, 0.00, 0.00],  # inflation
        [0.00, 0.00, 0.00, 0.05, 0.50, 0.00, 0.00],  # growth
        [0.00, 0.00, 0.00, 0.00, 0.10, 0.65, 0.00],  # credit_spread
        [0.00, 0.05, 0.00, 0.03, 0.00, 0.00, 0.65],  # curvature
    ])


def _default_sigma() -> np.ndarray:
    """
    7×7 annualised innovation covariance matrix.

    Built from per-variable annualised volatilities and an empirically
    motivated correlation matrix.  Curvature innovations:
      - negatively correlated with rates (when rates rise in parallel the hump
        compresses) and credit spreads
      - mildly positively correlated with inflation (CB tightening cycles
        create humps) and growth
    """
    vols = np.array([0.008, 0.012, 0.010, 0.008, 0.025, 0.006, 0.008])
    corr = np.array([
        #  r_s    r_l    r_r    π      g      cs     C
        [ 1.00,  0.70,  0.50,  0.20, -0.10,  0.20, -0.15],  # short_rate
        [ 0.70,  1.00,  0.60,  0.40, -0.15,  0.30, -0.20],  # long_rate
        [ 0.50,  0.60,  1.00, -0.20, -0.10,  0.20, -0.10],  # real_rate
        [ 0.20,  0.40, -0.20,  1.00,  0.10,  0.00,  0.10],  # inflation
        [-0.10, -0.15, -0.10,  0.10,  1.00, -0.40,  0.05],  # growth
        [ 0.20,  0.30,  0.20,  0.00, -0.40,  1.00, -0.10],  # credit_spread
        [-0.15, -0.20, -0.10,  0.10,  0.05, -0.10,  1.00],  # curvature
    ])
    D = np.diag(vols)
    return D @ corr @ D


@dataclass
class VARParams:
    """
    Parameters that fully describe the 7-variable VAR(1) macro model.

    All fields have calibrated defaults so callers only need to override
    the parameters they want to change.  The seventh state variable is
    ``curvature`` (Diebold-Li β₂ factor).
    """

    long_run_mean: np.ndarray = field(default_factory=_default_long_run_mean)
    phi:           np.ndarray = field(default_factory=_default_phi)
    sigma:         np.ndarray = field(default_factory=_default_sigma)

    # Soft floors applied after each step to prevent economically implausible states
    floors: dict[str, float] = field(default_factory=lambda: {
        "short_rate":    -0.02,
        "long_rate":      0.00,
        "real_rate":     -0.05,
        "inflation":     -0.05,
        "growth":        -0.20,
        "credit_spread":  0.00,
        "curvature":     -0.05,  # hard inversion beyond −5 % is unphysical
    })


# ===========================================================================
# VAR(1) scenario engine
# ===========================================================================

class MacroScenarioEngine:
    """
    Generates correlated macro-state paths via a 7-variable VAR(1).

    Usage::

        engine = MacroScenarioEngine(VARParams(), initial_state, seed=42)
        paths  = engine.simulate(n_steps=20, n_scenarios=1_000)
        df     = engine.to_dataframe(paths)
    """

    def __init__(
        self,
        params:        VARParams,
        initial_state: MacroState,
        dt:            float = 1.0,
        seed:          Optional[int] = None,
    ) -> None:
        self.params        = params
        self.initial_state = initial_state
        self.dt            = dt
        self.rng           = np.random.default_rng(seed)

        # Cholesky of scaled covariance (recompute if params change)
        self._chol = np.linalg.cholesky(params.sigma * dt)

    # ------------------------------------------------------------------
    # Single-step transition
    # ------------------------------------------------------------------

    def step(self, state: MacroState) -> MacroState:
        """Advance the macro state by one time step (length self.dt years)."""
        x     = state.to_array()
        x_bar = self.params.long_run_mean
        shock = self._chol @ self.rng.standard_normal(len(x))

        x_new = x_bar + self.params.phi @ (x - x_bar) + shock

        for i, fname in enumerate(MacroState._FIELDS):
            floor    = self.params.floors.get(fname, -np.inf)
            x_new[i] = max(x_new[i], floor)

        return MacroState.from_array(x_new)

    # ------------------------------------------------------------------
    # Multi-step simulation
    # ------------------------------------------------------------------

    def simulate(
        self,
        n_steps:     int,
        n_scenarios: int = 1,
    ) -> list[list[MacroState]]:
        """
        Simulate ``n_scenarios`` independent paths of length ``n_steps``.

        Returns
        -------
        paths : list[list[MacroState]]
            ``paths[s][t]`` is the MacroState for scenario s at step t.
            Step 0 is always ``self.initial_state``.
        """
        paths: list[list[MacroState]] = []
        for _ in range(n_scenarios):
            path  = [self.initial_state]
            state = self.initial_state
            for _ in range(n_steps):
                state = self.step(state)
                path.append(state)
            paths.append(path)
        return paths

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def to_dataframe(self, paths: list[list[MacroState]]) -> pd.DataFrame:
        """Flatten simulated paths into a tidy long-format DataFrame."""
        records = []
        for s, path in enumerate(paths):
            for t, state in enumerate(path):
                row = {"scenario": s, "step": t}
                row.update(dict(zip(MacroState._FIELDS, state.to_array())))
                records.append(row)
        return pd.DataFrame(records)


# ===========================================================================
# Deterministic stress scenarios
# ===========================================================================

@dataclass
class StressScenario:
    """
    A hand-crafted deterministic macro path for stress testing.

    ``states[0]`` is the initial (t=0) state.  Subsequent entries are the
    states at each successive time step.  All constructors propagate the
    initial ``curvature`` unless the stress explicitly changes curve shape.
    """

    name:   str
    states: list[MacroState]

    # ------------------------------------------------------------------
    # Named constructors
    # ------------------------------------------------------------------

    @classmethod
    def parallel_rate_shock(
        cls,
        initial:    MacroState,
        n_steps:    int,
        shock_bps:  float = 200.0,
        ramp_steps: int   = 1,
    ) -> StressScenario:
        """
        Parallel upward shift of the entire yield curve.

        Level (long_rate) and slope (short_rate) shift by the same amount so
        the Nelson-Siegel slope factor is unchanged.  Curvature is preserved
        (a parallel shift does not alter curve shape by construction).
        """
        shock  = shock_bps / 10_000
        states = [initial]
        for t in range(1, n_steps + 1):
            ramp = min(t / ramp_steps, 1.0)
            states.append(MacroState(
                short_rate    = initial.short_rate    + shock * ramp,
                long_rate     = initial.long_rate     + shock * ramp,
                real_rate     = initial.real_rate     + shock * ramp,
                inflation     = initial.inflation,
                growth        = initial.growth,
                credit_spread = initial.credit_spread,
                curvature     = initial.curvature,          # shape unchanged
            ))
        return cls(f"parallel_rate_shock_{shock_bps:.0f}bps", states)

    @classmethod
    def stagflation(
        cls,
        initial:         MacroState,
        n_steps:         int,
        inflation_shock: float = 0.04,
        growth_shock:    float = -0.03,
    ) -> StressScenario:
        """
        High-inflation / low-growth shock.

        CB policy hikes the short rate but the long end rises less, flattening
        the curve.  Curvature turns negative as the CB-induced inversion takes hold.
        """
        states = [initial]
        for _ in range(n_steps):
            states.append(MacroState(
                short_rate    = initial.short_rate    + 0.010,
                long_rate     = initial.long_rate     + 0.005,
                real_rate     = initial.real_rate     - 0.010,
                inflation     = initial.inflation     + inflation_shock,
                growth        = initial.growth        + growth_shock,
                credit_spread = initial.credit_spread + 0.005,
                curvature     = initial.curvature     - 0.010,  # flattening → inversion
            ))
        return cls("stagflation", states)

    @classmethod
    def deflation(
        cls,
        initial:         MacroState,
        n_steps:         int,
        inflation_shock: float = -0.03,
        growth_shock:    float = -0.04,
    ) -> StressScenario:
        """
        Deflationary recession shock.

        Curve bull-flattens: long rates fall more than short rates (CB cuts are
        limited by the lower bound).  Curvature goes slightly negative as the
        medium-term hump disappears in a low-growth environment.
        """
        states = [initial]
        for _ in range(n_steps):
            states.append(MacroState(
                short_rate    = max(initial.short_rate - 0.020, -0.020),
                long_rate     = max(initial.long_rate  - 0.010,  0.000),
                real_rate     = initial.real_rate     + 0.010,
                inflation     = initial.inflation     + inflation_shock,
                growth        = initial.growth        + growth_shock,
                credit_spread = initial.credit_spread + 0.015,
                curvature     = initial.curvature     - 0.005,  # hump fades in recession
            ))
        return cls("deflation", states)
