# W8.11 sensitivity, ex-ante TE, and the €100bn translation — 2026-09-10

Run on branch `w811-te-sensitivity` from `main` at `107c0d6` (post fx-loadings-round2).
Committed calibration untouched throughout: the +3pp variant is a run-config override,
sha256-guarded in `tools/run_w811_sensitivity.py` and in
`tests/test_invariants.py::test_w811_vol_variant_leaves_committed_calibration_unchanged`.
**Test suite: 50 passed** (49 committed + the new calibration-hash guard).

---

## ⚠ Finding first: the §8.6 covariance appears to be built on an inverted FX translation

Validating the frontier construction against the published anchors exposed a discrepancy
that is reported here rather than reconciled silently. The published §8.6 figures
(Current 5.3% at **20.9%** vol, Sharpe 0.26; 30% Asia 6.3% at **22.0%**, Sharpe 0.29) are
reproduced almost exactly only when the EUR translation applies the FX factor **the wrong
way round** (`u_t/u_{t-1}` instead of `u_{t-1}/u_t`, `u` = USD per EUR): that construction
gives 20.7% / 21.8%, Sharpes 0.258 / 0.289. The **correct** EUR translation of the same
committed data (`data/ret_usd.csv` × `data/fx_levels.csv`) gives **14.1% / 14.3%**,
Sharpes 0.378 / 0.441. The inversion strips out the natural equity–dollar damping a EUR
investor gets (the dollar strengthens in equity selloffs) and inflates every regional vol
by roughly 5pp. Under the correct translation the proposal's story *improves*: the vol
gap between 30% Asia and Current shrinks from 1.1pp to 0.2pp and the Sharpe margin widens.
Panel (a)'s 100%-USA Sharpe of 0.46 and Table 6's existing rows rest on the same
`ret_eur.pkl` and would move with a correction. **The W8.11 verdict below holds under
both constructions**, so the row is usable either way; correcting §8.6 itself is an
article-side decision (candidate W8 item).

---

## 1. W8.11 — Asian volatility +3pp

### Frontier row (article Table 6 format)

| Scenario (vs §8.6 forward inputs) | Tangency Asia weight | 30%-Asia still beats Current? |
|---|---:|:---:|
| Asian volatility +3pp (published covariance construction) | 87% | Yes |
| Asian volatility +3pp (correct EUR translation) | 40% | Yes |

Method: Asia ex-Japan row/column of the historical covariance scaled so its vol rises
3pp absolute (26.1%→29.1% published construction; 18.9%→21.9% correct), correlations
unchanged; forward means USA 4 / Europe 7 / Japan 6 / AxJ 8.5 (% nominal EUR); long-only
tangency; Sharpe = ER/vol (rf = 0, matching the published 0.26/0.29).

**Frontier-point sentence:** under +3pp Asian volatility, the 30%-Asia allocation remains
inside the acceptable region — it still beats Current on Sharpe by +0.026 (published
construction: 0.278 vs 0.253) or +0.049 (correct translation: 0.418 vs 0.369), a margin
of roughly 10–13% of the Current Sharpe in either construction.

### Participant simulation (5 seeds × N=1000, both worlds, p50 real pot, EUR000)

All Asian equity sleeves (committed `ASIA` set, **incl. Japan**: JPN, CHN, IND, KOR,
TWN, IDN, VNM, SGP) at total vol +3pp absolute via idio override
(`sqrt((mbeta·σF)² + idio_new²) = total + 0.03`; market betas, hence absolute cross-sleeve
covariances, unchanged). Seeds [42, 137, 271, 314, 577]. Unperturbed reference =
committed record `output/fxr2_attribution.csv` (numerically identical to `vd5_*`; note
the vm7 record quoted in the task brief — 1,252k/899k — predates the fx-derivation round;
the current committed record is 1,246k/896k for step (i)).

