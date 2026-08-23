# Input provenance

This file maps every numerical input the participant model consumes back to the
article it accompanies, so a reader can audit where each figure comes from. It is
the reference companion to the code in `allocations/country_inputs.py`.

> Convention: `drift` is the **local-currency nominal** expected return — exactly
> the §3.1 Table 1a `r_nom` column and the §13.6 frontier input. FX appreciation
> is handled **separately** by the `FXModel` overlay (the `fx` key), never folded
> into `drift`, mirroring how §3.1 keeps the "+FX" column distinct from the
> frontier input.

---

## Status summary — what the model rests on

Closes validation finding **V-M6**, which recorded that provenance was complete for
article-sourced inputs and absent for everything else. Every calibrated numerical input the
participant model consumes is now classified as one of:

- **Article** — traceable to a stated section of the paper.
- **Derived** — produced by a regression or calculation, with the script named.
- **Judgement** — nobody measured it. This is a legitimate and common status; recording it
  honestly is the entire point. A provenance document that launders assumptions into
  citations is worse than none.

| Block | Article | Derived | Judgement | Total |
|---|---:|---:|---:|---:|
| VAR calibration (X̄, floors, Φ, Σ vols, Σ correlations) | 0 | 0 | 71 | 71 |
| Global equity market factor (volatility + 6 correlations) | 0 | 1 | 6 | 7 |
| FX macro loadings (3 columns × 15 currencies) | 0 | 36 | 9 | 45 |
| FX other parameters (carry, drift, PPP, idio × 15) | 0 | 1 | 74 | 75 |
| Country equity: drift, CAPE now, CAPE fair (3 × 10) | 24 | 0 | 6 | 30 |
| Country equity: gbeta, ibeta, mbeta, idio (4 × 10) | 0 | 14 | 26 | 40 |
| Sovereign bond overlay (6 × 6) | 7 | 0 | 29 | 36 |
| Participant configuration + cohort glide path | 0 | 0 | 29 | 29 |
| Sub-portfolio structure (LHP/RSP weights, durations, betas) | 0 | 0 | 23 | 23 |
| **Total** | **31** | **52** | **273** | **356** |
| **Share** | **9%** | **15%** | **77%** | |

**Read that table before reading any exhibit.** Roughly three quarters of the model's
calibrated inputs are judgement calls, and the single largest unsourced block — the VAR, at
71 numbers — was also the subject of validation finding **V-M3**: as first written it
produced long-bond return volatility of 22.7% against a plausible 10–15%. Resolved
2026-08-22 — the innovation volatilities are now anchored to realised euro yield history
(LongGovt 14.3%) and guarded by tests, though they remain anchored judgement, not estimation.

What *is* evidence-backed is concentrated where the paper's argument lives: the country
equity return and valuation inputs (Article), and the FX and equity factor loadings
(Derived). The macro engine underneath them is assumption.

### Two places where I decline to write "Derived"

The brief for this document proposed recording the **`global_growth` block** and the
**CGB long-run yield of 2.3%** as Derived. Neither was produced by a regression or a
calculation from data. Both were specified as target calibrations with economic reasoning,
which I then sanity-checked for stationarity, PSD and internal consistency. Checking a
number is not deriving it. They are recorded as **Judgement**, with the reasoning attached,
because the alternative is exactly the laundering this document exists to prevent.

---

## Per-country equity inputs (`COUNTRY_INPUTS`)

| Market | drift = §3.1 r_nom | CAPE now | CAPE anchor | FX key | Article source |
|---|---:|---:|---:|:--|:--|
| USA | 4.0% | 40.1 | 27.5 | USD | §3.1 Table 1a; anchor = 20-yr avg CAPE |
| Europe | 7.0% | 17.0 | 17.0 | — (EUR base) | §3.1 Table 1a; at long-run median |
| Japan | 6.0% | 24.0 | 22.0 | JPY | §3.1 Table 1a; ROE-convergence upside (§5/§6) |
| China | 8.4% | 11.0 | 14.0 | CNY | §3.1 Table 1a; post-recovery median anchor |
| India | 6.4% | 28.0 | 24.0 | INR | §3.1 Table 1a; negative multiple-reversion (the "India tension") |
| Korea | 7.1% | 12.0 | 16.0 | KRW | §3.1 Table 1a; §5.1 Value-Up re-rating |
| Taiwan | 5.6% | 21.0 | 19.0 | TWD | §3.1 Table 1a |
| Indonesia | 8.8% | 17.0 | 18.0 | IDR | §3.1 Table 1a |
| Vietnam† | 9.0% | 13.0 | 16.0 | VND | PROXY — not in §3.1; illustrative dial |
| Singapore† | 6.0% | 14.0 | 15.0 | SGD | PROXY — not in §3.1; illustrative dial |

