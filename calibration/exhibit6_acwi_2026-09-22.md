# Exhibit 6 reseed under the ACWI benchmark, and three queries resolved (2026-09-22)

Model commit `e402850` (branch `exhibit6-acwi`, from `b5-benchmark-acwi`), seeds
[42, 137, 271, 314, 577], N=1000, both worlds. Record: `output/acwi6_attribution.csv`,
`acwi6_pot_distributions.csv`, `acwi6_cgb_dial.csv`. Suite **52 passed** before this
note. t-statistics are mean/SE across the five seeds, as in the existing record.

## 1. The reseed

**Invariance, proven not assumed:** steps (ii)-(iv) and the entire CGB dial are
byte-identical to the `fxr2_*` record (max diff 0.000k) — they never touch the
benchmark. Everything §11.3 quotes that moved, moved through step (i) only.

| Quantity | Published (§11.3) | Replacement (acwi6) | Direction |
|---|---|---|---|
| Step (i) median real pot | 1,246.1k / 895.5k | **1,214.0k / 873.2k** | down — ACWI holds more U.S. |
| Equity re-anchoring | "on the order of 8%" both worlds | **+11.1% baseline / +11.0% repression** (+134.3k t=36.7; +96.1k t=80.1) | up by ~a third |
| China cap step | +2.5k / +1.0k, t≈1.2 / 0.7 | **+2.9k t=2.6 / +0.3k t=0.6** | see note below |
| Unrepressed sovereign allocation | +2.5% / ~6% | **+2.4% / +5.4%** (+32.9k t=76.2; +52.1k t=78.2) | unchanged in substance (benchmark-independent; sharper rounding) |
| Full proposal | +11% / +14% | **+14.0% / +17.0%** (+170.1k t=57.2; +148.5k t=97.1) | up |
| Step-vs-ramp note figure | 4.6% vs 5.8% | **unchanged** | benchmark-independent, proven by the invariance check |

**China-cap note:** the published +2.5k/+1.0k (t 1.2/0.7) were vm7-era values; the
step itself did not move in this reseed (identical to fxr2), so the published figures
were already stale before B5-0 — the fx-derivation round had moved them to +2.9k/+0.3k
and §11.3 was never refreshed. Direction stated: the baseline step strengthens
(t 2.6), the repression step weakens to noise (t 0.6).

**Prose flag (flagged, not written):** the re-anchoring is now +11% in both worlds and
carries **79% of the full baseline improvement** (134.3k of 170.1k). "The equity
re-anchoring is the dominant lever… on the order of 8%" needs rewriting as a stronger
claim, and the three-results paragraph re-drafted rather than renumbered. **Retraction
of my own earlier flag:** the smoke test's "roughly doubles" did not survive N=1000 —
8.2% → 11.1% is a rise of about a third; the doubling was N=100 noise.

Panel (b) distributions: `acwi6_pot_distributions.csv` carries the Current rows under
ACWI (lower medians, wider gap to Proposed A); Proposed A rows identical to fxr2.
Exhibit 6 rebuilds article-side from this record after merge.

## 2. Query — the China cap's volatility cost: the published 1bp does not reproduce

Computed in `build_b5_acwi_benchmark.py` (article repo), funding rule stated: China
varied, released weight redistributed **pro-rata across the other Asian lines**,
non-Asian weights untouched; committed panel, committed vectors.

| Metric | At 6% cap | Minimum | Var-min China weight | Cap cost |
|---|---|---|---|---|
| Asian-sleeve volatility | 19.74% | 19.58% | ~10% of the equity sleeve | **16bp** |
| Portfolio volatility | 14.58% | 14.30% | ~21% | 28bp |

The published pair (19.11% vs 19.10%, 1bp) **does not reproduce** from the committed
pipeline under any comparator we can construct — it was a scratch calculation with no
committed builder, and the paper has published it; said directly, as ordered. What
survives of it: the variance-minimising China weight (~9-10% of the equity sleeve) is
confirmed. The B5-0 note's **7bp is also retired** — it compared 6% against the
cap-weighted share (7.9%), a third comparator, mislabelled as the cap's cost; the
number was arithmetic-correct but answers a different question. **The sound figure for
§9.8's metric (sleeve volatility against the variance minimum) is 16bp** — sixteen
times the published value, still economically small, and the honest sentence is
19.74 vs 19.58. Portfolio-level (28bp) reported alongside for completeness; which
level the paper quotes is an article-side choice, but 19.11/19.10 must go either way.

## 3. Query — Panel (a) benchmark Sharpe, four decimals

| Vector | ER | Vol | Sharpe |
|---|---|---|---|
| Old stylised 60/15/10/15 | 6.6346% | 14.0723% | **0.4715** |
| New ACWI 68.21/16.80/5.21/9.79 | 6.7382% | 14.2307% | **0.4735** |

It moves at the third decimal (+0.0020): more U.S. raises the historical-mean ER by
more than the vol rises. At the paper's two-decimal precision both print 0.47; per the
order's rule, the paper should carry **0.4735 → 0.47**, and if any passage quotes three
decimals, 0.474.

## 4. Within-Asia selection decomposition — now computed and asserted

In `build_b5_acwi_benchmark.py`, asserted against the scratch values: proposal Asian
sleeve **7.26%** vs the ACWI Asian mix **6.83%** (34% Taiwan at the lowest Table 1a
row, 26% China), a **+0.43pp** selection effect on the 31% sleeve = **13.2bp = 13.7%**
of the advantage. Against the old stylised comparator the same decomposition gives
**1.7bp** (its Asian mix, 7.20%, sat close to the proposal's) — recorded: the figure is
strongly benchmark-dependent.

## 5. Singapore mapped two ways — bounded by computation

Breaking Singapore out of the benchmark's Europe line into an own Asian-risk line at a
bounding raw-ACWI weight of 0.3-0.5% moves: benchmark ER by **-0.3 to -0.5bp**,
the advantage by **+0.3 to +0.5bp**, and TE by **-2.6 to -4.4bp** (3.73% → 3.69% at
worst). Every published figure is quoted at 0.1pp / whole-bp granularity, so this is
demonstrated immaterial — with one rounding edge worth knowing: at the top of the bound
the 96bp advantage prints as 97bp. Full consistency = an MSCI Singapore series added to
the panel plus a benchmark line and a pipeline rerun — one Bloomberg pull (MXSG net TR,
monthly, 2001-2026) and roughly an hour; it would move nothing above the rounding edge.

*Both `exhibit6-acwi` branches held unmerged pending the article chat's §11.3/§9.8
rewrite; the `b5-benchmark-acwi` model branch is contained in this one.*
