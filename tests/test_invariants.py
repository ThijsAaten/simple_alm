"""
Invariant tests for the participant model + country mosaic.

These are the load-bearing properties a reader should be able to trust:
allocations are well-formed, every FX key the mosaic references actually exists
in the FX model, the replacement-ratio indexation behaves as documented, the
mosaic wires into the RSP, and runs are reproducible.

Run from the repo root, either way:
    pytest tests/
    python -m tests.test_invariants
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import dataclasses
import numpy as np

import main_participant as mp
from assets.fx import FXModel
from portfolio.portfolio import SleeveSpec
from participant.lifecycle import _stable_offset
from allocations import (
    COUNTRY_INPUTS, build_equity_specs,
    CURRENT_EQUITY, PROPOSED_EQUITY, PROPOSED_CONSERVATIVE, PROPOSED_TIGHT_CHINA,
)
from examples.run_equity_only import config_with

_ALL_ALLOCATIONS = {
    "CURRENT": CURRENT_EQUITY, "PROPOSED_A": PROPOSED_EQUITY,
    "CONSERVATIVE": PROPOSED_CONSERVATIVE, "TIGHT_CHINA": PROPOSED_TIGHT_CHINA,
}


def test_allocations_sum_to_one():
    for name, w in _ALL_ALLOCATIONS.items():
        assert abs(sum(w.values()) - 1.0) < 1e-9, f"{name} sums to {sum(w.values())}"


def test_china_cap_respected():
    # The article's headline caps China at 6%; the tight variant at 3%.
    assert PROPOSED_EQUITY["China"] <= 0.06 + 1e-9
    assert PROPOSED_TIGHT_CHINA["China"] <= 0.03 + 1e-9


def test_every_fx_key_exists_in_fx_model():
    supported = set(FXModel.default().currencies)
    for country, inp in COUNTRY_INPUTS.items():
        fx = inp["fx"]
        if fx is not None:
            assert fx in supported, f"{country}: FX key {fx!r} not in FXModel"


def test_stable_offset_is_deterministic():
    # Process-stable hash: same input -> same output (the reproducibility fix).
    assert _stable_offset("GlobalEquity") == _stable_offset("GlobalEquity")
    assert _stable_offset("China") != _stable_offset("Korea")


def test_mosaic_builds_one_sleeve_per_nonzero_weight():
    specs = build_equity_specs(PROPOSED_EQUITY)
    nonzero = sum(1 for v in PROPOSED_EQUITY.values() if v > 0)
    assert len(specs) == nonzero
    assert all(isinstance(s, SleeveSpec) for s in specs)


def _run(weights, indexation, n=40):
    cfg = dataclasses.replace(config_with(weights), career_average_indexation=indexation)
    paths = mp.build_scenario_engine(mp.build_initial_state()).simulate(
        n_steps=mp.N_STEPS, n_scenarios=n)
    return mp._run_batch(paths, cfg)


def test_indexation_none_reproduces_nominal_average():
    # Legacy basis: revalued average == raw nominal average, exactly.
    res = _run(PROPOSED_EQUITY, "none")
    for r in res:
        assert abs(r.career_avg_salary - r.career_avg_salary_nominal) < 1e-6


def test_wage_indexation_lifts_the_denominator():
    # Wage revaluation must raise the career-average above the raw nominal one,
    # which lowers the replacement ratio onto a conventional scale.
    res = _run(PROPOSED_EQUITY, "wage")
    revalued = np.array([r.career_avg_salary for r in res])
    nominal  = np.array([r.career_avg_salary_nominal for r in res])
    assert np.all(revalued > nominal)
    rr = np.array([r.replacement_ratio for r in res])
    assert 0.40 < np.median(rr) < 1.30, f"median RR {np.median(rr):.2f} off conventional scale"


def test_overlay_weights_and_eur_residual():
    from allocations import build_overlay_specs
    assert abs(sum(s.weight for s in build_overlay_specs()) - 0.20) < 1e-9
    assert abs(sum(s.weight for s in build_overlay_specs(china_weight=0.02)) - 0.22) < 1e-9


def test_overlay_fx_keys_exist_in_fx_model():
    from allocations import build_overlay_specs
    supported = set(FXModel.default().currencies)
    for s in build_overlay_specs(china_weight=0.05):   # include China line
        for cur in s.sleeve.fx_exposures:
            assert cur in supported, f"overlay FX key {cur!r} not in FXModel"


def test_china_overlay_defaults_to_zero():
    from allocations import build_overlay_specs
    names = {s.sleeve.name for s in build_overlay_specs()}
    assert "China" not in names                       # off by default (a dial)
    assert "China" in {s.sleeve.name for s in build_overlay_specs(china_weight=0.02)}


def test_low_beta_govvie_decouples_from_eur_rates():
    # The decoupling dial: under an identical EUR-rate drop, a HIGH-beta sleeve's
    # return responds more than a LOW-beta one (idio noise switched off).
    from scenarios.engine import MacroState
    from assets.em_bonds import GovernmentBondSleeve

    def state(long_rate):
        return MacroState(short_rate=long_rate, long_rate=long_rate, real_rate=0.01,
                          inflation=0.02, growth=0.02, credit_spread=0.01, curvature=0.0)

    def ret(beta, dy):
        sl = GovernmentBondSleeve("X", long_run_yield=0.05, initial_yield=0.05,
                                  global_rate_beta=beta, idio_yield_vol=0.0, seed=1)
        return sl.period_return(state(0.03), state(0.03 + dy))

    drop = -0.01
    hi = ret(0.90, drop) - ret(0.90, 0.0)
    lo = ret(0.10, drop) - ret(0.10, 0.0)
    assert abs(hi) > abs(lo), "high-beta sleeve should respond more to an EUR-rate move"


def test_rsp_and_lhp_see_the_same_fx_rates_within_a_year():
    """Both sub-portfolios must read ONE currency path, not two.

    LifecycleSimulator.run shares a single FXModel between the RSP and the LHP.
    FXModel.step both draws the period's shock and rolls the PPP gaps forward,
    so if each sub-portfolio advances the shared model itself, they draw
    INDEPENDENT shocks for the same year and the gaps decay twice per year.
    The unhedged-overlay thesis depends on a common currency shock hitting both
    sides of the fund together, so this asserts they are identical.

    Fails on the pre-fix behaviour (SubPortfolio.step advancing the shared model).
    """
    from portfolio.portfolio import SubPortfolio
    from examples.run_attribution import build_lhp_with_overlay

    lhp_specs = build_lhp_with_overlay(0.10, 0.10, 0.02)
    lhp_names = frozenset(s.sleeve.name for s in lhp_specs)
    cfg = dataclasses.replace(config_with(PROPOSED_EQUITY), lhp_specs=lhp_specs)

    consumed: list[tuple[str, dict]] = []
    fx_calls = [0]
    orig_init, orig_step, orig_fx = SubPortfolio.__init__, SubPortfolio.step, FXModel.step

    def init(self, specs, initial_value, fx_model=None):
        orig_init(self, specs, initial_value, fx_model)
        self._side = "LHP" if frozenset(s.sleeve.name for s in specs) == lhp_names else "RSP"

    def step(self, state_t, state_t1, dt=1.0, fx_returns=None):
        consumed.append((self._side, dict(fx_returns) if fx_returns is not None else None))
        return orig_step(self, state_t, state_t1, dt, fx_returns)

    def fx_step(self, state_t, state_t1, dt=1.0):
        fx_calls[0] += 1
        return orig_fx(self, state_t, state_t1, dt)

    SubPortfolio.__init__, SubPortfolio.step, FXModel.step = init, step, fx_step
    try:
        path = mp.build_scenario_engine(mp.build_initial_state()).simulate(
            n_steps=mp.N_STEPS, n_scenarios=1)[0]
        mp._run_batch([path], cfg)
    finally:
        SubPortfolio.__init__, SubPortfolio.step, FXModel.step = orig_init, orig_step, orig_fx

    assert len(consumed) == 2 * mp.N_STEPS, f"expected 2 sub-portfolio steps per year, got {len(consumed)}"
    assert fx_calls[0] == mp.N_STEPS, (
        f"FXModel advanced {fx_calls[0]} times over {mp.N_STEPS} years — "
        f"must advance exactly once per simulated year")

    for year in range(mp.N_STEPS):
        (side_a, fx_a), (side_b, fx_b) = consumed[2 * year], consumed[2 * year + 1]
        assert {side_a, side_b} == {"RSP", "LHP"}, f"year {year}: unexpected step order"
        assert fx_a is not None and fx_b is not None, (
            f"year {year}: a sub-portfolio drew its own FX instead of the shared draw")
        assert fx_a.keys() == fx_b.keys()
        for cur in fx_a:
            assert fx_a[cur] == fx_b[cur], (
                f"year {year}: RSP and LHP saw different {cur} returns "
                f"({fx_a[cur]:.6%} vs {fx_b[cur]:.6%})")


# Joint-regression loadings (assets/fx.py, 2026-08). Supersedes the univariate
# table: those absorbed shared global-cycle exposure into the dollar coefficient.
# ccy: (b_usd, resid_growth_beta, inflation_loading, growth_loading, global_growth_loading)
DERIVED_LOADINGS = {
    "USD": (1.000,  0.000, 0.50, -0.30,  0.00),
    "HKD": (0.988,  0.001, 0.50, -0.30,  0.00),
    "VND": (1.027,  0.024, 0.50, -0.30,  0.00),
    "IDR": (0.997,  0.217, 0.50, -0.30,  0.15),
    "INR": (0.938,  0.160, 0.45, -0.30,  0.10),
    "CNY": (0.933,  0.039, 0.45, -0.30,  0.00),
    "TWD": (0.863,  0.105, 0.45, -0.25,  0.05),
    "THB": (0.814,  0.103, 0.40, -0.25,  0.05),
    "KRW": (0.760,  0.262, 0.40, -0.25,  0.15),
    "SGD": (0.720,  0.087, 0.35, -0.20,  0.05),
    "GBP": (0.596,  0.122, 0.30, -0.20,  0.05),
    "JPY": (0.447, -0.120, 0.20, -0.15, -0.05),
}

# CHF, CAD and AUD are absent from the FX dataset, so no joint regression exists.
# Each is wrong by at least one convention and is left alone deliberately rather
# than corrected by assertion — see the UN-DERIVED note in assets/fx.py.
UNDERIVED = {"CHF", "CAD", "AUD"}


def test_derived_loadings_match_the_published_table():
    """Pin all three loading columns; they are load-bearing and easy to drift."""
    from assets.fx import _DEFAULT_CURRENCIES
    for ccy, (_b, _rg, il, gl, ggl) in DERIVED_LOADINGS.items():
        assert ccy in _DEFAULT_CURRENCIES, f"{ccy} missing from FXModel"
        p = _DEFAULT_CURRENCIES[ccy]
        assert abs(p.inflation_loading - il) < 1e-9, f"{ccy} inflation {p.inflation_loading} != {il}"
        assert abs(p.growth_loading - gl) < 1e-9, f"{ccy} growth {p.growth_loading} != {gl}"
        assert abs(p.global_growth_loading - ggl) < 1e-9, \
            f"{ccy} global_growth {p.global_growth_loading} != {ggl}"


def test_no_negative_inflation_loading_outside_known_exceptions():
    """No currency may weaken vs EUR when EUR inflation rises.

    The repression world is euro-SPECIFIC (EUR real -1.5%, EUR inflation 3.5%,
    foreign curves untouched), so every non-euro currency should appreciate
    against the EUR — the only question is by how much.
    """
    from assets.fx import _DEFAULT_CURRENCIES
    bad = {c: p.inflation_loading for c, p in _DEFAULT_CURRENCIES.items()
           if p.inflation_loading < 0.0 and c not in UNDERIVED}
    assert not bad, f"negative inflation_loading for {sorted(bad)} — see assets/fx.py"


def test_indonesia_and_vietnam_use_their_own_currencies():
    """The THB-proxies-IDR/VND substitution stays retired.

    THB and IDR both land at a 0.30 inflation_loading, but via different
    correlations (0.713 vs 0.510) offset by different volatilities. The agreement
    is a coincidence of the beta arithmetic and does not survive re-estimation
    (post-2017: THB 0.13, IDR 0.33), so the proxy must not creep back.

    RESTORED 2026-08-21: this test and the one below were silently lost when the
    loadings block was rewritten during the global-growth round.
    """
    from allocations import COUNTRY_INPUTS, BOND_INPUTS
    assert COUNTRY_INPUTS["Indonesia"]["fx"] == "IDR"
    assert COUNTRY_INPUTS["Vietnam"]["fx"] == "VND"
    assert BOND_INPUTS["Indonesia"]["fx"] == "IDR"


def test_preview_fx_table_covers_every_mosaic_currency():
    """allocations/preview.py keeps its own FX table; a new currency must reach it.

    Repointing Indonesia to IDR without updating preview.FX_TAILWIND would have
    raised a KeyError at runtime — a seam with two independent currency lists.
    """
    from allocations.preview import FX_TAILWIND
    from allocations import COUNTRY_INPUTS
    missing = {v["fx"] for v in COUNTRY_INPUTS.values()} - set(FX_TAILWIND)
    assert not missing, f"preview.FX_TAILWIND missing {sorted(missing)}"


def test_every_derived_growth_loading_is_negative():
    """EURO growth above trend strengthens the EUR, so foreign currencies lose.

    Cyclical exposure belongs in global_growth_loading, NOT here. Before 2026-08
    the table carried POSITIVE growth loadings for CNY/TWD/KRW/CAD/AUD justified
    by comments about "global growth" and "risk-on" — a factor the model did not
    then have. This asserts that confusion cannot return.
    """
    from assets.fx import _DEFAULT_CURRENCIES
    bad = {c: p.growth_loading for c, p in _DEFAULT_CURRENCIES.items()
           if p.growth_loading >= 0.0 and c not in UNDERIVED}
    assert not bad, (
        f"non-negative growth_loading for {sorted(bad)} — euro-growth column. "
        f"Cyclical exposure belongs in global_growth_loading.")


def test_loading_columns_imply_the_same_dollar_beta():
    """THE TEST THAT WOULD HAVE CAUGHT THE ORIGINAL ERROR.

    inflation_loading and growth_loading are both derived from the SAME b_usd
    (0.50 x b_usd and -0.30 x b_usd), so each column independently implies a
    dollar beta. They must agree. Under the old table CNY implied b_usd = 0.90
    from its inflation column and b_usd = -1.00 from its growth column (+0.30
    against USD's -0.30) — a currency cannot track the dollar for inflation and
    oppose it for growth. That contradiction is what this catches.

    Tolerance 0.15 is set by the rounding, not by taste: both columns are rounded
    to 0.05, so the inflation column can be off by 0.025/0.50 = 0.05 in beta
    terms and the growth column by 0.025/0.30 = 0.083, for a worst case of 0.133.
    """
    from assets.fx import _DEFAULT_CURRENCIES
    TOL = 0.15
    for ccy, (b_usd, _rg, _il, _gl, _ggl) in DERIVED_LOADINGS.items():
        p = _DEFAULT_CURRENCIES[ccy]
        implied_from_inflation = p.inflation_loading / 0.50
        implied_from_growth    = p.growth_loading / -0.30
        assert abs(implied_from_inflation - implied_from_growth) < TOL, (
            f"{ccy}: inflation column implies b_usd={implied_from_inflation:.2f}, "
            f"growth column implies {implied_from_growth:.2f} — the columns disagree")
        for label, implied in (("inflation", implied_from_inflation),
                               ("growth", implied_from_growth)):
            assert abs(implied - b_usd) < TOL, (
                f"{ccy}: {label} column implies b_usd={implied:.2f}, measured {b_usd:.2f}")


def test_model_implied_correlations_match_the_measured_betas():
    """STEP 4 — the consistency test that would have caught the original error.

    Builds the implied cross-currency correlation matrix two ways and compares
    them elementwise:

      MODEL      from the ROUNDED loadings actually stored in _DEFAULT_CURRENCIES
      REFERENCE  from the UNROUNDED regression coefficients
                 (0.50*b_usd, -0.30*b_usd, 0.60*resid_g)

    Both use the same variance decomposition — common macro part from the VAR's
    own unconditional covariance of (inflation, euro growth, global growth),
    plus each currency's idio_vol — so the ONLY difference is whether the
    loadings faithfully represent the measured betas.

    TOLERANCE 0.02, chosen from measurement rather than taste:
      * the correct table gives a maximum elementwise difference of 0.0061
      * restoring the historical bug (CNY at growth_loading +0.30, tracking the
        dollar at 0.93 for inflation while opposing it for growth) gives 0.1015
    A 17x separation, so 0.02 sits comfortably between them: tight enough to
    catch a single mis-signed loading, loose enough that 0.05 rounding passes.

    NOTE ON WHAT IS BEING COMPARED. The raw FX return series is not in this repo,
    so a true *observed* correlation matrix cannot be recomputed here; the
    reference is reconstructed from the published regression coefficients
    instead. That is sufficient for the failure mode this guards against — a
    loading that contradicts its own measured beta — but it would not detect an
    error in the regression itself.
    """
    import itertools
    from assets.fx import _DEFAULT_CURRENCIES
    from scenarios.engine import VARParams, MacroState

    p = VARParams()
    n = p.phi.shape[0]
    V = np.linalg.solve(np.eye(n * n) - np.kron(p.phi, p.phi),
                        p.sigma.reshape(-1)).reshape(n, n)
    idx = [MacroState._FIELDS.index(f) for f in ("inflation", "growth", "global_growth")]
    Vm = V[np.ix_(idx, idx)]
    ccys = sorted(DERIVED_LOADINGS)

    def implied(loadings):
        var = {c: float(loadings[c] @ Vm @ loadings[c]) + _DEFAULT_CURRENCIES[c].idio_vol ** 2
               for c in ccys}
        return {(a, b): float(loadings[a] @ Vm @ loadings[b]) / np.sqrt(var[a] * var[b])
                for a, b in itertools.combinations(ccys, 2)}

    model = implied({c: np.array([_DEFAULT_CURRENCIES[c].inflation_loading,
                                  _DEFAULT_CURRENCIES[c].growth_loading,
                                  _DEFAULT_CURRENCIES[c].global_growth_loading])
                     for c in ccys})
    reference = implied({c: np.array([0.50 * DERIVED_LOADINGS[c][0],
                                      -0.30 * DERIVED_LOADINGS[c][0],
                                      0.60 * DERIVED_LOADINGS[c][1]]) for c in ccys})

    TOL = 0.02
    worst_pair, worst = max(((k, abs(model[k] - reference[k])) for k in model),
                            key=lambda kv: kv[1])
    assert worst < TOL, (
        f"implied correlation for {worst_pair} differs by {worst:.4f} between the "
        f"stored loadings and the measured betas (tolerance {TOL}) — a loading "
        f"contradicts its own regression coefficient")
    assert all(v > 0 for v in model.values()), \
        "some currency pair is implied to co-move negatively against the EUR"


def test_var_transition_matrix_is_stationary():
    """All eigenvalues of Φ inside the unit circle, or paths diverge silently."""
    from scenarios.engine import VARParams
    ev = np.linalg.eigvals(VARParams().phi)
    worst = float(np.max(np.abs(ev)))
    assert worst < 1.0, f"VAR is non-stationary: max |eigenvalue| = {worst:.4f}"
    assert worst < 0.95, f"VAR is near-unit-root: max |eigenvalue| = {worst:.4f}"


def test_var_covariance_is_psd_and_cholesky_succeeds():
    """Σ must stay PSD; MacroScenarioEngine.__init__ Choleskys it on construction."""
    from scenarios.engine import VARParams, MacroScenarioEngine
    import main_participant as mp
    p = VARParams()
    w = np.linalg.eigvalsh(p.sigma)
    assert w.min() > -1e-12, f"Σ is not PSD: min eigenvalue {w.min():.3e}"
    np.linalg.cholesky(p.sigma)                      # raises if it fails
    MacroScenarioEngine(p, mp.build_initial_state(), seed=1)   # exercises the real path


def test_macro_state_has_global_growth_and_roundtrips():
    """The state vector is 8 wide and global_growth is last, at index [7]."""
    from scenarios.engine import VARParams, MacroState
    import main_participant as mp
    assert MacroState._FIELDS[7] == "global_growth", "global_growth must be index [7]"
    assert len(MacroState._FIELDS) == 8
    p = VARParams()
    assert p.phi.shape == (8, 8) and p.sigma.shape == (8, 8)
    assert p.long_run_mean.shape == (8,)
    s = mp.build_initial_state()
    assert np.allclose(MacroState.from_array(s.to_array()).to_array(), s.to_array())


def test_fx_global_growth_term_is_wired_through():
    """A global-growth deviation must move exactly the currencies with a loading."""
    import dataclasses
    from assets.fx import FXModel, _DEFAULT_CURRENCIES
    import main_participant as mp
    s0 = mp.build_initial_state()
    hot = dataclasses.replace(s0, global_growth=s0.global_growth + 0.02)
    base = FXModel.default(seed=7).step(s0, s0)
    warm = FXModel.default(seed=7).step(hot, hot)
    for ccy, p in _DEFAULT_CURRENCIES.items():
        moved = warm[ccy] - base[ccy]
        assert abs(moved - p.global_growth_loading * 0.02) < 1e-12, \
            f"{ccy}: global-growth term not applied as calibrated"


def test_equity_equilibrium_return_equals_its_documented_drift():
    """VALIDATION A-1. At the VAR's long-run means an equity sleeve must return
    exactly its `drift`, because allocations/country_inputs.py documents drift as
    "§3.1 local-currency nominal expected return (the EquitySleeve's long-run
    nominal total return)".

    Fails on the pre-2026-08 behaviour, where _factor_return applied
    inflation_beta to the raw inflation LEVEL while applying growth as a
    deviation in the same expression. That produced a permanent offset of
    inflation_beta x pi-bar — 50 to 75bp depending on the market — so no market
    returned its stated drift, and markets with smaller |inflation_beta| (China,
    Indonesia at -0.20) were silently advantaged over Europe and the USA (-0.30).
    """
    from assets.growth import EquitySleeve
    from scenarios.engine import MacroState, VARParams
    from allocations import COUNTRY_INPUTS

    equilibrium = MacroState.from_array(VARParams().long_run_mean)
    for country, inp in COUNTRY_INPUTS.items():
        sleeve = EquitySleeve(
            country, drift=inp["drift"], growth_beta=inp["gbeta"],
            inflation_beta=inp["ibeta"], idio_vol=0.0, seed=1,
            cape=20.0, cape_fair=20.0, valuation_beta=0.05,
            long_run_earnings_growth=0.04,
        )
        r = sleeve.period_return(equilibrium, equilibrium, dt=1.0)
        assert abs(r - inp["drift"]) < 1e-12, (
            f"{country}: equilibrium return {r:.4%} != documented drift "
            f"{inp['drift']:.4%} (gap {r - inp['drift']:+.4%})")


def test_equity_inflation_offset_does_not_differ_across_markets():
    """VALIDATION A-1, the part that biased the article's central comparison.

    Whatever the inflation convention, two markets sitting at the same macro
    state must not receive DIFFERENT permanent return offsets purely because
    their inflation betas differ. Under the old level form Europe lost 75bp and
    China 50bp in equilibrium — a 25bp standing tilt toward Asia that nobody
    chose and that appears nowhere in the article's inputs.
    """
    from assets.growth import EquitySleeve
    from scenarios.engine import MacroState, VARParams
    from allocations import COUNTRY_INPUTS

    equilibrium = MacroState.from_array(VARParams().long_run_mean)
    offsets = {}
    for country, inp in COUNTRY_INPUTS.items():
        sleeve = EquitySleeve(
            country, drift=inp["drift"], growth_beta=inp["gbeta"],
            inflation_beta=inp["ibeta"], idio_vol=0.0, seed=1,
            cape=20.0, cape_fair=20.0, valuation_beta=0.05,
            long_run_earnings_growth=0.04,
        )
        offsets[country] = sleeve.period_return(equilibrium, equilibrium) - inp["drift"]
    spread = max(offsets.values()) - min(offsets.values())
    assert spread < 1e-12, (
        f"equilibrium offset differs by {spread:.4%} across markets: {offsets}")


def test_sleeve_rng_streams_are_distinct_across_scenarios():
    """VALIDATION B-1. No two (scenario, sleeve) pairs may share a random stream.

    Fails on the pre-2026-08 behaviour, where _reseed_specs used
    ``default_rng(base_seed + offset)``. base_seed increments by one per
    scenario, so any two sleeves whose name-derived offsets differed by less than
    N shared a stream: Taiwan (82420) and RealAssets (82419) differ by ONE, so
    scenario i's Taiwan drew the identical sequence to scenario i+1's RealAssets
    — with both live in the RSP simultaneously. 12.2% of sleeve-runs were
    affected at N=1000, rising to 20.6% at N=5000, so adding paths made the
    dependence worse rather than better.
    """
    import copy
    from participant.lifecycle import _reseed_specs, _DOMAIN_RSP, _DOMAIN_LHP
    from allocations import PROPOSED_EQUITY
    from examples.run_attribution import build_lhp_with_overlay
    from examples.run_equity_only import rsp_specs_with_mosaic

    rsp_template = rsp_specs_with_mosaic(PROPOSED_EQUITY)
    lhp_template = build_lhp_with_overlay()
    N = 200                       # collisions appear at lag 1, so 200 suffices
    seen: dict[tuple, tuple] = {}
    for i in range(N):
        run_seed = mp.SEED + i
        for specs, domain, tag in ((copy.deepcopy(rsp_template), _DOMAIN_RSP, "RSP"),
                                   (copy.deepcopy(lhp_template), _DOMAIN_LHP, "LHP")):
            _reseed_specs(specs, base_seed=run_seed, domain=domain)
            for spec in specs:
                rng = getattr(spec.sleeve, "_rng", None) or getattr(spec.sleeve, "rng", None)
                if rng is None:
                    continue
                sig = tuple(np.round(rng.standard_normal(6), 12))
                if sig in seen:
                    raise AssertionError(
                        f"shared RNG stream: scenario {i} {tag} {spec.sleeve.name} "
                        f"draws the same sequence as {seen[sig]}")
                seen[sig] = (i, tag, spec.sleeve.name)


def test_macro_paths_are_not_mutated_by_a_simulation_batch():
    """MacroState is a plain (mutable) dataclass and the same path list is reused
    across configurations, so in-place mutation would silently contaminate every
    later comparison. Assert the paths come back byte-identical."""
    import hashlib
    from allocations import PROPOSED_EQUITY
    from examples.run_attribution import build_lhp_with_overlay, cfg

    paths = mp.build_scenario_engine(mp.build_initial_state()).simulate(
        n_steps=mp.N_STEPS, n_scenarios=3)
    def digest(ps):
        return hashlib.sha256(
            np.array([[s.to_array() for s in p] for p in ps]).tobytes()).hexdigest()
    before = digest(paths)
    mp._run_batch(paths, cfg(PROPOSED_EQUITY, build_lhp_with_overlay(0.1, 0.1, 0.02)))
    assert digest(paths) == before, "a simulation batch mutated the shared macro paths"


def test_every_stochastic_sleeve_is_reachable_by_the_reseeder():
    """Generalises B-2 beyond the two attribute spellings that exist today.

    _reseed_specs can only reseed a generator it can find. Any sleeve that owns a
    Generator under a name the reseeder does not look for will silently keep its
    template state and repeat one draw path in every scenario. Assert that every
    Generator attribute on every sleeve is actually reseeded.
    """
    import copy
    from participant.lifecycle import _reseed_specs, _DOMAIN_RSP
    from allocations import PROPOSED_EQUITY
    from examples.run_attribution import build_lhp_with_overlay
    from examples.run_equity_only import rsp_specs_with_mosaic

    for template in (rsp_specs_with_mosaic(PROPOSED_EQUITY), build_lhp_with_overlay()):
        a, b = copy.deepcopy(template), copy.deepcopy(template)
        _reseed_specs(a, base_seed=1, domain=_DOMAIN_RSP)
        _reseed_specs(b, base_seed=2, domain=_DOMAIN_RSP)
        for sa, sb in zip(a, b):
            gens = [k for k, v in vars(sa.sleeve).items()
                    if isinstance(v, np.random.Generator)]
            for attr in gens:
                da = getattr(sa.sleeve, attr).standard_normal(4)
                db = getattr(sb.sleeve, attr).standard_normal(4)
                assert not np.array_equal(da, db), (
                    f"{sa.sleeve.name}.{attr} is identical under two different base "
                    f"seeds — the reseeder is not reaching it")


def test_bond_price_response_matches_duration_and_convexity():
    """METHOD D. A parallel +100bp shift must cost ~ -D*dy + 0.5*C*dy^2."""
    from assets.bonds import NominalBondSleeve
    from assets.linkers import LinkerSleeve
    from scenarios.engine import MacroState, VARParams

    eq = MacroState.from_array(VARParams().long_run_mean)
    up = dataclasses.replace(eq, short_rate=eq.short_rate + 0.01,
                             long_rate=eq.long_rate + 0.01,
                             real_rate=eq.real_rate + 0.01)
    for sleeve, D in ((NominalBondSleeve("b", duration=20.0, maturity=25.0), 20.0),
                      (LinkerSleeve("l", real_duration=18.0, maturity=22.0), 18.0)):
        flat = sleeve.period_return(eq, eq)
        shocked = sleeve.period_return(eq, up)
        price_move = shocked - flat
        expected = -D * 0.01 + 0.5 * (D ** 2) * 0.01 ** 2
        assert price_move < 0, f"{sleeve.name} gained on a rate rise"
        assert abs(price_move - expected) < 0.02, (
            f"{sleeve.name}: price move {price_move:.3%} vs duration+convexity "
            f"{expected:.3%}")


def test_linker_beats_nominal_when_inflation_rises():
    """METHOD D. The whole point of holding linkers in the LHP."""
    from assets.bonds import NominalBondSleeve
    from assets.linkers import LinkerSleeve
    from scenarios.engine import MacroState, VARParams

    eq = MacroState.from_array(VARParams().long_run_mean)
    hot = dataclasses.replace(eq, inflation=eq.inflation + 0.02)
    linker_gain = (LinkerSleeve("l", real_duration=18.0, maturity=22.0).period_return(hot, hot)
                   - LinkerSleeve("l", real_duration=18.0, maturity=22.0).period_return(eq, eq))
    nominal_gain = (NominalBondSleeve("b", duration=20.0, maturity=25.0).period_return(hot, hot)
                    - NominalBondSleeve("b", duration=20.0, maturity=25.0).period_return(eq, eq))
    assert linker_gain > nominal_gain, "linker must out-earn the nominal bond on an inflation surprise"
    assert abs(linker_gain - 0.02) < 1e-9, f"linker accrual should be exactly +2pp, got {linker_gain:.4%}"


def test_low_pass_through_sovereign_loses_less_under_euro_repression():
    """METHOD D. The entire rationale for the unrepressed overlay."""
    from assets.em_bonds import GovernmentBondSleeve
    from scenarios.engine import MacroState, VARParams

    eq = MacroState.from_array(VARParams().long_run_mean)
    rep = dataclasses.replace(eq, real_rate=-0.015, inflation=0.035,
                              long_rate=0.020, short_rate=0.010)
    def real_return(beta):
        sl = GovernmentBondSleeve("s", duration=7.0, initial_yield=0.045,
                                  long_run_yield=0.045, global_rate_beta=beta,
                                  idio_yield_vol=0.0, seed=1)
        return sl.period_return(eq, rep) - rep.inflation
    low, high = real_return(0.10), real_return(1.00)
    assert low < high, (
        "under EUR repression the LOW pass-through sovereign should import less of "
        f"the EUR rally, got low-beta {low:.3%} vs high-beta {high:.3%}")


def test_cape_above_anchor_drags_and_below_anchor_boosts():
    """METHOD D. Sign of the valuation term, and that it vanishes at the anchor."""
    from assets.growth import EquitySleeve
    from scenarios.engine import MacroState, VARParams

    eq = MacroState.from_array(VARParams().long_run_mean)
    def contribution(cape):
        sl = EquitySleeve("x", drift=0.07, growth_beta=0.60, inflation_beta=-0.30,
                          idio_vol=0.0, seed=1, cape=cape, cape_fair=20.0,
                          valuation_beta=0.05)
        return sl.period_return(eq, eq) - 0.07
    assert contribution(30.0) < 0, "expensive market must carry a valuation drag"
    assert abs(contribution(20.0)) < 1e-12, "at the anchor the valuation term must vanish"
    assert contribution(12.0) > 0, "cheap market must carry a valuation boost"


def test_carry_scales_linearly_with_dt():
    """METHOD C. dt applied exactly once on every carry term."""
    from assets.cash import CashSleeve
    from assets.bonds import NominalBondSleeve
    from assets.linkers import LinkerSleeve
    from scenarios.engine import MacroState, VARParams

    eq = MacroState.from_array(VARParams().long_run_mean)
    for sleeve in (CashSleeve("c"),
                   NominalBondSleeve("b", duration=20.0, maturity=25.0),
                   LinkerSleeve("l", real_duration=18.0, maturity=22.0)):
        full = sleeve.period_return(eq, eq, dt=1.0)
        half = sleeve.period_return(eq, eq, dt=0.5)
        assert abs(half / full - 0.5) < 1e-9, (
            f"{sleeve.name}: dt is not applied exactly once "
            f"(r(1)={full:.6f}, r(0.5)={half:.6f})")


def test_var_simulated_moments_match_the_calibration():
    """METHOD E. Simulated long-run means must match X-bar, and the unconditional
    spread must match the analytic solution. Catches a calibration edit that
    quietly changes what the engine actually produces."""
    from scenarios.engine import VARParams, MacroState

    p = VARParams()
    paths = mp.build_scenario_engine(mp.build_initial_state(), seed=7).simulate(
        n_steps=65, n_scenarios=400)
    X = np.array([[s.to_array() for s in path] for path in paths])
    n = p.phi.shape[0]
    V = np.linalg.solve(np.eye(n * n) - np.kron(p.phi, p.phi),
                        p.sigma.reshape(-1)).reshape(n, n)
    analytic_sd = np.sqrt(np.diag(V))
    tail = X[:, 40:, :]
    for i, field in enumerate(MacroState._FIELDS):
        gap = tail[:, :, i].mean() - p.long_run_mean[i]
        # credit_spread's floor at 0.0 truncates its left tail and lifts the mean;
        # 25bp is loose enough to accommodate that and tight enough to catch drift.
        assert abs(gap) < 0.0025, f"{field}: simulated mean off X-bar by {gap:+.4f}"
        ratio = tail[:, :, i].std() / analytic_sd[i]
        assert 0.80 < ratio < 1.20, (
            f"{field}: simulated sd is {ratio:.2f}x the analytic unconditional sd")


def test_no_state_variable_explodes_or_degenerates_over_the_horizon():
    """METHOD E. Cross-sectional spread must neither collapse nor blow up."""
    from scenarios.engine import MacroState

    paths = mp.build_scenario_engine(mp.build_initial_state(), seed=11).simulate(
        n_steps=65, n_scenarios=400)
    X = np.array([[s.to_array() for s in path] for path in paths])
    for i, field in enumerate(MacroState._FIELDS):
        sd20, sd65 = X[:, 20, i].std(), X[:, 65, i].std()
        assert sd65 > 1e-6, f"{field}: spread has degenerated to zero by year 65"
        assert 0.3 < sd65 / sd20 < 3.0, (
            f"{field}: spread moved {sd65/sd20:.2f}x between year 20 and 65")


def test_credit_spread_floor_does_not_bind_more_than_expected():
    """METHOD E. The credit_spread floor at 0.0 truncates the distribution and
    lifts the simulated mean above X-bar. It currently binds on ~10% of steps,
    which is already material; this pins the level so a calibration change cannot
    quietly make it worse."""
    from scenarios.engine import VARParams, MacroState

    idx = MacroState._FIELDS.index("credit_spread")
    floor = VARParams().floors["credit_spread"]
    paths = mp.build_scenario_engine(mp.build_initial_state(), seed=13).simulate(
        n_steps=65, n_scenarios=400)
    X = np.array([[s.to_array() for s in path] for path in paths])
    share = float((np.abs(X[:, 1:, idx] - floor) < 1e-12).mean())
    assert share < 0.15, (
        f"credit_spread sits at its floor on {share:.1%} of steps — the simulated "
        f"process is materially not the calibrated one")


def _simulate_equity_returns(n_scenarios=150, n_steps=65, seed=5):
    """Per-market annual equity return panels, shared by the V-C3 guards."""
    from assets.growth import EquitySleeve
    from allocations import COUNTRY_INPUTS

    paths = mp.build_scenario_engine(mp.build_initial_state(), seed=seed).simulate(
        n_steps=n_steps, n_scenarios=n_scenarios)
    out = {}
    for j, (market, inp) in enumerate(COUNTRY_INPUTS.items()):
        rows = []
        for k, path in enumerate(paths):
            sleeve = EquitySleeve(
                market, drift=inp["drift"], growth_beta=inp["gbeta"],
                inflation_beta=inp["ibeta"], idio_vol=inp["idio"],
                seed=10_000 * j + k, cape=inp["cape_now"], cape_fair=inp["cape_now"],
                market_beta=inp["mbeta"])
            rows.append([sleeve.period_return(path[y], path[y + 1]) for y in range(n_steps)])
        out[market] = np.array(rows)
    return out


def test_equity_market_factor_has_its_calibrated_moments():
    """V-C3 guard. The factor must be mean-zero, at its calibrated volatility, and
    close to white noise.

    Mean zero matters: the expected return lives in each sleeve's `drift`, so a
    factor with drift would inflate every market simultaneously. Near-zero
    autocorrelation is why the factor is drawn as an innovation rather than added
    to the VAR state vector, which would impose AR(1) persistence on it.
    """
    from scenarios.engine import EQUITY_FACTOR_VOL

    paths = mp.build_scenario_engine(mp.build_initial_state(), seed=3).simulate(
        n_steps=65, n_scenarios=400)
    F = np.array([[s.equity_factor for s in p[1:]] for p in paths])
    assert abs(F.mean()) < 0.01, f"factor mean {F.mean():+.4f} is not ~0"
    assert abs(F.std() - EQUITY_FACTOR_VOL) < 0.01, (
        f"factor vol {F.std():.4f} != calibrated {EQUITY_FACTOR_VOL}")
    rho = float(np.corrcoef(F[:, :-1].ravel(), F[:, 1:].ravel())[0, 1])
    assert abs(rho) < 0.05, f"factor has autocorrelation {rho:+.3f}; it should be white noise"
    assert all(p[0].equity_factor == 0.0 for p in paths), (
        "the t=0 state should carry no factor return — it describes no period")


def test_simulated_cross_country_equity_correlation_is_plausible():
    """V-C3 GUARD — the finding this whole item closes.

    Before the market factor existed, simulated cross-country equity correlation
    was +0.01 against an observed 0.5-0.9, so the country mosaic appeared to
    diversify in a way real markets do not. A single global factor cannot
    reproduce the observed matrix exactly (see the North Asia note below), so this
    asserts a plausible BAND rather than a point match:

        mean pairwise correlation over the seven markets with real return data
        reproduces 0.518 against the 0.52 the calibration implies and 0.57 observed.

    The floor is what matters — anything near zero means the factor has been
    disconnected again.
    """
    import itertools
    S = _simulate_equity_returns()
    calibrated = ["USA", "Europe", "Japan", "Korea", "Taiwan", "India", "China"]
    M = np.array([S[m].ravel() for m in calibrated])
    K = np.corrcoef(M)
    pairs = [K[i, j] for i, j in itertools.combinations(range(len(calibrated)), 2)]
    mean_rho = float(np.mean(pairs))
    assert 0.40 < mean_rho < 0.65, (
        f"mean pairwise equity correlation {mean_rho:.3f} outside the plausible "
        f"band [0.40, 0.65] — calibration implies ~0.52, observed ~0.57")
    assert min(pairs) > 0.20, (
        f"weakest pair correlates {min(pairs):.3f}; a global factor should leave "
        f"no developed/EM pair near zero")


def test_simulated_equity_total_volatility_matches_target():
    """V-C3 guard. Adding market_beta WITHOUT cutting idio_vol would have roughly
    doubled every market's volatility. The stored idio values are residuals, so
    market_beta^2 * var(F) + idio^2 must reproduce the observed total.

    Tolerance 1.0pp: the model also carries macro factor exposure worth ~2% of
    volatility, which is deliberately NOT netted out of idio (see the note in
    allocations/country_inputs.py). That biases every market ~0.2-0.6pp high, and
    the tolerance accommodates it without hiding a real break.
    """
    from allocations import COUNTRY_INPUTS
    from scenarios.engine import EQUITY_FACTOR_VOL

    # OBSERVED total volatilities from the calibration, pinned EXTERNALLY. Deriving
    # the target from the stored mbeta/idio instead would make the test vacuous:
    # it would still pass if someone added market_beta and left idio_vol at its
    # old value, which is precisely the mistake that doubles every market's vol.
    OBSERVED_TOTAL_VOL = {
        "USA": 0.152, "Europe": 0.151, "Japan": 0.168, "Korea": 0.212,
        "Taiwan": 0.206, "India": 0.217, "China": 0.248,
        # JUDGEMENT markets — implied by their assigned mbeta/idio, not observed
        "Indonesia": 0.231, "Vietnam": 0.267, "Singapore": 0.181,
    }
    S = _simulate_equity_returns()
    for market, inp in COUNTRY_INPUTS.items():
        observed = OBSERVED_TOTAL_VOL[market]
        simulated = float(S[market].std())
        assert abs(simulated - observed) < 0.010, (
            f"{market}: simulated vol {simulated:.3%} vs observed {observed:.3%} — "
            f"check that idio_vol is a RESIDUAL, not the pre-factor total")
        # and the stored parameters must reproduce that same total
        implied = np.sqrt(inp["mbeta"] ** 2 * EQUITY_FACTOR_VOL ** 2 + inp["idio"] ** 2)
        assert abs(implied - observed) < 0.002, (
            f"{market}: stored mbeta/idio imply {implied:.3%}, observed {observed:.3%}")


def test_every_engine_in_the_codebase_can_take_a_step():
    """A state extension must not silently break a second engine.

    Adding global_growth extended MacroScenarioEngine and left RegimeSwitchingEngine
    with 7-variable calibrations, which failed with an opaque shape error deep in a
    matmul — undetected because nothing constructed it. This walks every engine and
    requires each either to step successfully or to refuse with a clear
    NotImplementedError. A raw ValueError/shape error fails the test.
    """
    from scenarios.engine import MacroScenarioEngine, VARParams
    from scenarios.regimes import RegimeSwitchingEngine, default_regime_spec

    initial = mp.build_initial_state()
    engines = [
        ("MacroScenarioEngine",
         lambda: MacroScenarioEngine(VARParams(), initial, seed=1)),
        ("RegimeSwitchingEngine",
         lambda: RegimeSwitchingEngine(spec=default_regime_spec(),
                                       initial_state=initial, seed=1)),
    ]
    for name, build in engines:
        try:
            engine = build()
        except NotImplementedError:
            continue          # explicitly and legibly unsupported — acceptable
        paths = engine.simulate(n_steps=2, n_scenarios=1)
        assert len(paths[0]) == 3, f"{name}: expected 3 states, got {len(paths[0])}"
        for state in paths[0]:
            assert len(state.to_array()) == len(mp.build_initial_state().to_array()), \
                f"{name}: produced a state of the wrong width"


def test_subportfolio_without_fx_model_refuses_exposed_sleeves():
    """A sleeve declaring fx_exposures in a sub-portfolio with no FXModel must
    RAISE, not silently earn zero currency return.

    This is the general form of the Portfolio-LHP defect: Portfolio built its LHP
    without an FX model, so the unhedged sovereign overlay would have had its
    entire currency return dropped with no error and no warning.
    """
    from portfolio.portfolio import SubPortfolio, SleeveSpec
    from assets.em_bonds import GovernmentBondSleeve

    sleeve = GovernmentBondSleeve("Australia", duration=8.0, initial_yield=0.048,
                                  long_run_yield=0.048, fx_key="AUD", seed=1)
    assert sleeve.fx_exposures, "fixture sleeve should declare FX exposure"
    sub = SubPortfolio([SleeveSpec(sleeve, weight=1.0)], initial_value=1.0, fx_model=None)
    state = mp.build_initial_state()
    try:
        sub.step(state, state, dt=1.0)
    except ValueError as exc:
        assert "fx_exposures" in str(exc)
        return
    raise AssertionError("silently returned a zero FX contribution instead of raising")


def test_portfolio_gives_its_lhp_an_fx_model():
    """Portfolio must hand the SAME FXModel to both sub-portfolios.

    Fails on the pre-2026-08-22 behaviour, where only the RSP received one.
    """
    from portfolio.portfolio import Portfolio
    from assets.fx import FXModel

    fx = FXModel.default(seed=1)
    pf = Portfolio(lhp_specs=mp.build_lhp_specs(), rsp_specs=mp.build_rsp_specs(),
                   initial_value=1.0, hedge_ratio=0.5, fx_model=fx)
    assert pf.lhp._fx_model is fx, "Portfolio built its LHP without the FX model"
    assert pf.rsp._fx_model is fx


def test_within_process_reproducibility():
    paths = mp.build_scenario_engine(mp.build_initial_state()).simulate(
        n_steps=mp.N_STEPS, n_scenarios=40)
    cfg = config_with(PROPOSED_EQUITY)
    a = np.array([r.pot_path[43] for r in mp._run_batch(paths, cfg)])
    b = np.array([r.pot_path[43] for r in mp._run_batch(paths, cfg)])
    assert np.array_equal(a, b)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


# ---------------------------------------------------------------------------
# V-M3 / V-M7 guards (added 2026-08-22 with the bond-volatility recalibration)
# ---------------------------------------------------------------------------

def _simulate_bond_sleeve_returns(n_scenarios=300, n_steps=40, burn=10, seed=11):
    """Annual returns of the three bond sleeves as configured in main_participant,
    on baseline paths, after a burn-in so the state is near its unconditional
    distribution. Returns dict name -> 1-D array."""
    from assets.bonds import NominalBondSleeve, CreditBondSleeve
    from assets.linkers import LinkerSleeve
    paths = mp.build_scenario_engine(mp.build_initial_state(), seed=seed).simulate(
        n_steps=n_steps, n_scenarios=n_scenarios)
    sleeves = {
        "LongGovt":  NominalBondSleeve("LongGovt", duration=20.0, maturity=25.0),
        "ILG":       LinkerSleeve("ILG", real_duration=18.0, maturity=22.0),
        "IG_Credit": CreditBondSleeve("IG_Credit", duration=7.0, maturity=8.0, seed=seed + 4),
    }
    out = {k: [] for k in sleeves}
    for p in paths:
        for t in range(burn, n_steps):
            for k, s in sleeves.items():
                out[k].append(s.period_return(p[t], p[t + 1], 1.0))
    return {k: np.asarray(v) for k, v in out.items()}


def test_var_long_rate_annual_change_volatility_is_in_band():
    """V-M3, the parameter itself. The annual-CHANGE sd of long_rate implied by
    (Φ, Σ) — the quantity a duration sleeve actually loads on — must sit in the
    60–90bp band set from realised Bund history. Analytic, so independent of any
    simulation noise. Note persistence barely moves this (var Δx = 2σ²/(1+φ));
    if this fails, look at Σ, not Φ."""
    from scenarios.engine import VARParams, MacroState
    p = VARParams()
    V = p.sigma.copy()
    for _ in range(500):
        V = p.phi @ V @ p.phi.T + p.sigma
    DV = 2 * V - p.phi @ V - V @ p.phi.T
    i = MacroState._FIELDS.index("long_rate")
    sd_change = float(np.sqrt(DV[i, i]))
    assert 0.0060 <= sd_change <= 0.0090, (
        f"long_rate annual-change sd {sd_change*1e4:.0f}bp outside 60–90bp band")


def test_bond_sleeve_volatilities_are_in_plausible_band():
    """V-M3 guard. Bands chosen with the 2026-08-22 recalibration (see
    docs/VALIDATION_REPORT.md). Pre-fix values were 22.7% / 18.9% / 9.8%."""
    R = _simulate_bond_sleeve_returns()
    bands = {"LongGovt": (0.10, 0.17), "ILG": (0.09, 0.16), "IG_Credit": (0.05, 0.085)}
    for k, (lo, hi) in bands.items():
        v = float(R[k].std())
        assert lo <= v <= hi, f"{k}: simulated annual vol {v:.1%} outside [{lo:.0%}, {hi:.0%}]"


def test_bond_sleeve_single_year_returns_are_bounded():
    """V-M7 gap. On baseline paths no bond sleeve should post a single-year
    return beyond the bound, and years beyond ±25% must be rare. The bound is
    loose because the fixed-duration/D²-convexity sleeve legitimately overstates
    moves from high-yield starting points (recorded as a design item)."""
    R = _simulate_bond_sleeve_returns()
    for k, arr in R.items():
        assert arr.min() > -0.55 and arr.max() < 1.10, (
            f"{k}: single-year return range [{arr.min():+.0%}, {arr.max():+.0%}]")
    share = float((np.abs(R["LongGovt"]) > 0.25).mean())
    # 14% sd implies ~8% beyond ±1.75σ on Gaussian grounds; convexity skew adds ~2pp.
    assert share < 0.13, f"LongGovt: {share:.1%} of years beyond ±25% (pre-fix: 28%)"
