# xGdatabase

This folder stores expected goals data for the World Cup 2026 prediction workflow.

## Current Pull

The current pull focuses only on 2026 FIFA World Cup qualifiers, as requested.

## Files

- `processed/team_xg_summary.csv`: team-level xG/xGA summary by confederation. Values are per match.
- `processed/qualifier_xg_coverage.csv`: coverage and data quality by confederation.
- `raw/world_cup_qualifiers/*/footystats_xg_snapshot.txt`: source snapshots where available.
- `raw/world_cup_qualifiers/ofc/data_gap.md`: OFC xG source gap note.

## Caveat

FootyStats uses its own xG model. Keep `source` and `source_url` when using the data, and avoid mixing these values directly with Opta, StatsBomb, FotMob, or Understat xG without calibration.

## Context Pull

Additional context data has been pulled for continental tournaments and deweighted international friendlies.

- `processed/context_xg_summary.csv`: team-level xG/xGA for context competitions.
- `processed/context_xg_coverage.csv`: coverage and data quality notes.
- `raw/continental_tournaments/`: source snapshots for Euro, Copa America, AFCON, Asian Cup, Gold Cup, and Nations League gap notes.
- `raw/international_friendlies/`: source snapshot for 2026 international friendlies.

Recommended weights are intentionally below 2026 World Cup qualifiers unless the competition is directly relevant to the teams being compared.

## Prediction Summary Tables

The planned prediction-ready summary tables have been generated from the parsed data:

- `processed/team_recent_form.csv`: one row per World Cup team, with weighted xG/xGA/xGD from qualifiers and context competitions.
- `processed/player_form_summary.csv`: one row per roster player, preferring 2025-26 Understat, then non-Big-5/manual 2025-26 supplements, then FBref 2024-25 fallback.
- `processed/opponent_strength.csv`: relative opponent strength index built from `team_recent_form.csv`.
- `processed/data_quality_notes.md`: known source gaps, coverage counts, and modeling caveats.

These summary tables are intended for prediction inputs. The lower-level parsed tables remain the audit trail.

## Club Player Form Pull

Club-form current-season data has been added from Understat Big 5 2025-26 player stats.

- `processed/club_player_form_understat_big5_2025_26.csv`: parsed 2025-26 Big 5 player form table from Understat.
- `processed/player_form_matched_understat_big5_2025_26.csv`: roster matches against the Understat 2025-26 Big 5 data.
- `processed/player_form_trusted_understat_big5_2025_26.csv`: higher-confidence subset where name and club align.
- `processed/player_form_missing_understat_coverage.csv`: roster players not found in the Understat Big 5 pull.
- `processed/player_form_coverage_by_team_understat_2025_26.csv`: team-level 2025-26 coverage summary.

The Understat matching script now normalizes accents, FIFA PDF duplicated shirt names, short football names, and same-club fuzzy matches. This reduced false missing rows and raised the current Understat match count to 615 roster players.

Supplement files for non-Big-5 and non-Understat gaps:

- `processed/player_form_supplement_priority.csv`: remaining missing-player distribution by club country and recommended follow-up sources.
- `processed/player_form_manual_supplement_2025_26.csv`: manually verified high-value player supplements from FotMob/Transfermarkt/PlayerStats references.
- `processed/player_form_non_big5_target_gaps.csv`: missing-player target list for Saudi, MLS, Eredivisie, Super Lig, Primeira Liga, Qatar, and Iran sources.
- `processed/player_form_non_big5_source_status.csv`: source availability and automation status for those target non-Big-5 leagues.
- `processed/player_form_non_big5_supplement_2025_26.csv`: normalized supplement layer promoted into `player_form_summary.csv`.
- `processed/player_form_current_coverage_summary.csv`: combined coverage summary using Understat plus manual supplements.

FBref Big 5 2024-25 player standard stats remain available as a stable baseline and cross-check:

- `processed/club_player_form_big5_2024_25.csv`: parsed Big 5 player form table.
- `processed/player_form_matched_big5_2024_25.csv`: conservative matches between the 48-team roster and FBref Big 5 data.
- `processed/player_form_missing_coverage.csv`: roster players not found in Big 5 data.
- `processed/player_form_coverage_by_team.csv`: team-level coverage summary.

Prefer 2025-26 Understat for current form. Use non-Big-5 supplements at lower weight because they mix FotMob, Transfermarkt, FBref snapshots, and public leaderboard references. The attempted `football-data-mcp` SofaScore route supports Eredivisie and Primeira Liga in principle, but failed in this environment when Botasaurus tried to download a Windows runtime DLL over SSL. Use 2024-25 FBref as a baseline when 2025-26 coverage is missing or when comparing across data models.