**FX proxies retired 2026-08.** `FXModel` now carries IDR and VND as first-class
currencies, calibrated from their own EUR-cross histories, so Indonesia and
Vietnam no longer stand in behind THB. Do not read the result as vindication of
the old proxy: THB and IDR both land at a 0.30 `inflation_loading`, but THB
correlates 0.713 with the USD against IDR's 0.510 — they converge only because
IDR's volatility (11.1% annualised) is materially higher than THB's (8.2%) and
the beta calculation offsets one against the other. Post-2017 the two diverge
sharply (THB 0.13, IDR 0.33). The substitution was never sound; it happened to be
roughly harmless at these particular parameters.

VND's 0.951 correlation with the USD is arithmetically correct and economically
misleading: the dong tracks the dollar because the State Bank of Vietnam manages
it to, not because a market chose that relationship. The parameter describes a
policy regime and would be badly wrong if the regime changed. At ~1% Vietnam
weight the exposure is small, but the caveat should stay visible.

`†` **Proxy markets.** Vietnam and Singapore have no §3.1 row; their inputs are
illustrative dials for "playing with weights", not sourced estimates. `real=False`
in `COUNTRY_INPUTS`; `proxy_markets()` lists them.

## Regional anchors (§13.6 four-region frontier)

The four bold rows of §3.1 Table 1a reproduce the §13.6 frontier inputs *by
construction* (see `scripts/build_cape_mapping_v2.py` in the article bundle):

| Region | real | local-nominal |
|---|---:|---:|
| USA | 2.0% | 4.0% |
| Europe | 5.0% | 7.0% |
| Japan | 4.0% | 6.0% |
| Asia ex-Japan | 6.5% | 8.5% |

## Method and calibration (for the referee)

- **Decomposition**: partial-reversion Gordon–Shiller,
  `r_real = D/P + g_real + (λ/N)·ln(CAPE_anchor / CAPE_now)`, with `N = 10`,
  `λ = 0.5` (multiple closes half the gap over the decade — the conservative
  choice; full reversion is *more* favourable to Asia and is shown as a
  sensitivity). `r_nom = r_real + 2.0%` EUR inflation (ECB target).
- **US anchor** = 20-yr-average CAPE (27.5), not the long-run median (16.0):
  half-reversion to the more generous reference reproduces §3's "~2% real" rather
  than an indefensible deep-negative figure. The choice deliberately weakens the
  article's own thesis.
- **CAPE / valuation data**: StarCapital / Keimling historical CAPE series;
  forward P/E, P/BV and dividend yields from MSCI index factsheets (Feb–Apr 2026,
  per Table 1).
- **FX tailwind**: §8.7 (renminbi ~10% PPP-undervalued, partial close) and §13.4
  (the won the strongest of the undervalued free-floaters; CNY/TWD anchored,
  modest). Pre-calibrated per currency in `assets/fx.py` (`_DEFAULT_CURRENCIES`).
