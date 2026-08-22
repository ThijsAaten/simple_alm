# V-M3 — bond volatility recalibration: summary

Branch `vm3-bond-volatility`, 2026-08-22. Diffs against `6f50ed4` (`main` before this work;
`main` has since acquired two housekeeping commits touching only `simple_alm_changes.zip`).

---

## 1. Diagnosis — what actually dominated

Variance decomposition of the LongGovt (D = 20, τ = 25) annual return on baseline paths,
N = 2000 × 30 years after a 10-year burn-in, **before** any change:

| term | sd | share of variance |
|---|---:|---:|
| carry (y·dt) | 2.0% | 3% |
| level (−D·Δ`long_rate`) | 24.7% | **106%** |
| slope + curvature (−D·(Δy₂₅ − Δ`long_rate`)) | 5.4% | −11% |
| convexity (½·D²·Δy²) | 3.3% | 2% |
| **total** | **22.6%** | 100% |

The level shock is the whole story. The 25y Nelson-Siegel yield moved 108bp/yr; 20 × 1.08%
≈ 22%. **The duration mapping is not the error** — the sanity check in the prompt holds.

**Persistence is not the error either.** For an AR(1), var(Δx) = 2σ²/(1+φ). With φ = 0.80
the annual-change sd of `long_rate` (125bp) is almost the innovation sd (120bp); the
unconditional *level* sd is 224bp. Bond returns load on the change, not the level, so
lowering φ would have narrowed the distribution of rate levels over 65 years while leaving
V-M3 untouched. The report's attribution to the innovation volatility is confirmed, and the
mean-reversion question it raised is answered: Φ stays.

**Two consequences of over-volatile yields that were hiding in the outputs.** LongGovt's mean
return was 6.8% on a 4.5% yield; the extra 2.3% was the convexity term ½·D²·E[Δy²] — the LHP
was being paid for a defect. And the V-M4 floor on `credit_spread` bound on 10.1% of steps
partly because the spread innovation was also too wide.

## 2. What changed, to what, on what basis

`scenarios/engine.py::_default_sigma`, three entries of the vol vector. Φ, the innovation
correlation matrix, X̄, the floors and the equity-factor correlations are all untouched; the
augmented 9×9 is rebuilt from the same vector so the equity-factor correlations survive.

| innovation | before | after | basis |
|---|---:|---:|---|
| `long_rate` | 120bp | **70bp** | realised annual changes in 10y Bund yields 1999–2025: sd ≈ 85bp including 2022, ≈ 70bp without; 30y moves less; the level factor is the ∞-maturity limit. Implied annual-change sd 73bp; 25y NS yield 69bp — mid-band of the 60–90bp target |
| `real_rate` | 100bp | **65bp** | long euro real yields (OATei / Bund-ei) show similar annual-change dispersion on a shorter record |
| `credit_spread` | 60bp | **45bp** | euro IG OAS annual changes ≈ 50bp; 45bp at φ = 0.65 reproduces this |

Alternatives run: (75/70/60) gave LongGovt 15.1%, IG_Credit 8.5%; (75/70/45) gave 15.1% and
7.8%. The chosen (70/65/45) lands LongGovt at 14.3%, lower half of the 12–18% range the
prompt asked for and inside the report's 10–15% band.

**Status: judgement, anchored.** Euro long-yield history is not in the repository. Recorded
in `docs/INPUT_PROVENANCE.md` with a pending check. **Bloomberg task, five minutes:** annual
changes of `GDBR10 Index` and `GDBR30 Index`, 1999–2025, sd with and without 2022; and
`GTDEMII10Y` or the OATei 2032 for the real leg. If the 30y figure is outside 60–80bp, revisit.

## 3. Before / after, every sleeve

| sleeve | before | after | band | max single year before → after |
|---|---:|---:|---|---:|
| LongGovt (D=20) | 22.7% | **14.3%** | 10–15% ✓ | 127% → 89% |
| ILG (D=18) | 18.9% | **13.3%** | 10–14% ✓ | 91% → 78% |
| IG_Credit (D=7) | 9.8% | **7.7%** | 5–7% — marginally above | 44% → 39% |
| Equity Europe | 17.3% | 17.3% | 15–18% ✓ | unchanged |
| LHP blend (50/40/10) | ~16% | **11.2%** | | 62% → 62% (see V-D7) |

LongGovt mean return 6.8% → 5.4%. V-M4 floor binding 10.1% → 7.1%. Equity block verified
unchanged (`test_simulated_equity_total_volatility_matches_target` passes with identical
values; the factor correlations are rebuilt from the same vector).

IG_Credit at 7.7% is the spread/jump block, not rates (7 × 0.69% ≈ 4.8% from rates). Its
remaining excess is the +0.30 rate–spread innovation correlation, which has the wrong sign
for flight-to-quality episodes. Not changed here — a correlation change is a different
decision — recorded under V-D7.

## 4. Re-run attribution and CGB dial

`tools/rerun_multiseed.py` (new; the harness that produced the frozen validation CSVs was
never committed). Same seeds and N as the validation record. Outputs
`output/vm3_attribution.csv`, `output/vm3_cgb_dial.csv`, `output/vm3_pot_distributions.csv`.

### Nested attribution, 5 seeds, N = 1000, EUR000 real at retirement

| step | baseline level | baseline Δ | repression level | repression Δ |
|---|---:|---:|---:|---:|
| (i) Current | 1,332 → **1,252** | | 1,037 → **982** | |
| (ii) +Re-anchor | | +115.7 ± 8.1 → **+101.6 ± 3.5** | | +88.0 ± 3.0 → **+82.5 ± 2.4** |
| (iii) +China cap | | −2.9 ± 5.4 → **+4.0 ± 3.9** (t 2.3) | | −3.0 ± 2.4 → **+4.1 ± 1.5** (t 6.2) |
| (iv) +Bond side | | +27.5 ± 3.5 → **+30.5 ± 2.7** | | +44.3 ± 2.7 → **+45.2 ± 4.5** |

