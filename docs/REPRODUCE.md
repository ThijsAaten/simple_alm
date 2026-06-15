# Reproduce

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

The article source and its figure-build scripts live in the **article working
bundle** (not this model repo). The model here generates the participant-wealth
exhibit; the CAPE-mapping, Markowitz and fiscal exhibits are built by the bundle's
`scripts/`, which read the data workbook. See the bundle's own `README.md`. To
rebuild the PDF once the exhibits are in place:

```bash
bash build_article.sh asia_pension_allocation_article_v4_2026-05-15      # margin-note build
bash build_article_faj.sh asia_pension_allocation_article_v4_2026-05-15  # FAJ two-column
```

Requires pandoc 3.x, xelatex (TeX Live 2023+), python3. See `docs/INPUT_PROVENANCE.md`
for where each input comes from.