- **FX macro loadings** (2026-08, joint estimation): all three columns come from
  ONE regression per currency — the EUR-cross log return on
  `[USD EUR-cross return, MSCI World EUR return]`, 2001-2026 monthly. Then
  `inflation_loading = 0.50 x b_usd`, `growth_loading = -0.30 x b_usd`, and
  `global_growth_loading = 0.60 x residual growth beta`, each rounded to 0.05.
  CNY's measured dollar correlation of 0.923 reproduces the 0.92 the article
  publishes independently, which validates the method.

  Three conventions, all enforced by tests:
    * `inflation_loading` POSITIVE for every currency — the repression world is
      euro-specific, so every non-euro currency appreciates against the EUR.
    * `growth_loading` NEGATIVE for every currency — EURO-AREA growth above trend
      strengthens the EUR. `state.growth` is euro growth.
    * `global_growth_loading` SIGNED — the only cyclical channel. Positive for
      exporters (KRW/IDR 0.15), negative for safe havens (JPY -0.05), zero where
      dollar-tracking explains everything (HKD/VND/CNY).

  The table previously carried POSITIVE growth loadings (CNY +0.30, TWD +0.40,
  KRW +0.30) justified by comments about "risk-on" and "global growth" — a factor
  the model did not then have. Those values were wrong against the euro-growth
  convention while the economics the comments described was real: residual growth
  betas of +0.105 for TWD (t=5.8) and +0.262 for KRW (t=8.4) against +0.001 for
  HKD (t=0.4). The fix added `global_growth` to the macro state so that exposure
  has somewhere to live, rather than flipping signs and losing it.

  WEAKEST LINK: the 0.60 conversion turns an equity-return beta into a
  growth-deviation loading by borrowing `EquitySleeve`'s own `growth_beta`. The
  ranking across currencies is robust; the level scales with that assumption.

  This SUPERSEDES the univariate loadings of the previous round, which absorbed
  shared growth exposure into the dollar coefficient (KRW 0.15 -> 0.40,
  IDR 0.30 -> 0.50, TWD 0.35 -> 0.45, JPY 0.35 -> 0.20).

  UN-DERIVED: CHF, CAD and AUD are absent from the FX dataset. CHF's -0.30
  inflation loading is the last negative; CAD's +0.10 and AUD's +0.20 growth
  loadings are global-cycle exposure in the euro-growth column. Left alone rather
  than corrected by assertion. Full derivation and flags: the note in
  `assets/fx.py`. Sensitivities:
  `python -m examples.run_fx_loading_sensitivity` (sample period) and
  `python -m examples.run_equity_growth_mode` (equity growth cycle).

- **`global_growth`** (2026-08): world real GDP growth, macro state index [7].
  Long-run mean 3.0% (vs euro 2.5%, since the world includes EM), persistence
  0.55 (vs 0.50 — a world aggregate is more persistent than one region),
  volatility 2.0% (vs 2.5% — diversification), innovation correlation 0.75 with
  euro growth and -0.30 with credit spread. Global growth feeds euro growth at
  0.20; the reverse spillover is ZERO, because a single region does not move the
  world aggregate. Side effect: euro growth's unconditional volatility rises
  10.9% and credit spread's 7.1%; the other five variables are unchanged.

## Still to be primary-sourced for the journal version

Two article exhibits use working-draft figures anchored to article-stated numbers,
flagged in their own captions and reproduced here for completeness:

- **Exhibit 1** (fiscal-composition scatter, §8.5) — social-expenditure and
  public-investment figures (OECD SOCX / Government at a Glance / ADB), illustrative.
- **Exhibit 5** (country-level frontier, §13.8) — uses the more bullish §5.1
  re-rating inputs (Korea 10 / China 9 / Taiwan 8 / India 7.5%), explicitly
  distinct from the conservative §3.1 CAPE figures above.

## Bond-side inputs (LDI / liability-hedging overlay)

The LHP holds a EUR-denominated core (the existing nominal + linker + cash hedge)
plus an unhedged overlay of unrepressed/managed sovereigns. `long_run_yield` is the
market's ~mid-2026 nominal 10-year yield; `global_rate_beta` is the EUR-rate
pass-through (LOW = decoupled / unrepressed). Source: central-bank policy
statements and 10-year benchmark yields, mid-June 2026.

| Sovereign | Block | long_run_yield | β (pass-through) | FX key | Note |
|---|:--|---:|---:|:--|:--|
| Australia | dev | 4.8% | 0.20 | AUD | AAA, commodity exporter |
| New Zealand | dev | 4.5% | 0.20 | AUD* | AA+, commodity exporter |
| Indonesia | em | 6.6% | 0.10 | IDR | ~4% real yield |
| India | em | 6.9% | 0.10 | INR | ~4% real yield |
| Korea | em | 3.7% | 0.15 | KRW | ~1.5% real yield |
| China (CGB) | managed | 1.8% -> 2.3%* | 0.10 | CNY | capped dial, default 0% |

`*` `FXModel` lacks NZD; **AUD** still proxies NZD (that substitution REMAINS live
and is not covered by the FX derivation — it needs its own beta). IDR is no longer proxied
(documented in `bond_inputs.py`). All overlay sleeves are held **unhedged** —
FX-hedging back to EUR would, by covered-interest parity, reintroduce the
(possibly repressed) EUR base rate.