| Allocation | World | Unperturbed | +3pp Asian vol | Δ | Δ per seed |
|---|---|---:|---:|---:|---|
| Reference mix (i) | baseline | 1,246.1k | 1,243.8k | **−2.3k** | −2.1/−3.1/−1.0/−1.4/−4.0 |
| Reference mix (i) | repression | 895.5k | 892.5k | **−2.9k** | −2.8/−2.0/−3.7/−3.5/−2.7 |
| Proposed A + bond side (iv) | baseline | 1,384.1k | 1,373.9k | **−10.2k** | −10.7/−6.3/−6.9/−12.6/−14.5 |
| Proposed A + bond side (iv) | repression | 1,021.7k | 1,015.8k | **−5.9k** | −4.7/−7.0/−4.7/−5.8/−7.4 |

The full-package advantage (iv)−(i) compresses from **+138.0k to +130.1k** at baseline
and **+126.3k to +123.3k** under repression — a 4–6% haircut on the advantage, which
survives with a wide margin. Record: `output/w811_asia_vol3pp_attribution.csv`
(calibration sha256 `757c97b15a855a75…` unchanged, printed by the run).

---

## 2. Ex-ante tracking error and active return — Proposed A vs ACWI proxy

**ACWI proxy**: the committed `CURRENT_EQUITY` (documented in `allocations/mosaic.py` as
the approximate MSCI-ACWI-benchmarked sleeve) — no separate benchmark vector exists in
the calibration, so no ACWI = World + EM construction was needed. Active weights
(Proposed A − proxy): USA −23, Europe +5, Japan +2, Korea +6, India +2.5, China +0.5,
Taiwan +1.5, Indonesia +3.5, Vietnam +1, Singapore +1 (pp).

| Quantity | Value | Basis |
|---|---:|---|
| **Ex-ante TE** | **2.83%** | historical EUR-translated (correct) country covariance 2001-03..2026-04; IDN/VNM/SGP mapped to the AsiaExJP column (their country series are not committed; combined active weight 4.5pp) |
| TE, cross-check | 1.60% | model factor covariance ββ′σF² + diag(idio²), local currency, exact sleeves — lower because it carries no FX term and no cross-idio correlation |
| Active return (a) re-rating view | **+0.94%** | model central expected returns incl. FX tailwind (6.13% − 5.19%, `allocations/preview.blended`) |
| Active return (b) Asia exJ ER −2pp | **+0.62%** | the harshest single-adverse row of Table 6 applied at country level (Asia ex-Japan drifts −2pp, Japan unchanged); −1pp variant: +0.78% |
| **IR (a)** | **0.33** | 0.94 / 2.83 (model-cov basis: 0.59) |
| **IR (b)** | **0.22** | 0.62 / 2.83 (−1pp variant: 0.28) |

**Sanity anchor:** the ex-ante TE of 2.83% matches the historical counterfactual's 2.8%
almost exactly. This is closer than one should expect — the counterfactual holds the
four-region 30%-Asia mix while this is the ten-sleeve Proposed A — but both are dominated
by the same single bet (US −23pp against Asia), so the agreement is genuine rather than
coincidental in sign and order. The TE is also **insensitive to the FX-inversion finding
above** (2.83% under either translation, verified): the FX factor is common to both
portfolios and the active weights sum to zero, so it nearly cancels in the difference —
the inversion distorts portfolio *levels* of vol, not the active-risk number.

---

## 3. Welfare-loss euro translation (€100bn fund, optional-use)

From the committed attribution record (`fxr2_attribution.csv`, no new simulation): the
p50 real terminal pot of the full proposal (step iv) exceeds the current mix (step i) by
**+11.1% at baseline** (1,384.1k vs 1,246.1k; +14.1% under repression). Scaled linearly
to a €100bn fund:

> **≈ €11bn** additional expected terminal wealth at baseline (≈ €14bn under repression)
> over the 43-year accumulation horizon, in entry-year real terms.

Assumptions: participant-level p50 ratio applied one-for-one to fund AUM (same glide
path, contribution schedule and liability structure for every euro of the fund); real,
entry-year euros; median not mean; equity-only version (step iii vs i) would be +8.4% ≈
€8.4bn. The register question on whether the article uses this number is still pending —
computed from existing runs only, as instructed.

---

*Scripts: `tools/run_w811_sensitivity.py` (simulation variant, hash-guarded),
`tools/compute_te_frontier_w811.py` (frontier row, TE/IR, both covariance
constructions). Seeds [42, 137, 271, 314, 577]; N=1000; suite 50 passed.*
