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
`mbeta`     = loading on the GLOBAL EQUITY MARKET FACTOR (15.5% p.a., mean zero).
              Added 2026-08-22 to close validation finding V-C3.
`idio`      = residual volatility AFTER removing the market factor. These are NOT
              the pre-2026-08-22 values: adding `mbeta` without cutting `idio`
              would have roughly DOUBLED every market's total volatility.
              mbeta^2 x var(F) + idio^2 reproduces each market's observed total
              volatility to three decimals (asserted in tests).

              Derived from monthly returns 2001-2025 in LOCAL currency (MSCI USD
              series un-crossed through their USD legs) so the equity factor
              structure is isolated from currency, which FXModel handles
              separately. Factor = MSCI World; mbeta = regression coefficient;
              idio = residual volatility.

                market      mbeta   idio   total vol   R2
                USA         0.961  0.034     15.2%    0.95
                Europe      0.852  0.073     15.1%    0.77
                Japan       0.739  0.124     16.8%    0.46
                Korea       0.925  0.156     21.2%    0.46
                Taiwan      0.870  0.156     20.6%    0.43
                India       0.867  0.170     21.7%    0.38
                China       0.913  0.204     24.8%    0.32
                Indonesia   0.85   0.19      23.1%    JUDGEMENT (between India/China)
                Vietnam     0.75   0.24      26.7%    JUDGEMENT (lower integration)
                Singapore   0.90   0.115     18.1%    JUDGEMENT (developed, open)

              NEGLECTED TERM, recorded rather than hidden: the macro factors add
              roughly 2% of volatility on top of market + idio. Removing it in
              quadrature changes TOTAL volatility by under 0.2pp for every market,
              so it is neglected. The effect on `idio` itself is larger where idio
              is small — the USA would move 0.034 -> 0.027, i.e. 0.65pp — so the
              "under 0.2pp" tolerance describes total volatility, not idio.

              NOTE the source script `equity_factor_calibration.py` was cited but
              is NOT in this repository, so the regression could not be re-run
              here. The table's internal consistency WAS verified: every row
              reproduces its stated total volatility and R-squared from mbeta,
              idio and the 15.5% factor volatility.
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
                   gbeta=0.60, ibeta=-0.30, idio=0.034, mbeta=0.961, real=True),
    "Europe": dict(drift=0.070, cape_now=17.0, cape_fair=17.0, fx=None,
                   gbeta=0.60, ibeta=-0.30, idio=0.073, mbeta=0.852, real=True),

    # ---------- Asia mosaic — Japan included (reforms underway, ROE-convergence upside) ----------
    "Japan":  dict(drift=0.060, cape_now=24.0, cape_fair=22.0, fx="JPY",
                   gbeta=0.55, ibeta=-0.25, idio=0.124, mbeta=0.739, real=True),
    "China":  dict(drift=0.084, cape_now=11.0, cape_fair=14.0, fx="CNY",
                   gbeta=0.70, ibeta=-0.20, idio=0.204, mbeta=0.913, real=True),
    "India":  dict(drift=0.064, cape_now=28.0, cape_fair=24.0, fx="INR",
                   gbeta=0.75, ibeta=-0.25, idio=0.17, mbeta=0.867, real=True),
    "Korea":  dict(drift=0.071, cape_now=12.0, cape_fair=16.0, fx="KRW",
                   gbeta=0.70, ibeta=-0.25, idio=0.156, mbeta=0.925, real=True),
    "Taiwan": dict(drift=0.056, cape_now=21.0, cape_fair=19.0, fx="TWD",
                   gbeta=0.70, ibeta=-0.25, idio=0.156, mbeta=0.87, real=True),
    "Indonesia": dict(drift=0.088, cape_now=17.0, cape_fair=18.0, fx="IDR",  # own currency since 2026-08 (was THB proxy)
                   gbeta=0.70, ibeta=-0.20, idio=0.19, mbeta=0.85, real=True),   # JUDGEMENT: mbeta/idio by analogy, not in the return data

    # ---------- PROXY markets (no §3.1 data — illustrative dials only) ----------
    "Vietnam":   dict(drift=0.090, cape_now=13.0, cape_fair=16.0, fx="VND",  # own currency since 2026-08 (was THB proxy)
                   gbeta=0.75, ibeta=-0.20, idio=0.24, mbeta=0.75, real=False),   # JUDGEMENT: mbeta/idio by analogy, not in the return data
    "Singapore": dict(drift=0.060, cape_now=14.0, cape_fair=15.0, fx="SGD",
                   gbeta=0.55, ibeta=-0.25, idio=0.115, mbeta=0.9, real=False),   # JUDGEMENT: mbeta/idio by analogy, not in the return data
}

# Which markets count as "Asia" for the total-Asia-weight dial (Japan INCLUDED per author).
ASIA = {"Japan", "China", "India", "Korea", "Taiwan", "Indonesia", "Vietnam", "Singapore"}

# FX PROXIES RETIRED 2026-08. Indonesia and Vietnam both pointed at THB because
# FXModel carried neither IDR nor VND. Both now exist as first-class currencies
# with loadings derived from their own EUR-cross histories, so the mosaic needs
# no FX proxy at all.
#
# A caution against reading the result as vindication of the old proxy: THB and
# IDR both land at a 0.30 inflation_loading, but by different routes. THB
# correlates 0.713 with the USD against IDR's 0.510; they converge only because
# IDR's volatility (11.1% ann.) is materially higher than THB's (8.2%), and the
# beta calculation offsets the weaker correlation against the larger amplitude.
# That coincidence does not survive re-estimation: post-2017 THB falls to 0.13
# while IDR holds at 0.33. The substitution was never sound; it happened to be
# roughly harmless at these particular parameters.
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
