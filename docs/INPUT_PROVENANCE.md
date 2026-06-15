# Input provenance

This file maps every numerical input the participant model consumes back to the
article it accompanies, so a reader can audit where each figure comes from. It is
the reference companion to the code in `allocations/country_inputs.py`.

> Convention: `drift` is the **local-currency nominal** expected return — exactly
> the §3.1 Table 1a `r_nom` column and the §13.6 frontier input. FX appreciation
> is handled **separately** by the `FXModel` overlay (the `fx` key), never folded
> into `drift`, mirroring how §3.1 keeps the "+FX" column distinct from the
> frontier input.

## Per-country equity inputs (`COUNTRY_INPUTS`)

| Market | drift = §3.1 r_nom | CAPE now | CAPE anchor | FX key | Article source |
|---|---:|---:|---:|:--|:--|
| USA | 4.0% | 40.1 | 27.5 | USD | §3.1 Table 1a; anchor = 20-yr avg CAPE |
| Europe | 7.0% | 17.0 | 17.0 | — (EUR base) | §3.1 Table 1a; at long-run median |
| Japan | 6.0% | 24.0 | 22.0 | JPY | §3.1 Table 1a; ROE-convergence upside (§5/§6) |
| China | 8.4% | 11.0 | 14.0 | CNY | §3.1 Table 1a; post-recovery median anchor |
| India | 6.4% | 28.0 | 24.0 | INR | §3.1 Table 1a; negative multiple-reversion (the "India tension") |
| Korea | 7.1% | 12.0 | 16.0 | KRW | §3.1 Table 1a; §5.1 Value-Up re-rating |
| Taiwan | 5.6% | 21.0 | 19.0 | TWD | §3.1 Table 1a |
| Indonesia | 8.8% | 17.0 | 18.0 | THB* | §3.1 Table 1a |
| Vietnam† | 9.0% | 13.0 | 16.0 | THB* | PROXY — not in §3.1; illustrative dial |
| Singapore† | 6.0% | 14.0 | 15.0 | SGD | PROXY — not in §3.1; illustrative dial |

`*` `FXModel` has no IDR or VND. **THB** is used as the nearest managed-float ASEAN
proxy for Indonesia and Vietnam. Flagged in `country_inputs.py`; revisit if the
FX contribution for those markets becomes load-bearing.

`†` **Proxy markets.** Vietnam and Singapore have no §3.1 row; their inputs are
illustrative dials for "playing with weights", not sourced estimates. `real=False`
in `COUNTRY_INPUTS`; `proxy_markets()` lists them.

## Regional anchors (§13.6 four-region frontier)

The four bold rows of §3.1 Table 1a reproduce the §13.6 frontier inputs *by
construction* (see `scripts/build_cape_mapping_v2.py` in the article bundle):

| Region | real | local-nominal |
|---|---:|---:|
| USA | 2.0% | 4.0% |
| Europe | 5.0% | 7.0% |
| Japan | 4.0% | 6.0% |
| Asia ex-Japan | 6.5% | 8.5% |

## Method and calibration (for the referee)

- **Decomposition**: partial-reversion Gordon–Shiller,
  `r_real = D/P + g_real + (λ/N)·ln(CAPE_anchor / CAPE_now)`, with `N = 10`,
  `λ = 0.5` (multiple closes half the gap over the decade — the conservative
  choice; full reversion is *more* favourable to Asia and is shown as a
  sensitivity). `r_nom = r_real + 2.0%` EUR inflation (ECB target).
- **US anchor** = 20-yr-average CAPE (27.5), not the long-run median (16.0):
  half-reversion to the more generous reference reproduces §3's "~2% real" rather
  than an indefensible deep-negative figure. The choice deliberately weakens the
  article's own thesis.
- **CAPE / valuation data**: StarCapital / Keimling historical CAPE series;
  forward P/E, P/BV and dividend yields from MSCI index factsheets (Feb–Apr 2026,
  per Table 1).
- **FX tailwind**: §8.7 (renminbi ~10% PPP-undervalued, partial close) and §13.4
  (the won the strongest of the undervalued free-floaters; CNY/TWD anchored,
  modest). Pre-calibrated per currency in `assets/fx.py` (`_DEFAULT_CURRENCIES`).

## Still to be primary-sourced for the journal version

Two article exhibits use working-draft figures anchored to article-stated numbers,
flagged in their own captions and reproduced here for completeness:

- **Exhibit 1** (fiscal-composition scatter, §8.5) — social-expenditure and
  public-investment figures (OECD SOCX / Government at a Glance / ADB), illustrative.
- **Exhibit 5** (country-level frontier, §13.8) — uses the more bullish §5.1
  re-rating inputs (Korea 10 / China 9 / Taiwan 8 / India 7.5%), explicitly
  distinct from the conservative §3.1 CAPE figures above.

## Bond-side inputs (LDI / liability-hedging overlay)

The LHP holds a EUR-denominated core (the existing nominal + linker + cash hedge)
plus an unhedged overlay of unrepressed/managed sovereigns. `long_run_yield` is the
market's ~mid-2026 nominal 10-year yield; `global_rate_beta` is the EUR-rate
pass-through (LOW = decoupled / unrepressed). Source: central-bank policy
statements and 10-year benchmark yields, mid-June 2026.

| Sovereign | Block | long_run_yield | β (pass-through) | FX key | Note |
|---|:--|---:|---:|:--|:--|
| Australia | dev | 4.8% | 0.20 | AUD | AAA, commodity exporter |
| New Zealand | dev | 4.5% | 0.20 | AUD* | AA+, commodity exporter |
| Indonesia | em | 6.6% | 0.10 | THB* | ~4% real yield |
| India | em | 6.9% | 0.10 | INR | ~4% real yield |
| Korea | em | 3.7% | 0.15 | KRW | ~1.5% real yield |
| China (CGB) | managed | 1.8% | 0.10 | CNY | capped dial, default 0% |

`*` `FXModel` lacks NZD and IDR; **AUD** proxies NZD and **THB** proxies IDR
(documented in `bond_inputs.py`). All overlay sleeves are held **unhedged** —
FX-hedging back to EUR would, by covered-interest parity, reintroduce the
(possibly repressed) EUR base rate.

CGB sits in its own `managed` block, explicitly **not** claimed as unrepressed
(the curve is managed and capital-controlled). It is included as a capped dial on
the rationale that over the past decade Bunds and USTs delivered roughly flat-to-
negative real returns while CGB broadly kept pace with inflation, and China is
visibly working to make the 10-year CGB a credible real store of value.

### Repression scenario (Napier thesis)
The financial-repression overlay (`examples/run_attribution.py`) pins the EUR real
rate to **−1.5%** and inflation to **3.5%** over a sustained ~12-year window, with
foreign curves left unrepressed via their low `global_rate_beta`. Calibration is an
explicit, falsifiable assumption — the result is reported as a conditional world
alongside the no-repression baseline, never blended into a single probability.
