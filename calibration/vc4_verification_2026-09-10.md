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