`*` China is the only row whose long-run (reversion-target) yield differs from its
initial yield: 1.8% initial, 2.3% long-run. Every other row sets the two equal, which
assumes today's yield IS the equilibrium — a defensible neutral prior for the five
unrepressed sovereigns, but not for CGB, where 1.8% is a cyclical low.

CGB sits in its own `managed` block, explicitly **not** claimed as unrepressed
(the curve is managed and capital-controlled). It is included as a capped dial for its
**low EUR pass-through** (β = 0.10; article §13 measures Fed-PBoC policy-cycle
correlation at ~0.03), which is what keeps a EUR-repression episode out of the sleeve.

On the store-of-value claim, the model **supports the weak form and not the strong
form**. Measured over accumulation, CGB earns a small positive real return in EUR terms
(~+0.9% baseline, ~+0.8% under repression), so "broadly keeps pace with inflation" holds
— though note this comes mostly from the unhedged CNY leg, not the 1.8% local carry.
What the model does **not** support is CGB out-earning what it displaces: the EUR core
returns ~2.2% real at baseline and ~1.3% under repression, leaving CGB ~127bp behind at
baseline and ~55bp behind under repression. That narrowing under repression, together
with the sleeve's volatility contribution, is the case for the line — not an absolute
return advantage. Measured figures: `output/cgb_dial_findings.md`; downside sensitivity
(flat 1.8% long-run) via `python -m examples.run_cgb_dial --flat-lr`.

### Repression scenario (Napier thesis)
The financial-repression overlay (`examples/run_attribution.py`) pins the EUR real
rate to **−1.5%** and inflation to **3.5%** for a **12-year** window, with **3-year
linear transitions in and out** (V-M7), and foreign curves left unrepressed via their
low `global_rate_beta`. The transitions blend both variables between the path's own
value and the pinned value at weights 1/4, 2/4, 3/4 going in and 3/4, 2/4, 1/4 coming
out; the pinned interior is unchanged. Calibration is an
explicit, falsifiable assumption — the result is reported as a conditional world
alongside the no-repression baseline, never blended into a single probability.


---

# Complete input register (added 2026-08-22, closing V-M6)

Every block below was previously undocumented. Values are generated from the live code, not
transcribed.

## 1. VAR macro engine — **Judgement throughout, no source**

The 71 numbers below are the largest unsourced block in the model. They were not estimated
from data, not taken from the paper, and not cited to a reference calibration. They are a
hand-built VAR that produces broadly sensible macro dynamics — simulated long-run means
match X̄ to within 8bp on seven of eight variables, nothing drifts or explodes over 65 years
— but the volatilities are demonstrably too high for the bond sleeves that consume them
(**V-M3**, resolved 2026-08-22: 22.7% simulated long-bond volatility against a plausible 10–15%, since recalibrated to 14.3%).

**If one block of this model should be replaced with estimated parameters before journal
submission, it is this one.**

### VAR long-run mean (X-bar) and floors

| Variable | X-bar | Floor | Status |
|---|---:|---:|---|
| `short_rate` | 0.0350 | -0.020 | Judgement |
| `long_rate` | 0.0450 | 0.000 | Judgement |
| `real_rate` | 0.0150 | -0.050 | Judgement |
| `inflation` | 0.0250 | -0.050 | Judgement |
| `growth` | 0.0250 | -0.200 | Judgement |
| `credit_spread` | 0.0100 | 0.000 | Judgement |
| `curvature` | 0.0050 | -0.050 | Judgement |
| `global_growth` | 0.0300 | -0.150 | Judgement |

### VAR persistence matrix Φ (non-zero entries only)

