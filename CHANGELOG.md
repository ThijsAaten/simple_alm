# Changelog

Reverse-chronological. Everything between `0adf3bb` (2026-06-15) and 2026-08-22 was
developed without intermediate commits, so this file is the history the git log does not
have. Finding IDs refer to `docs/VALIDATION_REPORT.md`.

**Headline:** the re-anchor attribution step — the paper's largest single number — falls from
**+166.4k** (what the June code produces) to **+105.2k**, a **37% reduction**. Measured
against the +172.5k figure current immediately before validation, the fall is **39%**. All
figures are 5-seed means at N=1000.

---

## 2026-08-23 — V-D5: the last four currencies derived, the last FX proxy retired

CHF, CAD, AUD and NZD derived by the standard joint regression from the committed
Bloomberg legs (`data/fx_bloomberg_legs.csv`); NZD added as a first-class currency and the
AUD-proxies-NZD substitution in the sovereign overlay retired. CHF's −0.30 — the last
negative inflation loading — became a measured **+0.10** (the data agreed with its own
comment); CAD's misplaced +0.10 euro-growth loading was global-cycle exposure (+0.15, right
column); AUD and NZD emerged as near-identical pure-cycle currencies (b_usd ≈ 0, global
+0.20), so the retired proxy was benign — now measured rather than assumed. The model now
has 16 currencies, zero proxies, zero negative loadings, all three loading columns
reproducible.

**Moves published numbers: no — measured.** Five seeds, N=1000, `vd5_*` vs `vm7_*`: every
waypoint within seed noise (largest |t| = 1.1); the bond-side repression step +0.0k. The
`vd5_*` files become the current exhibit record. Tests remain 48, with the guard-set
exceptions (`UNDERIVED`, `KNOWN_NEGATIVE_LOADINGS`) now empty.


## 2026-08-22 — Global equity market factor, and two seam repairs

**Closes V-C3.** Equity sleeves had no market factor at all: they carried only macro
exposures against idiosyncratic volatility of 16–28%, so simulated cross-country equity
correlation was **+0.01** against 0.5–0.9 observed. The country mosaic therefore appeared to
diversify in a way real markets do not — the mosaic showed 8.4% blended volatility against
the cap-weighted allocation's 10.7%, a 2.3pp advantage that was entirely manufactured.

- Added `MacroState.equity_factor` (15.5% p.a., mean zero), drawn as a **ninth innovation**
  rather than a ninth VAR state variable — `F` is a return, not a level, and has no
  persistence. Φ and Σ are untouched.
- Added `market_beta` to `EquitySleeve`; replaced every `idio_vol` with the regression
  **residual**, so `market_beta² × var(F) + idio²` reproduces observed total volatility.
- Mean pairwise correlation now **0.518** against 0.57 observed.
- `allocations/preview.py` rewritten to the same single-factor model — it had been assuming
  a 14% common factor at 0.75 correlation, the very assumption the simulation contradicted.
- **V-P1**: `Portfolio` built its LHP with no FXModel while the RSP received one, silently
  dropping LHP currency returns to zero. Fixed both ways — the LHP now receives the model,
  and `SubPortfolio` raises if an FX-exposed sleeve has none.
- **V-R1**: `scenarios/regimes.py` carried 7-variable calibrations against the 8-variable
  state. Marked unsupported with a `NotImplementedError` naming the cause.

**Moves published numbers: yes.** Re-anchor step +115.7k → **+105.2k** baseline (t = 2.5);
the China-cap step flips sign under repression, −3.0 → **+2.7** (t = 4.9), because spreading
across more markets is no longer mechanically rewarded. Bond-side step unchanged within noise.
CGB dial conclusions unchanged. Tests 37 → 43.

## 2026-08-21 — Independent validation

A systematic validation pass (methods A–G: semantic consistency, cross-module seams,
dimensional audit, behavioural tests, statistical properties, seed hygiene, provenance).
Found **three Critical and seven Major** defects. Two Criticals fixed in this round.

- **V-C1 (Critical)** — `_reseed_specs` guarded on `hasattr(sleeve, "_rng")`, but
  `_FactorAssetSleeve` stores its generator as `rng`, without the underscore. **All ten
  equity sleeves, RealAssets and Commodities were never reseeded**, so every scenario drew
  the identical idiosyncratic path. Pot dispersion suppressed ~45%, p95 understated ~15%,
  median biased. One arbitrary draw path — favourable to the Asia-heavy allocation the paper
  advocates — was reported as the central estimate.
- **V-C2 (Critical)** — `_factor_return` applied `inflation_beta` to the raw inflation
  **level** while applying growth as a **deviation** in the same expression. No market
  returned its documented drift, and the offset scaled with each market's own
  `inflation_beta`, handing China and Indonesia a standing 25bp advantage over Europe and
  the USA.
- **V-M1 (Major)** — sleeve RNG streams collided across scenarios: Taiwan (offset 82420) and
  RealAssets (82419) shared a stream one scenario apart, both live in the RSP at once. 12.2%
  of sleeve-runs at N=1000, **worsening to 20.6% at N=5000**.

