"""
Macro Scenario Engine
=====================
Generates correlated macro scenarios via a Vector Auto-Regression (VAR(1)) process.

State vector  X = [short_rate, long_rate, real_rate, inflation, growth,
                   credit_spread, curvature, global_growth]

The seventh variable, ``curvature``, is the β₂ factor from the Diebold-Li
(2006) dynamic Nelson-Siegel model.  It controls the hump (or inversion) of
the yield curve at medium maturities and is simulated jointly with all other
macro variables so that curve-shape risk is captured in scenarios.

The eighth variable, ``global_growth`` (added 2026-08), is world real GDP
growth. ``growth`` is EURO-AREA growth and always was; the distinction was
implicit until currency and equity betas started needing a global cycle to
attach to. Two things follow, and both are deliberate:

  * The euro area is a PRICE-TAKER on the global cycle. Global growth feeds
    euro growth (Φ[growth, global_growth] = 0.20); the reverse spillover is
    zero. A single region does not drive the world aggregate.
  * The world aggregate is MORE PERSISTENT and LESS VOLATILE than any one
    region (φ 0.55 vs 0.50; σ 2.0% vs 2.5%), which is what diversification
    across regions should produce.

It is appended at index [7] so every existing positional index is unchanged.

Separately, ``MacroState.equity_factor`` carries a global equity market factor
return. It is NOT part of the VAR state vector — see the field comment for why —
but it is drawn from the same innovation vector, so its correlation with growth
and credit-spread shocks is exact rather than approximate.

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

    ``growth`` is EURO-AREA real GDP growth; ``global_growth`` is the world
    aggregate. Anything reading ``state.growth`` is reading the euro cycle.
    """

    short_rate:    float   # short-term nominal risk-free rate
    long_rate:     float   # long-term nominal yield (e.g. 30yr government)
    real_rate:     float   # long-term real yield    (e.g. 30yr index-linked)
    inflation:     float   # realised / expected CPI inflation
    growth:        float   # real GDP growth
    credit_spread: float   # IG credit spread over government bonds
    curvature:     float   # Diebold-Li β₂: yield-curve hump/inversion factor
    global_growth: float = 0.030   # world real GDP growth (NOT euro-area growth)
    # Defaulted so the seven-argument constructor keeps working; every existing
    # positional and keyword construction is unaffected.

    equity_factor: float = 0.0
    # Global equity market factor RETURN for the period ENDING at this state.
    # NOT a VAR state variable and deliberately NOT in _FIELDS: it is a return,
    # not a level, it has no persistence, and it must not be propagated through
    # Φ or floored. The engine draws it jointly with the macro innovations so it
    # is contemporaneously correlated with them (negatively with the credit-spread
    # innovation, positively with growth), then attaches it to the state that the
    # innovation produced. Consumers read `state_t1.equity_factor` — the factor
    # realised over [t, t+1] — not `state_t`.

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
        "inflation", "growth", "credit_spread", "curvature", "global_growth",
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
#   [6] curvature          ← Diebold-Li β₂
#   [7] global_growth      ← world real GDP growth (2026-08); `growth` above is
#                            EURO-AREA growth and always was

def _default_long_run_mean() -> np.ndarray:
    # Equilibrium (long-run mean) values for each state variable.
    # curvature ≈ 0.005 (mild positive hump) in the unconditional distribution.
    # global_growth 0.030 > euro growth 0.025: the world aggregate includes EM,
    # whose trend growth is higher than the euro area's.
    return np.array([0.035, 0.045, 0.015, 0.025, 0.025, 0.010, 0.005, 0.030])


def _default_phi() -> np.ndarray:
    """
    8×8 persistence matrix.

    Diagonal entries: per-variable mean-reversion speed.
    Off-diagonal entries: cross-variable spillovers.

    Curvature (row/col 6) responds to slope deviations (col 1) — when the
    curve steepens the hump tends to build — and persists moderately on its own.
    Other variables are not directly driven by curvature deviations.

    global_growth (row/col 7) is DELIBERATELY ASYMMETRIC. Euro growth responds
    to global-growth deviations at 0.20 (row 4, col 7); the global-growth row is
    autonomous — no term responds to euro deviations, because a single region
    does not move the world aggregate. Reversing that asymmetry, or making it
    two-way, would let euro shocks feed back through the global cycle into every
    currency and equity beta, which is exactly the confound this variable exists
    to remove.

    The 0.20 spillover is on the conservative side. The euro area is small and
    open, so a case could be made for 0.30-0.40; 0.20 was chosen to understate
    rather than overstate the new channel.
    """
    return np.array([
        #  r_s   r_l   r_r   π     g     cs    C     G
        [0.70, 0.10, 0.00, 0.05, 0.00, 0.00, 0.00, 0.00],  # short_rate
        [0.05, 0.80, 0.00, 0.05, 0.00, 0.00, 0.00, 0.00],  # long_rate
        [0.00, 0.00, 0.75, 0.05, 0.00, 0.00, 0.00, 0.00],  # real_rate
        [0.05, 0.05, 0.00, 0.60, 0.00, 0.00, 0.00, 0.00],  # inflation
        [0.00, 0.00, 0.00, 0.05, 0.50, 0.00, 0.00, 0.20],  # growth  <- global spillover
        [0.00, 0.00, 0.00, 0.00, 0.10, 0.65, 0.00, 0.00],  # credit_spread
        [0.00, 0.05, 0.00, 0.03, 0.00, 0.00, 0.65, 0.00],  # curvature
        [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.55],  # global_growth (autonomous)
    ])


