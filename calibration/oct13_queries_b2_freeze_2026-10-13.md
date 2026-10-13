# Six queries answered; B2 frozen (2026-10-13)

Part 1 answers each carry the committed builder that produced them; Part 2 freezes B2 on
the reconciled numbers with an explicit clean-clone reproduction. Suite **52 passed**.

## Part 1 — the six queries

**Q1 — §9.8 tail correlations: pre-correction throughout, except the headline claim,
which survives.** Builder: `exhibits/scripts/build_oct13_queries.py` on the current EUR
panel. China–Europe unconditional: full sample **0.49** (= Tables 4/5), post-2017
**0.24** — the published "0.60 unconditionally" is USD-era/pre-correction residue.
Worst-decile-of-European-months conditional, post-2017 (n=11): **−0.05** — the section's
most striking figure, −0.06, survives the correction almost exactly. Full-sample
worst-decile (n=30): **+0.33**, replacing the published 0.61. Direction, stated plainly:
the tail-decoupling *claim* stands, but its published *contrast* (−0.06 against 0.60)
overstates — the honest pair is **−0.05 against 0.24**, and the full-sample tail anchor
falls from 0.61 to 0.33. The paragraph reads less dramatic once corrected; the
conclusion (China is the sleeve's post-2017 tail diversifier, capped anyway for custody
reasons) is unchanged.

**Q2 — §9.2's impossible pair: resolved; the fall is larger, not smaller.** Same
builder, one run. Sub-period simple correlations China–US: pre-2017 **0.54**, post-2017
**0.21**, full sample **0.42** — the full-sample figure now sits properly between its
sub-periods. (Rolling-mean form, if the prose prefers it: 0.50 → 0.35; end-2016 rolling
reading 0.44, latest 0.03.) The published 0.77→0.53 is pre-correction. Direction: the
pre/post fall widens from 0.24 to 0.33 — the paper's pre-specified test comes out
*stronger* under the corrected panel.

**Q3 — Table 6 US+2pp cell: confirmed, not corrected.** Builder:
`build_oct13_queries.py` (same machinery as `build_b5_acwi_benchmark.py`). Proposal
**0.4528**, benchmark **0.4354**, margin +0.0174. The published 0.452/0.436 was restated
correctly after the re-anchor, and it remains the narrowest margin in the table.

**Q4 — §8.11 payout loadings: confirmed from the factor builder.** Builder:
`run_factor_decomposition_v2.py` → `results/W47v2_primary.csv`, `W47v2_split.csv`
(rerun on the current panel). Asia-ex-Japan net-payout loading: full sample **−0.60
(t −3.69)**; 2001–2016 **−0.732 (t −3.56)**; 2017–2025 **−0.658 (t −2.69)** — exactly
the published triple. Both sub-periods sitting outside the full-sample figure is
genuine, not an error: sub-period regression loadings are not a convex combination of
the full-sample loading when factor variances differ across regimes, as they do here.

**Q5 — the three drawdowns: all confirmed; the windows differ, as suspected.** Builder:
`build_oct13_queries.py`. Constructed benchmark, **2001-04..2026-04**: **−55%** (the
§8.7 validation window — it contains the 2001–02 bear market *and* the GFC). Actual
ACWI series, same window: **−52%**. Constructed benchmark, **2004-01..2026-04** (Table
7's window): **−51%** — GFC only. The text can state the window difference in one
clause.

**Q6 — Table 6a: Asia-ex-Japan column confirmed; two 1bp corrections on the U.S. side.**
Builder: `build_oct13_queries.py`, from the actual vectors. The inferred active weight
is **+20.8037pp** ("roughly 21" was right; per 0.1pp of dilution = 2.08bp). AxJ rows
confirmed exactly: 86.51 → **87**, 76.11 → **76**, 65.71 → **66**. U.S. rows: 106.27 →
**106** ✓, 128.12 → **128** ✓, but 1.0% shrinkage is **112.52bp, which prints 113, not
112**; and both-adverse (1.0%/1.0%) is **91.71bp, which prints 92, not 91** — the
published cells rounded components before summing. IRs as published (0.29/0.31→0.31 at
113/0.35; 0.24/0.21/0.18; both-adverse 0.25). **Tracking error invariance confirmed and
asserted in code: 3.6672% in every row** — the perturbation touches expected returns
only, so the IR column is safe.

## Part 2 — B2 frozen

- **Merges:** both `b1-reconciliation` branches were already in their mains (21 Sep);
  `singapore-panel` now merged in both repos. One clean-up this surfaced:
  the singapore round's PROXY_COL change had silently enlarged Exhibit 5's universe and
  broke `build_b1_canonical.py` on a clean clone — caught by this freeze's reproduction
  run (its purpose), fixed by pinning the exhibit universe to its caps dict so a panel
  addition can never again alter a published exhibit as a side effect.
- **Pins** (manifest, freeze section): seeds 42/137/271/314/577 (dial 42/137/271),
  N=1000, placebo seed 20260909, panel anchors asserted (EURUSD levels; Singapore
  18.48%/20.35%). Tags `b2-freeze-2026-10-13` in both repos.
- **Clean-clone reproduction, explicit:** both repos cloned fresh into a scratch
  directory; model-clone suite **52 passed**; `bash replication/run_all.sh` with
  `SIMPLE_ALM` at the model clone ran **end-to-end, exit 0, zero warnings**; and the
  clone's own output reproduces every frozen statistic: benchmark **4.88 / 14.3 /
  0.340** (4dp: 4.8814/14.3452/0.3403), proposal **5.85 / 14.6** (5.8505/14.5561),
  advantage **96.91bp**, TE **3.67%** (3.6672), IR **0.26**, no-reversion **6.160 /
  6.486, IR 0.09**, A6 **0.108 / 0.136 / 0.725**, selection **14.2bp**, China cap
  **2.3bp ER / 26.4bp portfolio-vol** (vs the variance minimum).
- **One figure moves against the frozen list as supplied, favourably, stated:** the
  proposal Sharpe is **0.4019 and prints 0.402**, not 0.401 — the Singapore round moved
  it 0.4015 → 0.4019 across the rounding boundary; the list's 0.401 was the
  pre-Singapore value.

Every query answer above has a committed builder; none required reconstruction from
scratch values, though two published §9.8/§9.2 figures (Q1's 0.60/0.61, Q2's 0.77/0.53)
had no builder and are confirmed as pre-correction residue now replaced by built values.
