# Push notes — validation fixes, June → August 2026

## Summary

Five rounds of model work, developed since 2026-06-15 without intermediate commits and now
committed together. An independent validation found three Critical and nine Major defects;
all three Criticals are fixed and guarded by tests. **The paper's headline participant number
falls by 37–39% as a result.**

## Why it matters

The validation was not a tidying exercise. Three defects were Critical in the sense that they
made published numbers wrong, and the largest of them systematically favoured the allocation
the paper advocates:

- **Every scenario drew the identical equity idiosyncratic path.** `_reseed_specs` looked for
  a generator attribute named `_rng`; the equity, real-asset and commodity sleeves store
  theirs as `rng`. So they were never reseeded. Equity idiosyncratic volatility of 16–28%
  contributed **zero** cross-scenario dispersion, and one arbitrary random path was presented
  as the central estimate. That path happened to favour the high-idiosyncratic-volatility
  Asian markets the re-anchor step buys.
- **The re-anchor attribution step falls from +166.4k to +105.2k** — a 37% reduction against
  what the June code produces, or 39% against the +172.5k figure current immediately before
  validation. 5-seed means, N=1000.

## What changed

Grouped by round, newest first. Full detail in `CHANGELOG.md`; finding IDs from
`docs/VALIDATION_REPORT.md`.

| Round | Change | Moves published numbers? |
|---|---|---|
| 2026-08-22 | **V-C3** — added a global equity market factor. Cross-country correlation +0.01 → 0.518. **V-P1** — `Portfolio` LHP had no FX model. **V-R1** — `regimes.py` marked unsupported | **Yes** |
| 2026-08-21 | **V-C1** reseeding, **V-C2** inflation deviation, **V-M1** RNG stream collisions | **Yes, substantially** |
| 2026-08-21 | Global growth factor; all FX loadings re-derived jointly | No waypoint moved beyond noise |
| 2026-08-21 | FX inflation-loading table; THB/IDR proxy retired; IDR, VND, SGD added | Yes |
| 2026-08-20 | CGB calibration reconciled; long-run yield 1.8% → 2.3% | Yes, for the CGB dial |
| 2026-08-20 | FX model was advancing twice per year; PPP gaps decaying at double speed | Yes |

## What this means if you are using the June version

**Results produced from `0adf3bb` are wrong.** Specifically:

1. **Frozen equity idiosyncratic paths.** Every scenario shared one draw. Your pot
   distribution's dispersion is understated by roughly 45%, p95 by roughly 15%, and the
   median is biased by whatever that single path happened to do.
2. **Cross-country equity correlation of +0.01**, against 0.5–0.9 observed. Any
   diversification result is an artefact. The country mosaic showed 8.4% blended volatility
   against the cap-weighted allocation's 10.7% — that 2.3pp advantage was manufactured
   entirely by holding more countries with independent draws.
3. **Equity inflation applied as a level, not a deviation.** No market returned the expected
   return documented for it; the shortfall was 50–75bp and *differed by market*, giving China
   and Indonesia a standing 25bp advantage over Europe and the USA.
4. **The FX model advanced twice per simulated year.** The two sub-portfolios drew
   independent currency shocks for the same year, and the PPP gaps decayed at double speed —
   the year-5 gap equalled the correct year-10 value.
5. **Sleeve random streams collided across scenarios.** Taiwan and RealAssets shared a stream
   one scenario apart, with both live in the same sub-portfolio. This got *worse* with more
   paths: 12.2% of sleeve-runs at N=1000, 20.6% at N=5000.

There is no partial remedy. Re-run anything you produced from the June code.

## What is still open

> **Superseded 2026-08-23.** This table records the state at the June→August push and is kept
> as history. Since then: V-M3 resolved (Σ recalibrated to realised euro yield history;
> LongGovt 14.3%; both Exhibit 6 panels publishable), V-M7 resolved (3-year ramped repression
> transition), V-F1 found and resolved (FX loadings re-derived from committed data), V-M4
> reduced to 7.1%. Current status: `README.md` and the dated verdict at the top of
> `docs/VALIDATION_REPORT.md`.

| ID | Issue | Affects a published number? |
|---|---|---|
| **V-M3** | Long-bond volatility 22.7% simulated against a plausible 10–15%; the whole VAR Σ block is unsourced | **Yes.** Exhibit 6 panel (a) is sound; **panel (b), the pot distribution, should not be published until this is resolved** — it is a pure dispersion claim |
| V-M7 | `repress()` produces ±50–63% single-year LHP returns at the window boundaries — a symptom of V-M3, not independent | Yes, indirectly |
| V-M2 | Construction seeds collide (Europe = RealAssets = 44). Masked in the participant path by the V-C1 fix; still live for any caller building sleeves without `_run_batch`, including `main.py` | No |
| V-M4 | The `credit_spread` floor binds on ~10% of steps, lifting its simulated mean 11bp above target and pulling its spread below the analytic value | Marginally |
| V-D1 | `global_growth` is calibrated as a GDP variable (mean 3%, vol 2%) while the currency loadings on it were derived against equity returns, whose volatility is ~8× larger | Small — loadings are 0–0.15 |
| V-D5 | CHF, CAD, AUD FX loadings un-derived. CHF's −0.30 inflation loading is the last remaining negative and contradicts its own comment. **AUD still proxies NZD in the bond overlay**, so its misplaced global-cycle exposure reaches the LHP | Not in the attribution or CGB runs |
| — | A single global equity factor under-fits North Asia: Korea–Taiwan 0.44 against ~0.70 observed. A second Asian regional factor is the natural remedy, and the natural home for the supply-chain concentration the paper's geopolitics section discusses | Small |
| — | **77% of the model's calibrated inputs are judgement calls** with no source — see the status table at the top of `docs/INPUT_PROVENANCE.md`. The largest unsourced block is the VAR, which is also the one V-M3 shows to be mis-specified | Context, not a defect |

`scenarios/regimes.py` now raises `NotImplementedError` rather than failing with a shape
error. `analytics/metrics.py`, `simulation/engine.py` and `liabilities/model.py` remain
untested and drive no published exhibit.

## Reproducibility

```bash
python -m pip install -r requirements.txt
python -m pytest tests/ -q              # 43 passed
python -m examples.run_attribution 1000 # Exhibit 6, both panels
python -m examples.run_cgb_dial 1000    # CGB dial sweep
```

Every command in `docs/REPRODUCE.md` was re-run against this tree on 2026-08-22.
`docs/REPRODUCE.md` also states which exhibits are model output and which are market data —
worth reading before checking any figure.

Two derivations **cannot** be re-run from a clean clone: `calibration/equity_factor_calibration.py`
reads two pickles from a path outside the repository, and the FX loading regression has no
committed script. Both are recorded as *Derived* in `docs/INPUT_PROVENANCE.md` with that
limitation stated rather than glossed over.

**Tag the commit that generates the paper's final figures, and cite it by tag.** Levels move
with the random draw sequence — adding a state variable or a factor changes them regardless
of economics — so a figure is only reproducible against a fixed commit. Citing a branch will
not survive the next change.

## Where to start reading

| File | What it tells you |
|---|---|
| `docs/VALIDATION_REPORT.md` | Every finding, its evidence, and the fix or recommendation |
| `docs/INPUT_PROVENANCE.md` | What each of the model's ~356 inputs rests on: Article, Derived, or Judgement |
| `CHANGELOG.md` | What changed in each round and whether it moved numbers |
| `docs/TEST_COVERAGE.md` | What the 43 tests cover, and which findings have **no** guard |
| `output/equity_factor_summary.md` | The most recent round in full, including the correlation matrix |
