# V-C4 verification — EUR translation inverted in the §8.6 return series (2026-09-10)

Independent verification of the 2026-09-10 finding (see
`calibration/sensitivity_w811_te_2026-09-10.md`), followed by regeneration of every
published number that descends from the affected series. Branch `w811-te-sensitivity`.
**Suite: 51 passed** (50 + the new damping-direction regression test).

## 1. Fresh-path verdict

`tools/verify_vc4_translation.py` rebuilds EUR monthly returns from first principles —
`r_eur = (1+r_usd)·(u_{t-1}/u_t) − 1`, `u` = USD per EUR, written out once, level-anchor
asserted (`0.8 ≤ EURUSD ≤ 1.6` over 2001–2026; the inverse convention breaches the lower
bound at the 2008 peak) — deliberately not importing the code path under suspicion.

| Series | USD vol | EUR, fresh path (correct) | EUR, inverted | Article ret_eur as committed |
|---|---:|---:|---:|---:|
| USA | 15.3% | **15.0%** | 20.1% | 20.3% |
| AsiaExJP | 21.0% | **18.9%** | 26.1% | 26.3% |

Per-observation comparison: the committed article series matches the **inverted**
construction (max monthly diff 0.023/0.031 — a marginally different FX source, same
formula) and is nowhere near the correct one (max diff 0.19). **Verdict: confirmed.
The article-side ret_eur series was built with the EUR translation inverted.**

**External anchor, one sentence:** USA sleeve 2001–2026 annualised vol in EUR — fresh
path **15.0%**, versus the committed 20.9%-generating value of ~20.3% and the corrected
value of 15.0%: only the fresh/corrected figure sits *below* the 15.3% USD vol, which is
what a EUR investor's equity–dollar damping (dollar strengthens in equity selloffs)
requires; no unhedged EUR translation of a USD asset can sit 5pp *above* it.

**Regression test that would have caught this:**
`tests/test_invariants.py::test_eur_translation_damps_usa_equity_vol` — EUR-translated
USA vol must be below USD vol (directional; the margin is only ~0.3pp on this sample, so
the test is direction-only plus a hard 19% ceiling that the inverted regime cannot pass).

## 2. Corrected outputs — old vs new, every affected number

Fix at source: the article repo previously had **no builder** for ret_eur (chat-sandbox
artifact). `exhibits/scripts/build_ret_eur.py` (new) now builds it correctly from the
committed `ret_usd.csv` + `fx_levels.csv` with the convention asserted;
`exhibits/scripts/build_table6_table7.py` (new) regenerates every dependent table.
**Implementation validated first**: run against the old (inverted) series it reproduces
every published number — Panel (a) 100% USA / 9.3% / Sharpe 0.46; Panel (b)
5.3%/20.9%/0.26, 6.3%/22.0%/0.29, tangency 68/32 Sharpe 0.33; all seven Table 6 rows
(100/51/5/100/82/100/0 with verdicts); all eight Table 7 numbers incl. TE 2.8% and
sub-periods; Exhibit 5's cap-constrained mix to the decimal. One reading was pinned down
in the process: Table 6's "Asian expected return" cuts apply to **Japan and Asia
ex-Japan together** (only that reproduces 51/5/0).

### §8.6 anchors

| Number | Old (published) | New (corrected) | Direction |
|---|---|---|---|
| Panel (a) USA historical mean, EUR | 9.3% | 7.4% | lower — EUR appreciated over the sample; inversion overstated USD-asset returns |
| Panel (a) tangency | 100% USA, Sharpe 0.46 | **75% USA / 25% AxJ**, Sharpe 0.51 | the "100%-USA small-sample pathology" softens: even backward-looking optimisation now takes 25% Asia |
| Panel (b) Current | 5.3% / 20.9% / 0.26 | 5.3% / **14.1%** / **0.38** | vol −6.8pp, Sharpe up |
| Panel (b) 30% Asia | 6.3% / 22.0% / 0.29 | 6.3% / **14.3%** / **0.44** | vol −7.7pp; vol gap vs Current narrows 1.1pp → 0.2pp |
| Panel (b) tangency | 68% AxJ / 32% Japan, Sharpe 0.33 | **45% Europe / 24% Japan / 31% AxJ**, Sharpe 0.51 | no longer an all-Asia corner; Europe enters |