| Row (responds) | Column (driver) | Value | Status |
|---|---|---:|---|
| `short_rate` | `short_rate` | 0.70 | Judgement |
| `short_rate` | `long_rate` | 0.10 | Judgement |
| `short_rate` | `inflation` | 0.05 | Judgement |
| `long_rate` | `short_rate` | 0.05 | Judgement |
| `long_rate` | `long_rate` | 0.80 | Judgement |
| `long_rate` | `inflation` | 0.05 | Judgement |
| `real_rate` | `real_rate` | 0.75 | Judgement |
| `real_rate` | `inflation` | 0.05 | Judgement |
| `inflation` | `short_rate` | 0.05 | Judgement |
| `inflation` | `long_rate` | 0.05 | Judgement |
| `inflation` | `inflation` | 0.60 | Judgement |
| `growth` | `inflation` | 0.05 | Judgement |
| `growth` | `growth` | 0.50 | Judgement |
| `growth` | `global_growth` | 0.20 | Judgement |
| `credit_spread` | `growth` | 0.10 | Judgement |
| `credit_spread` | `credit_spread` | 0.65 | Judgement |
| `curvature` | `long_rate` | 0.05 | Judgement |
| `curvature` | `inflation` | 0.03 | Judgement |
| `curvature` | `curvature` | 0.65 | Judgement |
| `global_growth` | `global_growth` | 0.55 | Judgement |

### VAR innovation volatilities (diagonal of Σ)

| Variable | Annualised σ | Status |
|---|---:|---|
| `short_rate` | 0.0080 | Judgement |
| `long_rate` | 0.0070 | Judgement, anchored (V-M3, 2026-08-22): targets annual-change sd of long euro yields 60–90bp; 10y Bund 1999–2025 ≈ 85bp incl. 2022 / ≈ 70bp excl.; 30y lower. Level factor is the ∞-maturity limit. Was 0.0120. **Pending:** verify against GDBR10 / GDBR30 annual changes from Bloomberg |
| `real_rate` | 0.0065 | Judgement, anchored (V-M3): long euro real yields (OATei/Bundei) show similar annual-change dispersion on a shorter record. Was 0.0100 |
| `inflation` | 0.0080 | Judgement |
| `growth` | 0.0250 | Judgement |
| `credit_spread` | 0.0045 | Judgement, anchored (V-M3): euro IG OAS annual changes ≈ 50bp; 45bp innovation at φ = 0.65 reproduces this. Was 0.0060 |
| `curvature` | 0.0080 | Judgement |
| `global_growth` | 0.0200 | Judgement |

### VAR innovation correlations (upper triangle, non-zero)

| Pair | ρ | Status |
|---|---:|---|
| `short_rate` × `long_rate` | +0.70 | Judgement |
| `short_rate` × `real_rate` | +0.50 | Judgement |
| `short_rate` × `inflation` | +0.20 | Judgement |
| `short_rate` × `growth` | -0.10 | Judgement |
| `short_rate` × `credit_spread` | +0.20 | Judgement |
| `short_rate` × `curvature` | -0.15 | Judgement |
| `short_rate` × `global_growth` | -0.08 | Judgement |
| `long_rate` × `real_rate` | +0.60 | Judgement |
| `long_rate` × `inflation` | +0.40 | Judgement |
| `long_rate` × `growth` | -0.15 | Judgement |
| `long_rate` × `credit_spread` | +0.30 | Judgement |
| `long_rate` × `curvature` | -0.20 | Judgement |
| `long_rate` × `global_growth` | -0.10 | Judgement |
| `real_rate` × `inflation` | -0.20 | Judgement |
| `real_rate` × `growth` | -0.10 | Judgement |
| `real_rate` × `credit_spread` | +0.20 | Judgement |
| `real_rate` × `curvature` | -0.10 | Judgement |
| `real_rate` × `global_growth` | -0.08 | Judgement |
| `inflation` × `growth` | +0.10 | Judgement |
| `inflation` × `curvature` | +0.10 | Judgement |
| `inflation` × `global_growth` | +0.08 | Judgement |
| `growth` × `credit_spread` | -0.40 | Judgement |
| `growth` × `curvature` | +0.05 | Judgement |
| `growth` × `global_growth` | +0.75 | Judgement |
| `credit_spread` × `curvature` | -0.10 | Judgement |
| `credit_spread` × `global_growth` | -0.30 | Judgement |
| `curvature` × `global_growth` | +0.05 | Judgement |

`global_growth` (index [7], added 2026-08) is part of the above and is **Judgement**: mean
3.0% against euro 2.5% because the world includes EM; persistence 0.55 against 0.50 because a
world aggregate is more persistent than one region; volatility 2.0% against 2.5% because of
diversification; spillover 0.20 into euro growth and **zero** back, because one region does
not move the world aggregate. Reasoned, sanity-checked, not measured.