def _default_sigma() -> np.ndarray:
    """
    8×8 annualised innovation covariance matrix.

    Built from per-variable annualised volatilities and an empirically
    motivated correlation matrix.  Curvature innovations:
      - negatively correlated with rates (when rates rise in parallel the hump
        compresses) and credit spreads
      - mildly positively correlated with inflation (CB tightening cycles
        create humps) and growth

    global_growth innovations carry 0.75 correlation with euro-growth
    innovations and inherit euro growth's SIGNS against every other variable at
    roughly three-quarters the magnitude — notably -0.30 against credit spread
    (euro growth: -0.40), since a global downturn widens spreads for the same
    reason a euro one does. Its volatility (2.0%) sits below euro growth's
    (2.5%): a diversified world aggregate is less volatile than any one region.
    """
    vols = np.array([0.008, 0.012, 0.010, 0.008, 0.025, 0.006, 0.008, 0.020])
    corr = np.array([
        #  r_s    r_l    r_r    π      g      cs     C      G
        [ 1.00,  0.70,  0.50,  0.20, -0.10,  0.20, -0.15, -0.08],  # short_rate
        [ 0.70,  1.00,  0.60,  0.40, -0.15,  0.30, -0.20, -0.10],  # long_rate
        [ 0.50,  0.60,  1.00, -0.20, -0.10,  0.20, -0.10, -0.08],  # real_rate
        [ 0.20,  0.40, -0.20,  1.00,  0.10,  0.00,  0.10,  0.08],  # inflation
        [-0.10, -0.15, -0.10,  0.10,  1.00, -0.40,  0.05,  0.75],  # growth
        [ 0.20,  0.30,  0.20,  0.00, -0.40,  1.00, -0.10, -0.30],  # credit_spread
        [-0.15, -0.20, -0.10,  0.10,  0.05, -0.10,  1.00,  0.05],  # curvature
        [-0.08, -0.10, -0.08,  0.08,  0.75, -0.30,  0.05,  1.00],  # global_growth
    ])
    D = np.diag(vols)
    return D @ corr @ D


# ---------------------------------------------------------------------------
# Global equity market factor
# ---------------------------------------------------------------------------
# F is a RETURN, not a macro level, and is handled outside the VAR recursion.
#
# WHY NOT IN THE VAR (decision recorded 2026-08-22). Putting F in the state
# vector would have been tidier in one sense — a single Φ, a single Σ — but it is
# wrong on three counts:
#   1. Category. Every other element of X is a LEVEL (a rate, a growth rate, a
#      spread). F is a period return. Mixing them means YieldCurve, the floors
#      dict, from_array/to_array and every consumer of the state vector would
#      carry a variable none of them should ever read.
#   2. Persistence. The VAR imposes AR(1) dynamics. Equity returns are close to
#      white noise. It is expressible (φ_FF = 0) but it makes Φ mean something
#      different in one row than in all the others.
#   3. Blast radius. It would take the state to nine variables, forcing a third
#      extension of Φ and Σ and a matching extension of scenarios/regimes.py.
# Drawing F as a ninth INNOVATION instead gives exact contemporaneous correlation
# with the macro shocks — which is the only property actually required — with
# none of the above. Φ and Σ are untouched; stationarity and PSD are unaffected
# for the macro block.
EQUITY_FACTOR_VOL = 0.155      # annualised, calibrated from MSCI World 2001-2025

