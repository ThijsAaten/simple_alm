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
