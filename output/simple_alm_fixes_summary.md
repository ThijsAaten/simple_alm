# Three fixes: FX stepping, CGB calibration, FX inflation loadings

Worked 2026-08. All figures N = 1000 paths. Where a number is quoted with `± x`, it is
the standard deviation across 5 independent seeds (3 for the CGB dial), so that
Monte-Carlo noise can be told apart from an actual change. Test suite: **17/17 pass**.

---

## Before/after attribution — Exhibit 6 waypoints

Marginal contribution Δ at each step, €000 of median real pot, **5 seeds**:

| Step | World | Pre-fix | After Item 1 | After all three | Item 1 moved | Items 2+3 moved |
|---|---|---:|---:|---:|---:|---:|
| (ii) +Re-anchor | Baseline | +166.4 ± 1.5 | +171.0 ± 1.9 | +172.4 ± 4.4 | **+4.6** | +1.4 (noise) |
| (ii) +Re-anchor | Repression | +125.9 ± 2.0 | +128.9 ± 1.9 | +133.7 ± 1.4 | **+3.0** | **+4.8** |
| (iii) +China cap | Baseline | −2.7 ± 1.5 | −2.6 ± 1.0 | −2.6 ± 0.4 | 0.0 | 0.0 |
| (iii) +China cap | Repression | −2.2 ± 1.1 | −2.6 ± 0.9 | −2.5 ± 1.2 | −0.4 (noise) | +0.1 (noise) |
| (iv) +Bond side | Baseline | +22.1 ± 3.2 | +22.6 ± 2.7 | +25.7 ± 1.7 | +0.5 (noise) | **+3.1** |
| (iv) +Bond side | Repression | +38.7 ± 3.7 | +40.4 ± 4.4 | +40.6 ± 4.1 | +1.7 (noise) | +0.2 (noise) |

Levels at seed 42, for reference (baseline / repression, €000):

| Step | Pre-fix | After Item 1 | After all three |
|---|---|---|---|
| (i) Current | 1181 / 924 | 1176 / 920 | 1176 / 924 |
| (ii) +Re-anchor | 1347 / 1049 | 1345 / 1051 | 1348 / 1058 |
| (iii) +China cap | 1346 / 1047 | 1341 / 1049 | 1345 / 1055 |
| (iv) +Bond side | 1365 / 1083 | 1361 / 1086 | 1373 / 1097 |

**Levels are not interpretable.** All three level shifts are inside one seed-standard-
deviation (8–13k baseline, 5–7k repression). The FX fix in particular consumes the
random stream differently, so seeded levels change even where nothing economic did.
Read the Δ columns, not the levels.

**The headline for Exhibit 6:** the bond-side step under repression — the number the
conditional-value argument rests on — is **statistically unchanged across all three
fixes** (+38.7 → +40.4 → +40.6, against a seed sd of ~4). What actually moved is the
**equity re-anchor step under repression, +7.8k in total**, and the bond-side step at
**baseline, +3.6k**. If the article quotes the bond-side repression figure, it does not
need revising. If it quotes the re-anchor figure, it does.

---

## Item 1 — FXModel advanced twice per year

**Confirmed, and worse than reported.** Tracing the FX dict each sub-portfolio actually
consumed: `FXModel.step` ran **130 times over 65 years**, and the RSP and LHP saw
different rates every single year — USD differing by up to 12.8pp within one year.

The report described one defect; there were two. `FXModel.step` also rolls the PPP gaps
forward, so **the PPP gaps decayed twice per simulated year**. Measured, the CNY gap at
year 5 pre-fix equalled the correct year-10 value, and year 10 equalled year 20 — exact
2× time compression, costing ~30bp/yr of CNY tailwind over the first 20 years. That
second defect turned out to be the economically larger of the two.

**Changed.** `SubPortfolio.step` takes an optional `fx_returns`; `LifecycleSimulator.run`
advances the model once per year and hands the same dict to both sub-portfolios. Omitting
the argument preserves the old self-advancing path, which `Portfolio` (used by `main.py`)
still relies on — that path never had the bug, since only its RSP holds an FX model.
Guarded by `test_rsp_and_lhp_see_the_same_fx_rates_within_a_year`, verified to fail on the
old behaviour before being kept.

**What moved.** +4.6k baseline / +3.0k repression on the equity re-anchor step; the
bond-side step did not move significantly. That distribution is the opposite of what the
report predicted — it expected the common-shock restoration to matter for the unhedged
overlay. It landed on the equity step instead, because the PPP tailwind lives in the first
~20 years, when the glide path holds 0% LHP and 100–120% RSP. **The PPP-decay repair, not
the common-shock restoration, is what moved the numbers.**

---

## Item 2 — CGB calibration conflict

**Confirmed as described.** `bond_inputs.py` had 1.8%/1.8%/β0.10; the `em_bonds.py`
docstring claimed 2.3%/2.5%/β0.20–0.30. Applied the target: initial 1.8% retained,
long-run **1.8% → 2.3%** via a new `lr` key (the five other sovereigns keep `lr == yld`),
β 0.10 retained with the §13 ≈0.03 correlation recorded inline. Class defaults in
`em_bonds.py` now equal the `bond_inputs` row so the two cannot drift apart.

