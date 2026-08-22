# Independent validation report — simple_alm

Performed 2026-08 as an independent validation, not by the model's author. Scope:
`scenarios/`, `assets/`, `portfolio/`, `participant/`, `liabilities/`, `allocations/`,
`simulation/`, `analytics/` and the `examples/` scripts that produce published exhibits.

**Test suite: 43/43 pass.** (Reported as 35 at the time; two tests had been silently lost in an earlier round and were restored — see `docs/TEST_COVERAGE.md` — and six were added on 2026-08-22 with the V-C3, V-P1 and V-R1 fixes.)

## Verdict up front

**The exhibits should not be submitted as they stand.** Two Critical defects were found
that change every published number, and a third — not fixable without a design decision —
inflates the case for the article's central proposal. The headline re-anchor benefit falls
by roughly a third once the defects are corrected.

The findings are concentrated in exactly the place the three prior accidental discoveries
pointed: **seams between modules, where nothing was asserted.** The economics of the
individual sleeves is largely sound; what fails is the plumbing between them, and it fails
silently.

---

## Register

| ID | Severity | Finding | Fixed? | Changes published numbers? |
|---|---|---|---|---|
| V-C1 | **Critical** | `_reseed_specs` never reached any factor sleeve; every scenario drew the identical equity idio path | **Yes** | **Yes — all of them** |
| V-C2 | **Critical** | Equity inflation applied as a level, not a deviation; no market returned its documented drift | **Yes** | **Yes — levels** |
| V-C3 | **Critical** | Cross-country equity correlation is +0.01; the mosaic's diversification benefit is an artefact | **RESOLVED 2026-08-22** | **Yes — corrected; see below** |
| V-M1 | Major | Sleeve RNG streams collided across scenarios (Taiwan ≡ RealAssets at lag 1) | **Yes** | Yes |
| V-M2 | Major | Construction seeds collide (Europe = RealAssets = 44; Japan = Commodities = 45) | Partly | No (masked by V-C1 fix) |
| V-M3 | Major | Bond return volatility ~1.5–2× plausible (LongGovt 22.7% vs 10–15%) | **RESOLVED 2026-08-22** — Σ recalibrated; LongGovt 14.3%, ILG 13.3%, IG_Credit 7.7% | **Yes — corrected; see below** |
| V-M4 | Major | `credit_spread` floor binds on 10.1% of steps; simulated process ≠ calibrated process | Partly — 7.1% after V-M3 narrowed the spread innovation | Marginal |
| V-M5 | Major | Reported seed-to-seed standard deviations were themselves understated | **Yes** (via V-C1) | Yes — all stated uncertainties |
| V-M6 | Major | Provenance doc omits the VAR, the FX non-loading block, and the equity betas | No — documentation | No |
| V-M7 | Major | `repress()` produces ±50–63% single-year LHP returns at the window boundaries | No — **re-measured after V-M3: now material, not a symptom** (+64% / −30% mean vs 11% baseline sd) | Yes, if corrected |
| V-P1 | Major | `Portfolio` built its LHP with no FX model; LHP currency returns silently dropped to zero | **RESOLVED 2026-08-22** | No (no exhibit uses that path) |
| V-R1 | Major | `scenarios/regimes.py` carried 7-variable calibrations against the 8-variable state | **RESOLVED 2026-08-22** | No (unreferenced) |
| **V-F1** | **Major** | The `b_usd` column behind 24 of the 36 FX loadings cannot be reproduced from the committed data | No — flagged, loadings unchanged | **No — measured, all changes within seed noise** |
| V-m1…m7 | Minor | Seven documentation / latent-risk defects | 3 fixed, 4 recorded | No |
| V-D1…D6 | Design | Six judgement calls, including all five known-open items | Recommendations only | — |

---

## Critical

### V-C1 — `_reseed_specs` silently skipped every factor sleeve

**Description.** `_reseed_specs` guarded on `hasattr(sleeve, "_rng")`. The bond sleeves
store their generator as `_rng`; `_FactorAssetSleeve` — the base of `EquitySleeve`,
`RealAssetSleeve` and `CommoditySleeve` — stores it as **`rng`, without the underscore**.
All ten equity sleeves, RealAssets and Commodities were therefore never reseeded. Each run
deepcopied the template, so every scenario inherited the same generator state and drew the
**identical idiosyncratic sequence**. Equity `idio_vol` of 0.16–0.28 contributed *zero*
cross-scenario dispersion; one arbitrary draw path was baked into every path as if certain.

