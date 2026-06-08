"""
Country-level equity inputs for the Asia re-anchoring participant simulation.

Each entry pins a market's forward expected return and CAPE-reversion inputs to
the article's §3.1 Table 1a (partial-reversion Gordon-Shiller), and its currency
exposure to §13.4 (which currencies are real diversifiers vs USD-proxies) and the
FXModel PPP-undervaluation thesis.

`drift`     = §3.1 local-currency nominal expected return (the EquitySleeve's
              long-run nominal total return). FX upside is handled SEPARATELY by
              the FXModel overlay via fx_exposures, exactly as §3.1 keeps the FX
              column distinct from the frontier input.
`cape_now`, `cape_fair` = §3.1 Table 1a CAPE_now and CAPE_anchor.
`fx`        = the home-currency exposure key in the FXModel (None => already EUR/
              treated as base for a EUR investor's developed holding).

REAL DATA (in §3.1 / return pickles): USA, Europe, Japan, China, India, Korea,
Taiwan, Indonesia.
PROXY DATA (flagged; NOT in §3.1 — illustrative for 'playing with weights'):
Vietnam, Singapore.
"""

# name -> dict of inputs
COUNTRY_INPUTS = {
    # ---------- Developed anchors ----------
    "USA":    dict(drift=0.040, cape_now=40.1, cape_fair=27.5, fx="USD",
                   gbeta=0.60, ibeta=-0.30, idio=0.16, real=True),
    "Europe": dict(drift=0.070, cape_now=17.0, cape_fair=17.0, fx=None,
                   gbeta=0.60, ibeta=-0.30, idio=0.17, real=True),

    # ---------- Asia mosaic — Japan included (reforms underway, ROE-convergence upside) ----------
    "Japan":  dict(drift=0.060, cape_now=24.0, cape_fair=22.0, fx="JPY",
                   gbeta=0.55, ibeta=-0.25, idio=0.18, real=True),
    "China":  dict(drift=0.084, cape_now=11.0, cape_fair=14.0, fx="CNY",
                   gbeta=0.70, ibeta=-0.20, idio=0.24, real=True),
    "India":  dict(drift=0.064, cape_now=28.0, cape_fair=24.0, fx="INR",
                   gbeta=0.75, ibeta=-0.25, idio=0.24, real=True),
    "Korea":  dict(drift=0.071, cape_now=12.0, cape_fair=16.0, fx="KRW",
                   gbeta=0.70, ibeta=-0.25, idio=0.26, real=True),
    "Taiwan": dict(drift=0.056, cape_now=21.0, cape_fair=19.0, fx="TWD",
                   gbeta=0.70, ibeta=-0.25, idio=0.24, real=True),
    "Indonesia": dict(drift=0.088, cape_now=17.0, cape_fair=18.0, fx="THB",  # THB as nearest ASEAN FX proxy; see note
                   gbeta=0.70, ibeta=-0.20, idio=0.24, real=True),

    # ---------- PROXY markets (no §3.1 data — illustrative dials only) ----------
    "Vietnam":   dict(drift=0.090, cape_now=13.0, cape_fair=16.0, fx="THB",  # PROXY: VND not in FXModel, THB stand-in
                   gbeta=0.75, ibeta=-0.20, idio=0.28, real=False),
    "Singapore": dict(drift=0.060, cape_now=14.0, cape_fair=15.0, fx="SGD",
                   gbeta=0.55, ibeta=-0.25, idio=0.18, real=False),
}

# Which markets count as "Asia" for the total-Asia-weight dial (Japan INCLUDED per author).
ASIA = {"Japan", "China", "India", "Korea", "Taiwan", "Indonesia", "Vietnam", "Singapore"}

# Indonesia FX note: FXModel lacks IDR. THB used as nearest managed-float ASEAN proxy.
# Real EPS-growth / earnings-growth for the CAPE updater: use drift-consistent values.
LONG_RUN_EPS_GROWTH = {  # nominal earnings growth feeding the CAPE update
    "USA":0.05, "Europe":0.04, "Japan":0.045, "China":0.06, "India":0.075,
    "Korea":0.055, "Taiwan":0.055, "Indonesia":0.07, "Vietnam":0.08, "Singapore":0.05,
}

def proxy_markets():
    return [k for k,v in COUNTRY_INPUTS.items() if not v["real"]]

if __name__ == "__main__":
    print("Markets defined:", list(COUNTRY_INPUTS))
    print("Asia set:", sorted(ASIA))
    print("Proxy (illustrative) markets:", proxy_markets())
