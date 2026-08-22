# Derivation scripts

Scripts that produced calibrated inputs, kept so the derivations can be audited.

| Script | Derives | Re-runnable from a clean clone? |
|---|---|---|
| `equity_factor_calibration.py` | `mbeta` and `idio_vol` per market, and the 15.5% equity factor volatility | **Yes**, since 2026-08-22 |
| `convert_source_data.py` | Nothing — converts the source data to CSV | Yes (pickle step is a no-op once the CSVs exist) |
| `fx_loading_calibration.py` | **FX macro loadings** — the joint regression behind `inflation_loading`, `growth_loading` and `global_growth_loading` | **Yes**, since 2026-08-22 — but see V-F1 |

## Equity market factor — reproducible

```bash
python calibration/equity_factor_calibration.py
```

Reads `data/ret_usd.csv` and `data/fx_levels.csv` and reproduces the `market_beta` /
`idio_vol` table in `allocations/country_inputs.py`, the 15.5% factor volatility in
`scenarios/engine.py`, and the documented worst-fitting pairs (Korea–Taiwan 0.26,
China–Taiwan 0.16), to the precision those files state. Verified under the repository's own
numpy 1.26.

Until 2026-08-22 this script read two pickles from an absolute path outside the repository
and could not be run at all. See `data/README.md` for why the source is now CSV.

## FX loadings — runnable, and it disagrees with what is committed

```bash
python calibration/fx_loading_calibration.py
```

The script implements the method exactly as `assets/fx.py` documents it, and validates its
own pipeline against four independently published figures — all 11 currency correlations
with the USD, the article's own CNY–USD 0.92 (measured 0.923), and the cited IDR (11.1%) and
THB (8.2%) volatilities. All reproduce exactly.

**`global_growth_loading` reproduces for all 12 currencies. `inflation_loading` and
`growth_loading` do not**, because both are computed from a `b_usd` column that cannot be
reproduced from this data under any specification or window tested. The script prints the
discrepancy and **leaves `assets/fx.py` untouched** — rewriting 17 live loadings is a
decision, not a side effect of running a calibration. Recorded as **V-F1** in
`docs/VALIDATION_REPORT.md`.

The same file would also support closing two open items — see `docs/VALIDATION_REPORT.md`:

- **V-D5**: CHF, CAD and AUD loadings are un-derived, and CHF's −0.30 `inflation_loading` is
  the last remaining negative in the table, contradicting its own inline comment.
- The **AUD-proxies-NZD** substitution in the bond overlay, the last live FX proxy.

Neither is attempted here. Both would change published numbers and are decisions for the
repository owner, not consequences of a data conversion.

## Related tooling

`tools/build_fx_bloomberg_sheet.py` generates `data/fx_history_bloomberg.xlsx`, the workbook
the FX legs were pulled with. It gathers an input rather than deriving one, so it sits under
`tools/`.
