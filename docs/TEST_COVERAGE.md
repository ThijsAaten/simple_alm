# Test suite coverage

`tests/test_invariants.py` — **46 tests, all passing** at the V-M3 commit, 2026-08-22 (43 at `0adf3bb`).
Run with `pytest tests/` or `python -m tests.test_invariants`.

This document exists to answer one question: **will the next change be caught by the suite,
or by another audit?** For a good part of the model, the honest answer is still "by another
audit", and the second half of this document says exactly where.

> **Correction on the count.** `VALIDATION_REPORT.md` states 35 tests. Writing this document
> surfaced that **two tests were silently lost** when the FX-loadings block was rewritten
> during the global-growth round — `test_indonesia_and_vietnam_use_their_own_currencies` and
> `test_preview_fx_table_covers_every_mosaic_currency`, both of which had passed in an
> earlier run. The block replacement spanned them and did not restore them. Both have been
> restored and re-verified to fail on their respective defects, taking the suite to **37**.
> The deletion was silent because nothing tracks the test count between rounds — the same
> class of failure as everything else in the register, this time in the test suite itself.

Categories used below:

| Category | Meaning |
|---|---|
| **Invariant** | Structural. Weights sum, keys exist, values match a pinned table. |
| **Behavioural** | Right sign and plausible magnitude under a known deterministic shock. |
| **Statistical** | Simulated output checked against what the calibration implies. |
| **Regression guard** | Pins a specific defect found in validation; fails if reintroduced. |

---

## What the suite covers

### Allocations and mosaic construction

| Test | Module / behaviour | Category |
|---|---|---|
| `test_allocations_sum_to_one` | `allocations/mosaic.py` — the four canonical allocations sum to 1.0 | Invariant |
| `test_china_cap_respected` | `allocations/mosaic.py` — China ≤ 6% headline, ≤ 3% tight variant | Invariant |
| `test_mosaic_builds_one_sleeve_per_nonzero_weight` | `allocations/mosaic.py` — no silent dropping of markets | Invariant |
| `test_overlay_weights_and_eur_residual` | `allocations/bond_inputs.py` — overlay + EUR-core residual = 1.0 | Invariant |
| `test_china_overlay_defaults_to_zero` | `allocations/bond_inputs.py` — the CGB dial stays at 0% by default | Invariant |

### Cross-module seams

| Test | Module / behaviour | Category |
|---|---|---|
| `test_every_fx_key_exists_in_fx_model` | `country_inputs.py` ↔ `assets/fx.py` — every equity FX key resolves | Invariant (seam) |
| `test_overlay_fx_keys_exist_in_fx_model` | `bond_inputs.py` ↔ `assets/fx.py` — every bond FX key resolves | Invariant (seam) |
| `test_preview_fx_table_covers_every_mosaic_currency` | `allocations/preview.py` keeps a *separate* FX table; a new currency must reach it | Invariant (seam) |
| `test_indonesia_and_vietnam_use_their_own_currencies` | The THB-proxies-IDR/VND substitution stays retired | Regression guard |
| `test_rsp_and_lhp_see_the_same_fx_rates_within_a_year` | `lifecycle.py` ↔ `portfolio.py` — FX advanced once per year, both sub-portfolios reading the same draw | **Regression guard** (prior finding 1) |
| `test_macro_paths_are_not_mutated_by_a_simulation_batch` | `MacroState` is mutable and paths are reused across configs; asserts no in-place mutation | Invariant (V-m4) |

### FX loadings — semantic consistency

| Test | Module / behaviour | Category |
|---|---|---|
| `test_derived_loadings_match_the_published_table` | `assets/fx.py` — all three loading columns pinned for 12 currencies | Invariant |
| `test_no_negative_inflation_loading_outside_known_exceptions` | Euro-specific shock ⇒ no currency weakens vs EUR (CHF exempted, documented) | Invariant (semantic) |
| `test_every_derived_growth_loading_is_negative` | Euro growth strengthens the EUR ⇒ every euro-growth loading negative | **Regression guard** (prior finding 2) |
| `test_loading_columns_imply_the_same_dollar_beta` | Both columns derive from one `b_usd` and must agree within rounding | **Regression guard** (prior finding 2) |
| `test_model_implied_correlations_match_the_measured_betas` | Implied correlation matrix from stored loadings vs from raw regression coefficients | Statistical |
| `test_fx_global_growth_term_is_wired_through` | A global-growth deviation moves exactly the currencies with a loading, by exactly the calibrated amount | Behavioural |

### Macro engine

