# B5-0 — benchmark re-anchored to MSCI ACWI (2026-09-22)

Ruling executed: the primary benchmark is MSCI ACWI at 31 August 2026, sourced and
dated; the proposed vector is untouched. Branches `b5-benchmark-acwi` in both repos,
held unmerged until the article chat confirms the §8/§9/§11 edits. Every number below
regenerates from `exhibits/scripts/build_b5_acwi_benchmark.py` (article repo) reading
the sourced weights CSV `replication/data/acwi_benchmark_2026-08-31.csv`.

## Step 0 — data, construction, validation

**Sources (official MSCI factsheets, 31 Aug 2026).** ACWI: USA 63.59, Japan 5.09,
Taiwan 3.25, UK 3.11, Canada 3.05, other 21.91 — the work order's anchors reproduced
exactly — with index cap USD 104,043,110.63mn. EM: Taiwan 27.44, Korea 20.84, China
20.62, India 11.25, Brazil 3.94, other 15.90, cap USD 12,338,300.43mn. MSCI Indonesia
cap USD 58,889.98mn (31 Jul 2026, latest available; ~6bp weight, immaterial, disclosed).
EM share of ACWI: cap ratio 11.859% vs the independent Taiwan bridge 11.844% — two
routes agree to 1.5bp. Note: a web-search summary initially returned different EM
weights (Korea 20.11 etc.); the official factsheet PDF was read directly and wins.

**Construction (rules as proposed, confirmed by execution).** Canada→USA;
AU/NZ/IL/HK/SG→Europe (so the Europe line = DM − USA − Japan − Canada, no further split
needed); non-modelled EM = 2.297% renormalised away pro-rata (order estimated 2.5–3%) —
this raises the U.S. line most and flatters the proposal; direction disclosed for §8.7.

**The benchmark vector** (percent): USA 68.21, Europe 16.80, Japan 5.21, Taiwan 3.33,
Korea 2.53, China 2.50, India 1.37, Indonesia 0.06. Sums to 100.0000, asserted; every
construction step asserted against the factsheet anchors in code.

**Validation vs the panel's ACWI series (not optional — run, committed as asserts):**

| | Ann. return | Vol | MaxDD |
|---|---|---|---|
| Constructed nine-line, fixed weights | 5.93% | 14.3% | −55% |
| Actual ACWI series (EUR panel) | 5.35% | 14.1% | −52% |

Vol within 0.2pp and drawdown within 3pp — the like-for-like checks pass. The return
gap (+0.58pp p.a.) is **not** a construction error: fixed 31-Aug-2026 weights held over
25 years embed the index's own weight drift (USA ~50%→63.6%), and holding today's
US-heavy weights through a US-winning sample must outperform the actual index. Reported
as ordered rather than reconciled away; the same fixed-weight convention governs
Table 7's rows, so the comparison inside the paper is internally consistent.

## Step 1 — the twelve statistics, old vs new, directions stated

