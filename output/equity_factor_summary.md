# Global equity market factor — closing V-C3, plus two seam repairs

Worked 2026-08-22. N = 1000 throughout; `± x` is the standard deviation across 5 seeds
(3 for the CGB dial). **Test suite: 43/43** (was 37; six added).

---

## Item 1 — the equity market factor

### Design decision: a ninth *innovation*, not a ninth state variable

The factor `F` is drawn jointly with the eight macro innovations and then sliced off. It is
attached to `MacroState.equity_factor` but is deliberately **not** in `_FIELDS`, so it never
enters Φ, never gets floored, and never appears in `to_array()`.

**Why not the VAR.** Three reasons, in decreasing order of weight:

1. **Category error.** Every element of the state vector is a *level* — a rate, a growth
   rate, a spread. `F` is a *period return*. Putting it in the vector means `YieldCurve`,
   the floors dict, `from_array`/`to_array` and every consumer would carry a variable none
   of them should read.
2. **Persistence.** The VAR imposes AR(1) dynamics; equity returns are close to white noise.
   It is expressible with φ_FF = 0, but then one row of Φ means something different from all
   the others.
3. **Blast radius.** It would take the state to nine variables, forcing a third extension of
   Φ and Σ and a matching extension of `regimes.py` — which Item 2 shows was already broken
   by the *second* extension.

Drawing `F` as a ninth innovation delivers the one property actually required — exact
contemporaneous correlation with the macro shocks — with none of that. Φ and Σ are
untouched, so macro stationarity and PSD are unaffected by construction. The 9×9 augmented
covariance is PSD (min eigenvalue 1.37e−05) and Choleskys cleanly.

Factor calibration: **15.5% p.a., mean zero**, correlated +0.25 with the growth innovation,
**−0.35 with the credit-spread innovation**, +0.30 with global growth, −0.10 with inflation.
Verified in simulation: mean −0.0006, sd 0.1548, lag-1 autocorrelation +0.006.

### Simulated correlation matrix

Mean pairwise correlation over the seven markets with real return data: **0.518**, against
the 0.52 the calibration implies and **0.57 observed**. Before this change it was **+0.01**.

|  | USA | Europe | Japan | China | India | Korea | Taiwan | Indon | Viet | Singa |
|---|---|---|---|---|---|---|---|---|---|---|
| **USA** | 1.00 | 0.85 | 0.66 | 0.55 | 0.61 | 0.66 | 0.64 | 0.55 | 0.42 | 0.75 |
| **Europe** | 0.85 | 1.00 | 0.59 | 0.50 | 0.55 | 0.60 | 0.57 | 0.50 | 0.38 | 0.68 |
| **Japan** | 0.66 | 0.59 | 1.00 | 0.38 | 0.42 | 0.46 | 0.45 | 0.38 | 0.29 | 0.52 |
| **China** | 0.55 | 0.50 | 0.38 | 1.00 | 0.35 | 0.38 | 0.37 | 0.32 | 0.24 | 0.43 |
| **India** | 0.61 | 0.55 | 0.42 | 0.35 | 1.00 | 0.43 | 0.41 | 0.36 | 0.27 | 0.48 |
| **Korea** | 0.66 | 0.60 | 0.46 | 0.38 | 0.43 | 1.00 | 0.44 | 0.39 | 0.30 | 0.53 |
| **Taiwan** | 0.64 | 0.57 | 0.45 | 0.37 | 0.41 | 0.44 | 1.00 | 0.37 | 0.28 | 0.50 |
| **Indonesia** | 0.55 | 0.50 | 0.38 | 0.32 | 0.36 | 0.39 | 0.37 | 1.00 | 0.25 | 0.45 |
| **Vietnam** | 0.42 | 0.38 | 0.29 | 0.24 | 0.27 | 0.30 | 0.28 | 0.25 | 1.00 | 0.33 |
| **Singapore** | 0.75 | 0.68 | 0.52 | 0.43 | 0.48 | 0.53 | 0.50 | 0.45 | 0.33 | 1.00 |

