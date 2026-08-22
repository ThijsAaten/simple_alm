# Global growth factor: separating the euro cycle from the world cycle

Worked 2026-08. N = 1000 paths throughout. `± x` is the standard deviation across
5 independent seeds (3 for the CGB dial), so mechanical movement can be told from
economic. Test suite: **22/22 pass** (was 17; six added, one rewritten).

---

## The defect, restated

`growth_loading` was defined as "return per 1 pp of EUR growth above long-run trend",
with the module docstring stating the convention: *EUR growth above trend → EUR
strengthens → foreign loses*. Under that definition every value must be negative.
USD's −0.30 was correct. But five currencies carried positive values justified by
comments describing a factor the model did not have:

```
CNY  +0.30   "strong global growth → risk-on → CNY gains"
TWD  +0.40   "semiconductor cycle dominates; global growth positive"
KRW  +0.30   "export economy; global growth positive"
CAD  +0.10   "oil-exporter benefits from global growth"
AUD  +0.20   "iron ore & resource exposure"
```

The values were wrong against the field's own definition; the economics the comments
described was real. Flipping the signs would have fixed the definition and destroyed
the economics. The model needed somewhere to put global-cycle exposure.

---

## Step 1 — `global_growth` as the eighth state variable

Appended at index `[7]`, so no existing positional index moves. Calibration as
suggested, and I agree with all four choices — with one caveat noted below:

| Parameter | Value | Rationale |
|---|---|---|
| Long-run mean | 0.030 | vs euro 0.025; the world includes EM |
| Persistence φ | 0.55 | vs euro growth 0.50 |
| Volatility σ | 0.020 | vs euro growth 0.025; diversification across regions |
| Spillover → euro growth | 0.20 | global feeds euro; **reverse spillover is zero** |
| Innovation corr with euro growth | 0.75 | signs inherited from euro growth at ~0.75× magnitude, notably −0.30 vs credit spread (euro: −0.40) |

**Verified**: Φ stationary at max \|eigenvalue\| **0.855**; Σ PSD with min eigenvalue
**1.4e−05**; Cholesky succeeds. Both asserted in `test_var_transition_matrix_is_stationary`
and `test_var_covariance_is_psd_and_cholesky_succeeds`.

**Adding it is not free, and this is an economic change, not a stream change.** The
0.20 spillover feeds global-cycle variance into euro growth:

| Variable | 7-var sd | 8-var sd | Change |
|---|---:|---:|---:|
| growth (euro) | 0.0289 | 0.0321 | **+10.9 %** |
| credit_spread | 0.0084 | 0.0090 | **+7.1 %** |
| all five others | — | — | unchanged to 4 dp |

Credit spread moves because it already loaded on euro growth at 0.10. Anything
calibrated against the old euro-growth dispersion is now looking at a slightly wider
distribution.

**Where I'd push back mildly:** 0.20 for the spillover is on the low side. The euro
area is small and open; 0.30–0.40 is defensible. I used 0.20 because it understates
rather than overstates the new channel, but it is a choice, not a measurement.

Stress scenarios now propagate the shock to `global_growth` at 0.75× the euro
magnitude (a euro growth shock of stress size is not a euro-only event); the parallel
rate shock leaves it untouched, being a curve event rather than a cycle event.

---

## Step 2/3 — the FX model and the joint table

`global_growth_loading` added to `CurrencyParams`; a third macro term added to the
return decomposition. All three conventions are now stated explicitly in the module
docstring, and each is enforced by a test rather than a comment.

**I verified the supplied table's arithmetic against its own stated method before
applying it.** All 12 rows reproduce from `b_usd` and `resid_g` under
`0.50 × b_usd`, `−0.30 × b_usd`, `0.60 × resid_g` rounded to 0.05 — including the
non-obvious cases (JPY's −0.15 comes from −0.30 × 0.447 = −0.134, which rounds to
−0.15 rather than the −0.12 you would get from scaling the inflation column).

The joint estimates supersede the previous univariate ones and move several
materially: **KRW 0.15 → 0.40, IDR 0.30 → 0.50, TWD 0.35 → 0.45, JPY 0.35 → 0.20.**
The univariate regression absorbed shared growth exposure into the dollar
coefficient; that the two columns could contradict each other at all follows directly
from their having been estimated separately.

**The 0.60 conversion is the weakest link and is labelled as such in the file.**
`b_g` is an equity-return beta; the model needs a growth-deviation loading, and 0.60
is `EquitySleeve`'s own `growth_beta` borrowed as the conversion factor. If the true
equity-to-growth sensitivity is 0.4 or 0.9, every `global_growth_loading` scales with
it. The **ranking** is robust (it comes straight from `b_g`); the **level** is not.

---

## Step 4 — the consistency test