## 2. Global equity market factor

### Global equity factor

| Input | Value | Source | Status |
|---|---:|---|---|
| Factor volatility | 0.155 | `calibration/equity_factor_calibration.py`, MSCI World monthly 2001–2025 | **Derived** |
| ρ(F, `short_rate`) | -0.05 | — | Judgement |
| ρ(F, `long_rate`) | -0.10 | — | Judgement |
| ρ(F, `real_rate`) | -0.05 | — | Judgement |
| ρ(F, `inflation`) | -0.10 | — | Judgement |
| ρ(F, `growth`) | +0.25 | — | Judgement |
| ρ(F, `credit_spread`) | -0.35 | — | Judgement |
| ρ(F, `global_growth`) | +0.30 | — | Judgement |

The factor volatility is **Derived and reproducible**. Run
`python calibration/equity_factor_calibration.py`: it reads `data/ret_usd.csv` and
`data/fx_levels.csv` and reproduces this value, the full `market_beta` / `idio_vol` table and
the documented worst-fitting pairs, under the repository's own numpy 1.26.

*(Before 2026-08-22 the source data sat outside the repository as numpy-2.x pickles that the
declared environment could not even read, and these inputs were recorded as Derived-but-not-
re-runnable. The data is now committed as CSV; see `data/README.md`.)*

The six correlations between the factor and the macro innovations are **Judgement**.

## 3. Country equity inputs — full table

### Country equity inputs

| Market | drift | CAPE now | CAPE fair | gbeta | ibeta | mbeta | idio | FX |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| USA | 0.040 | 40.1 | 27.5 | 0.60 | -0.30 | 0.961 | 0.034 | USD |
| Europe | 0.070 | 17.0 | 17.0 | 0.60 | -0.30 | 0.852 | 0.073 | None |
| Japan | 0.060 | 24.0 | 22.0 | 0.55 | -0.25 | 0.739 | 0.124 | JPY |
| China | 0.084 | 11.0 | 14.0 | 0.70 | -0.20 | 0.913 | 0.204 | CNY |
| India | 0.064 | 28.0 | 24.0 | 0.75 | -0.25 | 0.867 | 0.170 | INR |
| Korea | 0.071 | 12.0 | 16.0 | 0.70 | -0.25 | 0.925 | 0.156 | KRW |
| Taiwan | 0.056 | 21.0 | 19.0 | 0.70 | -0.25 | 0.870 | 0.156 | TWD |
| Indonesia | 0.088 | 17.0 | 18.0 | 0.70 | -0.20 | 0.850 | 0.190 | IDR |
| Vietnam | 0.090 | 13.0 | 16.0 | 0.75 | -0.20 | 0.750 | 0.240 | VND |
| Singapore | 0.060 | 14.0 | 15.0 | 0.55 | -0.25 | 0.900 | 0.115 | SGD |

| Column | Status | Source |
|---|---|---|
| `drift`, `cape_now`, `cape_fair` | **Article** (8 markets) | §3.1 Table 1a — see the table earlier in this file |
| `drift`, `cape_now`, `cape_fair` | Judgement (Vietnam, Singapore) | Not in §3.1; illustrative dials, flagged `real=False` |
| `mbeta`, `idio` | **Derived, reproducible** (7 markets) | `calibration/equity_factor_calibration.py` on `data/ret_usd.csv` + `data/fx_levels.csv` |
| `mbeta`, `idio` | Judgement (Indonesia, Vietnam, Singapore) | Assigned by analogy; marked JUDGEMENT inline in `country_inputs.py` |
| `gbeta` | Judgement | No source. Note the ordering is only coherent against a *global* cycle — see `examples/run_equity_growth_mode.py` and validation item V-D2 |
| `ibeta` | Judgement | No source |

## 4. Sovereign bond overlay — full table

### Sovereign bond overlay

| Sovereign | Block | within | y0 | long-run | duration | β global | idio | FX |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Australia | dev | 0.50 | 0.048 | 0.048 | 8.0 | 0.20 | 0.006 | AUD |
| NewZealand | dev | 0.50 | 0.045 | 0.045 | 8.0 | 0.20 | 0.007 | AUD |
| Indonesia | em | 0.35 | 0.066 | 0.066 | 7.0 | 0.10 | 0.009 | IDR |
| India | em | 0.35 | 0.069 | 0.069 | 7.0 | 0.10 | 0.009 | INR |
| Korea | em | 0.30 | 0.037 | 0.037 | 8.0 | 0.15 | 0.007 | KRW |
| China | managed | 1.00 | 0.018 | 0.023 | 7.0 | 0.10 | 0.005 | CNY |

