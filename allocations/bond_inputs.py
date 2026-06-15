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
                 and capital-controlled. It is a separate, capped, *store-of-value*
                 line, included as a dial (default 0%). Rationale: over the past
                 decade Bunds and USTs delivered roughly flat-to-negative real
                 returns, while CGB broadly kept pace with inflation; China is
                 visibly working to make the 10y CGB a credible real store of
                 value (the role the Bund once played). Its low pass-through beta
                 means it also does not import a EUR-repression episode.

`long_run_yield` ~ current nominal 10y yield (mid-2026). `global_rate_beta` is
the EUR-rate pass-through (LOW = decoupled). `fx` is the FXModel key; NZD and IDR
are not in the model, so AUD and THB proxy them (documented).
"""
from assets.em_bonds import GovernmentBondSleeve
from portfolio.portfolio import SleeveSpec

# name -> calibration. `within` = weight share inside its block (sums to 1 per block).
BOND_INPUTS = {
    # ---- Developed unrepressed (AAA/AA, commodity exporters) ----
    "Australia":   dict(block="dev", within=0.5, yld=0.048, dur=8.0, beta=0.20,
                        idio=0.006, fx="AUD"),
    "NewZealand":  dict(block="dev", within=0.5, yld=0.045, dur=8.0, beta=0.20,
                        idio=0.007, fx="AUD"),   # AUD proxies NZD (not in FXModel)
    # ---- EM unrepressed (healthy balance sheets, high real yield) ----
    "Indonesia":   dict(block="em",  within=0.35, yld=0.066, dur=7.0, beta=0.10,
                        idio=0.009, fx="THB"),   # THB proxies IDR (not in FXModel)
    "India":       dict(block="em",  within=0.35, yld=0.069, dur=7.0, beta=0.10,
                        idio=0.009, fx="INR"),
    "Korea":       dict(block="em",  within=0.30, yld=0.037, dur=8.0, beta=0.15,
                        idio=0.007, fx="KRW"),
    # ---- Managed store-of-value (capped dial, default 0%) ----
    "China":       dict(block="managed", within=1.0, yld=0.018, dur=7.0, beta=0.10,
                        idio=0.005, fx="CNY"),   # CGB: managed, decoupled, store-of-value
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
            initial_yield=inp["yld"], long_run_yield=inp["yld"],
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
            print(f"  {s.sleeve.name:<11} w={s.weight:.3f} yld={s.sleeve.long_run_yield:.3f} "
                  f"beta={s.sleeve.global_rate_beta:.2f} fx={s.sleeve.fx_exposures}")