Total volatilities reproduce their observed targets within **+0.13 to +0.55pp**, the small
positive bias being exactly the neglected ~2% macro contribution.

**Known limitation, recorded not fixed.** A single global factor leaves residual regional
structure: Korea–Taiwan comes out at 0.44 and China–Taiwan at 0.37, against observed values
roughly 0.16–0.26 higher. That is the semiconductor supply chain and North Asian trade
linkage showing up. A second Asian regional factor would tighten it and would also be the
natural place to represent the supply-chain concentration the article's geopolitics section
discusses. **Design option; not implemented.**

### Where I disagree with the brief

- **`equity_factor_calibration.py` was cited as supplied but is not in the repository**, so I
  could not re-run the regression. I verified the table's *internal* consistency instead:
  every row reproduces its stated total volatility and R² from `mbeta`, `idio` and the 15.5%
  factor vol, to within 0.001. That establishes the table is self-consistent, not that the
  underlying regression is right — the same limitation `VALIDATION_REPORT.md` records for the
  FX consistency test (V-D3).
- **The "under 0.2pp" claim about the neglected macro term is right about total volatility
  and wrong about `idio_vol`.** For the USA, removing 2% in quadrature from an idio of 0.034
  moves it to 0.027 — 0.65pp, not 0.2pp. On *total* volatility the effect is +0.13pp, within
  the stated bound. I neglected the term as instructed and recorded the distinction inline.
- **`allocations/preview.py` needed changing too**, which the brief did not mention. It
  carried its own vol model assuming a 14% common factor at 0.75 correlation — the very
  assumption V-C3 said the simulation contradicted. Left alone it would have disagreed with
  the model *more* after this fix, not less. It now uses the same single-factor formula.

---

## Item 2 — `scenarios/regimes.py`

**Recommendation and implementation: option 2, marked unsupported.** `RegimeSwitchingEngine`
now raises `NotImplementedError` at construction with a message naming the cause, the reason
it was not extended, and what re-enabling requires.

Reasoning: extending four regime calibrations to eight variables means inventing four sets of
`global_growth` mean, persistence, volatility and correlation parameters with no source — in a
codebase where "provenance absent for everything not taken from the article" is already a
Major finding (V-M6). Adding four more unsourced blocks to a module no published exhibit uses
would trade a loud failure for a quiet fabrication. Item 1 did *not* put the factor in the
VAR, so the module would need eight variables rather than nine, but that does not change the
argument.

Guarded by `test_every_engine_in_the_codebase_can_take_a_step`, which walks every engine and
requires each either to step successfully or to refuse legibly. Verified: with the guard
removed the test fails with the original raw `ValueError: matmul ... size 8 is different
from 7`.

---

## Item 3 — `Portfolio` built its LHP without an FX model

**Both routes taken, as suggested.**

1. `Portfolio.__init__` now passes the same `FXModel` to the LHP that it passes to the RSP.
2. `SubPortfolio.step` now **raises** if a sleeve declares `fx_exposures` and there is neither
   an attached FX model nor a passed-in `fx_returns` dict.

The second is the general protection and is what would catch the next instance. Both are
guarded, and both guards were verified to fail against reconstructions of the old behaviour.

---

## What moved

### Attribution — marginal Δ, €000, 5 seeds