| Column | Status | Source |
|---|---|---|
| `yld` (initial yield) | **Article** | Current 10y nominal yields, mid-2026; see the bond-side section above |
| `beta` for China | **Article** | §13 Fed–PBoC policy-cycle correlation ≈ 0.03; 0.10 is a conservative margin above it |
| `beta` for the other five | Judgement | No source |
| `lr` (long-run yield, China only) | Judgement | 2.3% chosen so the sleeve is not assumed to sit at a cyclical low permanently. Reasoned, not derived |
| `within`, `dur`, `idio` | Judgement | No source |
| `fx` | Structural | **AUD still proxies NZD** — that substitution remains live (V-D5) |

## 5. FX currency parameters — full table

### FX currency parameters

| Ccy | infl_load | growth_load | global_load | carry | drift | ppp_rev | ppp_gap0 | idio_vol |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| USD | +0.50 | -0.30 | +0.00 | +0.015 | -0.010 | 0.10 | +0.00 | 0.100 |
| GBP | +0.30 | -0.20 | +0.05 | +0.005 | -0.005 | 0.10 | -0.05 | 0.090 |
| CAD | +0.20 | +0.10 | +0.00 | +0.005 | +0.000 | 0.10 | +0.00 | 0.080 |
| AUD | +0.10 | +0.20 | +0.00 | +0.010 | +0.000 | 0.10 | +0.00 | 0.110 |
| CHF | -0.30 | -0.50 | +0.00 | -0.005 | +0.005 | 0.10 | +0.00 | 0.080 |
| JPY | +0.20 | -0.15 | -0.05 | -0.008 | +0.003 | 0.08 | -0.25 | 0.090 |
| CNY | +0.45 | -0.30 | +0.00 | +0.005 | +0.005 | 0.12 | -0.20 | 0.050 |
| HKD | +0.50 | -0.30 | +0.00 | +0.015 | +0.000 | 0.15 | +0.00 | 0.030 |
| TWD | +0.45 | -0.25 | +0.05 | +0.005 | +0.005 | 0.12 | -0.20 | 0.070 |
| KRW | +0.40 | -0.25 | +0.15 | +0.015 | +0.003 | 0.12 | -0.15 | 0.100 |
| SGD | +0.35 | -0.20 | +0.05 | +0.005 | +0.005 | 0.10 | -0.10 | 0.060 |
| THB | +0.40 | -0.25 | +0.05 | +0.010 | +0.000 | 0.12 | -0.15 | 0.120 |
| IDR | +0.50 | -0.30 | +0.15 | +0.035 | -0.020 | 0.12 | -0.15 | 0.111 |
| VND | +0.50 | -0.30 | +0.00 | +0.030 | -0.020 | 0.10 | -0.20 | 0.040 |
| INR | +0.45 | -0.30 | +0.10 | +0.030 | -0.015 | 0.15 | -0.10 | 0.070 |

| Column | Status | Source |
|---|---|---|
| `inflation_loading`, `growth_loading`, `global_growth_loading` | **Derived, reproducible** (12 currencies) | One joint regression per currency: EUR-cross monthly log return on `[USD EUR-cross, MSCI World EUR]`, 2001–2026. `0.50 × b_usd`, `−0.30 × b_usd`, `0.60 × residual growth beta`, each rounded to 0.05. Full table and validation in `assets/fx.py` |
| The same three | Judgement (CHF, CAD, AUD) | **Un-derived** — absent from the FX dataset. CHF's −0.30 inflation loading is the last remaining negative and contradicts its own comment (V-D5) |
| `idio_vol` for IDR | **Derived** | 11.1% annualised, measured on the same sample |
| `carry_spread`, `fx_drift`, `ppp_reversion`, `initial_ppp_gap`, `idio_vol` (all others) | Judgement | **No source for any of the 74.** These drive the FX tailwind central to the unhedged-overlay thesis |

The derivation is validated at one point: CNY's measured dollar correlation of 0.923
reproduces the 0.92 the article publishes independently. That validates the *method*, not
each of the 36 loadings.

