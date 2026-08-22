# What the CGB dial costs at 0%

`examples/run_cgb_dial.py`, N = 1000 paths, seeds as in `examples/run_attribution.py`.
CGB weight taken from the EUR core; developed (10%) and EM (10%) overlay blocks held
fixed; equity at PROPOSED A. Pot = median real pension pot at retirement, entry-year
EUR (€000). LHP vol / real return are the LHP sub-portfolio's own annual statistics over
the accumulation window. Raw data: `output/cgb_dial_sweep.csv`.

**Superseded numbers.** An earlier version of this note was produced before three fixes
landed (2026-08): the FX model was being advanced twice per simulated year, CGB's
long-run yield was pinned at its 1.8% initial level, and CNY's `inflation_loading` was
0.10 instead of 0.45. All figures below are post-fix. The headline conclusion changed:
under repression the line is no longer a cost.

| World | CGB w | median | Δ vs 0% | p5 | p25 | p75 | p95 | LHP vol | LHP real |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0% | 1362k | — | 1039k | 1226k | 1550k | 1820k | 13.54% | 2.80% |
| baseline | 1% | 1360k | −1.9k | 1040k | 1225k | 1548k | 1814k | 13.38% | 2.80% |
| baseline | 2% | 1358k | −3.5k | 1039k | 1224k | 1544k | 1809k | 13.22% | 2.79% |
| baseline | 3% | 1357k | −4.9k | 1039k | 1224k | 1541k | 1803k | 13.05% | 2.78% |
| baseline | 5% | 1355k | −6.3k | 1043k | 1224k | 1535k | 1793k | 12.73% | 2.78% |
| repression | 0% | 1087k | — | 851k | 977k | 1211k | 1394k | 14.80% | 2.07% |
| repression | 1% | 1087k | −0.2k | 852k | 977k | 1209k | 1392k | 14.62% | 2.07% |
| repression | 2% | 1087k | +0.0k | 852k | 978k | 1208k | 1390k | 14.44% | 2.08% |
| repression | 3% | 1087k | +0.4k | 853k | 979k | 1208k | 1390k | 14.27% | 2.08% |
| repression | 5% | 1087k | +0.4k | 856k | 980k | 1206k | 1388k | 13.94% | 2.08% |

Δ(5% vs 0%) across 3 seeds, to separate signal from Monte Carlo noise:

| Calibration | baseline Δ | repression Δ |
|---|---:|---:|
| 1.8% → 2.3% long-run (as calibrated) | −6.15k ± 0.10k | +1.53k ± 1.07k |
| 1.8% flat long-run (downside sensitivity) | −7.87k ± 0.15k | +0.25k ± 0.92k |

## Is the 0% default costing anything?

**In the baseline world, no — holding CGB costs, and that cost is precisely measured.**
−6.15k ± 0.10k of median pot at a 5% weight (−0.45%). The common-random-number pairing
across weights makes this one of the tightest estimates in the model; the sign is not in
doubt.

**Under repression the picture has flipped: the line is now free, possibly mildly
positive.** +1.53k ± 1.07k at 5%. With three seeds that is suggestive of a genuine small
gain rather than proof of one — the honest reading is **zero to mildly positive**, where
before the fixes it was a clear −2.4k cost. The 0% default is therefore forgoing a hedge
that costs nothing in the world it hedges against, and ~6k of baseline median to hold.

**The left tail improves in both worlds.** p5 rises monotonically with weight: +4k
baseline, +5k under repression. Under repression the p5 gain exceeds the median give-up
at every weight; at baseline it does not.

## Does the 0.10 pass-through beta do its job?

**Yes, and the case is now about the gap narrowing rather than absolute protection.**
Standalone (N=300), the CGB sleeve earns **+0.95% real** at baseline and **+0.79% real**
under repression. Both are positive: the sleeve does keep pace with EUR inflation. That
comes mostly from the unhedged CNY leg, not the 1.8% local carry.

What it does not do is out-earn what it displaces. The EUR core returns 2.22% real at
baseline and 1.34% under repression, so CGB gives up **127bp at baseline and 55bp under
repression** — the gap more than halves when repression hits. That narrowing is the
conditional-value case, and it is what the article should claim.

On the volatility axis the trade is now strictly favourable under repression: −86bp of
LHP vol for **+1bp** of LHP real return, versus −81bp for −2bp at baseline. Under
repression, adding CGB improves both axes at once.

## Linearity and a defensible weight

Baseline cost is close to linear (≈ −1.3k per pp) with no inflection through 5%. Under
repression the median is flat-to-rising across the whole range while p5 keeps climbing,
so nothing in this range marks a point where CGB stops helping. The binding constraint
is entirely the baseline world.

**2–3% remains the defensible range, and the basis is now stronger.** At 3%: baseline
−4.9k, repression +0.4k, p5 up in both worlds, LHP vol −49bp. The trade is roughly "pay
~5k of baseline median to hold a repression hedge that is free-to-positive in the world
it hedges." Above 3% the baseline cost keeps accruing linearly while the repression gain
flattens, which is what caps it rather than any change in sign.

## Caveats

1. **The reversion assumption matters for the baseline cost, not the conclusion.** The
   flat-1.8% downside sensitivity widens the baseline cost from −6.15k to −7.87k and
   pulls the repression gain from +1.53k to +0.25k. The qualitative result — costs at
   baseline, free under repression — survives both calibrations. The 2.3% long-run yield
   is worth roughly 50bp of annualised real return on the sleeve.
2. **CNY at `inflation_loading = 0.45` cuts both ways.** The RMB now inherits ~90% of the
   dollar's response to EUR inflation, which is what makes CGB useful under EUR
   repression. The same correlation means the RMB offers little diversification *away
   from* the dollar. The article should not claim both.
3. **The pot metric is a weak instrument for this dial.** The cohort glide path holds 0%
   LHP until age 45 and averages 15.1% over accumulation, so 5% of LHP is 0.76% of
   time-averaged assets. Median deltas are necessarily small; the LHP-level statistics
   carry the signal.
4. **LHP returns are not exposed by the model.** `ParticipantResult` carries no
   sub-portfolio return series. The script captures the LHP return from inside the real
   run by instrumenting `SubPortfolio.step`, re-validated after the FX fix to reproduce
   `pot_path` exactly (rel. error 0.0).
5. **Still-open FX inconsistencies.** HKD (+0.10) is a hard USD peg and should plausibly
   sit near USD's +0.50; KRW and THB carry *negative* inflation loadings that sit oddly
   with their risk-on growth loadings. Flagged in `assets/fx.py`, not changed.
