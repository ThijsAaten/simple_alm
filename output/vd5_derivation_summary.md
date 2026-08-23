# V-D5 — the last four currencies derived, the last FX proxy retired

**`output/vd5_*.csv` are the current exhibit record**, superseding `vm7_*.csv` (kept as the
previous record). `python tools/rerun_multiseed.py 1000 vd5`; five seeds attribution, three
dial, N=1000.

## What changed

The CHF/CAD/AUD/NZD legs in `data/fx_bloomberg_legs.csv` were run through the standard joint
regression (`calibration/fx_loading_calibration.py`, window 2001-03..2026-04):

| ccy | b_usd | resid_g (t) | infl | growth | global | was |
|---|---:|---:|---:|---:|---:|---|
| CHF | 0.170 | −0.042 (−1.8) | **0.10** | **−0.05** | **−0.05** | −0.30 / −0.50 / 0.00 (judgement) |
| CAD | 0.400 | +0.259 (+10.4) | **0.20** | **−0.10** | **+0.15** | 0.20 / +0.10 / 0.00 (judgement) |
| AUD | 0.012 | +0.341 (+11.4) | **0.00** | **0.00** | **+0.20** | 0.10 / +0.20 / 0.00 (judgement) |
| NZD | −0.022 | +0.301 (+8.8) | **0.00** | **0.00** | **+0.20** | absent — AUD proxied it |

NZD's idio_vol is measured (9.4% annualised); its carry/drift/PPP parameters are judgement,
marked. The NewZealand sovereign sleeve now points at NZD. The model has **16 currencies,
zero proxies, zero negative loadings**; the calibration script reproduces all three columns
for all sixteen, and the guard-set exceptions in the tests are now empty.

Three findings worth keeping: CHF's notorious −0.30 was wrong in sign but its *comment* was
right all along — the data gives +0.10. CAD and AUD had global-cycle exposure sitting in the
euro-growth column, the defect the 2026-08 rounds fixed everywhere else. And AUD/NZD are
near-identical pure-cycle currencies from a EUR seat (zero dollar-beta, +0.20 global), so the
retired proxy was benign — a conclusion now measured, not assumed.

## Measured effect — nothing beyond seed noise

| Step | World | vm7 | vd5 | t |
|---|---|---:|---:|---:|
| (ii) +Re-anchor | Baseline | +101.8 ± 3.0 | +102.2 ± 6.8 | 0.11 |
| (iii) +China cap | Baseline | +2.5 ± 4.7 | +2.9 ± 2.5 | 0.18 |
| (iv) +Bond side | Baseline | +31.9 ± 3.9 | +32.9 ± 1.0 | 0.59 |
| (ii) +Re-anchor | Repression | +72.1 ± 2.1 | +73.9 ± 2.8 | 1.10 |
| (iii) +China cap | Repression | +1.0 ± 3.0 | +0.3 ± 1.3 | −0.42 |
| (iv) +Bond side | Repression | +52.1 ± 3.6 | **+52.1 ± 1.5** | **0.00** |
| CGB Δ(5%) | Baseline | −2.95 ± 1.07 | −3.02 ± 1.54 | — |
| CGB Δ(5%) | Repression | +4.96 ± 0.94 | +4.92 ± 1.90 | — |

Levels shifted a few thousand (−5.7k baseline Current): mechanical — adding a 16th currency
to the FX model changes every currency's draw sequence. Deltas are the meaningful object and
none moved. The step V-D5 sat inside — the bond overlay under repression — moved by +0.0k.