**Where I disagree with the instruction.** The brief states the sleeve "loses real value in
both worlds" and that at 1.8% nominal it "cannot preserve real value". **Measured, that is
false at both calibrations.** CGB earns a *positive* real return in EUR terms: +0.92%
baseline, +0.75% under repression at the new calibration (+0.41% / +0.16% at the old one).
The 1.8% local carry alone would not do it — the unhedged CNY leg lifts total return to
~3.4–3.5% nominal against realised EUR CPI. So the weak store-of-value claim
("keeps pace with inflation") is *supported*.

What is **not** supported is out-earning what it displaces: the EUR core returns 2.22%
real at baseline and 1.34% under repression, leaving CGB **127bp behind at baseline and
55bp behind under repression**. The honest claim is that the gap **more than halves** when
repression hits — conditional value, not absolute advantage. The file wording now says
this. (I had myself written the "loses real value" claim into four files earlier in this
work before measuring it; corrected.)

**Downside sensitivity** (`--flat-lr`, long-run pinned at 1.8%), Δ(5% vs 0%), 3 seeds:

| Calibration | Baseline | Repression |
|---|---:|---:|
| 1.8% → 2.3% (as calibrated) | −6.00k ± 1.53 | +0.51k ± 0.85 |
| 1.8% flat (downside) | −7.75k ± 1.56 | −0.72k ± 1.06 |

The reversion assumption is worth ~1.8k of baseline cost and ~1.2k of repression outcome —
it moves the magnitude, not the sign. Both calibrations say the same thing: CGB costs at
baseline, and is free under repression.

---

## Item 3 — FX inflation loadings

**Applied in full**, with the derivation, the 0.923 CNY validation figure, and the
euro-specific-shock reasoning recorded in `assets/fx.py`.

**A finding stronger than the brief's.** The brief calls the negatives "inconsistent with
observed currency behaviour". They are worse than inconsistent — **two of them were plain
sign errors**, because their own inline comments described the opposite of what the number
did:

```
JPY  -0.20   "safe-haven; gains when EUR weakens"
CHF  -0.30   "EUR inflation -> EUR weakens -> CHF gains in EUR terms"
```

Both comments describe a *positive* loading. The intent was right; the sign was wrong.
That is worth knowing, because it means the negatives were never a considered view that
someone might defend on the merits.

**Flagged, deliberately not changed:**

- **CHF (−0.30) is the last remaining negative** and is *not* in the derived table, so
  there is no measured beta to replace it with. It is wrong by the euro-specific argument
  and by its own comment, but correcting it without a beta swaps one assertion for
  another. It sits at 2% in `build_rsp_specs`' GlobalEquity sleeve, so it affects the
  **headline participant charts** — but **not** the attribution or CGB runs, which swap
  that sleeve out for the country mosaic. **This one needs a beta.**
- **CAD (+0.20) and AUD (+0.10)** are also outside the derived table. Both positive, so
  neither contradicts the argument, but neither was measured. AUD at 0.10 has the look of
  the same unreasoned block default that produced the old CNY/HKD/TWD 0.10.
- **The `growth_loading` column has the same disease.** The new correlations expose it:
  CNY correlates 0.923 with the USD yet carries `growth_loading` +0.30 against USD's
  −0.30. A currency cannot track the dollar for inflation and move opposite it for growth.
  VND (corr 0.951) has the same conflict. This needs the same regression treatment.
- **THB's `idio_vol` is 12.0% but measures 8.2%** on the derivation sample. IDR's measured
  11.1% is used directly. Not reconciled — outside the brief's scope.

**Post-2017 sensitivity** (`python -m examples.run_fx_loading_sensitivity`): essentially
nothing moves. Every attribution waypoint shifts ≤0.7k; the CGB dial Δ(5%) moves −0.7k
baseline and −0.2k repression. **The sample-period choice is not load-bearing for these
outputs.**

**Caveat on that sensitivity — it is partial.** Only the four post-2017 loadings the brief
supplied directly (CNY 0.30, THB 0.13, IDR 0.33, HKD 0.50) are applied. TWD and JPY
post-2017 *correlations* are given (0.60, 0.25) but not their betas, and loading cannot be
recovered from correlation alone — scaling CNY's full-sample loading by its correlation
ratio predicts 0.35 where the measured post-2017 value is 0.30. Rather than guess, those
two are left at full sample, so the sensitivity **understates** the true post-2017 effect.
JPY is 12% of the equity mosaic, so it is the one that would matter.

---

## Item 3b — THB-proxies-IDR retired

**Every substitution found, before changing anything** — two more than the brief listed:

| Location | Proxy | Status |
|---|---|---|
| `country_inputs.py:42` | Indonesia equity → THB | **Retired** → IDR |
| `country_inputs.py:46` | **Vietnam equity → THB** | **Retired** → VND *(not in the brief)* |
| `bond_inputs.py:64` | Indonesia bond → THB | **Retired** → IDR |
| `bond_inputs.py:61` | **NewZealand bond → AUD** | **STILL LIVE** — NZD absent from the table |
| `preview.py:22` | `FX_TAILWIND["THB"]` = "ASEAN proxy" | **Updated** — would have raised `KeyError` *(not in the brief)* |
| `em_bonds.py:206` | docstring | Updated |

`allocations/preview.py` carries its own separate FX table; repointing Indonesia without
touching it would have crashed the allocation preview. Vietnam was proxied by THB too —
the brief only mentioned Indonesia for `country_inputs.py`.

IDR and VND added to `assets/fx.py`. **Only `inflation_loading` and IDR's 11.1% vol are
measured**; `carry_spread`, `fx_drift`, `growth_loading`, `ppp_reversion` and
`initial_ppp_gap` for both are my judgement and are marked `JUDGEMENT` inline. VND's
`idio_vol` of 4.0% in particular is a guess sitting between HKD's hard peg and CNY.

**The effect is not zero.** Isolating the Indonesia change alone (N=600, all else fixed):

| World | THB proxy | IDR direct | Diff |
|---|---:|---:|---:|
| Baseline | 1364.3k | 1371.3k | **+7.05k** |
| Repression | 1089.8k | 1095.8k | **+5.96k** |

The gain comes from IDR's higher carry net of drift (+1.5%/yr vs THB's +1.0%), not from
the loading — both sit at 0.30. Indonesia is 4.5% of equity plus 3.5% of the EM bond
overlay. The EM overlay block's real return rose from 4.85% to 5.07% baseline, which is
most of the +3.1k on the bond-side step at baseline.

**The brief's caution is right and worth repeating in the article.** THB and IDR landing
on the same 0.30 is a coincidence of the beta arithmetic — THB correlates 0.713 against
IDR's 0.510, and they converge only because IDR's volatility (11.1%) is much higher than
THB's (8.2%). Post-2017 they diverge to 0.13 and 0.33. Recorded in `country_inputs.py`
and guarded by `test_indonesia_and_vietnam_use_their_own_currencies`.

---

## CGB dial sweep — corrected model vs old

Δ vs 0% weight, seed 42, N = 1000 (multi-seed figures for the 5% column in Item 2 above):

| CGB w | Baseline OLD | Baseline NEW | Repression OLD | Repression NEW |
|---|---:|---:|---:|---:|
| 1% | −1.9k | +0.1k | −0.2k | −0.0k |
| 2% | −3.5k | −0.9k | +0.0k | −0.3k |
| 3% | −4.9k | −2.3k | +0.4k | −0.2k |
| 5% | −6.6k | −5.3k | +0.4k | −0.5k |

Answering the three questions directly:

1. **Does the median give-up shrink?** At baseline, yes at intermediate weights — the 2–3%
   cost roughly halves (−3.5k → −0.9k, −4.9k → −2.3k). At 5% the multi-seed figures are
   −6.15k ± 0.10 before and −6.00k ± 1.53 after, i.e. **unchanged**. Under repression both
   are indistinguishable from zero (+1.53 ± 1.07 before, +0.51 ± 0.85 after); the apparent
   fall is **not** significant.
2. **Does the left-tail gain grow?** Marginally. p5 at 5% weight rises +6k baseline (was
   +4k) and +5k repression (was +5k). Still monotonic in weight in both worlds.
3. **Does 2–3% still hold?** **Yes, and the case is slightly stronger.** The baseline cost
   at 2–3% is now −0.9k to −2.3k rather than −3.5k to −4.9k, repression is flat, p5 rises,
   and LHP vol falls ~16bp per pp of weight. Nothing in the sweep marks a point where CGB
   stops helping; the binding constraint remains the baseline cost above 3%.

---

## Attribution of what moved

Where the two can be separated, they are:

- **Mechanical (random-stream) — not economic.** All level shifts. The FX fix changes which
  draws each sub-portfolio consumes, so seeded levels move without any economic content.
  Every level change reported here is inside one seed sd.
- **Economic, Item 1.** The PPP gaps decaying at the calibrated rate instead of double
  speed. +4.6k / +3.0k on the equity re-anchor step, several standard errors clear.
- **Economic, Item 3/3b.** Higher Asian inflation loadings and IDR replacing THB. +4.8k on
  the re-anchor step under repression, +3.1k on the bond-side step at baseline.
- **Cannot be separated.** Within Item 1, the common-shock restoration and the PPP-decay
  repair land in the same code change and cannot be run independently. The evidence that
  the PPP repair dominates is indirect — the gain falls on the equity step, in the years
  when the LHP has zero weight and no common RSP/LHP shock is possible. I have not
  isolated them and am not claiming a split beyond that.
- **Items 2 and 3 are separable only because CGB carries 0% weight in `run_attribution`,**
  so Item 2 cannot affect the attribution at all. In the CGB sweep they are not separable
  and I have not tried.