"Before" is the validated CSV at `0adf3bb` (21 Aug), which predates the V-C3 equity factor.
Against the handover's post-V-C3 article figures (+105k / +84k) the re-anchor step is
**unchanged within noise**. Three readings:

- **Levels fall ~6%** (baseline) and ~5% (repression). This is the convexity windfall
  leaving the LHP. Every pot *level* in the paper needs restating, including the
  denominator of the "roughly eight per cent more pension" line.
- **The re-anchor and bond-side deltas do not move.** The overlay's +30k / +45k was not a
  product of an over-volatile LHP — worth a sentence in §13 or §17.8 as a robustness point.
- **The China cap is now positive in both worlds**, +4k with t = 2.3 baseline and t = 6.2
  under repression. §17.8 currently says it flipped sign under repression only; it should
  now say the cap is weakly positive in both, and that the sign depends on realistic
  cross-market correlation (it was negative under the zero-correlation defect).

### CGB dial, 3 seeds, N = 1000

| world | w | Δ median old → new | LHP vol old → new | p5 old → new |
|---|---:|---:|---:|---:|
| baseline | 5% | −5.8 → **−4.1k** | 13.5% → 9.2% | 1,032 → 952 |
| repression | 5% | +1.3 → **+1.7k** | 14.8% → 11.9% | 842 → 772 |

Volatility reduction from a 5% CGB line is 52bp baseline / 69bp repression (was 77 / 84), but
**5.7% of LHP vol in both worlds before and after** — the proportional claim in §17.7 is
untouched; the basis-point figures are not. Left-tail improvement (p5) at 5% weight: +3k
baseline, +5k repression, as before. The conclusion — small median cost at baseline, small
gain under repression, payoff in volatility and the left tail, roughly 3× more efficient
under repression, defensible at 2–3% — survives. Quote the new figures.

## 5. Exhibit 6 panel (b) — is the pot distribution publishable?

**As far as V-M3 is concerned, yes.** Sleeve volatilities are in band and guarded, the
equity block is unchanged, and the distribution now rests on realistic rate dynamics.

**But V-M7 has changed status, and it sits in the repression leg of every published number.**
Re-measured after V-M3: baseline LHP single-year sd is 11.2%; the `repress()` boundary
produces a mean **+64%** LHP year at the window open (p5 +20%, p95 +118%) and **−30%** at the
close. Before V-M3 this hid inside a noisy baseline; it no longer does. And it is not
symmetric: 1.64 × 0.70 = 1.15, so the step is a net windfall to the LHP.

Sensitivity, one seed, N = 300, 3-year linear ramp into and out of the window versus the
current step:

| | Current | Proposed / EUR LHP | + overlay | bond-side Δ | equity Δ |
|---|---:|---:|---:|---:|---:|
| step (current) | 955k | 1,044k | 1,094k | +49.6k | +89.2k |
| 3-year ramp | **875k** | **958k** | **1,011k** | +53.2k | +83.2k |

**Repression levels are inflated by ~8% by the boundary artefact. Deltas are within seed
noise.** So: panel (a) is publishable; panel (b) in the baseline world is publishable; panel
(b) in the repression world shows levels that depend on a boundary treatment that should be
changed first. The decision is a scenario-definition one — "12 years pinned" becomes "12
years pinned, 3-year transitions" — and belongs with D-level decisions, so it is recommended
here and not implemented. Implementation is ~15 lines in `examples/run_attribution.py`
(`repress(..., ramp=3)`) plus a test on repressed paths; then re-run the harness.

## 6. Register and coverage

`docs/VALIDATION_REPORT.md`: V-M3 marked resolved with the diagnosis above; V-M4 updated to
7.1%; V-M7 re-measured and upgraded from symptom to open design item; V-D7 added (fixed
modified duration and D² convexity overstate moves from high-yield states — the +74%
baseline LongGovt year is a 260bp fall from 8.6%, where a real 25y bond has D ≈ 11; and the
rate–spread correlation sign). `docs/TEST_COVERAGE.md`: 46 tests; V-M3 guarded by two tests;
V-M7 partly guarded (baseline paths only, by design until the ramp decision).

Tests added: `test_var_long_rate_annual_change_volatility_is_in_band` (analytic, on Φ,Σ —
fails on Σ, not on Φ, by construction), `test_bond_sleeve_volatilities_are_in_plausible_band`
(LongGovt 10–17%, ILG 9–16%, IG_Credit 5–8.5%), `test_bond_sleeve_single_year_returns_are_bounded`
((−55%, +110%); LongGovt years beyond ±25% under 13%, currently 10.4%, was 28%). Φ stationarity
and Σ PSD tests unchanged and passing. Suite 46/46.

## 7. What remains open, and whether it affects a published number

The handover's understanding was that after V-M3 nothing open affects a published number.
**That is not quite right, and the correction matters:**

- **V-M7 — yes, it does.** Repression-leg *levels* by ~8%; deltas no. Decision needed (ramp
  length), then a ~15-line change and a re-run. Recommend 3 years.
- **V-M4** — marginal, improved to 7.1%, hygiene.
- **V-M2** — hygiene, unchanged.
- **V-D7** (new) — tails only; affects p5/p95 of panel (b) slightly, not medians. Recommend
  leaving for a later round and disclosing "fixed duration" in the model description.
- **The calibration itself** — pending the five-minute Bloomberg check above. If the 30y
  annual-change sd comes back inside 60–80bp, nothing changes.