**Status of the FX loadings — all three columns Derived and reproducible (2026-08-22).**
`calibration/fx_loading_calibration.py`, run on `data/fx_levels.csv`,
`data/fx_bloomberg_legs.csv` and `data/ret_usd.csv`, reproduces every loading in
`assets/fx.py` to three decimals, and a test asserts that it continues to.

This replaced a round-4 `b_usd` column that could not be reproduced from the committed data
under any specification or window, and whose origin was **not recoverable** from the
repository, the full git history, or the laptop (validation finding V-F1). 17 loadings
changed — 8 inflation, 9 growth; `global_growth_loading` changed for none. The superseded
values are recorded inline in each changed entry in `assets/fx.py`.

Note also the **round-3 / round-4 inconsistency** this exposed: the round-3 univariate column
reproduces here exactly (KRW 0.300, IDR 0.615, CNY 0.865) while the round-4 table claimed
0.760, 0.997 and 0.933 for the same three currencies on the same data and window. Both were
described as a beta against the USD. Only round-3's is reproducible.

| Column | Status |
|---|---|
| `global_growth_loading` (12) | **Derived, reproducible** — all 12 reproduce exactly |
| `inflation_loading` (12) | **Derived, NOT reproducible** — see V-F1 |
| `growth_loading` (12) | **Derived, NOT reproducible** — see V-F1 |

The script reproduces the article's own CNY–USD correlation of 0.92 (measured 0.923), all 11
round-3 correlations to 3dp, and the cited IDR/THB volatilities exactly — so the data and
method are right. What it cannot reproduce is the `b_usd` column from which the inflation and
growth loadings are computed. **24 of the 36 FX loadings therefore rest on a coefficient that
cannot be traced to this data.** Full detail in `docs/VALIDATION_REPORT.md` under V-F1.

## 6. Participant configuration

### Participant configuration

| Input | Value | Status |
|---|---:|---|
| `entry_age` | 25 | Judgement / convention |
| `retirement_age` | 68 | Judgement / convention |
| `death_age` | 90 | Judgement / convention |
| `contribution_rate` | 0.2 | Judgement / convention |
| `AMBITION_RR` | 0.7 | Judgement / convention |
| `adjustment_floor` | -0.03 | Judgement / convention |
| `adjustment_smoothing_years` | 3 | Judgement / convention |
| `solidarity_reserve_rate` | 0.05 | Judgement / convention |
| `lambda_ (Nelson-Siegel)` | 5.0 | Judgement / convention |
| `base_salary` | 50000 | Judgement / convention |
| `salary real_growth` | 0.005 | Judgement / convention |
| `N_SCENARIOS default` | 500 | Judgement / convention |
| `SEED` | 42 | Judgement / convention |

### Cohort glide path

| Age band | RSP | LHP | Status |
|---|---:|---:|---|
| 25–34 | 1.20 | 0.00 | Judgement / Dutch WTP convention |
| 35–44 | 1.00 | 0.00 | Judgement / Dutch WTP convention |
| 45–54 | 0.80 | 0.20 | Judgement / Dutch WTP convention |
| 55–64 | 0.70 | 0.30 | Judgement / Dutch WTP convention |
| 65–74 | 0.50 | 0.50 | Judgement / Dutch WTP convention |
| 75–84 | 0.20 | 0.80 | Judgement / Dutch WTP convention |
| 85–94 | 0.20 | 0.80 | Judgement / Dutch WTP convention |
| 95–104 | 0.20 | 0.80 | Judgement / Dutch WTP convention |

None of these is sourced. Several are Dutch WTP conventions rather than free choices — the
70% career-average ambition and the −3% adjustment floor in particular — but the paper is
not cited for them here and they should not be read as measured.

## 7. Sub-portfolio structure

`build_lhp_specs` (LongGovt 50% at duration 20, ILG 40% at real duration 18, cash 10%) and
`build_rsp_specs` (equity 50%, real assets 25%, IG credit 15%, commodities 10%, with their
growth/inflation betas and FX exposures) are **Judgement** — a plausible Dutch fund shape,
not a calibration. The `GlobalEquity` sleeve in `build_rsp_specs` is replaced by the country
mosaic in every published exhibit, so its own betas do not reach the article's numbers.
