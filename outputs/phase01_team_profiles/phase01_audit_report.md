# Phase 01 Audit Report

Generated: 2026-06-20

## 3.1 File Existence

| File | Exists | Rows | Columns |
|---|---|---:|---|
| `database/competition/group_assignments.csv` | yes | 48 | 4 |
| `database/competition/wc2026_match_id_mapping.csv` | yes | 72 | 8 |
| `database/competition/wc2026_group_fixtures.csv` | yes | 72 | 17 |
| `database/team_style/raw/raw_team_phase_metrics.csv` | yes | 8 | 26 |
| `database/team_style/raw/raw_match_state_response.csv` | yes | 8 | 14 |
| `database/team_style/processed/team_tactical_profile.csv` | yes | 8 | 27 |
| `database/team_style/processed/team_match_state_response.csv` | yes | 8 | 14 |
| `database/team_style/processed/team_formation_matchups.csv` | yes | 4 | 20 |
| `database/team_style/processed/tactical_matchup_matrix.csv` | yes | 4 | 25 |
| `database/eventflow/processed/eventflow_scenario_weights.csv` | yes | 68 | 40 |

## 3.2 Team Coverage

- expected_teams_count: **48**
- raw_team_phase_metrics_teams_count: **8**
- team_tactical_profile_teams_count: **8**
- missing_in_raw_team_phase_metrics (40): Algeria, Argentina, Austria, Belgium, Bosnia and Herzegovina, Canada, Cape Verde, Colombia, Croatia, Curacao, Czechia, DR Congo, Ecuador, Egypt, England, France, Germany, Ghana, Iran, Iraq, Ivory Coast, Japan, Jordan, Mexico, Netherlands, New Zealand, Norway, Panama, Portugal, Qatar, Saudi Arabia, Senegal, South Africa, South Korea, Spain, Sweden, Switzerland, Tunisia, Uruguay, Uzbekistan
- missing_in_team_tactical_profile (40): Algeria, Argentina, Austria, Belgium, Bosnia and Herzegovina, Canada, Cape Verde, Colombia, Croatia, Curacao, Czechia, DR Congo, Ecuador, Egypt, England, France, Germany, Ghana, Iran, Iraq, Ivory Coast, Japan, Jordan, Mexico, Netherlands, New Zealand, Norway, Panama, Portugal, Qatar, Saudi Arabia, Senegal, South Africa, South Korea, Spain, Sweden, Switzerland, Tunisia, Uruguay, Uzbekistan
- extra_teams_not_in_group_assignments: —

## 3.3 Match Matrix Coverage (audit only)

- expected_group_matches_count: **72**
- team_formation_matchups_count: **4** (unique match_ids: 4)
- tactical_matchup_matrix_count: **4** (unique match_ids: 4)
- eventflow_scenario_weights_match_count: **4**
- eventflow_scenario_weights_row_count: **68**
- missing_match_ids_in_formation_matchups: 68
- missing_match_ids_in_tactical_matchup_matrix: 68
- missing_match_ids_in_eventflow_scenario_weights: 68
