# Phase 04A R2 Scenario Weights Build Report

Generated: 2026-06-20T18:12:04

## Inputs

- `database\team_style\staging\team_tactical_profile_48_candidate.csv`
- `database\team_style\staging\tactical_matchup_matrix_R2_candidate.csv`
- `database\eventflow\processed\eventflow_scenario_weights.csv` (preserve 68 rows for 4 matches)
- `scripts/build_eventflow_scenario_weights.py` (sandbox, 20 new matches)
- `database/competition/wc2026_match_id_mapping.csv` (round==2)

## Generation Summary

- R2 expected match count: **24**
- candidate row count: **408**
- preserved existing scenario rows: **68**
- new generated scenario rows: **340**
- min confidence: **0.7000**
- max confidence: **0.7500**
- avg confidence: **0.7037**
- fallback rows count: **0**
- processed files changed: **no**
- realtime data used: **no**
- prediction chain executed: **no**
