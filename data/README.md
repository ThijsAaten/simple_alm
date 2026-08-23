# Calibration source data

CSV is the canonical format here. Everything in this directory is monthly, indexed on a
`date` column of month-end timestamps.

| File | Rows × cols | Span | Quote convention |
|---|---|---|---|
| `ret_usd.csv` | 302 × 11 | 2001-03 … 2026-04 | MSCI total returns **in USD**, decimal (0.05 = 5%) |
| `fx_levels.csv` | 303 × 8 | 2001-02 … 2026-04 | FX levels **per EUR** (`USD` = USD per EUR, `JPY` = JPY per EUR) |
| `fx_bloomberg_legs.csv` | 307 × 9 | 2001-01 … 2026-07 | FX levels **per USD** — except `EURUSD`, which is USD per EUR |
| `fx_history_bloomberg.xlsx` | — | — | The Bloomberg workbook the legs were pulled with |

**The two quote conventions are different and this matters.** `fx_levels.csv` is per-EUR;
`fx_bloomberg_legs.csv` is per-USD. Each file keeps the convention it was produced in rather
than being silently harmonised — a direction error in a currency conversion is exactly the
class of defect this repository has repeatedly found, and a conversion applied here would be
invisible at the point of use. Convert explicitly at the call site.

## Truncation — read before re-deriving

`fx_bloomberg_legs.csv` stops at **2026-07**. The workbook was pulled with an end date of
2026-12-31, which is in the future; Bloomberg's `Fill=P` carries the last observation forward,
so every leg repeats its July value through December. Those five rows are dropped on
conversion. **A re-derivation that does not truncate will silently dilute every estimate with
a run of zero returns.**

## Why CSV and not the original pickles

The equity factor calibration originally read `ret_usd.pkl` and `fx_levels.pkl`. Those were
written by numpy 2.x and **cannot be read by the environment this repository declares** in
`requirements.txt` (`numpy>=1.26`) — `pd.read_pickle` fails with
`ModuleNotFoundError: No module named 'numpy._core.numeric'`, and a module-alias shim does
not rescue it. Committing them would have looked like reproducibility without being it.

Pickle is also version-coupled, opaque to diff, unreviewable, and executes arbitrary code on
load. CSV costs about 140 KB for the whole dataset and is readable by anything.

Conversion is done by `calibration/convert_source_data.py` and is verified: the equity factor
calibration run from these CSVs reproduces the published `market_beta` / `idio_vol` table and
the 15.5% factor volatility to their full stated precision, **using the repository's own
numpy 1.26**. The pickles themselves are gitignored — the CSVs supersede them, and keeping
both would leave it ambiguous which is canonical.

Round-trip precision is exact to within one unit in the last place (~1e-16), a `float_format`
artefact far below the precision of the underlying data. Verified immaterial: betas computed
from CSV differ from betas computed from pickle by at most 7.8e-16.

## What each file supports

- **`ret_usd.csv` + `fx_levels.csv`** fully reproduce the **equity market factor** calibration
  (`calibration/equity_factor_calibration.py`). USA, Europe, Japan, China, India, Korea and
  Taiwan are all present. Indonesia, Vietnam and Singapore are **not** — consistent with those
  three being marked JUDGEMENT in `allocations/country_inputs.py`.
- **`fx_bloomberg_legs.csv`** supplies the four currencies (IDR, THB, SGD, VND) that
  `fx_levels.csv` lacks, plus **CHF, CAD, AUD and NZD**. Together the two files cover every
  currency in the model — all sixteen. The loading regression is committed
  (`calibration/fx_loading_calibration.py`) and reproduces every loading in `assets/fx.py`;
  the CHF/CAD/AUD/NZD legs closed **V-D5** on 2026-08-23, retiring the AUD-proxies-NZD
  substitution, the model's last FX proxy.

## Licensing

These are derived MSCI and Bloomberg series. They are committed at the repository owner's
direction. Anyone forking or redistributing this repository should satisfy themselves that
their own licence permits it.