`test_model_implied_correlations_match_the_measured_betas` builds the implied
cross-currency correlation matrix twice — once from the rounded loadings actually
stored, once from the unrounded regression coefficients — using the same variance
decomposition (common macro part from the VAR's own unconditional covariance of
inflation/euro growth/global growth, plus each currency's `idio_vol`).

**Tolerance 0.02, set by measurement rather than taste:**

| Configuration | Max elementwise difference |
|---|---:|
| Correct table | **0.0061** |
| Historical bug restored (CNY growth_loading +0.30) | **0.1015** |

A 17× separation. Verified by injecting the old CNY value and confirming the test
fails on the pair `(CNY, HKD)` — the two currencies whose measured relationship the
old value most flatly contradicted.

**A limitation I could not engineer away:** the raw FX return series is not in this
repo, so a true *observed* correlation matrix cannot be recomputed here. The
reference is reconstructed from the published regression coefficients. That catches a
loading contradicting its own measured beta — the failure mode in question — but
would not detect an error in the regression itself. My first attempt at this test
used `b_usd_c × b_usd_d` as the reference and failed at rho = 0.615; the reference
was wrong, not the loadings, because it ignored idiosyncratic variance that differs
4× across currencies (HKD 3 %, THB 12 %).

---

## Step 5 — the equity question: recommendation

**The defect is real.** `country_inputs.py` puts India at 0.75, China 0.70, Korea
0.70 against Europe 0.60 and Japan 0.55, all applied to `state.growth`, which is euro
growth. Indian equities cannot respond more strongly to euro-area growth than
European equities do. That ordering is only coherent against a global cycle.

Implemented as `build_equity_specs(..., growth_mode=)` with three options, **default
unchanged at `"euro"`**, so nothing published moves unless a caller opts in.

Comparison at N = 1000 — marginal Δ, €000:

| Step | World | euro (current) | split | global |
|---|---|---:|---:|---:|
| (ii) +Re-anchor | Baseline | +171 | +170 | +168 |
| (iii) +China cap | Baseline | −5 | −3 | −4 |
| (iv) +Bond side | Baseline | +22 | +24 | +25 |
| (ii) +Re-anchor | Repression | +133 | +134 | +135 |
| (iii) +China cap | Repression | −2 | −2 | −3 |
| (iv) +Bond side | Repression | +41 | +38 | +38 |
| CGB Δ(5 %) | Baseline | −5.1 | −3.9 | −7.9 |
| CGB Δ(5 %) | Repression | +0.6 | +1.8 | +2.3 |

**Every attribution waypoint is within seed noise across all three modes** (spread
≤3k against seed sds of 1.4–2.7k). The CGB dial moves more but stays the same sign
and the same conclusion.

**Why so small — and this matters for how much weight to put on the choice.** Euro
growth and global growth realise a correlation of **0.78** in simulation (0.75
innovation correlation plus the 0.20 spillover). In this model the two cycles are
near-substitutes, so reassigning a beta between them barely changes anything. The
case for changing is **coherence, not magnitude**.

> **Recommendation: adopt `"split"`.** It is the only option defensible for Europe
> and EM simultaneously — `"global"` leaves European equities with no euro-cycle
> sensitivity at all, which is its own error. It costs nothing measurable, so it can
> be adopted **without regenerating any published number**, and that is precisely why
> it should be done now rather than deferred until it is entangled with a change that
> does move numbers.
>
> **Condition on that recommendation:** `EURO_CYCLE_SHARE` is illustrative. I reasoned
> it (Europe 0.70, USA 0.20, Japan 0.15, EM 0.05); nobody regressed it. Adopting
> `"split"` replaces an implicit wrong assignment with an explicit unvalidated one —
> better, because the ordering becomes defensible and the assumption becomes visible,
> but it should be estimated before it carries weight in the article.

---

## Attribution — before vs after

Marginal Δ, €000, **5 seeds**. "Before" is the end of the previous round (7-variable
engine, univariate loadings); "after" is this round.

| Step | World | Before | After | Change | Verdict |
|---|---|---:|---:|---:|---|
| (ii) +Re-anchor | Baseline | +172.4 ± 4.4 | +172.5 ± 1.9 | +0.1 | unchanged |
| (ii) +Re-anchor | Repression | +133.7 ± 1.4 | +135.2 ± 1.5 | +1.5 | t ≈ 1.6, **not significant** |
| (iii) +China cap | Baseline | −2.6 ± 0.4 | −2.6 ± 1.6 | 0.0 | unchanged |
| (iii) +China cap | Repression | −2.5 ± 1.2 | −2.6 ± 0.5 | −0.1 | unchanged |
| (iv) +Bond side | Baseline | +25.7 ± 1.7 | +23.2 ± 2.7 | −2.5 | t ≈ 1.8, **not significant** |
| (iv) +Bond side | Repression | +40.6 ± 4.1 | +43.2 ± 1.4 | +2.6 | t ≈ 1.3, **not significant** |

Levels, seed 42 (baseline / repression, €000): (i) 1178/924 → 1178/918;
(ii) 1348/1058 → 1349/1051; (iii) 1345/1055 → 1344/1049; (iv) 1373/1097 → 1367/1090.
All inside one seed sd (9–11k). **Not interpretable** — adding a state variable
changes the draw sequence.

**No attribution waypoint moved significantly.** That is the headline, and it is not
the result I expected: a new state variable plus twelve currencies re-estimated, with
every growth loading changing sign and four inflation loadings moving by 0.10–0.25,
leaves the marginal contributions statistically where they were. The reason is
offsetting: the inflation-loading revisions went both ways across the mosaic (KRW,
IDR, TWD up; JPY down), the euro-growth term is mean-zero so flipping its sign adds
variance rather than level, and the global loadings are small (0 to 0.15).

### Does Exhibit 6 need regenerating?

**The marginal contributions do not.** Every Δ is statistically unchanged, so the
conditional-value argument the exhibit makes stands exactly as published.

**The levels should be refreshed if the exhibit shows them.** They shifted by up to
7k — within noise, so nothing economic is being reported, but a published level
should match what the code now produces. If Exhibit 6 shows only the Δ column, leave
it alone.

---

## CGB dial — before vs after

Δ(5 % vs 0 %) on median real pot, 3 seeds:

| Calibration | World | Before | After |
|---|---|---:|---:|
| 1.8 % → 2.3 % | Baseline | −6.00 ± 1.53 | **−4.39 ± 0.58** |
| 1.8 % → 2.3 % | Repression | +0.51 ± 0.85 | **+0.04 ± 0.50** |
| 1.8 % flat | Baseline | −7.75 ± 1.56 | −6.05 ± 0.68 |
| 1.8 % flat | Repression | −0.72 ± 1.06 | −1.24 ± 0.60 |

Full sweep at seed 42 (calibrated): baseline −1.4 / −2.3 / −3.1 / −5.1k at
1/2/3/5 %; repression +0.3 / +0.3 / +0.1 / +0.6k. p5 rises monotonically in both
worlds and by more than before — **+6k baseline, +10k repression** at 5 %.

The baseline cost shrinks (−6.00 → −4.39, t ≈ 1.7 — suggestive, not established) and
the repression outcome remains indistinguishable from zero. **The conclusion is
unchanged: CGB costs at baseline, is free under repression, and 2–3 % remains the
defensible range** — now at a baseline cost of only 2.3–3.1k.

---

## What I disagree with, and what is still open

1. **"CurrencySpec"** — the class is `CurrencyParams`. Cosmetic, noted only so the
   diff is easy to follow.
2. **The 0.20 spillover is conservative.** 0.30–0.40 is defensible for an economy as
   open as the euro area. I used the suggested value; it understates the channel.
3. **The 0.60 conversion factor is circular in a way worth naming.** It borrows
   `EquitySleeve.growth_beta` — a parameter on the equity side — to calibrate the FX
   side. If Step 5's recommendation is adopted and equity betas are re-estimated
   against the global cycle, that conversion factor should be revisited with them,
   not left pinned at 0.60.
4. **CHF, CAD, AUD remain un-derived**, marked `TODO(un-derived)` in `assets/fx.py`:
   - **CHF** — priority. `inflation_loading` −0.30 is the last remaining negative and
     contradicts its own comment (which describes CHF *gaining* as the EUR weakens).
     Its `growth_loading` of −0.50 is, by contrast, correct under the convention. CHF
     sits at 2 % in `build_rsp_specs`' GlobalEquity sleeve, so it reaches the headline
     participant charts but **not** the attribution or CGB runs.
   - **CAD +0.10, AUD +0.20** growth loadings are global-cycle exposure sitting in
     the euro-growth column — the exact defect this change fixes everywhere else.
     AUD matters more than it looks: it still proxies NZD in the bond overlay, so its
     loadings reach the LHP.
5. **The post-2017 sensitivity is now stale.** `POST_2017_INFLATION_LOADINGS` was
   derived under the univariate method and has not been re-estimated jointly. It is
   retained and flagged, but is no longer strictly comparable to the headline table,
   and it does not vary the global column at all.
6. **The two growth cycles are 0.78-correlated in this model**, which limits how much
   any decision resting on distinguishing them can be worth. That is a property of my
   own calibration choices (0.75 innovation correlation, 0.20 spillover), not a fact
   about the world — a lower innovation correlation would make the two factors more
   distinguishable and the Step 5 choice more consequential.
