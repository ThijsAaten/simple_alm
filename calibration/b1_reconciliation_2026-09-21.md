# B1 reconciliation — one portfolio, one panel (2026-09-21)

Referee response, severity #1. Step-0 ruling (author, 2026-09-21): **the §11
implementation is canonical** — the 10-country vector with the 6% China cap. §8.6/§8.8
are the analysis leading to it; every frontier and risk statistic below is computed on
the implemented country vector from one return panel.

Everything here regenerates from committed code: the canonical vector is
`replication/data/canonical_allocation_2026-09-21.csv` (article repo) and every number
prints from `exhibits/scripts/build_b1_canonical.py` (article repo, branch
`b1-reconciliation`). The panel is the corrected EUR translation built by
`build_ret_eur.py` (FX convention level-anchored in code; 301 months,
2001-04..2026-04). One proxy assumption, stated: Indonesia, Vietnam and Singapore
(6.5pp combined proposed weight) have no country series in the panel; their **risk**
maps to the AsiaExJP column. Their **expected-return** inputs: Table 1a's Indonesia row;
Vietnam and Singapore carry the participant model's judgement drifts (9.0%/6.0%),
flagged non-Table-1a (2.0pp combined weight). Model-repo guard:
`test_allocations_match_canonical_2026_09_21` asserts the participant simulation runs
exactly these vectors (suite **52 passed**, incl. the damping and hash guards).

## 1. The canonical vectors (percent of equity sleeve; both sum to 100.0, asserted)

| | USA | Europe | Japan | China | India | Taiwan | Korea | Indonesia | Vietnam | Singapore |
|---|---|---|---|---|---|---|---|---|---|---|
| Benchmark (ACWI proxy) | 60.0 | 15.0 | 10.0 | 5.5 | 4.0 | 3.0 | 1.5 | 1.0 | 0 | 0 |
| Proposed A (canonical) | 37.0 | 20.0 | 12.0 | 6.0 | 6.5 | 4.5 | 7.5 | 4.5 | 1.0 | 1.0 |

Derived four-region view (a view, not a second definition): benchmark 60/15/10/15
(exact); proposed **37/20/12/31**. The §11.4 grid 37/20/40 is rounding of the canonical
vector (actual Asia incl. Japan = 43.0; the grid's 3pp residual is rounding slack and
must be labelled as such). **§8.6's 35/25/10/30 and §8.8's China-12 split are
superseded as analysis inputs.**

## 2. The Asian aggregate reconciliation (the referee's 7.18%)

Confirmed. Table 1a's country rows applied to the §8.8 split give **7.18%** — the
referee's figure is exactly reproduced. Applied to the canonical Asia-ex-Japan split
they give **7.26%**. The 8.5% regional row is not a weighting error but a different
object: Table 1a's own note says the aggregate row deliberately uses the aggregate CAPE
rather than cap-weighting the country rows. The reconciliation, per the ruling: the
regional 8.5% row remains a Table 1a exhibit, but **no portfolio statistic uses it any
more** — the canonical expected returns aggregate the country rows (7.26% Asian
sub-portfolio), and the prose must stop implying the held portfolio earns the regional
8.5%.

## 3. Old vs new — every manuscript number that moves (direction stated)

Headline input set is Table 1a throughout; §5.1 re-rating inputs appear only as a
labelled sensitivity.