**Moves published numbers: yes, substantially.** Re-anchor step +172.5k → **+115.7k**
baseline, +135.2k → +88.0k repression. Decomposition: V-C1 accounts for ~90% of the level
shift and more than all of the step fall; V-C2 pushes the step slightly the other way.
Reported standard deviations were themselves understated, because frozen idio meant
artificially small seed dispersion.

Also fixed: three documentation defects where a comment contradicted the code. Tests 26 → 35
(later corrected to 37 — two tests had been silently lost in the previous round).

## 2026-08-21 — Global growth factor

`growth` had always been euro-area growth, but currency and equity betas were loading on it
as though it were a global cycle: five currencies carried **positive** `growth_loading`
values justified by comments describing "risk-on" and "global growth", a factor the model did
not have.

- Added `global_growth` at state index `[7]`. Euro growth is a price-taker: spillover 0.20
  in, **zero** out.
- Added `global_growth_loading` to `CurrencyParams` and a third macro term to the FX return.
- Re-derived all three FX loading columns from **one joint regression** per currency,
  superseding the univariate estimates, which had absorbed shared growth exposure into the
  dollar coefficient (KRW 0.15 → 0.40, IDR 0.30 → 0.50, JPY 0.35 → 0.20).
- Added `growth_mode` to `build_equity_specs` (`euro` / `split` / `global`), default
  unchanged, so the equity-side version of the same question could be measured without
  changing any number.
- Side effect recorded: euro growth's unconditional volatility rises 10.9% and credit
  spread's 7.1%, because both inherit global-cycle variance.

**Moves published numbers: no waypoint moved significantly.** Every attribution Δ stayed
within seed noise despite twelve currencies being re-estimated — the revisions offset.

## 2026-08-21 — FX inflation-loading table and proxy retirement

- Applied a fully derived `inflation_loading` table. **Two of the old negative values were
  plain sign errors**: JPY at −0.20 and CHF at −0.30 carried inline comments describing the
  *opposite* of what the number did.
- Established that no loading may be negative: the repression world is euro-*specific*, so
  every non-euro currency should appreciate against the EUR.
- **Retired the THB-proxies-IDR substitution.** Found in more places than reported —
  Vietnam was proxied by THB too, and `allocations/preview.py` carried a separate FX table
  that would have raised `KeyError`. Added IDR, VND and SGD as first-class currencies.
- **NZD is still proxied by AUD.** That substitution remains live.

**Moves published numbers: yes.** Isolated, the Indonesia change alone is +7.05k baseline.

## 2026-08-20 — CGB calibration reconciliation

`allocations/bond_inputs.py` and the `assets/em_bonds.py` docstring disagreed on both carry
and decoupling, and `bond_inputs.py` was what drove results.

- Long-run yield raised **1.8% → 2.3%** so the sleeve is not assumed to sit at a cyclical low
  permanently; `global_rate_beta` 0.10 retained with the article's §13 Fed–PBoC correlation
  of ≈0.03 recorded inline; class defaults reconciled so the two files cannot drift apart.
- Corrected the store-of-value language. **I had myself written "the sleeve loses real value"
  into four files before measuring it** — it does not; it earns +0.92% real at baseline and
  +0.75% under repression. What fails is out-earning the EUR core it displaces.
- Added `--flat-lr` as a reproducible downside sensitivity.

**Moves published numbers: yes**, for the CGB dial. Conclusion unchanged: costs at baseline,
free under repression, 2–3% defensible.

## 2026-08-20 — FX stepping repair

`LifecycleSimulator` shared one `FXModel` between the two sub-portfolios while
`SubPortfolio.step` advanced it, so it ran **twice per simulated year**.

- The RSP and LHP drew **independent** currency shocks for the same year — USD differing by
  up to 12.8pp — destroying the common shock the unhedged-overlay thesis depends on.
- **A second consequence not in the original report:** `FXModel.step` also rolls the PPP gaps,
  so they decayed at double speed. The year-5 gap equalled the correct year-10 value, costing
  ~30bp/yr of CNY tailwind over the first 20 years. This turned out to be the economically
  larger of the two.
- Fixed by advancing once per year at the lifecycle level and passing the same dict to both.

**Moves published numbers: yes.** The equity re-anchor step gained +4.6k baseline / +3.0k
repression; the bond-side step did not move significantly — the opposite of what was
expected, because the PPP tailwind lives in the first ~20 years when the glide path holds no
LHP at all.

## 2026-08-20 — CGB dial pricing

Added `examples/run_cgb_dial.py` to price the China government bond line, which sat in the
overlay at a 0% default so the attribution never reported what holding it would contribute.

**Moves published numbers: no** — new analysis, no model change.

---

## 2026-06-15 — `0adf3bb`, the last commit before this sequence

The state of the public repository until 2026-08-22. **Results produced from this commit are
wrong** — see `PUSH_NOTES.md` for what specifically.