**Evidence.** Instrumentation, not inspection. Reseeding two scenarios and comparing the
first draws: Europe, China and RealAssets identical across four scenarios; IG_Credit (which
owns `_rng`) differs. Impact on the pot distribution, N=1000:

| World | | p5 | p50 | p95 | sd |
|---|---|---:|---:|---:|---:|
| Baseline | old | 1071 | 1388 | 1856 | 241 |
| Baseline | fixed | 1042 | **1467** | **2140** | **346** |
| Repression | old | 878 | 1116 | 1445 | 173 |
| Repression | fixed | 847 | **1168** | **1673** | **256** |

Dispersion was suppressed ~45%; p95 understated ~15%; the median biased low.

**This is the finding that moves the article's headline.** Decomposing the re-anchor step:

| Configuration | (i) level | (ii) Δ baseline | (ii) Δ repression |
|---|---:|---:|---:|
| Old, as published | 1176k | +170k | +130k |
| V-C2 fixed only | 1195k | +174k | +135k |
| **V-C1 fixed only** | 1310k | **+109k** | **+83k** |
| Both fixed | 1325k | +116k | +88k |

The frozen draw path happened to favour the high-idio-vol Asian markets the re-anchor step
buys (China 0.24, India 0.24, Korea 0.26, Vietnam 0.28, against USA 0.16 and Europe 0.17).
**One arbitrary random path, favourable to the allocation the article advocates, was
presented as the central estimate.** I record explicitly that my first hypothesis — that
V-C2's cross-country tilt drove this — was wrong; V-C2 contributes +4k of the change and
V-C1 contributes −61k.

**Fix applied.** `_reseed_specs` now reseeds every Generator attribute it finds, under
either spelling. Guarded by `test_sleeve_rng_streams_are_distinct_across_scenarios` and
generalised by `test_every_stochastic_sleeve_is_reachable_by_the_reseeder`, which asserts
that *any* Generator on *any* sleeve responds to a base-seed change — so a future sleeve
introducing a third attribute name cannot reintroduce this.

### V-C2 — equity inflation applied as a level, not a deviation