### Table 6 (verdict column unchanged on every row)

| Row | Old tangency Asia | New tangency Asia | 30%A beats Current? |
|---|---:|---:|---|
| Base case | 100% | 55% | Yes (0.441 vs 0.378) |
| Asian ER −1pp | 51% | 29% | Yes (0.413 vs 0.361) |
| Asian ER −2pp | 5% | 6% | Yes (0.385 vs 0.343) |
| U.S. ER +1pp | 100% | 55% | Yes (0.466 vs 0.421) |
| U.S. ER +2pp | 82% | 55% | Yes (0.490 vs 0.464) |
| Pre-2017 correlations | 100% | 50% | Yes (0.418 vs 0.368) |
| All three adverse | 0% | 0% | No (0.411 vs 0.417) |
| **Asian volatility +3pp (W8.11, new row)** | 89% | **40%** | **Yes (0.418 vs 0.369)** |

The headline sensitivity sentence changes from "swings from 100% to 5%" to "swings from
55% to 6%" — less dramatic, same qualitative point, and every survives/fails verdict is
identical.

### Table 7 (historical counterfactual, 2004–2026)

| Number | Old | New | Direction |
|---|---|---|---|
| Current ann. return / vol / maxDD | 6.3% / 21.0% / −64% | 8.2% / 13.0% / −50% | returns up, vol and drawdown down |
| 30% Asia ann. return / vol / maxDD | 5.5% / 22.2% / −67% | 7.5% / 13.2% / −54% | same |
| Tilt underperformance | ~0.8pp p.a. | ~0.7pp p.a. | marginally narrower |
| Tracking error | 2.8% | 2.8% | **unchanged** (common factor cancels in the active difference) |
| Sub-periods (tilt, pp p.a.) | +0.1 / −2.0 / +4.0 | +0.2 / −2.0 / +3.5 | 2014–24 identical |

### §8.8 / Exhibit 5 (country frontier)

| Number | Old | New | Direction |
|---|---|---|---|
| Cap-constrained tangency | Eur 28 / Jpn 20 / Chn 20 / Kor 15 / Twn 10 / Ind 6.9 / US 0 | Eur **40** (at cap) / Jpn 20 / Chn 20 / Kor **6** / Twn 10 / Ind 4 / US 0 | Europe rises to its cap; **Korea's weight drops 15→6** — the Korea emphasis in the §8.8 text needs revisiting |
| Cap-constrained Sharpe | 0.323 | 0.505 | up |
| Unconstrained tangency | Jpn 33 / Chn 31 / Kor 25 / Twn 10 | Eur 49 / Jpn 26 / Chn 21 / Twn 4, **Korea 0** | Korea exits entirely under the correct covariance |

### Consumers of ret_eur (grep, complete list)

