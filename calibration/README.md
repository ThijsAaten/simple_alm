# Derivation scripts

Scripts that produced calibrated inputs, kept so the derivations can be audited.

| Script | Derives | Re-runnable from a clean clone? |
|---|---|---|
| `equity_factor_calibration.py` | `mbeta` and `idio_vol` per market, and the 15.5% equity factor volatility | **Yes**, since 2026-08-22 |
| `convert_source_data.py` | Nothing — converts the source data to CSV | Yes (pickle step is a no-op once the CSVs exist) |
| *(none)* | **FX macro loadings** — the joint regression behind `inflation_loading`, `growth_loading` and `global_growth_loading` | **No — no script exists** |

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

## FX loadings — data present, script absent

`data/fx_bloomberg_legs.csv` (added 2026-08-22) supplies IDR, THB, SGD and VND, which
`fx_levels.csv` lacked, plus CHF, CAD, AUD and NZD. **Every currency the FX loading table
needs is now present in the repository.** What is missing is the regression script itself, so
the 36 derived FX loadings still cannot be re-derived here and remain marked as such in
`docs/INPUT_PROVENANCE.md`.

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