**Description.** `_FactorAssetSleeve._factor_return` computed `growth_dev = growth −
long_run_growth` and then, in the same expression, applied `inflation_beta ×
state_t.inflation` — the raw **level**. The result was a permanent return offset of
`inflation_beta × π̄`. No market returned the `drift` that
`allocations/country_inputs.py` documents as "§3.1 local-currency nominal expected return
(the EquitySleeve's long-run nominal total return)".

**Evidence.** At the VAR's long-run means, with CAPE at anchor and idio suppressed:

| Market | drift (§3.1) | realised | gap |
|---|---:|---:|---:|
| USA | 4.00% | 3.25% | −0.75% |
| Europe | 7.00% | 6.25% | −0.75% |
| China | 8.40% | 7.90% | −0.50% |
| Indonesia | 8.80% | 8.30% | −0.50% |

The offset **differs by market**, because it scales with each market's own
`inflation_beta`. China and Indonesia (−0.20) received a standing 25bp advantage over
Europe and the USA (−0.30) — a permanent tilt to the article's central Asia-vs-West
comparison that appears nowhere in its inputs.

**Both readings stated.** A level-form inflation effect is defensible economics for
equities (money illusion, Modigliani–Cohn). But three things decide it: growth in the same
expression uses a deviation; `CommoditySleeve` uses the deviation form and explains why;
and `country_inputs.py` states that drift *is* the long-run nominal total return, which is
only true under the deviation form. **Judgement: defect.** Had the level form been
intended, the correct repair would have been to the documentation instead — but the
market-varying offset is indefensible under either reading.

**Fix applied.** Inflation now enters as a deviation. Every market returns exactly its
documented drift. `RealAssetSleeve` keeps the level form — its docstring states it
explicitly and real assets have a genuine inflation pass-through — so it is left alone and
recorded as V-m7. Guarded by two tests, including one asserting the offset cannot differ
across markets.

### V-C3 — cross-country equity correlation is +0.01 — **RESOLVED 2026-08-22**

**Description.** Equity sleeves share only `growth_beta × growth_dev` and
`inflation_beta × infl_dev` as common factors. Those contribute ~2% of return volatility
against idiosyncratic volatilities of 17–26%, so the model produces **essentially
independent** country equity returns.

**Evidence.** Simulated pooled annual correlations (250 paths × 65 years):

```
             LongGovt   ILG  Credit  EqEurope  EqChina  RealAst  Commod
EqEurope        -0.01 -0.01   -0.03      1.00     0.01    -0.00    0.01
EqChina         -0.00  0.00   -0.03      0.01     1.00     0.01    0.01
```

Historical DM/EM equity correlation is +0.6 to +0.8. The consequence for the article's
central proposal:

| Allocation | simulated blended equity vol |
|---|---:|
| CURRENT (ACWI-like, 5 markets) | 10.7% |
| PROPOSED A (mosaic, 10 markets) | **8.4%** |

Global equity vol is 15–17% in reality. **The mosaic appears 2.3pp less volatile than the
cap-weighted allocation purely because it holds more countries with independent draws.**
That is a manufactured risk advantage for the proposal the paper advocates.

`allocations/preview.py` in this same repository assumes the opposite — `common = 0.14`
with `corr 0.75 across markets` — and reports ~14.5–15.9% blended vol. **Two components of
the codebase model the world incompatibly**, and the exhibit-producing one is the
optimistic one.

**RESOLVED 2026-08-22.** A global equity market factor was added: `MacroState.equity_factor`
(15.5% p.a., mean zero), drawn as a ninth *innovation* alongside the macro shocks rather than
added to the VAR state vector, plus a `market_beta` on `EquitySleeve`. Each market's
`idio_vol` was replaced with the regression *residual*, so `market_beta² × var(F) + idio²`
reproduces its observed total volatility.

| | Before | After | Observed |
|---|---:|---:|---:|
| Mean pairwise correlation (7 calibrated markets) | **+0.01** | **0.518** | 0.57 |
| Blended equity vol, CURRENT | 10.7% | ~15% | 15–17% |
| Blended equity vol, PROPOSED A | 8.4% | ~15% | 15–17% |

The spurious 2.3pp mosaic volatility advantage is gone. **The risk-based claim for the mosaic
can now be made**, within the limits below.

**Guards:** `test_simulated_cross_country_equity_correlation_is_plausible` (asserts mean
pairwise correlation in [0.40, 0.65] and no pair below 0.20; fails at +0.01 on the old
behaviour), `test_simulated_equity_total_volatility_matches_target` (pins each market against
its *externally* stated observed total, so it also catches adding `market_beta` while leaving
`idio_vol` at its pre-factor value), and `test_equity_market_factor_has_its_calibrated_moments`.

**Residual limitation, not fixed:** a single global factor under-fits North Asia —
Korea–Taiwan 0.44 and China–Taiwan 0.37 against observed values roughly 0.16–0.26 higher. A
second Asian regional factor is the natural remedy and the natural home for the supply-chain
concentration the article's geopolitics section discusses. Recorded as a design option.

Full detail: `output/equity_factor_summary.md`.

---

## Major

**V-M1 — sleeve RNG streams collided across scenarios. Fixed.** `_reseed_specs` composed
seeds additively (`base_seed + offset`) while `base_seed` increments by one per scenario,
so any two sleeves whose name-derived offsets differed by less than N shared a stream.
Taiwan (82420) and RealAssets (82419) differ by **one**: scenario *i*'s Taiwan drew the
identical sequence to scenario *i+1*'s RealAssets, with both live in the RSP at once. Five
colliding pairs within N=1000, affecting 12.2% of sleeve-runs — and **worsening with N**
(20.6% at N=5000), so more paths made the dependence worse. Fixed by composing seeds as a
sequence through `SeedSequence` with a domain tag separating RSP/LHP/FX; verified 22,000
of 22,000 streams distinct.

**V-M2 — construction seeds collide.** `build_equity_specs(seed=SEED+1)` assigns `seed+i`
per country, while `build_rsp_specs` uses `SEED+2`, `SEED+3`, `SEED+4`. Europe and
RealAssets both get 44; Japan and Commodities both get 45; Korea and IG_Credit both get 46.
Verified by identical draw sequences. Now masked in the participant path because the V-C1
fix reseeds everything, but it remains live for any caller that builds sleeves without
`_run_batch` — including `main.py`. **Not fixed** (changing seed constants is a numbers
change with no upside once reseeding works); recorded so it is not rediscovered.

**V-M3 — bond volatility is 1.5–2× plausible. RESOLVED 2026-08-22.** Simulated annual
return volatilities against market reality, before and after:

| Sleeve | before | after | plausible | max single-year before → after |
|---|---:|---:|---|---:|
| LongGovt (D=20) | 22.7% | **14.3%** | 10–15% | 127% → 89% |
| ILG (D=18) | 18.9% | **13.3%** | 10–14% | 91% → 78% |
| IG_Credit (D=7) | 9.8% | **7.7%** | 5–7% | 44% → 39% |
| Equity Europe | 17.3% | 17.3% | 15–18% ✓ | unchanged |

**Diagnosis, measured rather than assumed.** Variance decomposition of the LongGovt return
on baseline paths: the level term (−D·Δ`long_rate`) accounted for 106% of variance, carry 3%,
convexity 2%, slope/curvature −11% (the 25y Nelson-Siegel yield moves slightly less than the
level factor). The duration mapping is therefore *not* the error. Nor is persistence: for an
AR(1) the annual-change variance is 2σ²/(1+φ), so with φ = 0.80 the change sd (125bp) is
almost the innovation sd (120bp) — lowering φ would narrow the *level* distribution and do
nothing for returns. The innovation volatility was simply too high: realised annual changes
in 10y Bund yields 1999–2025 have an sd of ~85bp including 2022 and ~70bp without it, and 30y
yields move less.

**Change.** `scenarios/engine.py::_default_sigma` vols: `long_rate` 0.0120 → **0.0070**,
`real_rate` 0.0100 → **0.0065**, `credit_spread` 0.0060 → **0.0045**. Φ and the innovation
correlation matrix untouched; Σ remains PSD and the augmented 9×9 is rebuilt from the same
vector, so the equity-factor correlations are preserved. Resulting analytic annual-change sd
of `long_rate` is 73bp; the 25y NS yield 69bp. Status: judgement (euro-area long-yield history
is not in the repository), recorded in `INPUT_PROVENANCE.md` with a pending Bloomberg check.

**Side effects, all in the right direction.** (i) LongGovt mean return falls from 6.8% to
5.4% on a 4.5% yield — the earlier figure was a convexity windfall (½·D²·Δy²) from yields
that were too volatile, so the LHP was being paid for a defect. (ii) V-M4's floor-binding
share drops from 10.1% to 7.1%. (iii) IG_Credit lands marginally above its band at 7.7%;
the remainder is the spread/jump block and the +0.30 rate–spread innovation correlation
(spreads historically widen when rates *fall*), recorded as V-D7.

**Guards added:** `test_var_long_rate_annual_change_volatility_is_in_band` (analytic, on Φ,Σ),
`test_bond_sleeve_volatilities_are_in_plausible_band`,
`test_bond_sleeve_single_year_returns_are_bounded`.

**Effect on published numbers:** see `output/bond_volatility_summary.md`.

**V-M4 — the `credit_spread` floor binds on 10.1% of steps.** The floor at 0.0 truncates
the left tail, lifting the simulated mean 11bp above X̄ (0.0111 vs 0.0100) and pulling the
simulated sd below the analytic unconditional value (0.0079 vs 0.0090). Every other
variable matches X̄ to within 8bp and its analytic sd to within 4%. Pinned by
`test_credit_spread_floor_does_not_bind_more_than_expected` so it cannot silently worsen.

**V-M5 — the previously reported uncertainties were themselves understated.** Because
equity idio was frozen (V-C1), seed-to-seed dispersion was artificially small. The
re-anchor step was reported as **+172.5 ± 1.9k**; correctly it is **+115.7 ± 8.1k**. Both
the estimate and its stated precision were wrong, and the precision was wrong in the
direction that made prior "within noise" judgements — including several I made in earlier
rounds of this work — look better supported than they were.

**V-M6 — provenance is complete for article-sourced inputs and absent for everything else.**
All ten equity markets, their drifts and CAPEs, all six sovereign yields and betas, and the
FX inflation/growth loadings are traceable. Not traceable: the **entire VAR calibration**
(Φ and Σ, 128 numbers — the largest unsourced block, and the one V-M3 shows is
mis-specified); the FX `carry_spread` / `fx_drift` / `ppp_reversion` / `initial_ppp_gap` /
`idio_vol` block (75 numbers, driving the FX tailwind central to the overlay thesis); the
equity `gbeta` / `ibeta` / `idio` inputs (30 numbers, and `idio` drives the whole
dispersion); and the participant config (contribution 20%, ambition 70%, floor −3%,
solidarity 5%, λ=5.0). GBP and New Zealand are never named in the document.

**V-M7 — `repress()` produces ±50–63% single-year LHP returns at the window boundaries.**
Pinning the state at year 25 drops `long_rate` from ~4.5% to 2.0% instantaneously. The
original judgement was that this was a symptom of V-M3, because the baseline path showed
the same extremes. **Re-measured after V-M3 (2026-08-22), that excuse is gone.** Baseline
LHP single-year sd is now 11.2% with 4.6% of years beyond ±25%; the repression boundary
produces a mean **+64.2%** (p5 +20%, p95 +118%) at the open and **−30.2%** at the close.
The step itself is unchanged by the recalibration — `repress()` imposes a fixed −243bp
average shock whatever Σ says — so it is now a genuine outlier rather than noise, and it
is *in* the repression leg of every published participant number. A ramped transition
(e.g. linear over 3 years into and out of the window) is now worth building; recommended,
not implemented here, because it changes the repression definition (decision D-level) and
the scenario's stated "12-year window" would need restating.

---

## V-F1 — the FX `b_usd` column is not reproducible (found 2026-08-22)

**Severity: Major.** The loadings may be right; they cannot be traced. Nothing is changed.

**Context.** `data/fx_bloomberg_legs.csv` completed the FX source data, so the loading
regression could finally be attempted. `calibration/fx_loading_calibration.py` now implements
the method exactly as `assets/fx.py` documents it.

**The pipeline is correct — verified four independent ways, all exact:**

| Check | Published | Reproduced |
|---|---|---|
| All 11 currency correlations with the USD | round-3 table | exact to 3dp, all 11 |
| CNY–USD correlation | **0.92 (the article's own figure)** | **0.923** |
| IDR annualised volatility | 11.1% | 11.1% |
| THB annualised volatility | 8.2% | 8.2% |
| All 12 `global_growth_loading` values | `assets/fx.py` | **12/12 exact** |

`global_growth_loading` comes from the residual growth beta of the *same* regression, and it
reproduces perfectly. So the data, the conventions and the regression are right.

**What does not reproduce.** The `b_usd` column, and therefore `inflation_loading`
(= 0.50 × b_usd) and `growth_loading` (= −0.30 × b_usd):

| ccy | b_usd derived | b_usd published | diff |
|---|---:|---:|---:|
| KRW | 0.240 | 0.760 | **−0.520** |
| IDR | 0.565 | 0.997 | **−0.432** |
| INR | 0.621 | 0.938 | −0.317 |
| JPY | 0.686 | 0.447 | **+0.239** |
| GBP | 0.355 | 0.596 | −0.241 |
| TWD | 0.655 | 0.863 | −0.208 |
| THB | 0.610 | 0.814 | −0.204 |
| SGD | 0.547 | 0.720 | −0.173 |
| CNY | 0.856 | 0.933 | −0.077 |
| VND | 0.981 | 1.027 | −0.046 |
| HKD | 0.985 | 0.988 | −0.003 |
| USD | 1.000 | 1.000 | anchor |

Searched and rejected: univariate vs joint; MSCI World in EUR, in USD, and ACWI in both;
log vs simple returns; and 28 start/end window combinations. The best case anywhere in that
space still misses KRW by 0.236 and JPY by 0.164 **in opposite directions**, so no single
specification explains it.

**A specific inconsistency.** The published `b_usd` is also inconsistent with the *round-3*
univariate column on the same data and window — that column reproduces exactly here
(KRW 0.300, IDR 0.615, CNY 0.865), while the round-4 `b_usd` claims 0.760, 0.997 and 0.933
for the same three currencies. Both were described as a beta against the USD.

**Consequence if re-derived:** 8 of 12 `inflation_loading` values and 9 of 12
`growth_loading` values would change — KRW 0.40 → 0.10, IDR 0.50 → 0.30, JPY 0.20 → 0.35
(the opposite direction). `global_growth_loading` would not change at all.

**Measured impact: none beyond noise.** Re-deriving all 17 differing loadings and re-running
both exhibits, 3 seeds at N=1000:

| | Baseline committed → re-derived | Repression committed → re-derived |
|---|---|---|
| (ii) +Re-anchor | +103.6 ± 4.3 → +102.9 ± 4.7 | +79.6 ± 1.7 → +79.4 ± 2.9 |
| (iii) +China cap | +2.4 ± 1.4 → +2.8 ± 0.6 | +2.9 ± 1.3 → +1.4 ± 3.0 |
| (iv) +Bond side | +26.8 ± 2.4 → +26.0 ± 1.4 | +40.0 ± 1.7 → +41.0 ± 2.6 |
| CGB Δ(5%) | −6.3 ± 3.4 → −4.8 ± 1.2 | +2.9 ± 2.5 → +1.7 ± 1.2 |

**Every change is inside one seed standard deviation**, the largest being −1.5k on the
China-cap step under repression. The loadings enter only through mean-zero deviation terms on
a modest unhedged-FX share of the portfolio, and the individual currency changes partly
offset. So this is a **provenance defect, not a numerical one**.

**Not changed, but the recommendation is now to change it.** Because adopting the derived
values costs nothing measurable, doing so would move 24 loadings from "cannot be traced" to
"reproducible from committed data and a committed script", closing the last provenance gap in
the model at no cost to any exhibit. That is a good trade — but it is still a decision about
17 live parameters and belongs to the repository owner, not to a calibration run.
`python calibration/fx_loading_calibration.py` prints the comparison and exits without
touching `assets/fx.py`.

---

## Resolved after the validation pass

**V-P1 — `Portfolio` built its LHP without an FX model. Fixed both ways.** `Portfolio.__init__`
now passes the same `FXModel` to both sub-portfolios, *and* `SubPortfolio.step` raises if a
sleeve declares `fx_exposures` while no FX model or `fx_returns` is available. The second is
the general protection against this class of error. Guarded by
`test_portfolio_gives_its_lhp_an_fx_model` and
`test_subportfolio_without_fx_model_refuses_exposed_sleeves`.

**V-R1 — `scenarios/regimes.py` broken by the state extension. Marked unsupported.**
`RegimeSwitchingEngine` now raises `NotImplementedError` at construction, naming the cause and
what re-enabling requires, instead of failing with an opaque shape error inside a matmul.
Extending its four regime calibrations would have required four sets of unsourced
`global_growth` parameters in a codebase where missing provenance is already Major finding
V-M6. Guarded by `test_every_engine_in_the_codebase_can_take_a_step`, which requires every
engine either to step or to refuse legibly.

---

## Minor

- **V-m1 (fixed)** — `em_bonds.py` docstring wrote the pass-through term as
  `β_global × Δy_EUR × dt`; the code omits the `dt`. The **code is right** (Δy_EUR is
  already a period change). Identical at dt=1.0, the only step length used.
- **V-m2 (fixed)** — the state-vector index comment in `scenarios/engine.py` never gained
  `[7] global_growth`.
- **V-m3 (fixed)** — `bonds.py` listed "model the credit spread as an additional VAR state
  variable (requires 8D VAR)" as future work; it has been state variable [5] all along.
- **V-m4 (recorded)** — `MacroState` is a mutable dataclass and the same path list is
  reused across configurations. No current code mutates it (verified by hashing before and
  after a batch, now asserted by `test_macro_paths_are_not_mutated_by_a_simulation_batch`),
  but `frozen=True` would remove the risk permanently.
- **V-m5 (recorded)** — `CreditBondSleeve` combines `spread_duration` with `convexity`
  derived from rate `duration`. No effect today because IG_Credit sets them equal.
- **V-m6 (recorded)** — GBP and New Zealand absent from `INPUT_PROVENANCE.md`.
- **V-m7 (recorded)** — inflation convention now differs deliberately across sleeves:
  Equity uses deviations (V-C2), RealAssets uses the level (documented), Commodities uses
  deviations (documented). Each is internally consistent; the set is not uniform.

---

## Design — recommendations only, code left alone

- **V-D1 — the global-growth factor is probably the wrong object.** Confirmed: it is
  calibrated as GDP (mean 3.0%, vol 2.0%) while the currency loadings on it were derived
  from regressions against global *equity* returns, whose volatility is roughly 8× larger.
  The `0.60` conversion factor bridges the two by borrowing `EquitySleeve.growth_beta`.
  Because the loadings are small (0 to 0.15) the distortion is currently minor — a 2pp GDP
  deviation moves KRW by 30bp — but under stress the factor cannot deliver the risk-appetite
  behaviour the regressions measured, since a GDP variable with 2% vol never moves as far as
  equities do. **Recommendation: re-specify the factor as a risk/cycle variable** (higher
  volatility, lower persistence) and re-derive the loadings against it, rather than
  re-deriving against a GDP series — the economics being captured is risk appetite, and the
  currencies that load on it (KRW, IDR) are risk-on currencies, not GDP-beta currencies.
- **V-D2 — `EURO_CYCLE_SHARE` is unvalidated.** The external estimate (Japan 0.08, Korea
  0.13, India 0.21, Asia ex-Japan 0.23, China 0.31) is directionally consistent with the
  current EM values but materially higher. Its developed-market figures are unusable, as
  noted, because a World index that is ~70% US makes the euro-specific residual mechanically
  negative against the US. **To estimate all of them properly you need a euro-area factor
  that is orthogonal to the World index by construction** — regress each market on
  `[World, Europe-ex-World-residual]` where the second is Europe's return orthogonalised
  against World, so the US no longer absorbs the common component. Until then the Asian
  shares can be adopted and the developed ones cannot.
- **V-D3 — the consistency test uses a reconstructed reference.** It compares the stored
  loadings against the published regression coefficients, so it cannot detect an error in
  the regression itself. **The fixture that would upgrade it** is the underlying return
  panel — monthly EUR-cross log returns per currency plus the MSCI World EUR series,
  2001–2026, committed as a small CSV (~300 rows × 14 columns). With that the test could
  re-run the regression and assert the loadings against a recomputed beta rather than a
  transcribed one.
- **V-D4 — `POST_2017_INFLATION_LOADINGS` is stale.** Univariate-derived, superseded by the
  joint estimates, and does not vary the global column. Flagged in the file. Either
  re-estimate jointly or withdraw the sensitivity; as it stands it is not comparable to the
  headline table.
- **V-D5 — CHF, CAD, AUD remain un-derived.** Confirmed unresolvable without an FX pull.
  CHF's `inflation_loading` of −0.30 is the last remaining negative and contradicts its own
  comment. **AUD matters more than its size suggests**: it still proxies NZD in the bond
  overlay, so its `growth_loading` of +0.20 — global-cycle exposure sitting in the
  euro-growth column — reaches the LHP directly. The `data/fx_history_bloomberg.xlsx`
  workbook already built would need CHF, CAD, AUD and NZD legs added.
- **V-D6 — sub-annual `dt` is not supported.** Carry terms scale correctly but yield-change
  terms do not, so `dt=0.5` produces returns larger than `dt=1.0` in the O-U sleeves. Every
  published run uses `dt=1.0`. Recommend asserting `dt == 1.0` rather than fixing.

- **V-D7 — fixed modified duration and D² convexity (added 2026-08-22).** The sleeves hold
  D constant whatever the yield level. The largest baseline LongGovt year after V-M3 (+74%)
  is a 260bp fall from an 8.6% starting yield; a real 25y bond yielding 8.6% has a modified
  duration nearer 11 than 20, and D² is a zero-coupon convexity. Returns from high-yield
  states are overstated roughly twofold. Affects tails only; a yield-dependent duration
  (D = f(y, τ)) would be the fix. Also: the +0.30 rate–spread innovation correlation has the
  wrong sign for flight-to-quality episodes and is why IG_Credit stays marginally above band.

---

## Regenerated exhibits

Attribution, marginal Δ, €000, **5 seeds**, N=1000:

| Step | World | As published | Validated | Change |
|---|---|---:|---:|---|
| (i) Current *(level)* | Baseline | 1179.4 ± 9.6 | **1331.9 ± 10.7** | **+152.5** |
| (i) Current *(level)* | Repression | 918.3 ± 9.4 | **1037.4 ± 6.0** | **+119.1** |
| (ii) +Re-anchor | Baseline | +172.5 ± 1.9 | **+115.7 ± 8.1** | **−56.8 (−33%)** |
| (ii) +Re-anchor | Repression | +135.2 ± 1.5 | **+88.0 ± 3.0** | **−47.2 (−35%)** |
| (iii) +China cap | Baseline | −2.6 ± 1.6 | −2.9 ± 5.4 | within noise |
| (iii) +China cap | Repression | −2.6 ± 0.5 | −3.0 ± 2.4 | within noise |
| (iv) +Bond side | Baseline | +23.2 ± 2.7 | +27.5 ± 3.5 | +4.3 (t≈2.2) |
| (iv) +Bond side | Repression | +43.2 ± 1.4 | +44.3 ± 2.7 | within noise |

CGB dial, Δ(5% vs 0%), 3 seeds:

| Calibration | World | As published | Validated |
|---|---|---:|---:|
| 1.8→2.3% | Baseline | −4.39 ± 0.58 | **−5.85 ± 2.75** |
| 1.8→2.3% | Repression | +0.04 ± 0.50 | **+1.33 ± 1.24** |
| 1.8% flat | Baseline | −6.05 ± 0.68 | −7.77 ± 2.75 |
| 1.8% flat | Repression | −1.24 ± 0.60 | −0.20 ± 1.25 |

The CGB left-tail claim weakens: baseline p5 now *declines* slightly with weight
(1042→1039k), and only the repression world shows a gain (847→851k). Previously reported as
+6k baseline and +10k repression.

**Exhibit 6 requires full regeneration** — both bars and both level and delta rows. This is
no longer a cosmetic refresh: the re-anchor bar changes by a third.

---

## Addendum — decomposition of the level shift and the step fall

Asked whether the +152.5k rise in the Current level and the one-third fall in the re-anchor
step are one effect or two. **They are two distinct consequences of one defect (V-C1), and
V-C2 contributes only marginally — in the opposite direction for the step.**

Single seed (42), N=1000, each fix applied in isolation and then jointly:

| Quantity | World | Old (published) | V-C2 only | V-C1 only | Both | V-C2 share | V-C1 share | Interaction |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| (i) level | Baseline | 1176 | 1195 | 1310 | 1325 | **+19** | **+134** | −4 |
| (i) level | Repression | 925 | 939 | 1026 | 1038 | **+14** | **+101** | −2 |
| (ii) Δ | Baseline | +170 | +174 | +109 | +116 | **+4** | **−61** | +3 |
| (ii) Δ | Repression | +130 | +135 | +83 | +88 | **+5** | **−47** | 0 |

**V-C1 accounts for ~90% of the level shift and more than all of the step fall** — V-C2
pushes the step slightly *up*, partially offsetting it. Interaction between the two fixes is
negligible (≤4k everywhere), so the effects are cleanly additive.

**Why one defect produces two different-looking movements.** The frozen idiosyncratic path
was, in absolute terms, a below-median draw, so unfreezing it raises the median pot for
*every* allocation:

| Allocation | World | p50 before | p50 after | Change |
|---|---|---:|---:|---:|
| CURRENT | Baseline | 1213.9 | 1348.4 | **+134.4** |
| CURRENT | Repression | 976.5 | 1082.6 | **+106.1** |
| PROPOSED A | Baseline | 1388.2 | 1466.6 | **+78.5** |
| PROPOSED A | Repression | 1115.8 | 1168.2 | **+52.4** |

The level rise is therefore *not* Asia-specific. The re-anchor step falls because the rise is
**larger for CURRENT (+134.4k) than for PROPOSED A (+78.5k)** — the frozen path was
relatively more favourable to the high-idiosyncratic-volatility Asian markets the re-anchor
step buys, so unfreezing it removes more of a spurious advantage from the Asia-heavy
allocation than from the cap-weighted one. The difference, +134.4 − 78.5 ≈ 56k, is the fall
in the step.

These two movements are logically separable, not one artefact seen twice: a frozen path could
have been unlucky in absolute terms while neutral across markets (level up, step unchanged),
or neutral absolutely while favouring Asia (level unchanged, step down). Both happened to be
true of this particular path.

Per-seed source data: `output/validated_attribution.csv`, `output/validated_pot_distributions.csv`.

---

## Closing statement

**The model's sleeve-level economics is sound and its plumbing is not.** Every behavioural
test in Method D passed with the right sign and a defensible magnitude: bonds lose duration
× shock net of convexity, linkers accrue inflation exactly, low-pass-through sovereigns
import less of a EUR repression, CAPE above anchor drags and below anchor boosts, and the
FX loadings apply exactly as calibrated. The VAR is stationary, PSD, matches its specified
long-run means to within 8bp on seven of eight variables, and neither drifts nor degenerates
over 65 years. Reproducibility is exact, seeds are now genuinely independent, and N=1000 is
adequately sampled (medians vary 0.5% between N=400 and N=5000).

**What I would stand behind now:** the direction and rough magnitude of the bond-side step
(iv), which survived every fix within noise in both worlds and is the narrowest, best-tested
claim in the paper. The China-cap step (iii), which is indistinguishable from zero and was
always reported as such. The CGB dial's qualitative conclusion — costs at baseline, free
under repression, 2–3% defensible — which survived, though with materially wider uncertainty
and a weakened left-tail claim.

**What must be regenerated:** every level, every percentile, and the re-anchor step. The
re-anchor benefit was overstated by roughly a third because one frozen random draw path
happened to favour the high-idiosyncratic-volatility Asian markets the proposal buys. That
is the kind of error a referee would not find but that would invalidate the result if
anyone reran it, and it is the single most consequential thing in this report.

**What rests on unvalidated assumptions:** the risk case for the country mosaic, which I
would withdraw entirely until V-C3 is addressed — an 8.4% versus 10.7% volatility advantage
that comes from holding more countries with uncorrelated draws is not a finding about
markets. The absolute level of LHP volatility and any claim resting on it, given V-M3. And
the entire VAR calibration, which has no recorded provenance and demonstrably produces bond
volatility well outside the plausible range.

Three material defects were found by accident in the preceding week; this systematic pass
found three more of Critical severity and seven Major, all at module seams, all silent, and
two of them in the same forty-line function. **The prior that more remains is still the
right prior.** The specific areas I would examine next are `scenarios/regimes.py` and
`simulation/engine.py`, which are in scope but produce no published exhibit and so were not
exercised by this pass, and `analytics/metrics.py`, whose outputs I did not trace to any
figure.
