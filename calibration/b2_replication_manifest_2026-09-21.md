# B2 replication manifest — every published number, its script and its data (2026-09-21)

Companion to `b1_reconciliation_2026-09-21.md`. The package lives in the article
repository (`replication/` — README, DATA_DICTIONARY, `run_all.sh`); this manifest maps
each published number to the committed script and data file that produce it.
`bash replication/run_all.sh` regenerates everything below in one command (verified
end-to-end, exit 0, 2026-09-21); the participant model is this public repository,
pinned at the commit containing suite **52 passed** (incl. the EUR-damping regression
test and the W8.11 calibration-hash guard).

Article-repo paths unless marked [model]. Data files as described in
`replication/DATA_DICTIONARY.md`.

| Published number(s) | Script | Data |
|---|---|---|
| Canonical vectors; every portfolio weight in §11.1/§11.4; benchmark | (data file is the source of truth) | `replication/data/canonical_allocation_2026-09-21.csv` |
| EUR return panel (input to every risk statistic) | `exhibits/scripts/build_ret_eur.py` | `exhibits/data/ret_usd.csv`, `fx_levels.csv` |
| §8.6 Panel (a)+(b) anchors, [MS-1]/[MS-2], Exhibit 4 | `build_b1_canonical.py`, `build_markowitz_v2.py`, `plot_markowitz.py` | panel + canonical CSV |
| §8.8 country frontier, [MS-3]/[MS-4], Exhibit 5 | `build_b1_canonical.py` (Table 1a headline + §5.1 sensitivity), `build_markowitz_country.py`, `plot_markowitz_country.py` | panel + canonical CSV |
| Table 6 (all rows incl. W8.11 +3pp), Table 7 | `build_b1_canonical.py` (canonical verdicts), `build_table6_table7.py` (four-region diagnostics) | panel + canonical CSV |
| Table 4, Table 5, §8.1/§8.3 prose correlations | `build_table4_correlations.py` | panel |
| Exhibit 3, §8.3 rolling figures | `build_rolling_corr_60m.py`, `build_exhibit3_rolling_corr.py` | panel |
| §8.9 volatilities ([MS-5]/[MS-6], EUR + USD, full sample + trailing 120m) | `build_b1_canonical.py` section [8] | panel + `ret_usd.csv` |
| §11.1 ex-ante TE (2.83%), IR (0.25 / 0.08) | `build_b1_canonical.py` section [7]; cross-check [model] `tools/compute_te_frontier_w811.py` | panel + canonical CSV |
| No-reversion sensitivity (referee cells + canonical) | `build_b1_canonical.py` section [9] | Table 1a decomposition (in-script, sourced to §3.1) |
| Table 1a machinery, §3.1 CAPE mapping | `build_cape_mapping_v2.py`, `calibrate_v3.py` | `exhibits/data/returns_levels.csv` |
| Exhibit 1 (fiscal composition) | `build_exhibit1_fiscal.py` | in-script sourced series |
| Exhibit 2 (fwd P/E vs implied ROE) | `build_exhibit2_scatter.py` | in-script Table 1 data |
| Exhibit 8 (conversion-chain mosaic) | `build_equity_mosaic.py` | [model] country inputs |
| §8.11 factor decomposition (W4.7 tables) | `run_factor_decomposition_v2.py`, `w5_corr_test.py` | `sources/factors/` (JKP theme CSVs + W4_7 Bloomberg pulls), panel |
| Event study (§9.3 / Exhibit 7): CAR(−1,+1) by tier, placebo-netted | spec released: workbook tabs 1/3/6/7 + `exhibits/event_study_final_2026-09-10.md`; estimation 280d ending t−30, min 120 obs; placebo 40 dates, seed 20260909 | `W5_1_taiwan_lookthrough_pull_2026-09-11.xlsx`; **per-name daily prices Bloomberg-licensed, not redistributable — the one exception, stated in the README** |
| Exhibit 6 (participant pots, both worlds) | `build_exhibit6_participant_wealth.py` + [model] `tools/rerun_multiseed.py` | [model] committed calibration; seeds 42/137/271/314/577; records `output/fxr2_*`, `output/w811_*` |
| V-M3 bond-vol sourcing (long_rate 70bp) | [model] `calibration/check_bond_vol_history_v2.py` | [model] `calibration/data/bloomberg_pull_VM3_and_FX2_v2_2026-08-24.xlsx` |
| FX loadings (16 currencies, derived) | [model] `calibration/fx_loading_calibration.py` (round-2 conventions asserted) | [model] `data/fx_levels.csv`, `fx_bloomberg_legs.csv`, round-2 workbook |

Gaps closed while assembling the package (each was a published number whose builder had
a chat-sandbox path or none at all — the defect class that produced V-C4 and the
Exhibit 3 failure): `w5_corr_test.py` and `run_factor_decomposition_v2.py` read
`/mnt/user-data/uploads` and wrote outside the repo (repointed to `sources/factors/`,
`exhibits/data/`, `results/`; the JKP input filenames had been bracket-mangled by the
sandbox upload); `build_equity_mosaic.py` hard-coded `/home/claude/simple_alm` (now the
same `$SIMPLE_ALM` locator as Exhibit 6); two pickle reads replaced with the committed
CSVs (numpy-2 pickles unreadable under the pinned environment).

Pot-to-income conversion: none used anywhere — Exhibit 6 is a real-pot comparison
(entry-year euros); documented in the README per the referee's note that a pot
comparison suffices absent institution-specific income claims.