1. `exhibits/scripts/build_markowitz_v2.py` → `markowitz_both.pkl`, `results/markowitz_summary.csv` → §8.6 text numbers, Exhibit 4 (`plot_markowitz.py`)
2. `exhibits/scripts/build_markowitz_country.py` → `markowitz_country.pkl` → §8.8 text numbers, Exhibit 5 (`plot_markowitz_country.py`)
3. Table 6 and Table 7 (no prior committed script; now `build_table6_table7.py`)
4. `simple_alm/tools/compute_te_frontier_w811.py` (this round's TE note — TE 2.83% verified insensitive to the inversion)

All four regenerated/rerun. Article-side working tree holds the corrected
`ret_eur.{csv,pkl}`, both frontier pkls, `markowitz_summary.csv`, both exhibit figures
(PDF+PNG), the two new builder scripts and the two path-fixed frontier scripts —
**deliberately uncommitted**, awaiting the V-C4 ruling and the article-text edits the new
numbers require (§8.6 prose, Table 6, Table 7, §8.8 Korea passage, both exhibit captions).

### One-month technicality

The corrected series necessarily starts 2001-04 (the translation consumes one month of FX
history); the inverted series started 2001-03. 301 vs 302 months — immaterial to any
figure above.

## Addendum (same day): Table 4, Table 5 and the §8.1/§8.3 prose correlations

These descend from the same series but had no committed builder and were missing from the
consumer list above. Now covered by `exhibits/scripts/build_table4_correlations.py`
(article repo, uncommitted with the rest). Validation against the old (inverted) series
reproduces the published Table 4 and §8.1 figures to within 0.01 (rounding), the full
Table 5 within 0.01–0.02, and pins down two method details: the published matrix was
computed on **simple returns, not the log returns the caption states** (simple: max error
0.005; log: up to 0.026) on the n=301 first-row-dropped sample, and two §8.3 prose
figures (the Japan/Korea/Taiwan "0.65–0.90 range", India "0.88 in 2013") were chart-read
approximations that the computed old series does not exactly reproduce (0.52–0.93 and
0.82). Adopting the correction should fix the caption too.

### Table 4, old → new (lower triangle; every pair falls)

| Pair (vs) | USA | Europe | Japan | AsiaExJP | EM | China | India | Korea |
|---|---|---|---|---|---|---|---|---|
| Europe | 0.93→0.80 | | | | | | | |
| Japan | 0.80→0.64 | 0.84→0.61 | | | | | | |
| Asia ex-Japan | 0.83→0.64 | 0.86→0.70 | 0.78→0.57 | | | | | |
| EM | 0.86→0.67 | 0.90→0.76 | 0.81→0.59 | 0.98→0.96 | | | | |
| China | 0.69→0.42 | 0.73→0.49 | 0.67→0.38 | 0.88→0.78 | 0.86→0.75 | | | |
| India | 0.72→0.53 | 0.75→0.58 | 0.70→0.50 | 0.82→0.71 | 0.83→0.72 | 0.67→0.46 | | |
| Korea | 0.78→0.61 | 0.80→0.67 | 0.75→0.57 | 0.91→0.85 | 0.89→0.83 | 0.68→0.50 | 0.70→0.55 | |
| Taiwan | 0.77→0.62 | 0.77→0.60 | 0.69→0.48 | 0.90→0.84 | 0.87→0.79 | 0.69→0.51 | 0.68→0.52 | 0.82→0.73 |

Direction: **every correlation falls**, by 0.02 (EM–AxJ) to 0.29 (Japan–Europe, China–
Japan). Mechanism: the inverted translation applied one identical FX factor to every
series the wrong way round, injecting a large common component that inflated all
cross-correlations; the correct translation's FX term is partly idiosyncratic to the
dollar leg and partly offsets equity comovement.

### §8.1 prose figures, old → new, direction per number

| Prose figure | Old | New | Direction |
|---|---|---|---|
| USA–Europe | 0.93 | 0.80 | falls — and now sits BELOW the USD-base 0.86, not above it |
| Japan–Europe | 0.84 | 0.61 | falls |
| Asia exJ–Europe | 0.86 | 0.70 | falls |
| China–Europe | 0.73 | 0.49 | falls |
| India–Europe | 0.75 | 0.58 | falls |
| Taiwan–Europe | 0.77 | 0.60 | falls |
| China–India | 0.67 | 0.46 | falls |
| China–Korea | 0.68 | 0.50 | falls |
| China–Taiwan | 0.69 | 0.51 | falls |

Two prose consequences beyond the numbers, stated rather than absorbed. (i) §8.1's causal
sentence — EUR-translation "adds a common currency factor that USD-base correlations
strip out", explaining why 0.93 exceeds the practitioner 0.85 — **inverts**: under the
correct translation the EUR-base USA–Europe correlation (0.80) sits *below* the USD-base
(0.86), because the FX term adds partly-offsetting noise to the USD leg. (ii) The claim
that adding U.S. exposure gives a European portfolio "approximately no diversification
benefit" rested on 0.93; at 0.80 it needs softening. The *relative* claim — the gain is
concentrated in specific Asian markets (China 0.49, India 0.58 vs USA 0.80) — survives
and strengthens: the China–USA gap widens from 0.20 to 0.31.

### Table 5 (regime rows, China and headline columns; full grid in the script output)

| Regime | USA old→new | AsiaExJP old→new | China old→new |
|---|---|---|---|
| Full sample | 0.93→0.80 | 0.86→0.70 | 0.73→0.49 |
| Post-GFC 2010–19 | 0.93→0.70 | 0.89→0.64 | 0.82→0.56 |
| Post-pandemic 2021–26 | 0.87→0.70 | 0.79→0.51 | 0.55→0.10 |
| GFC Sep08–Mar09 | 0.99→0.79 | 0.99→0.98 | 0.97→0.88 |
| Eurozone Jul11–Sep12 | 0.98→0.80 | 0.95→0.79 | 0.92→0.73 |
| China shock Jul15–Mar16 | 0.99→0.99 | 0.85→0.75 | 0.82→0.69 |
| COVID Jan–Sep20 | 0.97→0.95 | 0.91→0.84 | 0.81→0.65 |
| Fed shock 2022 | 0.92→0.85 | 0.80→0.46 | 0.48→**−0.09** |

Direction: every cell falls or holds. The §8.2 narrative survives — Western-origin stress
still correlates Asia up (AxJ 0.98 in the GFC) — but its numbers change materially, and
the "most striking decoupling observation" sharpens: China–Europe in 2022 goes from 0.48
to **−0.09**, actually negative. One nuance: GFC-window USA–Europe falls to 0.79 (from
0.99), so "every market 0.93–0.99 in the GFC" no longer holds for the USA — that sentence
needs its range recomputed.

### §8.3 prose figures, old → new

| Figure | Old (published) | Old (computed) | New | Direction |
|---|---|---|---|---|
| USA–Europe rolling band 2006–26 | 0.86–0.97 | 0.86–0.97 | 0.54–0.90 | band shifts down and widens — "fortress that does not decouple" weakens |
| Japan/Korea/Taiwan range | 0.65–0.90 | 0.52–0.93 | 0.20–0.84 | falls (published range was a chart approximation) |
| China rolling, 2014 → latest | 0.87 → 0.55 | 0.86 → 0.55 | 0.43 → 0.13 | both ends fall; the decade-long decline survives at a lower level |
| India rolling, 2013 → latest | 0.88 → 0.68 | 0.82 → 0.68 | 0.52 → 0.33 | both ends fall; pattern survives |

Exhibit 3 (`rolling_corr_60m` / `build_exhibit3_rolling_corr.py`) descends from the same
translation and needs regenerating with the same correction — added to the consumer list.

## 3. Status

- Fresh-path verification: **confirmed inverted** — V-C4 substantiated.
- The correction favours the thesis (vols fall, Sharpes rise, drawdowns shrink, Panel (a)
  takes 25% Asia even backward-looking); it was therefore validated by exact reproduction
  of every published number under the old construction before a single new number was
  produced.
- One number moves *against* the emphasis of the text: Korea's optimal weight in §8.8.
  Stated here rather than absorbed.
- simple_alm branch `w811-te-sensitivity`: verification script + damping test committed;
  suite 51 passed (incl. the W8.11 calibration-hash guard). Held unmerged for confirmation.
