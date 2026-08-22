# Reproduce

> ## File-naming rule for the article
>
> **The date in the filename is the VERSION date. New content means a new name.
> There is exactly one live master.**
>
> Applied 2026-08-22. Before that, four different documents — 921, 962, 1,059 and
> 1,289 lines — all carried the name `..._v4_2026-05-15.md`, because the date had
> drifted into meaning "the date the v4 branch opened" rather than "the date of
> this content". That makes it impossible to tell which file an exhibit or a
> review was built against.
>
> Current state:
>
> | File | Lines | Status |
> |---|---:|---|
> | `article/asia_pension_allocation_article_v4_2026-08-22.md` | 1,289 | **live master** (contains §13.11) |
> | `_archive/asia_pension_allocation_article_v4_2026-08-14.md` | 1,059 | superseded |
>
> Superseded versions go to `_archive/` under their own version date. `build_article.sh`
> takes the basename as its first argument, so a rename needs no change to the script —
> only to the invocation, and to this file.


A runbook for reproducing the participant-wealth results from a clean clone. The
model is fully synthetic (Monte Carlo from sleeve parameters — no market-data
files needed) and, since the seeding fix below, deterministic across machines.

## Setup

```bash
git clone <repo-url> && cd simple_alm
python -m pip install -r requirements.txt        # numpy, pandas, matplotlib
```

Run everything from the **repo root** so the top-level packages (`assets`,
`portfolio`, `participant`, `allocations`, …) resolve. The example, driver and
tests also bootstrap the repo root onto `sys.path` from their own location, so
they work from any working directory.

## Participant-wealth results (the headline)

```bash
python reproduce_participant.py            # 500 scenarios, all four allocations
python reproduce_participant.py 200        # faster
```

Prints the real-pension-pot distribution (entry-year EUR) and the replacement
ratio for Current / Proposed A / Conservative (C) / Tight-China (D), all on one
shared set of macro paths so the comparison is paired. Proposed A and D land
materially above Current; D ≈ A demonstrates that the tight China cap costs
almost nothing in expected wealth.

To run the bond-side nested attribution under baseline vs EUR financial repression (Option C):

```bash
python -m examples.run_attribution        # baseline vs repression, all four attribution steps
```

To price the China (CGB) dial that block leaves at 0% by default — swept across
0/1/2/3/5% of the LHP, both worlds, same seeding:

```bash
python -m examples.run_cgb_dial           # 1000 scenarios; or: python -m examples.run_cgb_dial 200
python -m examples.run_cgb_dial --flat-lr # downside: CGB long-run yield pinned at 1.8%
```

Writes `output/cgb_dial_sweep.csv` (and `..._flat_lr.csv`); the read-out is in
`output/cgb_dial_findings.md`.

To run the FX inflation-loading sample-period sensitivity (full-sample vs post-2017):

```bash
python -m examples.run_fx_loading_sensitivity     # 1000 scenarios
```

The 2026-08 fixes to FX stepping, CGB calibration and the FX loading table — with
before/after attribution — are written up in `output/simple_alm_fixes_summary.md`.

To inspect just the equity-only Current-vs-A validation:

```bash
python -m examples.run_equity_only         # or: python -m examples.run_equity_only 200
```

To see the static (no-Monte-Carlo) allocation preview, or rebuild the mosaic:

```bash
python -m allocations.preview
python -m allocations.mosaic
```

## Tests

```bash
pytest tests/                              # if pytest is installed
python -m tests.test_invariants            # zero-dependency fallback
```

The invariants cover: allocations sum to 1.0 and respect the China cap, every FX
key the mosaic references exists in the FX model, the replacement-ratio
indexation behaves as documented (`"none"` reproduces the legacy nominal
average; `"wage"` lifts the denominator onto a conventional scale), the mosaic
wires into the RSP, and runs are reproducible.

## Reproducibility

All randomness flows from a single base seed (`main_participant.SEED`): the macro
scenario engine, each sleeve's idiosyncratic noise, and the FX model. Sleeve
seeds are derived with a **process-stable** hash (`participant.lifecycle._stable_offset`),
so repeated runs reproduce bit-for-bit across processes and machines. (The
earlier use of Python's built-in `hash()` was salted per process and caused a
~0.3% run-to-run drift; that is fixed.)

## Replacement-ratio basis

`ParticipantConfig.career_average_indexation` controls the middelloon denominator:

- `"wage"` (default) — revalue each year's pensionable salary to retirement-year
  terms by economy-wide nominal wage growth (CPI × structural real-wage drift),
  excluding individual promotion jumps. Conventional *geïndexeerd middelloon*.
- `"price"` — revalue by realised CPI only.
- `"none"` — raw nominal average (legacy; understates the denominator and
  overstates the replacement ratio).

## Rebuilding the article PDF and exhibits

The article source and its figure-build scripts live in the **article project**,
which is a separate local repository and is not this model repo. It holds the
unpublished manuscript, is **private and local-only** — no remote, and it should
not be given a public one — and was placed under version control on 2026-08-22.

The model in *this* repository generates the participant-wealth exhibit (Exhibit 6);
the CAPE-mapping, Markowitz and fiscal exhibits are built by the article project's
own scripts, which read its data workbook. To rebuild the PDF once the exhibits are
in place, from the article project's `article/` directory:

```bash
bash build_article.sh asia_pension_allocation_article_v4_2026-08-22      # margin-note build
bash build_article_faj.sh asia_pension_allocation_article_v4_2026-08-22  # FAJ two-column
```

Requires pandoc 3.x, xelatex (TeX Live 2023+), python3. See `docs/INPUT_PROVENANCE.md`
for where each input comes from.


---

## Which exhibits are model output and which are market data

Easy to conflate, and the distinction decides what a reader can check.

| Exhibit / figure | Kind | Regenerate with |
|---|---|---|
| **Exhibit 6** — nested attribution, both worlds | **Model output** | `python -m examples.run_attribution 1000` |
| CGB dial sweep | **Model output** | `python -m examples.run_cgb_dial 1000` |
| Participant fan charts, replacement-ratio distribution | **Model output** | `python main_participant.py` |
| Allocation preview: `E[r]loc`, `+FX`, `~vol` columns | **Model output** (closed-form, no Monte Carlo) | `python -m allocations.preview` |
| §3.1 Table 1a inputs: `drift`, CAPE now, CAPE anchor | **Market data** — not produced here | — |
| Sovereign 10y yields in the bond overlay | **Market data** | — |
| Equity `mbeta` / `idio` and the 15.5% factor volatility | **Market data → derived** | `python calibration/equity_factor_calibration.py` — reproducible |
| FX loadings | **Market data → derived** | `python calibration/fx_loading_calibration.py` — runs, but see V-F1 |
| FX history for re-deriving the FX inputs | **Market data** | `data/fx_history_bloomberg.xlsx` — needs a Bloomberg terminal |

**One derivation cannot be re-run from a clean clone.** The equity market factor now can:

```bash
python calibration/equity_factor_calibration.py    # reproduces the published betas
```

The FX loading regression is also runnable now:

```bash
python calibration/fx_loading_calibration.py   # prints derived loadings AND their disagreement
```

and since 2026-08-22 it reproduces **all three** columns exactly — the loadings in
`assets/fx.py` were re-derived from it (V-F1 resolved). A test asserts the script and the
model cannot drift apart.

**Current exhibit record: `output/vm7_attribution.csv`, `output/vm7_cgb_dial.csv`,
`output/vm7_pot_distributions.csv`**, produced by `python tools/rerun_multiseed.py 1000 vm7`.
They supersede `output/fx_*.csv`, which remain committed as the previous record. See
`output/vm7_ramp_summary.md`. Everything in the "Model output" rows above **is** fully
reproducible from this repository.

## Regenerating Exhibit 6

```bash
python -m examples.run_attribution 1000
```

Prints both panels: the four waypoints as levels and as marginal contributions, under the
no-repression baseline and the EUR financial-repression world (12 years pinned, 3-year transitions).

For the multi-seed standard deviations that should accompany any published figure — levels
move with the random draw sequence and are not interpretable on a single seed — the per-seed
record behind the current numbers is committed at `output/validated_attribution.csv`.

> **Panel (b), the pot distribution, is not yet publication-ready.** It is a pure dispersion
> claim, and validation finding **V-M3** (long-bond volatility 22.7% against a plausible
> 10–15%) is still open. Panel (a), the marginal contributions, is sound. See
> `docs/VALIDATION_REPORT.md`.

## Verifying the install

Every command in this file was re-run on 2026-08-22 against the committed tree. The fastest
check that a clone is working:

```bash
python -m pytest tests/ -q          # 43 passed
python -m examples.run_attribution 20   # a few seconds; numbers will be noisy at N=20
```
