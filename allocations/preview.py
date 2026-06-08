"""
Allocation-preview table (no Monte Carlo).
For each candidate equity allocation, show: Asia-incl-Japan %, China %, USA %,
blended forward nominal expected return (drift-weighted), blended FX tailwind
to a EUR investor, and a crude blended vol. Lets you tune weights against their
implied return/risk characteristics BEFORE spending compute.

Run from the repo root:  python -m allocations.preview
"""
import numpy as np
from allocations.country_inputs import COUNTRY_INPUTS, ASIA

# FX tailwind per currency: annualised PPP-closure drift a EUR investor earns
# (from FXModel: ppp_gap closing + carry + drift, approximate annualised).
FX_TAILWIND = {
    "USD": -0.005,  # dollar-debasement bias, net of carry => slight drag for EUR
    "JPY":  0.012,  # deeply undervalued, BoJ-managed normalisation
    "CNY":  0.008,  # PBOC-managed structural appreciation (§8.7)
    "INR":  0.005,  # high carry, RBI-managed; partial PPP
    "KRW":  0.012,  # undervalued free-floater (§13.4 strongest diversifier)
    "TWD":  0.006,  # CA surplus, semis
    "THB":  0.008,  # ASEAN proxy (Indonesia/Vietnam)
    "SGD":  0.005,  # MAS managed appreciation
    None:   0.000,  # EUR base (Europe)
}


def blended(weights):
    er = sum(w * COUNTRY_INPUTS[c]["drift"] for c, w in weights.items())
    # apply FX only on the UNHEDGED portion: developed USD 50% hedged, Asia unhedged, JPY 85%
    fx_eff = 0.0
    for c, w in weights.items():
        k = COUNTRY_INPUTS[c]["fx"]
        if k == "USD":   unhedged = 0.5
        elif k == "JPY": unhedged = 0.85
        elif k is None:  unhedged = 0.0
        else:            unhedged = 1.0
        fx_eff += w * FX_TAILWIND[k] * unhedged
    asia = sum(w for c, w in weights.items() if c in ASIA)
    china = weights.get("China", 0.0)
    usa = weights.get("USA", 0.0)
    # crude vol proxy: common market factor 14% + idio, corr 0.75 across markets
    idios = np.array([COUNTRY_INPUTS[c]["idio"] for c in weights])
    ws = np.array(list(weights.values()))
    common = 0.14
    vol = np.sqrt(0.75 * common**2 + np.sum((ws * idios)**2))  # simplified blended
    return dict(asia=asia, china=china, usa=usa, er=er, fx=fx_eff, er_eur=er + fx_eff, vol=vol)


# ---- Candidate allocations to compare ----
CANDIDATES = {
 "Current (ACWI-like)": {
    "USA":0.60,"Europe":0.15,"Japan":0.10,"China":0.055,"India":0.04,
    "Taiwan":0.03,"Korea":0.015,"Indonesia":0.010},

 "Proposed A: Asia 40% (=article)": {
    "USA":0.37,"Europe":0.20,"Japan":0.12,"Korea":0.075,"India":0.065,
    "China":0.06,"Taiwan":0.045,"Indonesia":0.045,"Vietnam":0.01,"Singapore":0.01},

 "Proposed C: Asia 35% (conservative)": {
    "USA":0.42,"Europe":0.23,"Japan":0.11,"Korea":0.06,"India":0.05,
    "China":0.05,"Taiwan":0.04,"Indonesia":0.035,"Vietnam":0.005},

 "Proposed D: China=3% (tight cap)": {
    "USA":0.36,"Europe":0.20,"Japan":0.12,"Korea":0.09,"India":0.08,
    "China":0.03,"Taiwan":0.05,"Indonesia":0.05,"Vietnam":0.01,"Singapore":0.01},
}


def main():
    print(f"{'Allocation':<36}{'Asia':>6}{'China':>7}{'USA':>6}{'E[r]loc':>9}{'+FX':>7}{'E[r]EUR':>9}{'~vol':>7}")
    print("-"*87)
    for name, w in CANDIDATES.items():
        assert abs(sum(w.values())-1) < 1e-6, f"{name} sums {sum(w.values())}"
        b = blended(w)
        print(f"{name:<36}{b['asia']*100:>5.0f}%{b['china']*100:>6.1f}%{b['usa']*100:>5.0f}%"
              f"{b['er']*100:>8.2f}%{b['fx']*100:>6.2f}%{b['er_eur']*100:>8.2f}%{b['vol']*100:>6.1f}%")
    print("\nNotes:")
    print(" E[r]loc = weight-blended §3.1 local-nominal expected return")
    print(" +FX     = blended EUR-investor FX tailwind on UNHEDGED portion (dev USD 50% hedged, Asia unhedged, JPY 85%)")
    print(" E[r]EUR = E[r]loc + FX")
    print(" ~vol    = crude blended equity vol proxy (illustrative only)")


if __name__ == "__main__":
    main()
