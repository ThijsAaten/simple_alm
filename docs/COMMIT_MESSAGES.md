# Commit messages

---

## Commit 1 — `participant/lifecycle.py`

```
Make sleeve re-seeding deterministic across processes

_reseed_specs() derived each sleeve's RNG offset from Python's built-in
hash(), which is salted per process via PYTHONHASHSEED. Identical runs
with different PYTHONHASHSEED values produced ~0.3% drift in replacement-
ratio results, breaking cross-machine reproducibility.

Replace with _stable_offset(): a fixed SHA-256 digest of the sleeve name,
truncated to the same modulo. Seeds are now identical across processes and
machines; all existing tests pass and the within-process reproducibility
invariant is verified by tests/test_invariants.py.

Also moves the career_average_indexation field comment from the docstring
into an inline block comment (style consistency).
```

---

## Commit 2 — `allocations/` (new package)

```
Bring the country mosaic into the model as a first-class package

The article's actual proposal — a bottom-up country sleeve with China
explicitly capped at 6% — previously lived in the article working bundle
and reached into the model via a hard-coded /home/claude/simple_alm
sys.path. Move it in-repo as the allocations/ package, importing the model
packages normally.

allocations/__init__.py      lazy-export façade (avoids double-import
                             RuntimeWarning when running as __main__)
allocations/country_inputs.py  per-market drift/CAPE/FX inputs sourced
                             from §3.1 Table 1a; proxy markets flagged
                             (real=False); THB-for-IDR/VND noted
allocations/mosaic.py        build_equity_specs(), four canonical
                             allocations (CURRENT / PROPOSED_A /
                             CONSERVATIVE / TIGHT_CHINA); FX wiring:
                             USD 50% hedged, JPY 85% unhedged, Asian
                             EM FX fully unhedged (the thesis)
allocations/preview.py       static blended-return/vol preview table,
                             no Monte Carlo
```

---

## Commit 3 — `examples/run_equity_only.py`, `reproduce_participant.py`, `docs/REPRODUCE.md`

```
Add runnable example, one-command driver, and reproduce runbook

examples/run_equity_only.py
    Equity-only validation: swaps the GlobalEquity block for the country
    mosaic while holding real assets / credit / commodities fixed. Runs
    CURRENT vs PROPOSED A on shared macro paths (common random numbers)
    so differences reflect equity composition, not scenario luck.
    Bootstraps repo root from __file__ — portable, replaces the old
    hard-coded absolute path.

reproduce_participant.py
    One-command driver: runs all four canonical allocations on a single
    shared set of macro paths and prints the real-pot distribution and
    replacement ratio for each. Accepts an optional scenario-count
    argument for faster iteration.

docs/REPRODUCE.md
    Step-by-step runbook: setup, how to run the headline results, how to
    run the equity-only validation and the static preview, how to run
    tests, and a note on the seeding fix that makes results reproducible.
    Also documents the three career_average_indexation modes.
```

---

## Commit 4 — `tests/` (`__init__.py`, `test_invariants.py`)

```
Add invariant tests: weights, China cap, FX keys, indexation, reproducibility

Eight load-bearing properties a reader should be able to trust, runnable
as either pytest tests/ or python -m tests.test_invariants (zero extra
dependencies beyond the model itself):

  test_allocations_sum_to_one         all four allocations sum to 1.0
  test_china_cap_respected            PROPOSED ≤ 6%, TIGHT_CHINA ≤ 3%
  test_every_fx_key_exists_in_fx_model  every mosaic FX key is in FXModel
  test_stable_offset_is_deterministic   SHA-256 hash: same in → same out
  test_mosaic_builds_one_sleeve_per_nonzero_weight
  test_indexation_none_reproduces_nominal_average
  test_wage_indexation_lifts_the_denominator  median RR on conventional scale
  test_within_process_reproducibility  same paths → bit-for-bit same results
```

---

## Commit 5 — `docs/INPUT_PROVENANCE.md`

```
Document input provenance: maps every figure to its article source

Maps every numerical input in allocations/country_inputs.py back to its
§3.1 / §13.6 source so a reader or referee can audit where each figure
comes from:

- Per-country table: drift (= §3.1 r_nom), CAPE now/anchor, FX key,
  article section
- Regional anchors: §13.6 four-region frontier reproduced from §3.1
  Table 1a by construction
- Method note: partial-reversion Gordon-Shiller decomposition, US anchor
  choice (20-yr avg CAPE = 27.5, not long-run median), CAPE data sources
- THB-for-IDR/VND proxy flagged; Vietnam and Singapore flagged as
  illustrative-only proxy markets
- Two exhibits still to be primary-sourced for the journal version noted
```