| # | Statistic | Old (stylised benchmark) | New (ACWI) | Direction |
|---|---|---|---|---|
| 1 | Benchmark ER / vol / Sharpe | 5.13% / 14.1% / 0.364 | **4.89% / 14.3% / 0.341** | ER and Sharpe down — more U.S. at 4% |
| 2 | Expected-return advantage | +0.72pp | **+0.965pp** | up — flatters the paper, cause stated (renormalisation + truer U.S. weight) |
| 3 | 30-year terminal wealth | ~23% | **~32%** | up, from (2) |
| 4 | Ex-ante tracking error | 2.83% | **3.73%** | up — gross active weight 46pp → 62pp |
| 5 | Information ratio | 0.25 | **0.26** | **invariant — the robustness result the order hoped for survives: advantage and TE scale together, the case does not depend on the benchmark choice** |
| 6 | No-reversion advantage / IR | +0.218pp / 0.08 | **+0.321pp / 0.09** | advantage up; IR again invariant |
| 7 | Panel (a) benchmark Sharpe (MS-1) | 0.47 | **0.47** | unchanged (coincidence of the 4-region view: 68.2/16.8/5.2/9.8) |
| 8 | Table 6 | 7 Yes / 1 No; US+2pp margin 0.003 | **same pattern**; margins widen (US+2pp 0.452 vs 0.436) | verdicts identical, less razor-thin |
| 9 | Table 7 benchmark row | 8.2% / 13.0% / −50% | **8.5% / 13.2% / −51%**; tilt −0.7pp p.a.; sub-periods +0.3 / −2.3 / +4.8; realised TE 3.7% | benchmark row up, tilt underperformance widens 0.4→0.7pp |
| 10 | A6 decomposition (Eur / Jpn / AxJ) | 0.15 / 0.04 / 0.53 | **0.10 / 0.14 / 0.73** (of +0.965) | Europe's share of the improvement falls to ~10%; Asia incl. Japan carries ~90% — strengthens the "this is an Asia case" reading |
| 11 | §9.8 China comparator | 5.5% benchmark weight | **2.50%**; 6% = **2.4× index** | the "cap" is a large overweight vs the index — see prose flag (a) |
| 12 | §8.3/§9.8 cap cost | 1bp vol, 4bp ER | **7bp vol, 2.7bp ER** (cap-weighted Asian sleeve would hold China at 7.9%; 1.4bp per pp forgone unchanged) | vol cost up (releasing the cap now sheds higher-vol Korea/India weight), ER cost down |

## Step 2 — prose flags for the article chat (flagged, not written)

- **(a)** ACWI China = 2.50%: the 6% position is 2.4× the index weight. §9.8 must name
  its reference point — it binds against the optimiser's 20% and the cap-weighted
  sleeve's 7.9%, and is a 2.4× overweight against the index. (Order's indicative 2.3%
  was slightly low; official panel gives 2.50.)
- **(b)** Japan: benchmark 5.21%, so 12% is **+6.8pp** of active weight, not +2pp.
- **(c)** Asia incl. Japan: **15.0% → 43.0%**, not 25→43. §11.1, §11.4, abstract.
- **(d)** "Familiar magnitude": TE is now 3.73% vs the index. The two-number story
  (Step 3) is the honest defence: 3.7% from the cap-weighted default, 2.8% from where a
  partly-tilted European fund already sits.
- **Abstract check:** modelled EM Asia in raw ACWI = 9.56%; adding the non-modelled
  Asian EM minors (MYS/THA/PHL, inside the dropped 2.30%) plausibly lands near
  10–10.5%. "Less than one-tenth" is no longer safe; **"about a tenth"** is.

## Step 3 — the stylised secondary comparator

The former benchmark vector (60/15/10/5.5/4/3/1.5/1) is retained as an explicitly
stylised "European fund that has already taken part of the step" — defined in the
paper, sourced to nothing because it claims nothing, kept in the model as
`STYLISED_TILTED_EQUITY`. TE of the proposal against it: **2.83%** (gross active 46pp).

## Guards and P6

Both vectors sum to 100.0 (asserted in the CSV consumer and the model). The weights CSV
carries source and as-of date in its header. `test_allocations_match_canonical_2026_09_21`
extended: benchmark = the ACWI vector, proposal unchanged, stylised comparator pinned.
Suite **52 passed**. **P6 confirmed:** the participant simulation adopted the new
benchmark in a single step — `CURRENT_EQUITY` swapped, nothing else touched, full
attribution runs end-to-end (smoke N=100: step (i) falls and the re-anchor marginal
roughly doubles, as (c) implies). The published multi-seed record (`fxr2_*`, `w811_*`)
still reflects the old step (i); a 5-seed N=1000 rerun is required before Exhibit 6
republishes — flagged as the one follow-up, not run here pending the article-side
confirmation this branch waits on.