| Step | World | Validated (pre-factor) | With factor | Change | t |
|---|---|---:|---:|---:|---:|
| (i) Current *(level)* | Baseline | 1331.9 ± 10.7 | 1294.6 ± 11.4 | −37.3 | *level* |
| (i) Current *(level)* | Repression | 1037.4 ± 6.0 | 1013.5 ± 14.2 | −23.9 | *level* |
| (ii) +Re-anchor | Baseline | +115.7 ± 8.1 | **+105.2 ± 5.1** | **−10.5** | 2.5 |
| (ii) +Re-anchor | Repression | +88.0 ± 3.0 | **+83.6 ± 6.0** | −4.4 | 1.5 |
| (iii) +China cap | Baseline | −2.9 ± 5.4 | +2.2 ± 4.1 | +5.1 | 1.7 |
| (iii) +China cap | Repression | −3.0 ± 2.4 | **+2.7 ± 1.0** | **+5.7** | 4.9 |
| (iv) +Bond side | Baseline | +27.5 ± 3.5 | +25.7 ± 2.4 | −1.8 | 0.9 |
| (iv) +Bond side | Repression | +44.3 ± 2.7 | **+40.4 ± 2.1** | −3.9 | 2.6 |

Levels moved because adding a ninth draw changes the random sequence; they are not
interpretable and are shown only for completeness.

**How much of the re-anchor step survives.** Against the **validated** figure, **91% baseline
and 95% repression** — so most of the remaining benefit was *not* volatility drag from
artificial diversification, contrary to the brief's expectation. Against the **originally
published** figure the cumulative survival is **61% baseline (+172.5k → +105.2k) and 62%
repression (+135.2k → +83.6k)**.

**One sign flip worth noting.** The China-cap step moved from −3.0 to **+2.7** under
repression (t = 4.9). Capping China at 6% now *slightly helps* rather than slightly hurting.
Under zero cross-country correlation, spreading weight across more markets was mechanically
rewarded; with realistic correlation that reward disappears and the cap's risk benefit shows
through. The step remains small in both worlds.

### CGB dial — Δ(5% vs 0%), 3 seeds

| Calibration | World | Validated | With factor |
|---|---|---:|---:|
| 1.8→2.3% | Baseline | −5.85 ± 2.75 | −6.28 ± 3.45 |
| 1.8→2.3% | Repression | +1.33 ± 1.24 | +2.87 ± 2.54 |
| 1.8% flat | Baseline | −6.05 ± 0.68* | −8.14 ± 3.45 |
| 1.8% flat | Repression | −1.24 ± 0.60* | +1.50 ± 2.66 |

Nothing here moves significantly (the repression change is t ≈ 0.9). **The CGB conclusion is
unchanged: costs at baseline, free-to-positive under repression, 2–3% defensible.** The
left-tail claim strengthens slightly — repression p5 now rises 756 → 762k across the sweep.

---

## Can Exhibit 6 be regenerated for publication?

**Panel (a), the marginal contributions — yes.** All four steps are now built on realistic
cross-country equity correlation, on equity volatilities that match their observed totals, on
independent random streams, and on markets that return their documented drift. Every step is
guarded by a test that fails if its defect returns. The residual known issues (V-M3 bond
volatility, V-D1 the factor-object mismatch) do not threaten the sign or the rough magnitude
of any step. I would publish panel (a).

**Panel (b), the pot distribution — substantially repaired, but not yet a calibrated risk
statement.** It was the panel most damaged by V-C3 and it is the one that improved most: the
equity block now carries realistic correlation and volatility, and equity is the dominant
contributor to dispersion at retirement, since the cohort glide path averages only **15.1%
LHP over accumulation**. Baseline p95/p5 widened from 2.05 to 2.27 as the artificial
diversification came out.

What still stands between it and publication is **V-M3**: simulated long-bond volatility is
22.7% against a plausible 10–15%, so the remaining ~15% of the portfolio carries volatility
overstated by roughly 1.5–2×. That inflates the tails of panel (b) by a smaller amount than
V-C3 did, but in the same direction and by an amount nobody has quantified. **My
recommendation: publish panel (b) only after V-M3 is resolved, or publish it with the bond
volatility caveat stated explicitly in the exhibit note.** It is no longer *wrong* in the way
it was — it is a dispersion claim resting on one input that is known to be mis-calibrated.
