# Derivation scripts

Scripts that produced calibrated inputs, kept so the derivations can be audited.

| Script | Derives | Re-runnable here? |
|---|---|---|
| `equity_factor_calibration.py` | `mbeta` and `idio_vol` per market, and the 15.5% equity factor volatility (`allocations/country_inputs.py`, `scenarios/engine.py`) | **No** — see below |

## Data dependency

`equity_factor_calibration.py` reads `ret_usd.pkl` and `fx_levels.pkl` from an absolute
path (`/mnt/user-data/uploads`) that is not part of this repository. **The script documents
the method but cannot be executed from a clean clone.** It is committed because a derivation
you can read is worth more than one you cannot, and because `docs/INPUT_PROVENANCE.md`
records these inputs as *Derived* — that claim needs the method visible.

What *was* verified without the source data: the resulting table is internally consistent.
For all seven markets, `market_beta² × var(F) + idio_vol²` reproduces the stated total
volatility to within 0.001 and the stated R² to two decimals. That establishes the table is
self-consistent, not that the underlying regression is correct.

To make it re-runnable, commit the two pickles (or a CSV extract of the columns used:
`USA, Europe, Japan, China, India, Korea, Taiwan, World` monthly returns and the matching FX
levels) and change `U` at the top of the script to a repo-relative path.

## Related tooling, kept elsewhere

`tools/build_fx_bloomberg_sheet.py` generates `data/fx_history_bloomberg.xlsx`, a Bloomberg
add-in workbook of live `=BDH()` formulas for the Asian FX legs. It gathers an input rather
than deriving one, so it sits under `tools/` rather than here. The workbook contains formulas
only — no Bloomberg data is redistributed.
