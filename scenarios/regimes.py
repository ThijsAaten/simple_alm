"""
Regime-Switching Macro Scenario Engine
=======================================
Extends the VAR(1) engine with a discrete Markov regime layer.

The economy is partitioned into four regimes defined by a 2×2 quadrant:

                 Inflation LOW      Inflation HIGH
  Growth HIGH │ Deflationary Boom │ Inflationary Boom │
  Growth LOW  │ Deflationary Bust │ Inflationary Bust │

At every time step:
  1.  The current regime transitions to a new regime drawn from the
      row of the 4×4 Markov transition matrix indexed by the current regime.
  2.  The new regime's VAR(1) parameters (mean, persistence Φ, covariance Σ)
      are used to advance the macro state.

This means each regime has its own equilibrium level, reversion speed, and
shock volatility — so a burst of stagflation looks fundamentally different
from a deflationary boom even if the *current* macro values are similar.

Drop-in compatibility
---------------------
``RegimeSwitchingEngine.simulate()`` returns ``list[list[MacroState]]`` —
the same type as ``MacroScenarioEngine.simulate()`` — so ``SimulationEngine``
works without any modification.

For richer analysis, use ``simulate_with_regimes()`` which also returns the
regime label at each step.

Extension points
----------------
- Replace the constant transition matrix with a time-varying or funding-ratio-
  dependent matrix (e.g. stressed transitions when FR < 1).
- Add a fifth "crisis" regime with fat-tailed innovations.
- Estimate the transition matrix and per-regime VARs from historical data via
  the EM algorithm (Hamilton 1989).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import numpy as np
import pandas as pd

from scenarios.engine import MacroState, VARParams


# ===========================================================================
# Regime labels
# ===========================================================================

class RegimeLabel(IntEnum):
    """
    Four-quadrant macro regime.

    The integer values index rows/columns of the transition matrix, so do not
    change them without updating the default transition matrix.
    """

    DEFLATIONARY_BOOM = 0   # high growth, low inflation  — "Goldilocks"
    DEFLATIONARY_BUST = 1   # low growth,  low inflation  — recession / deflation
    INFLATIONARY_BOOM = 2   # high growth, high inflation — overheating
    INFLATIONARY_BUST = 3   # low growth,  high inflation — stagflation

    # ------------------------------------------------------------------

    @property
    def growth_level(self) -> str:
        return "high" if self in (
            RegimeLabel.DEFLATIONARY_BOOM, RegimeLabel.INFLATIONARY_BOOM
        ) else "low"

    @property
    def inflation_level(self) -> str:
        return "high" if self in (
            RegimeLabel.INFLATIONARY_BOOM, RegimeLabel.INFLATIONARY_BUST
        ) else "low"

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    def __str__(self) -> str:
        return self.label


# Convenient alias
N_REGIMES = len(RegimeLabel)


# ===========================================================================
# Per-regime VAR parameters
# ===========================================================================
#
# State vector order (must match MacroState._FIELDS):
#   [0] short_rate
#   [1] long_rate
#   [2] real_rate
#   [3] inflation
#   [4] growth
#   [5] credit_spread
#   [6] curvature      ← Diebold-Li β₂ (yield-curve hump/inversion factor)

def _make_sigma(vols: list[float], corr: np.ndarray) -> np.ndarray:
    """Build a covariance matrix from per-variable volatilities and a correlation matrix."""
    D = np.diag(vols)
    return D @ corr @ D


# ---------------------------------------------------------------------------
# Regime 0 — Deflationary Boom ("Goldilocks")
# ---------------------------------------------------------------------------
# Growth above trend, inflation below target.  Policy rates are moderate,
# credit spreads tight, volatility low.

def _deflationary_boom() -> VARParams:
    # Goldilocks: slight positive hump — medium-term rates are elevated as the
    # market expects policy rates to stay firm but eventually ease.
    long_run_mean = np.array([0.030, 0.040, 0.025, 0.015, 0.035, 0.008, 0.005])
    phi = np.array([
        #  r_s   r_l   r_r   π     g     cs    C
        [0.65, 0.08, 0.00, 0.04, 0.00, 0.00, 0.00],  # short_rate
        [0.04, 0.75, 0.00, 0.04, 0.00, 0.00, 0.00],  # long_rate
        [0.00, 0.00, 0.70, 0.03, 0.00, 0.00, 0.00],  # real_rate
        [0.04, 0.04, 0.00, 0.55, 0.00, 0.00, 0.00],  # inflation
        [0.00, 0.00, 0.00, 0.04, 0.45, 0.00, 0.00],  # growth
        [0.00, 0.00, 0.00, 0.00, 0.08, 0.60, 0.00],  # credit_spread
        [0.00, 0.04, 0.00, 0.02, 0.00, 0.00, 0.62],  # curvature
    ])
    vols = [0.005, 0.009, 0.007, 0.005, 0.018, 0.004, 0.006]
    corr = np.array([
        #  r_s    r_l    r_r    π      g      cs     C
        [ 1.00,  0.65,  0.45,  0.15, -0.10,  0.15, -0.12],
        [ 0.65,  1.00,  0.55,  0.35, -0.10,  0.25, -0.18],
        [ 0.45,  0.55,  1.00, -0.25, -0.05,  0.15, -0.08],
        [ 0.15,  0.35, -0.25,  1.00,  0.10,  0.00,  0.08],
        [-0.10, -0.10, -0.05,  0.10,  1.00, -0.35,  0.05],
        [ 0.15,  0.25,  0.15,  0.00, -0.35,  1.00, -0.08],
        [-0.12, -0.18, -0.08,  0.08,  0.05, -0.08,  1.00],
    ])
    return VARParams(long_run_mean=long_run_mean, phi=phi,
                     sigma=_make_sigma(vols, corr))


# ---------------------------------------------------------------------------
# Regime 1 — Deflationary Bust (recession / deflation)
# ---------------------------------------------------------------------------
# Growth below trend or negative.  Inflation falling, central banks cutting.
# Credit spreads widen materially.  Higher persistence — busts are sticky.

def _deflationary_bust() -> VARParams:
    # Recession / deflation: curve bull-flattens then can invert as CB cuts are
    # limited.  Curvature turns negative — the medium-term hump disappears.
    long_run_mean = np.array([0.010, 0.025, 0.015, 0.005, -0.005, 0.020, -0.005])
    phi = np.array([
        #  r_s   r_l   r_r   π     g     cs    C
        [0.80, 0.10, 0.00, 0.05, 0.00, 0.00, 0.00],  # short_rate
        [0.05, 0.85, 0.00, 0.05, 0.00, 0.00, 0.00],  # long_rate
        [0.00, 0.00, 0.78, 0.04, 0.00, 0.00, 0.00],  # real_rate
        [0.05, 0.05, 0.00, 0.70, 0.00, 0.00, 0.00],  # inflation
        [0.00, 0.00, 0.00, 0.05, 0.60, 0.00, 0.00],  # growth
        [0.00, 0.00, 0.00, 0.00, 0.12, 0.75, 0.00],  # credit_spread
        [0.00, 0.05, 0.00, 0.03, 0.00, 0.00, 0.72],  # curvature (sticky in busts)
    ])
    vols = [0.007, 0.012, 0.010, 0.007, 0.030, 0.010, 0.008]
    corr = np.array([
        #  r_s    r_l    r_r    π      g      cs     C
        [ 1.00,  0.70,  0.55,  0.20, -0.15,  0.30, -0.18],
        [ 0.70,  1.00,  0.65,  0.40, -0.20,  0.40, -0.22],
        [ 0.55,  0.65,  1.00, -0.20, -0.15,  0.30, -0.12],
        [ 0.20,  0.40, -0.20,  1.00,  0.05,  0.05,  0.08],
        [-0.15, -0.20, -0.15,  0.05,  1.00, -0.50,  0.05],
        [ 0.30,  0.40,  0.30,  0.05, -0.50,  1.00, -0.12],
        [-0.18, -0.22, -0.12,  0.08,  0.05, -0.12,  1.00],
    ])
    return VARParams(long_run_mean=long_run_mean, phi=phi,
                     sigma=_make_sigma(vols, corr))


# ---------------------------------------------------------------------------
# Regime 2 — Inflationary Boom (overheating)
# ---------------------------------------------------------------------------
# Growth above trend, inflation above target.  Central banks tightening.
# Real yields can fall if CB lags behind the curve.

def _inflationary_boom() -> VARParams:
    # Overheating: the CB is behind the curve; market prices in future hikes,
    # creating a pronounced positive curvature (hump at 2–5yr maturities).
    long_run_mean = np.array([0.045, 0.055, 0.020, 0.035, 0.030, 0.012, 0.010])
    phi = np.array([
        #  r_s   r_l   r_r   π     g     cs    C
        [0.70, 0.08, 0.00, 0.06, 0.00, 0.00, 0.00],  # short_rate
        [0.04, 0.78, 0.00, 0.06, 0.00, 0.00, 0.00],  # long_rate
        [0.00, 0.00, 0.72, 0.05, 0.00, 0.00, 0.00],  # real_rate
        [0.06, 0.06, 0.00, 0.65, 0.00, 0.00, 0.00],  # inflation
        [0.00, 0.00, 0.00, 0.05, 0.50, 0.00, 0.00],  # growth
        [0.00, 0.00, 0.00, 0.00, 0.10, 0.65, 0.00],  # credit_spread
        [0.00, 0.04, 0.00, 0.04, 0.00, 0.00, 0.65],  # curvature
    ])
    vols = [0.008, 0.013, 0.010, 0.010, 0.025, 0.006, 0.009]
    corr = np.array([
        #  r_s    r_l    r_r    π      g      cs     C
        [ 1.00,  0.72,  0.48,  0.30, -0.08,  0.18, -0.15],
        [ 0.72,  1.00,  0.58,  0.48, -0.12,  0.28, -0.20],
        [ 0.48,  0.58,  1.00, -0.18, -0.08,  0.18, -0.10],
        [ 0.30,  0.48, -0.18,  1.00,  0.12,  0.02,  0.12],
        [-0.08, -0.12, -0.08,  0.12,  1.00, -0.38,  0.05],
        [ 0.18,  0.28,  0.18,  0.02, -0.38,  1.00, -0.10],
        [-0.15, -0.20, -0.10,  0.12,  0.05, -0.10,  1.00],
    ])
    return VARParams(long_run_mean=long_run_mean, phi=phi,
                     sigma=_make_sigma(vols, corr))


# ---------------------------------------------------------------------------
# Regime 3 — Inflationary Bust (stagflation)
# ---------------------------------------------------------------------------
# The most persistent and damaging regime.  Low/negative growth, high inflation.
# Policy rates elevated.  Real yields compressed or negative.  Credit blows out.

def _inflationary_bust() -> VARParams:
    # Stagflation: the CB has been forced to invert the curve (short > long) to
    # break inflation.  Curvature is strongly negative — the most extreme curve
    # shape inversion of any regime.  This regime is the stickiest and noisiest.
    long_run_mean = np.array([0.055, 0.060, 0.005, 0.050, -0.010, 0.030, -0.010])
    phi = np.array([
        #  r_s   r_l   r_r   π     g     cs    C
        [0.82, 0.10, 0.00, 0.06, 0.00, 0.00, 0.00],  # short_rate
        [0.05, 0.87, 0.00, 0.06, 0.00, 0.00, 0.00],  # long_rate
        [0.00, 0.00, 0.80, 0.05, 0.00, 0.00, 0.00],  # real_rate
        [0.06, 0.06, 0.00, 0.75, 0.00, 0.00, 0.00],  # inflation
        [0.00, 0.00, 0.00, 0.05, 0.65, 0.00, 0.00],  # growth
        [0.00, 0.00, 0.00, 0.00, 0.12, 0.78, 0.00],  # credit_spread
        [0.00, 0.05, 0.00, 0.04, 0.00, 0.00, 0.75],  # curvature (very persistent)
    ])
    vols = [0.010, 0.015, 0.012, 0.013, 0.035, 0.015, 0.012]
    corr = np.array([
        #  r_s    r_l    r_r    π      g      cs     C
        [ 1.00,  0.72,  0.52,  0.35, -0.18,  0.35, -0.20],
        [ 0.72,  1.00,  0.62,  0.48, -0.22,  0.45, -0.25],
        [ 0.52,  0.62,  1.00, -0.15, -0.18,  0.32, -0.15],
        [ 0.35,  0.48, -0.15,  1.00,  0.08,  0.08,  0.15],
        [-0.18, -0.22, -0.18,  0.08,  1.00, -0.55,  0.05],
        [ 0.35,  0.45,  0.32,  0.08, -0.55,  1.00, -0.15],
        [-0.20, -0.25, -0.15,  0.15,  0.05, -0.15,  1.00],
    ])
    return VARParams(long_run_mean=long_run_mean, phi=phi,
                     sigma=_make_sigma(vols, corr))


# ===========================================================================
# Transition matrix
# ===========================================================================

def _default_transition_matrix() -> np.ndarray:
    """
    Row-stochastic 4×4 Markov transition matrix (annual probabilities).

    Rows = current regime, columns = next regime.
    Ordering: [DefBoom, DefBust, InfBoom, InfBust]

    Design principles:
    - All regimes have high diagonal (self-persistence).
    - Bust regimes are stickier than boom regimes (harder to exit).
    - Adjacent quadrant transitions are more likely than diagonal ones:
        DefBoom ↔ InfBoom  (inflation surprise while growing)
        DefBoom ↔ DefBust  (growth shock, disinflationary)
        InfBoom → InfBust  (growth collapses under inflation pressure)
        InfBust → DefBust  (inflation breaks, growth stays low)
    """
    T = np.array([
        # To:  DefBoom  DefBust  InfBoom  InfBust
        [       0.70,    0.10,    0.15,    0.05   ],  # From: DefBoom
        [       0.25,    0.60,    0.03,    0.12   ],  # From: DefBust
        [       0.08,    0.05,    0.65,    0.22   ],  # From: InfBoom
        [       0.05,    0.25,    0.10,    0.60   ],  # From: InfBust
    ], dtype=float)

    # Sanity check
    assert np.allclose(T.sum(axis=1), 1.0), "Transition matrix rows must sum to 1"
    return T


# ===========================================================================
# Regime specification container
# ===========================================================================

@dataclass
class RegimeSpec:
    """
    Everything needed to define a regime-switching model.

    Parameters
    ----------
    params_by_regime : dict mapping RegimeLabel → VARParams
        Per-regime VAR parameters (equilibrium mean, persistence, covariance).
    transition_matrix : np.ndarray of shape (4, 4)
        Row-stochastic Markov transition matrix.
        ``transition_matrix[i, j]`` = P(next regime = j | current regime = i).
    """

    params_by_regime:  dict[RegimeLabel, VARParams]
    transition_matrix: np.ndarray

    def __post_init__(self) -> None:
        if self.transition_matrix.shape != (N_REGIMES, N_REGIMES):
            raise ValueError(
                f"transition_matrix must be ({N_REGIMES}, {N_REGIMES}), "
                f"got {self.transition_matrix.shape}"
            )
        row_sums = self.transition_matrix.sum(axis=1)
        if not np.allclose(row_sums, 1.0, atol=1e-6):
            raise ValueError(f"All rows must sum to 1.0, got {row_sums}")

    # ------------------------------------------------------------------

    def stationary_distribution(self) -> np.ndarray:
        """
        Compute the stationary distribution π such that π @ T = π.

        This is the long-run fraction of time spent in each regime.
        """
        # Left eigenvector of T corresponding to eigenvalue 1
        eigenvalues, eigenvectors = np.linalg.eig(self.transition_matrix.T)
        # Find the eigenvector for eigenvalue closest to 1
        idx    = np.argmin(np.abs(eigenvalues - 1.0))
        pi     = np.real(eigenvectors[:, idx])
        return pi / pi.sum()

    def expected_regime_duration(self) -> dict[RegimeLabel, float]:
        """Mean duration (in steps) of each regime = 1 / (1 − p_ii)."""
        return {
            r: 1.0 / (1.0 - self.transition_matrix[int(r), int(r)])
            for r in RegimeLabel
        }


def default_regime_spec() -> RegimeSpec:
    """Build a ``RegimeSpec`` from the four calibrated default VARParams."""
    return RegimeSpec(
        params_by_regime={
            RegimeLabel.DEFLATIONARY_BOOM: _deflationary_boom(),
            RegimeLabel.DEFLATIONARY_BUST: _deflationary_bust(),
            RegimeLabel.INFLATIONARY_BOOM: _inflationary_boom(),
            RegimeLabel.INFLATIONARY_BUST: _inflationary_bust(),
        },
        transition_matrix=_default_transition_matrix(),
    )


# ===========================================================================
# Regime-switching engine
# ===========================================================================

class RegimeSwitchingEngine:
    """
    Generates macro-state paths via a Markov regime-switching VAR(1) model.

    The model is a Hamilton (1989)-style mixture of VAR processes: at every
    step the latent regime is drawn from a Markov chain and the corresponding
    VAR parameters are used to advance the macro state.

    Drop-in interface
    -----------------
    ``simulate()`` returns ``list[list[MacroState]]`` — identical to
    ``MacroScenarioEngine.simulate()`` — so ``SimulationEngine`` works
    without modification.

    Extended interface
    ------------------
    ``simulate_with_regimes()`` returns the same paths *plus* the list of
    regime labels at each step, enabling regime-aware analytics.

    Parameters
    ----------
    spec           : RegimeSpec
        Per-regime VAR parameters and transition matrix.
    initial_state  : MacroState
        Starting macro state (t = 0).
    initial_regime : RegimeLabel
        Starting regime (t = 0).
    dt             : float
        Time step in years (default 1.0).
    seed           : int or None
        RNG seed for reproducibility.

    Example
    -------
    >>> spec   = default_regime_spec()
    >>> engine = RegimeSwitchingEngine(spec, initial_state, seed=42)
    >>> paths, regime_paths = engine.simulate_with_regimes(n_steps=20, n_scenarios=1000)
    >>> df = engine.to_dataframe(paths, regime_paths)
    """

    def __init__(
        self,
        spec:           RegimeSpec,
        initial_state:  MacroState,
        initial_regime: RegimeLabel = RegimeLabel.DEFLATIONARY_BOOM,
        dt:             float = 1.0,
        seed:           Optional[int] = None,
    ) -> None:
        self.spec           = spec
        self.initial_state  = initial_state
        self.initial_regime = initial_regime
        self.dt             = dt
        self.rng            = np.random.default_rng(seed)

        # Pre-compute Cholesky decompositions (one per regime, scaled by dt)
        self._chols: dict[RegimeLabel, np.ndarray] = {
            regime: np.linalg.cholesky(params.sigma * dt)
            for regime, params in spec.params_by_regime.items()
        }

    # ------------------------------------------------------------------
    # Core single-step transition
    # ------------------------------------------------------------------

    def step(
        self,
        state:  MacroState,
        regime: RegimeLabel,
    ) -> tuple[MacroState, RegimeLabel]:
        """
        Advance one time step.

        1. Sample the new regime from the Markov chain.
        2. Draw a macro shock conditional on the new regime's VAR.
        3. Apply soft floors.

        Returns
        -------
        (new_state, new_regime)
        """
        # --- Step 1: regime transition ---
        probs      = self.spec.transition_matrix[int(regime)]
        new_regime = RegimeLabel(self.rng.choice(N_REGIMES, p=probs))

        # --- Step 2: VAR step under new regime ---
        params = self.spec.params_by_regime[new_regime]
        x      = state.to_array()
        x_bar  = params.long_run_mean
        shock  = self._chols[new_regime] @ self.rng.standard_normal(len(x))

        x_new  = x_bar + params.phi @ (x - x_bar) + shock

        # --- Step 3: floors ---
        for i, fname in enumerate(MacroState._FIELDS):
            floor    = params.floors.get(fname, -np.inf)
            x_new[i] = max(x_new[i], floor)

        return MacroState.from_array(x_new), new_regime

    # ------------------------------------------------------------------
    # Simulation — drop-in interface
    # ------------------------------------------------------------------

    def simulate(
        self,
        n_steps:     int,
        n_scenarios: int = 1,
    ) -> list[list[MacroState]]:
        """
        Generate ``n_scenarios`` paths of length ``n_steps``.

        Returns the same type as ``MacroScenarioEngine.simulate()``
        (regime information is discarded).  Use ``simulate_with_regimes``
        if you need the regime labels.
        """
        paths, _ = self.simulate_with_regimes(n_steps, n_scenarios)
        return paths

    # ------------------------------------------------------------------
    # Simulation — extended interface with regimes
    # ------------------------------------------------------------------

    def simulate_with_regimes(
        self,
        n_steps:     int,
        n_scenarios: int = 1,
    ) -> tuple[list[list[MacroState]], list[list[RegimeLabel]]]:
        """
        Generate ``n_scenarios`` paths, returning both macro states and regimes.

        Returns
        -------
        paths        : list[list[MacroState]]
            ``paths[s][t]`` — macro state for scenario s at step t.
        regime_paths : list[list[RegimeLabel]]
            ``regime_paths[s][t]`` — active regime for scenario s at step t.

        Both include t = 0 (the initial conditions).
        """
        all_paths:   list[list[MacroState]]  = []
        all_regimes: list[list[RegimeLabel]] = []

        for _ in range(n_scenarios):
            path    = [self.initial_state]
            regimes = [self.initial_regime]
            state   = self.initial_state
            regime  = self.initial_regime

            for _ in range(n_steps):
                state, regime = self.step(state, regime)
                path.append(state)
                regimes.append(regime)

            all_paths.append(path)
            all_regimes.append(regimes)

        return all_paths, all_regimes

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dataframe(
        self,
        paths:        list[list[MacroState]],
        regime_paths: list[list[RegimeLabel]] | None = None,
    ) -> pd.DataFrame:
        """
        Flatten simulation output into a tidy long-format DataFrame.

        If ``regime_paths`` is provided a ``"regime"`` column (string label)
        and a ``"regime_id"`` column (integer) are added.
        """
        records = []
        for s, path in enumerate(paths):
            for t, state in enumerate(path):
                row = {"scenario": s, "step": t}
                row.update(dict(zip(MacroState._FIELDS, state.to_array())))
                if regime_paths is not None:
                    r = regime_paths[s][t]
                    row["regime"]    = r.label
                    row["regime_id"] = int(r)
                records.append(row)
        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def regime_frequency(
        self,
        regime_paths: list[list[RegimeLabel]],
        exclude_t0: bool = True,
    ) -> pd.DataFrame:
        """
        Compute the empirical frequency of each regime across all scenarios
        and steps.  Useful for validating that simulated frequencies match
        the theoretical stationary distribution.

        Parameters
        ----------
        regime_paths : output of ``simulate_with_regimes``
        exclude_t0   : if True, skip the deterministic initial regime
        """
        from collections import Counter
        counts: Counter = Counter()
        for path in regime_paths:
            for t, r in enumerate(path):
                if exclude_t0 and t == 0:
                    continue
                counts[r] += 1

        total    = sum(counts.values())
        stationary = self.spec.stationary_distribution()

        rows = []
        for r in RegimeLabel:
            rows.append({
                "regime":            r.label,
                "simulated_freq":    counts[r] / total if total > 0 else 0.0,
                "theoretical_freq":  stationary[int(r)],
                "expected_duration": self.spec.expected_regime_duration()[r],
            })
        return pd.DataFrame(rows)