# Correlation of the factor innovation with each macro innovation, in _FIELDS
# order. Equity drawdowns should coincide with spread widening and weak growth
# rather than arriving independently.
_EQUITY_FACTOR_CORR = np.array([
    -0.05,   # short_rate
    -0.10,   # long_rate
    -0.05,   # real_rate
    -0.10,   # inflation      — equities dislike inflation surprises
    +0.25,   # growth         — pro-cyclical
    -0.35,   # credit_spread  — drawdowns coincide with spread widening
    +0.00,   # curvature
    +0.30,   # global_growth  — the world cycle, more than the euro one
])


def _default_augmented_sigma() -> np.ndarray:
    """9x9 innovation covariance: the 8x8 macro block plus the equity factor.

    Only the macro 8x8 sub-block feeds the VAR recursion. The ninth row/column
    exists so the factor draw is correlated with the macro draw; it is sliced off
    after the shock is generated.
    """
    macro = _default_sigma()
    n = macro.shape[0]
    aug = np.zeros((n + 1, n + 1))
    aug[:n, :n] = macro
    macro_sd = np.sqrt(np.diag(macro))
    aug[n, :n] = aug[:n, n] = _EQUITY_FACTOR_CORR * macro_sd * EQUITY_FACTOR_VOL
    aug[n, n] = EQUITY_FACTOR_VOL ** 2
    return aug


@dataclass
class VARParams:
    """
    Parameters that fully describe the 8-variable VAR(1) macro model.

    All fields have calibrated defaults so callers only need to override
    the parameters they want to change.  The seventh state variable is
    ``curvature`` (Diebold-Li β₂ factor); the eighth is ``global_growth``.
    """

    long_run_mean: np.ndarray = field(default_factory=_default_long_run_mean)
    phi:           np.ndarray = field(default_factory=_default_phi)
    sigma:         np.ndarray = field(default_factory=_default_sigma)
    # 9x9: the macro sigma above plus the equity-factor row/column. The factor is
    # drawn from this joint distribution and then sliced off — it never enters Φ.
    augmented_sigma: np.ndarray = field(default_factory=_default_augmented_sigma)

    # Soft floors applied after each step to prevent economically implausible states
    floors: dict[str, float] = field(default_factory=lambda: {
        "short_rate":    -0.02,
        "long_rate":      0.00,
        "real_rate":     -0.05,
        "inflation":     -0.05,
        "growth":        -0.20,
        "credit_spread":  0.00,
        "curvature":     -0.05,  # hard inversion beyond −5 % is unphysical
        "global_growth": -0.15,  # shallower floor than euro growth: a world
                                 # aggregate contracting 20 % is not credible
    })


# ===========================================================================
# VAR(1) scenario engine
# ===========================================================================

class MacroScenarioEngine:
    """
    Generates correlated macro-state paths via an 8-variable VAR(1).

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

        # Cholesky of the AUGMENTED scaled covariance: 8 macro innovations plus
        # the equity-factor innovation, drawn jointly so their contemporaneous
        # correlation is exact. Only the first 8 rows feed the VAR recursion.
        self._chol = np.linalg.cholesky(params.augmented_sigma * dt)
        self._n_macro = len(MacroState._FIELDS)

    # ------------------------------------------------------------------
    # Single-step transition
    # ------------------------------------------------------------------

    def step(self, state: MacroState) -> MacroState:
        """Advance the macro state by one time step (length self.dt years)."""
        x     = state.to_array()
        x_bar = self.params.long_run_mean
        n     = self._n_macro

        # One joint draw: [0:n] are the macro innovations, [n] is the equity
        # factor return for this period. Slicing here — rather than adding the
        # factor to the state vector — is what keeps it out of Φ and out of the
        # floors below, which is the whole point (see the note above VARParams).
        joint = self._chol @ self.rng.standard_normal(n + 1)
        shock, factor_return = joint[:n], float(joint[n])

        x_new = x_bar + self.params.phi @ (x - x_bar) + shock

        for i, fname in enumerate(MacroState._FIELDS):
            floor    = self.params.floors.get(fname, -np.inf)
            x_new[i] = max(x_new[i], floor)

        new_state = MacroState.from_array(x_new)
        # The factor describes the period [t, t+1], so it is attached to the state
        # the transition produced. Sleeves read state_t1.equity_factor.
        new_state.equity_factor = factor_return
        return new_state

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
                row["equity_factor"] = state.equity_factor
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
                global_growth = initial.global_growth,      # a curve event, not a cycle event
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
                # A euro growth shock of this size does not happen in isolation.
                # Damped by 0.75: the world aggregate moves less than one region.
                global_growth = initial.global_growth + growth_shock * 0.75,
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
                global_growth = initial.global_growth + growth_shock * 0.75,
            ))
        return cls("deflation", states)