| Test | Module / behaviour | Category |
|---|---|---|
| `test_var_transition_matrix_is_stationary` | `scenarios/engine.py` — all eigenvalues of Φ inside the unit circle | Statistical (structural) |
| `test_var_covariance_is_psd_and_cholesky_succeeds` | Σ stays PSD; exercises the real `MacroScenarioEngine.__init__` path | Statistical (structural) |
| `test_macro_state_has_global_growth_and_roundtrips` | 8-wide state, `global_growth` at index `[7]`, array round-trip | Invariant |
| `test_var_simulated_moments_match_the_calibration` | Simulated means vs X̄ (±25bp) and simulated sd vs the analytic unconditional sd (±20%) | **Statistical** |
| `test_no_state_variable_explodes_or_degenerates_over_the_horizon` | Cross-sectional spread neither collapses nor blows up between year 20 and 65 | **Statistical** |
| `test_credit_spread_floor_does_not_bind_more_than_expected` | Pins the floor-binding share below 15% (currently 7.1%) | **Statistical** (V-M4) |
| `test_var_long_rate_annual_change_volatility_is_in_band` | Analytic annual-change sd of `long_rate` from (Φ, Σ) in 60–90bp | **Regression guard** (V-M3) |
| `test_bond_sleeve_volatilities_are_in_plausible_band` | Simulated LongGovt / ILG / IG_Credit annual vol inside chosen bands | **Statistical** (V-M3) |
| `test_bond_sleeve_single_year_returns_are_bounded` | No bond sleeve year outside (−55%, +110%); LongGovt years beyond ±25% under 13% | **Statistical** (V-M7) |

### Asset sleeves — behavioural

| Test | Module / behaviour | Category |
|---|---|---|
| `test_bond_price_response_matches_duration_and_convexity` | `bonds.py`, `linkers.py` — +100bp costs ≈ −D·dy + ½C·dy² | **Behavioural** |
| `test_linker_beats_nominal_when_inflation_rises` | `linkers.py` vs `bonds.py` — linker accrues exactly +2pp on a +2pp surprise | **Behavioural** |
| `test_low_pass_through_sovereign_loses_less_under_euro_repression` | `em_bonds.py` — the entire rationale for the unrepressed overlay | **Behavioural** |
| `test_low_beta_govvie_decouples_from_eur_rates` | `em_bonds.py` — high-β sleeve responds more to an EUR-rate move | Behavioural |
| `test_cape_above_anchor_drags_and_below_anchor_boosts` | `growth.py` — valuation term sign, and that it vanishes at the anchor | **Behavioural** |
| `test_carry_scales_linearly_with_dt` | `cash.py`, `bonds.py`, `linkers.py` — `dt` applied exactly once on carry | Behavioural (dimensional) |
| `test_equity_equilibrium_return_equals_its_documented_drift` | `growth.py` — every market returns its §3.1 drift at equilibrium | **Regression guard** (V-C2) |
| `test_equity_inflation_offset_does_not_differ_across_markets` | No market may receive a different permanent offset from its inflation beta | **Regression guard** (V-C2) |

### Participant lifecycle and seed hygiene

| Test | Module / behaviour | Category |
|---|---|---|
| `test_indexation_none_reproduces_nominal_average` | `lifecycle.py` — `career_average_indexation="none"` matches the raw nominal average | Behavioural |
| `test_wage_indexation_lifts_the_denominator` | `lifecycle.py` — wage revaluation raises the middelloon denominator | Behavioural |
| `test_stable_offset_is_deterministic` | `lifecycle.py` — name→offset stable across processes (no `PYTHONHASHSEED` salt) | Invariant |
| `test_sleeve_rng_streams_are_distinct_across_scenarios` | No two (scenario, sleeve) pairs share a stream | **Regression guard** (V-C1, V-M1) |
| `test_every_stochastic_sleeve_is_reachable_by_the_reseeder` | *Generalised*: any `Generator` on any sleeve, under any attribute name, must respond to a base-seed change | **Regression guard** (V-C1) |
| `test_within_process_reproducibility` | Same seeds ⇒ identical pot paths | Invariant |

---

### Equity market factor and engine/portfolio seams *(added 2026-08-22)*

