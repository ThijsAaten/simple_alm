"""
Configurable country-mosaic equity-sleeve builder for the participant simulation.

Usage:
    from allocations.mosaic import build_equity_specs, PROPOSED_EQUITY
    specs = build_equity_specs(PROPOSED_EQUITY, seed=1)
where `weights` is a dict {country: weight} summing to 1.0 over the equity sleeve.

Returns a list[SleeveSpec] — one EquitySleeve per country, each carrying its
§3.1 drift/CAPE inputs and its FXModel currency exposure. Drop straight into the
RSP equity portion (see examples/run_equity_only.py for the wiring).

Two canonical allocations are provided:
    CURRENT_EQUITY   — ACWI-like: USA-heavy, Asia ~15% cap-weighted within itself
    PROPOSED_EQUITY  — Asia ~40% (incl. Japan dial separate), demographically
                       tilted, CHINA EXPLICITLY CAPPED.
Both are starting points to experiment from, not fixed.

NOTE: this module previously inserted "/home/claude/simple_alm" onto sys.path.
That hard-coded path has been removed — run from the repo root (or with the repo
root on PYTHONPATH, e.g. `python -m allocations.mosaic`) so that `assets` and
`portfolio` resolve as the model's own packages.
"""
from assets.growth import EquitySleeve
from portfolio.portfolio import SleeveSpec
from allocations.country_inputs import COUNTRY_INPUTS, LONG_RUN_EPS_GROWTH, ASIA


# Share of each market's growth beta attributed to the EURO-AREA cycle under
# growth_mode="split"; the remainder loads on the global cycle. ILLUSTRATIVE —
# these are a reasoned split for the comparison run, NOT a calibration. Nobody
# regressed these. See output/global_growth_factor_summary.md.
EURO_CYCLE_SHARE = {
    "Europe": 0.70,   # domestic cycle dominant, though EU corporates export heavily
    "USA":    0.20,
    "Japan":  0.15,
    "Singapore": 0.10,
    "China":  0.05, "India": 0.05, "Korea": 0.05,
    "Taiwan": 0.05, "Indonesia": 0.05, "Vietnam": 0.05,
}

GROWTH_MODES = ("euro", "split", "global")


def build_equity_specs(weights, seed=1, hedge_developed=0.5, growth_mode="euro"):
    """weights: {country: weight}, must sum ~1.0. hedge_developed = fraction of
    USD/EUR-developed FX that is hedged (Asian FX left unhedged per §17 pt 5).

    growth_mode controls which growth cycle each country's `gbeta` loads on:

      "euro"   (default, CURRENT BEHAVIOUR) — the whole beta loads on
               state.growth, which is EURO-AREA growth. This is almost certainly
               wrong: COUNTRY_INPUTS puts India at 0.75 and China at 0.70 against
               Europe's 0.60, and Indian equities cannot plausibly respond more
               strongly to euro-area growth than European equities do. That
               ordering only makes sense against a GLOBAL cycle.
      "split"  — beta is divided between the two cycles by EURO_CYCLE_SHARE,
               preserving each country's TOTAL growth sensitivity so the
               comparison isolates reallocation, not magnitude.
      "global" — the whole beta loads on state.global_growth. Makes the existing
               ordering coherent in one line, but leaves European equities with
               no euro-cycle sensitivity at all, which is its own error.

    Default is "euro" so no published number changes unless a caller opts in.
    """
    if growth_mode not in GROWTH_MODES:
        raise ValueError(f"growth_mode must be one of {GROWTH_MODES}, got {growth_mode!r}")
    tot = sum(weights.values())
    assert abs(tot - 1.0) < 1e-6, f"weights sum to {tot}, not 1.0"
    specs = []
    for i, (country, w) in enumerate(weights.items()):
        if w <= 0:
            continue
        inp = COUNTRY_INPUTS[country]
        if growth_mode == "euro":
            euro_share = 1.0
        elif growth_mode == "global":
            euro_share = 0.0
        else:
            euro_share = EURO_CYCLE_SHARE[country]
        sl = EquitySleeve(
            country,
            drift=inp["drift"],
            growth_beta=inp["gbeta"] * euro_share,
            global_growth_beta=inp["gbeta"] * (1.0 - euro_share),
            market_beta=inp["mbeta"],
            inflation_beta=inp["ibeta"],
            idio_vol=inp["idio"],
            seed=seed + i,
            cape=inp["cape_now"],
            cape_fair=inp["cape_fair"],
            valuation_beta=0.05,
            long_run_earnings_growth=LONG_RUN_EPS_GROWTH[country],
        )
        # FX overlay: developed (USD) partly hedged; Asian FX left unhedged to
        # capture §8.7/§13.4 PPP-undervaluation tailwind. EUR-base => Europe no overlay.
        fxk = inp["fx"]
        if fxk is None:
            sl.fx_exposures = {}
        elif fxk == "USD":
            sl.fx_exposures = {"USD": 1.0 * (1 - hedge_developed)}
        elif fxk == "JPY":
            # Japan: developed, but JPY deeply undervalued — leave mostly unhedged
            sl.fx_exposures = {"JPY": 0.85}
        else:
            # Asian EM FX: fully unhedged (the thesis)
            sl.fx_exposures = {fxk: 1.0}
        specs.append(SleeveSpec(sl, weight=w))
    return specs


