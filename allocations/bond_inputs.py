"""
Overlay-sovereign bond inputs for the LDI / liability-hedging portfolio.

Beyond the EUR-denominated core liability hedge, the article's bond-side proposal
adds, inside the LHP, sovereigns chosen for one of three reasons. All are held
UNHEDGED: hedging the currency back to EUR would, by covered-interest parity,
drag the return toward the (possibly repressed) EUR base rate and defeat the
purpose.

Three blocks:
  * DEVELOPED  — New Zealand, Australia. AAA/AA, commodity exporters, unrepressed
                 curves with a positive real yield.
  * EM         — Indonesia, India, Korea. Healthy balance sheets; the highest
                 real yields of the set; unrepressed curves.
  * MANAGED    — China (CGB). NOT claimed as "unrepressed": the curve is managed
                 and capital-controlled. A separate, capped line held as a dial
                 (default 0%). Its low pass-through beta means it does not import
                 a EUR-repression episode, which is the whole reason the line
                 exists.

                 The store-of-value claim is SUPPORTED but MODEST, and the case
                 for the line is RELATIVE. Measured over accumulation, the sleeve
                 earns a small POSITIVE real return in EUR terms — about +0.9%
                 baseline and +0.8% under repression. The 1.8% local carry alone
                 would not do that; the unhedged CNY leg (carry + managed drift +
                 PPP convergence) is what lifts total return to ~3.4-3.6% nominal
                 against realised EUR CPI. So "keeps pace with inflation" holds.

                 What does NOT hold is any claim that it out-earns what it
                 displaces: the EUR core returns ~2.2% real at baseline and ~1.3%
                 under repression, so CGB gives up ~127bp at baseline and ~55bp
                 under repression. That NARROWING is the conditional-value case —
                 the line is justified by what happens to the gap when repression
                 hits, and by its volatility contribution, not by an absolute
                 return advantage. Measured figures: `output/cgb_dial_findings.md`.

`yld` = current nominal 10y yield (mid-2026), used as the sleeve's INITIAL yield.
`lr` = long-run (reversion-target) yield; omitted means "same as `yld`", i.e. no
reversion pull. `global_rate_beta` is the EUR-rate pass-through (LOW = decoupled).
`fx` is the FXModel key. IDR is now a first-class currency (the THB-proxies-IDR
substitution was retired 2026-08). NZD is still NOT in the model, so AUD proxies
New Zealand — that substitution REMAINS and is not covered by the FX derivation;
it needs its own beta before it can be retired the same way.

Only China carries an explicit `lr` distinct from `yld`. Setting the two equal —
as every other row does — embeds the assumption that today's yield IS the
equilibrium. For the five unrepressed sovereigns that is a defensible neutral
prior. For CGB it was not: 1.8% is a cyclical low, so `lr == yld` silently
asserted that Chinese yields stay at that low permanently, and it made the
sleeve's own store-of-value rationale arithmetically impossible to satisfy. A
modest reversion target makes that claim testable rather than excluded by
construction. See the China row below for the per-parameter provenance.
"""
from assets.em_bonds import GovernmentBondSleeve
from portfolio.portfolio import SleeveSpec

# name -> calibration. `within` = weight share inside its block (sums to 1 per block).
BOND_INPUTS = {
    # ---- Developed unrepressed (AAA/AA, commodity exporters) ----
    "Australia":   dict(block="dev", within=0.5, yld=0.048, dur=8.0, beta=0.20,
                        idio=0.006, fx="AUD"),
    "NewZealand":  dict(block="dev", within=0.5, yld=0.045, dur=8.0, beta=0.20,
                        idio=0.007, fx="AUD"),   # PROXY STILL LIVE: AUD stands in for NZD
    # ---- EM unrepressed (healthy balance sheets, high real yield) ----
    "Indonesia":   dict(block="em",  within=0.35, yld=0.066, dur=7.0, beta=0.10,
                        idio=0.009, fx="IDR"),   # own currency since 2026-08 (was THB proxy)
    "India":       dict(block="em",  within=0.35, yld=0.069, dur=7.0, beta=0.10,
                        idio=0.009, fx="INR"),
    "Korea":       dict(block="em",  within=0.30, yld=0.037, dur=8.0, beta=0.15,
                        idio=0.007, fx="KRW"),
    # ---- Managed, low-pass-through (capped dial, default 0%) ----
    # yld  1.8% — mid-2026 10y CGB. Chinese 10y yields fell through 2% in late
    #             2024 on deflation and property deleveraging; 1.8% is the market,
    #             not a forecast. (The 2.3% that used to sit in the em_bonds
    #             docstring is a stale 2023-era figure.)
    # lr   2.3% — reversion target, deliberately ABOVE spot. Distinct from `yld`
    #             so the sleeve carries a mean-reversion pull instead of assuming
    #             the cyclical low is permanent; see module docstring.
    # beta 0.10 — EUR pass-through. Article §13 measures Fed-PBoC policy-cycle
    #             correlation at ~0.03; a low beta is far better supported by that
    #             than the 0.20-0.30 the em_bonds docstring used to quote. Kept
    #             at 0.10 (not 0.03) as a deliberately conservative margin — it
    #             concedes more repression pass-through than the data implies.
    "China":       dict(block="managed", within=1.0, yld=0.018, lr=0.023, dur=7.0,
                        beta=0.10, idio=0.005, fx="CNY"),
}

DEVELOPED = [k for k, v in BOND_INPUTS.items() if v["block"] == "dev"]
EM        = [k for k, v in BOND_INPUTS.items() if v["block"] == "em"]
MANAGED   = [k for k, v in BOND_INPUTS.items() if v["block"] == "managed"]


def build_overlay_specs(dev_weight=0.10, em_weight=0.10, china_weight=0.0, seed=7):
    """Return SleeveSpecs for the non-EUR overlay of the LHP.

    Each block's weight is its share of the TOTAL LHP; within a block, names
    split by their `within` share. China defaults to 0% — present as a dial.
    Returned weights sum to dev_weight + em_weight + china_weight; the caller
    supplies the EUR-core residual (1 - that sum).
    """
    block_weight = {"dev": dev_weight, "em": em_weight, "managed": china_weight}
    specs = []
    for i, (name, inp) in enumerate(BOND_INPUTS.items()):
        w = block_weight[inp["block"]] * inp["within"]
        if w <= 0:
            continue
        sl = GovernmentBondSleeve(
            name=name, duration=inp["dur"],
            initial_yield=inp["yld"], long_run_yield=inp.get("lr", inp["yld"]),
            yield_reversion=0.20, global_rate_beta=inp["beta"],
            idio_yield_vol=inp["idio"], fx_key=inp["fx"], seed=seed + i,
        )
        specs.append(SleeveSpec(sl, weight=w))
    return specs


if __name__ == "__main__":
    for cw in (0.0, 0.02):
        specs = build_overlay_specs(china_weight=cw)
        tot = sum(s.weight for s in specs)
        print(f"china_weight={cw}: {len(specs)} overlay sleeves, total {tot:.2f}, "
              f"EUR-core residual {1-tot:.2f}")
        for s in specs:
            print(f"  {s.sleeve.name:<11} w={s.weight:.3f} "
                  f"y0={BOND_INPUTS[s.sleeve.name]['yld']:.3f} "
                  f"lr={s.sleeve.long_run_yield:.3f} "
                  f"beta={s.sleeve.global_rate_beta:.2f} fx={s.sleeve.fx_exposures}")
