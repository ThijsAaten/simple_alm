# Singapore added to the panel — the rounding edge flips to 97bp (2026-09-22)

Branch `singapore-panel` in both repos from the merged mains. Data:
`replication/data/msci_singapore_2026-09-22.csv` (article repo) — NDDUSG Index net TR
USD + EURUSD spot, 302 monthly levels 2001-03..2026-04, full sourcing header kept.
Suite **52 passed** before this note.

## The headline first, because it is the point of the exercise

**The advantage is 96.91bp. The paper's headline becomes 97 basis points.** It stood at
96.49bp (prints 96); breaking Singapore out moves it +0.42bp across the rounding edge.
Everything downstream moves together: the abstract, §8.6, §9.8's "of the ninety-six",
§11.1, §11.4.

## What was done

1. **Panel**: `build_ret_eur.py` adds Singapore as its own line, translated in code
   (EUR level = USD level / USD-per-EUR), with asserts: 301 returns on the exact panel
   index; the CSV's EURUSD reconciled against the panel FX series; and the frozen
   series anchors **18.48% EUR / 20.35% USD** realised vol (damping direction visible —
   the V-C4 check), so a pipeline change cannot silently alter the series.
2. **Benchmark**: Singapore out of the Europe fold at its raw ACWI weight, **0.4006%**
   (MSCI Singapore factsheet cap USD 416,825.83mn at 31 Aug 2026 / ACWI cap
   104,043,110.63mn — the same official-factsheet route as B5-0), renormalised as
   before; benchmark line 0.4100 after renormalisation, sums asserted at 100.0.
   Rule 2 now reads AU/NZ/IL -> Europe with **Hong Kong still folded there — flagged**:
   it is the remaining Asian developed market mapped to Europe; HK's ACWI weight is
   materially larger than Singapore's, so the same argument applies with more force,
   and it is the natural next break-out if the article wants the mapping fully clean.
3. **Proposal**: the 1.0% Singapore line now takes its own risk (PROXY_COL entry
   removed). Weights unchanged. The remaining proxy assumption is Indonesia + Vietnam
   (5.5pp combined), and Vietnam alone still carries a non-Table-1a return input —
   the R3 input-mixing disclosure survives, shrunk, exactly as the order states.

## Old vs new, direction stated (old = the 09-22d published set)

| Statistic | Old | New | Direction |
|---|---|---|---|
| Benchmark ER / vol / Sharpe | 4.89% / 14.3% / 0.341 | 4.88% / 14.3% / 0.340 | ER −1bp (SG's 6.0% enters below Europe's 7.0%) |
| **Advantage** | **96.49bp (prints 96)** | **96.91bp (prints 97)** | **up, across the edge — headline flips** |
| Ex-ante TE | 3.73% | **3.67%** | down 6bp (own series + both-sides consistency; slightly beyond the old Q5 bound, which priced only the benchmark side) |
| Information ratio | 0.26 | 0.26 (0.259 → 0.264) | invariant |
| 30y terminal wealth | 32% | 32% | unchanged |
| No-reversion advantage / IR | +0.321pp / 0.09 | +0.325pp / 0.09 | up a hair |
| A6 (Eur / Jpn / AxJ) | 0.096 / 0.136 / 0.733 | 0.108 / 0.136 / 0.725 | Europe +1.2bp (its active weight rose as SG left the fold), AxJ −0.8bp |
| Table 6 | 7 Yes / 1 No | same verdicts, margins within 0.002 | unchanged |
| Table 7 benchmark row | 8.5 / 13.2 / −51; realised TE 3.7% | same at 1dp; realised TE **3.6%** | TE down with ex-ante |
| Within-Asia selection | 13.2bp = 13.7% (mix 6.83%) | **14.2bp = 14.7%** (mix 6.80%) | up — ACWI's Asian mix now carries SG at the lowest non-Taiwan input; asserts re-pinned |
| China cap, ER cost | 2.7bp (cap-weighted share 7.9%) | **2.3bp (share 7.6%)** | down — SG dilutes China's share of the benchmark sleeve |
| China cap, sleeve-vol cost (§9.8) | 16.0bp (19.74 vs 19.58, var-min ~10.0%) | **14.1bp (19.59 vs 19.45, var-min ~9.7%)** | down; portfolio-level 27.6 → 26.4bp |
| Panel (a) benchmark Sharpe [MS-1] | 0.4735 | **0.4743** | third decimal again; prints 0.47 |
| Stylised comparator TE | 2.83% | **2.78%** | still prints "2.8%" |

The old Q5 materiality bound is retired from the script (superseded by the exact
recomputation); step-0 validation vs the actual ACWI series re-run under the new
construction: vol 14.3% vs 14.1%, maxDD −55% vs −52% — unchanged conclusions.

## Exhibit 6 — demonstrated, not asserted

Model `CURRENT_EQUITY` revised in a single step (Europe 16.7969 → 16.3869, Singapore
0.4100 in; canonical guard test re-pinned; suite 52). Impact on the published `acwi6`
record, measured at seed 42, N=1000, both worlds: step (i) moves **+0.10k baseline /
+0.71k repression** — under 0.08% of the pot and an order of magnitude inside
five-seed noise (the China-cap step itself is ±2.9k). The `acwi6` record therefore
stands for Exhibit 6 at its stated precision; a reseed under the revised vector is
optional hygiene for the next natural rerun, not a correction.

*Both `singapore-panel` branches held unmerged pending the article chat's §8.7/§9.8/
headline sweep (96 -> 97 touches the abstract, §8.6, §9.8, §11.1, §11.4).*