# ---- Canonical allocations (equity sleeve = 100%) ----
# CURRENT: approximate MSCI-ACWI-benchmarked Dutch equity sleeve.
# Asia (incl Japan) ~ 25% but cap-weighted: Japan 10, China ~5, India ~4, TWN ~3, KOR ~2, INDO ~1
CURRENT_EQUITY = {
    "USA": 0.60, "Europe": 0.15,
    "Japan": 0.10, "China": 0.055, "India": 0.04, "Taiwan": 0.03,
    "Korea": 0.015, "Indonesia": 0.010,
}

# PROPOSED (= "Proposed A"): Asia-incl-Japan ~40%, matching the article's §13.6
# anchor (Asia ex-Japan 30% + Japan ~12%). EM-Asia mosaic tilted to cheap/young/
# reforming markets; CHINA EXPLICITLY CAPPED at 6% of the equity sleeve (a
# governance-discount weight, well below cap-weighted share).
# USA cut 60->37, Europe 15->20, Japan 10->12 (ROE-convergence upside).
PROPOSED_EQUITY = {
    "USA": 0.37, "Europe": 0.20,
    "Japan": 0.12, "Korea": 0.075, "India": 0.065, "China": 0.06,
    "Taiwan": 0.045, "Indonesia": 0.045, "Vietnam": 0.01, "Singapore": 0.01,
}

# Companion scenarios for attribution / robustness (per reviewer feedback):
#   C = conservative (Asia ~35%); D = tight China cap (China 3%)
PROPOSED_CONSERVATIVE = {
    "USA": 0.42, "Europe": 0.23,
    "Japan": 0.11, "Korea": 0.06, "India": 0.05, "China": 0.05,
    "Taiwan": 0.04, "Indonesia": 0.035, "Vietnam": 0.005,
}
PROPOSED_TIGHT_CHINA = {
    "USA": 0.36, "Europe": 0.20,
    "Japan": 0.12, "Korea": 0.09, "India": 0.08, "China": 0.03,
    "Taiwan": 0.05, "Indonesia": 0.05, "Vietnam": 0.01, "Singapore": 0.01,
}


def asia_weight(weights):
    return sum(w for c, w in weights.items() if c in ASIA)


if __name__ == "__main__":
    for name, w in [("CURRENT", CURRENT_EQUITY), ("PROPOSED", PROPOSED_EQUITY)]:
        s = build_equity_specs(w)
        print(f"{name}: {len(s)} sleeves, sum={sum(w.values()):.3f}, "
              f"Asia(incl Japan)={asia_weight(w)*100:.0f}%, "
              f"China={w.get('China',0)*100:.1f}%")
        print("   weights:", {c: round(v,3) for c,v in w.items()})