| Test | Module / behaviour | Category |
|---|---|---|
| `test_equity_market_factor_has_its_calibrated_moments` | `scenarios/engine.py` — factor is mean-zero, 15.5% vol, white noise; t=0 carries none | **Regression guard** (V-C3) |
| `test_simulated_cross_country_equity_correlation_is_plausible` | `growth.py` + engine — mean pairwise correlation in [0.40, 0.65], no pair below 0.20 | **Regression guard** (V-C3) |
| `test_simulated_equity_total_volatility_matches_target` | Each market's simulated vol against its **externally pinned** observed total | **Regression guard** (V-C3) |
| `test_every_engine_in_the_codebase_can_take_a_step` | Every engine must step or refuse legibly; a raw shape error fails | **Regression guard** (V-R1) |
| `test_subportfolio_without_fx_model_refuses_exposed_sleeves` | `portfolio.py` — an FX-exposed sleeve with no FX model must raise, not earn zero | **Regression guard** (V-P1) |
| `test_portfolio_gives_its_lhp_an_fx_model` | `portfolio.py` — both sub-portfolios receive the same FXModel | **Regression guard** (V-P1) |

The volatility test is pinned against externally stated observed totals rather than against
the stored `mbeta`/`idio`. Deriving the target from the stored parameters would have made it
vacuous — it would still pass if someone added `market_beta` and left `idio_vol` at its
pre-factor value, which is exactly the mistake that doubles every market's volatility. As
written it fails that case (USA 22.1% simulated against 15.2% observed).

---

## Finding-by-finding guard status

The register in `VALIDATION_REPORT.md` has 3 Critical and 9 Major findings (V-P1 and V-R1
were added on 2026-08-22). **Seven of the twelve are guarded. Five are not.**

| ID | Severity | Guarded by | Status |
|---|---|---|---|
| V-C1 | Critical | `test_sleeve_rng_streams_are_distinct_across_scenarios` **and** `test_every_stochastic_sleeve_is_reachable_by_the_reseeder` | ✅ **Guarded, and generalised** — a future sleeve using a third attribute name is still caught |
| V-C2 | Critical | `test_equity_equilibrium_return_equals_its_documented_drift`, `test_equity_inflation_offset_does_not_differ_across_markets` | ✅ **Guarded** — both the level and the cross-market bias |
| V-C3 | Critical | `test_simulated_cross_country_equity_correlation_is_plausible`, `test_simulated_equity_total_volatility_matches_target`, `test_equity_market_factor_has_its_calibrated_moments` | ✅ **RESOLVED and guarded** (2026-08-22). Correlation floor asserted at 0.20 per pair and a [0.40, 0.65] band on the mean; volatility pinned externally |
| V-M1 | Major | `test_sleeve_rng_streams_are_distinct_across_scenarios` | ✅ Guarded |
| V-M2 | Major | — | ❌ **NOT GUARDED.** The construction-seed collisions (Europe = RealAssets = 44) are *masked* in the participant path because reseeding now overwrites them. Any caller that builds sleeves without `_run_batch` — including `main.py` — still gets colliding streams, and no test looks at construction seeds |
| V-M3 | Major | `test_var_long_rate_annual_change_volatility_is_in_band`, `test_bond_sleeve_volatilities_are_in_plausible_band` | ✅ Guarded since the 2026-08-22 recalibration — analytic 60–90bp band on Φ,Σ and simulated sleeve bands LongGovt 10–17%, ILG 9–16%, IG_Credit 5–8.5% |
| V-M4 | Major | `test_credit_spread_floor_does_not_bind_more_than_expected` | ✅ Guarded — pinned below 15%, currently 7.1% (10.1% before V-M3) |
| V-M5 | Major | *indirect only* | ⚠️ **Partially.** Understated seed dispersion was a consequence of V-C1, so fixing V-C1 fixes it. But nothing asserts that reported standard deviations are computed over genuinely independent draws — a future defect that re-froze any stochastic input would understate uncertainty again without failing any test |
| V-M6 | Major | — | ❌ **NOT GUARDED.** No test checks that a calibrated input appears in `INPUT_PROVENANCE.md`. This is mechanisable — a test could walk `COUNTRY_INPUTS`, `BOND_INPUTS` and `_DEFAULT_CURRENCIES` and assert each key is named in the doc — and it is the cheapest missing guard in this list |
| V-M7 | Major | `test_bond_sleeve_single_year_returns_are_bounded` | ⚠️ Partly — bounds single-year sleeve returns on *baseline* paths. The `repress()` boundary itself is not tested because it is a design choice still open; once a ramp is built, add a test on repressed paths |
| V-P1 | Major | `test_portfolio_gives_its_lhp_an_fx_model`, `test_subportfolio_without_fx_model_refuses_exposed_sleeves` | ✅ **RESOLVED and guarded** (2026-08-22). The second guard is general — it catches any FX-exposed sleeve in any sub-portfolio lacking a model |
| V-R1 | Major | `test_every_engine_in_the_codebase_can_take_a_step` | ✅ **RESOLVED and guarded** (2026-08-22). Verified to fail with the original raw `ValueError` when the guard is removed |

---

## What the suite deliberately does not cover