| # | Manuscript number | Published (09-19 master) | Canonical replacement | Direction |
|---|---|---|---|---|
| 1 | §8.6 Panel (b) proposal ER | 6.3% (35/25/10/30, regional inputs) | **5.85%** (country Table 1a) | down — the regional-input flattering goes |
| 2 | §8.6 Panel (b) proposal vol / Sharpe | 14.3% / 0.44 | **14.6% / 0.401** | vol up slightly, Sharpe down |
| 3 | §8.6 Panel (b) benchmark ER / vol / Sharpe | 5.3% / 14.1% / 0.38 | **5.13% / 14.1% / 0.364** | ER and Sharpe down (country granularity) |
| 4 | Active expected-return advantage | 97bp ("33% terminal wealth") | **+72bp** | down ~a quarter; the 33% terminal-wealth sentence must be recomputed |
| 5 | [MS-1] Panel (a) benchmark Sharpe | bracket | **0.47** | — |
| 6 | [MS-2] Panel (a) proposal Sharpe | bracket | **0.45** | **below the benchmark** — under backward-looking means the proposal loses; state it (it is the honest counterpart of Panel (a)'s USA imprint) |
| 7 | [MS-3]/[MS-4] §8.8 anchor vol / Sharpe | bracket (was China-12 split) | **14.6% / 0.401** (canonical vector) | replaces the China-12 illustration |
| 8 | §8.8 cap-constrained tangency (headline now Table 1a) | Eur 40/Jpn 20/Chn 20/Kor 6/Twn 10/Ind 4 (§5.1 inputs) | **USA 10.7/Eur 40/Jpn 20/Chn 20/Ind 8.1/Twn 1.2, Korea 0** (Table 1a); the §5.1 mix becomes the labelled sensitivity | Korea exits the Table-1a tangency entirely; the U.S. re-enters at ~11 |
| 9 | Table 6 verdicts | 6 Yes + 1 No (four-region) | **same pattern** on canonical vectors (Sharpes in script output; US+2pp margin narrows to 0.452 vs 0.449) | verdicts unchanged, margins slimmer |
| 10 | Table 7 counterfactual | benchmark 8.2%/13.0%/−50%; 30%A 7.5%/13.2%/−54%; tilt −0.7pp; TE 2.8%; sub-periods +0.2/−2.0/+3.5 | benchmark unchanged; **proposed 7.8%/13.5%/−54%; tilt −0.4pp; TE 2.8%; sub-periods +0.2/−1.9/+6.0** | tilt underperformance narrows (less China than the 30%A vector); 2025-26 sub-period improves |
| 11 | §11.1 ex-ante TE | ~2.8% | **2.83%** (unchanged; now from the canonical vector) | confirmed |
| 12 | Information ratio | 0.33 (old +0.94% active) | **0.25** (Table 1a +0.72%); no-reversion **0.08** | down |
| 13 | No-reversion advantage | referee: +0.380pp (regional) | regional reproduced **exactly** (6.385/6.765); canonical country-level **+0.218pp** (6.268 vs 6.486) | the referee's own robustness case shrinks further at country level — report both, own both |

## 4. [MS-5]/[MS-6] — §8.9 volatilities, EUR and USD side by side

Old published values validated first: the committed pre-correction series reproduces
§8.9's 20.3/30.7/30.3/33.2 and the decade pairs exactly; "last decade" is pinned as the
trailing 120 months. Replacements (corrected translation; EUR below USD everywhere =
the damping direction, visible not asserted):

| Market | EUR full | EUR last 10y | USD full | USD last 10y | Old published (EUR full → 10y) |
|---|---|---|---|---|---|
| USA | 15.0% | 14.9% | 15.3% | 15.5% | 20.3% |
| China | 23.5% | 21.0% | 25.8% | 23.3% | 30.7% → 27.2% |
| India | 24.2% | 18.7% | 25.9% | 19.6% | 30.3% → 22.7% |
| Korea | 26.9% | 27.2% | 28.8% | 29.6% | 33.2% |
| Japan | 15.3% | 12.7% | 15.7% | 14.4% | 20.8% → (unpub.) |
| AsiaExJP | 18.9% | 15.6% | 21.0% | 18.1% | 26.3% |
| ACWI | 14.1% | 13.2% | 15.7% | 14.7% | 21.6% |

Decade-on-decade sentence: falls for India (24.2 → 18.7), China (23.5 → 21.0) and Japan
(15.3 → 12.7); **rises slightly for Korea (26.9 → 27.2)** — the old sentence's
direction survives for India/China/Japan at lower levels, and Korea must be stated as
the exception (it was 33.2 flat before).

## 5. No-reversion sensitivity (referee-supplied, reproduced in our pipeline)

Per-cell agreement with the referee at the regional level — **exact on all six cells**:
U.S. 5.9, Europe 7.0, Japan 6.4, Asia ex-Japan 7.7; current 6.385%, proposed(35/25/10/30)
6.765%, advantage +0.380pp (≈39% of 0.975pp). Canonical country-level version:
benchmark **6.268%**, proposed **6.486%**, advantage **+0.218pp** — smaller, because the
canonical Asia split holds more of the low-reversion markets. Both are in the committed
script; the manuscript should quote the canonical number and may cite the regional one
as the referee's own computation, confirmed.

## 6. Manuscript passages whose prose must change (for the article chat)

1. §8.6 Panel (b) paragraph — anchor set becomes benchmark vs canonical proposal; ER
   5.85/5.13, vols, Sharpes; the "97-basis-point / 33% terminal wealth" sentence
   recomputed at +72bp.
2. §8.6 [MS-1]/[MS-2] — 0.47 / 0.45, with one honest sentence: under historical means
   the proposal sits below the benchmark; the case is the forward-looking inputs.
3. §8.8 — the China-12 illustration goes; canonical vector becomes the exhibit anchor
   ([MS-3]/[MS-4] = 14.6% / 0.401); Table 1a inputs are the headline frontier, §5.1 the
   labelled sensitivity; Korea's zero weight under Table 1a inputs needs a sentence
   (extends the existing V-C4 Korea reframe).
4. §8.10 Table 6 — re-typeset from canonical verdicts (pattern unchanged); Table 7 row
   for the proposal (7.8/13.5/−54, tilt −0.4pp, sub-periods +0.2/−1.9/+6.0).
5. §8.9 — [MS-5]/[MS-6] from the table above (§8.9 in the committed 09-19 master is NOT
   yet bracketed — the old numbers still stand in prose; they are pre-correction values
   and must be replaced regardless).
6. §11.1 — TE 2.83% confirmed; IR sentence updated (0.25 re-rating, 0.08 no-reversion).
7. §11.4 grid — label as rounding of the canonical vector (43.0 Asia incl. Japan;
   3pp slack).
8. §3.1 Table 1a — add one sentence: the regional Asia-ex-Japan row is an aggregate-CAPE
   exhibit; portfolio statistics use the country rows (canonical Asian sub-portfolio
   7.26%; the referee's 7.18% on the §8.8 split confirmed).

## Deviations from the order, for the record

- `w811-te-sensitivity` was already merged into main and pushed on 10 Sep (order said
  held-unmerged); nothing to merge.
- §8.9 in the committed 2026-09-19 master carries the old volatilities in live prose,
  not [MS-5]/[MS-6] brackets; the replacements above stand either way.
- The §11.4 grid's "40% Asia" rounds 43.0 down by 3pp — larger than rounding; flagged
  in item 7 rather than silently relabelled.

*Scripts: article repo `exhibits/scripts/build_b1_canonical.py` (branch
`b1-reconciliation`) + `replication/data/canonical_allocation_2026-09-21.csv`; model
repo branch `b1-reconciliation`, suite 52. Both branches held unmerged until the
article chat confirms the §8/§11 edits.*