### Modules with no tests at all

| Module | Lines | Referenced by a published exhibit? | Tested? |
|---|---:|---|---|
| `scenarios/regimes.py` | 582 | No | **None** |
| `simulation/engine.py` | 236 | No | **None** |
| `analytics/metrics.py` | 267 | No | **None** |
| `liabilities/model.py` | 249 | No | **None** |
| `participant/salary.py` | 58 | Yes (via `main_participant`) | Only indirectly, through the two indexation tests |

Roughly **1,300 lines — a quarter of the codebase — carry no test at all.** `regimes.py` and
`Portfolio` are now *constructed* by tests (V-R1, V-P1) but their internals remain unexercised. Three of those
four untested modules are also unreachable from any published exhibit, which is why the
validation pass did not exercise them and why nothing in the article depends on them today.

### Behaviours asserted only indirectly

- **`portfolio.Portfolio`** (as distinct from `SubPortfolio`) has no test. Rebalancing,
  `hedge_ratio` drift and `effective_hedge_ratio` are never asserted. Only `SubPortfolio` is
  covered, through the FX-sharing test.
- **The FX PPP-gap dynamics** are exercised only as a side effect of the FX-sharing test.
  Nothing asserts the gap decays at its calibrated rate — which is precisely the defect that
  went undetected for the longest (prior finding 1's second half).
- **Decumulation** — the pension adjustment mechanism, the −3% floor, smoothing, and the
  solidarity reserve — has no direct test. `test_within_process_reproducibility` runs through
  it but asserts only determinism, not correctness.
- **Currency conversion direction.** No test asserts that a foreign return is converted once
  and in the right direction; the FX tests check the *size* of the loading, not the sign
  convention of the conversion itself.
- **`StressScenario`** constructors are never asserted, including the `global_growth`
  propagation added in the previous round.
- **N-stability** was verified manually (medians vary 0.5% between N=400 and N=5000) but is
  not in the suite, because a meaningful version costs several minutes per run.

---

## Where an undetected defect is most likely to remain

> **Update 2026-08-22.** Areas 1 and 2 below have since been resolved (V-R1 and V-P1) and
> are retained as the record of how they were found. The concern in area 3 stands unchanged,
> and `analytics/metrics.py` remains the largest untested, unaudited module in the repository.

**1. `scenarios/regimes.py` — and this is no longer a hypothetical.** *(RESOLVED — see V-R1.)* I checked it while
writing this document and **it is broken**. All four regime calibrations still carry
7-variable `long_run_mean`, `phi` and `sigma`, while `MacroState` has had eight fields since
the global-growth change. `RegimeSwitchingEngine.simulate()` raises
`ValueError: matmul: ... size 8 is different from 7`. **I introduced this defect when I added
`global_growth` and did not check the second engine that also builds `MacroState` objects.**
It affects no published number because nothing references the module — but it is the same
failure mode as everything else in the register: a seam between modules with nothing
asserting it. It is not fixed, because this task was scoped to write-up and export; it needs
either the four regime calibrations extended to eight variables, or the module explicitly
marked unsupported.

**2. `simulation/engine.py` and `portfolio.Portfolio` — a specific trap, not just absence.** *(RESOLVED — see V-P1.)*
`Portfolio.__init__` constructs its LHP as `SubPortfolio(lhp_specs, lhp_value)` with **no
`fx_model`**, while the RSP gets one. Any unhedged foreign-currency sleeve placed in the LHP
through this path — which is exactly what the bond overlay is — would have its FX return
**silently dropped to zero**, with no error and no warning. `LifecycleSimulator` does not have
this problem, and every published exhibit runs through `LifecycleSimulator`, so nothing is
currently wrong. But if anyone reproduces the overlay results through `SimulationEngine`,
they will get materially different numbers and no indication why. That is the highest-value
untested trap I know of in the codebase.

**3. `analytics/metrics.py` — here the honest answer is only that it was never run.** It is
unreferenced, untested, and I did not audit it. The only thing I noticed in passing is that
it exposes `mean_annual_return` and `std_annual_return` without any visible annualisation
convention, which in a codebase that has already produced one dimensional defect is worth a
look before any figure is ever sourced from it. I am not asserting a defect — I am recording
that I have no basis to assert its absence.

**A closing note on priors.** Of the ten Critical and Major findings, six have no guard, one
of the three unexercised modules turned out to be outright broken the moment it was executed,
and that break was introduced by this same body of work two rounds earlier. The suite is now
good at catching the specific defects that have already been found and at asserting the
seams that were audited. It is not yet a suite that would catch a *new* defect of the kind
that has been found repeatedly here.
