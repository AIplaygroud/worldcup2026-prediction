# Data Quality Notes

Last verified: 2026-06-15

## Generated Summary Tables

- `team_recent_form.csv`: weighted team xG/xGA recent-form summary from qualifiers and context competitions.
- `player_form_summary.csv`: one row per roster player, preferring the 2025-26 layer with the highest recommended_weight (Understat Big-5, manual/non-Big-5 supplements, MLS-USL ASA API, FootyStats non-Big-5), then FBref 2024-25 fallback.
- `opponent_strength.csv`: relative team strength index derived from `team_recent_form.csv`.

## Known Team xG Gaps

- WC Qualification Oceania: missing_xg - No verifiable public team xG table parsed; Cloudflare blocked direct fetch.
- UEFA Nations League 2024-25: missing_xg - FootyStats current page empty for 2026/27; FBref direct fetch 403.
- Teams with context-only team xG: Canada, Mexico, USA.

## Player Form Coverage

- Understat 2025-26 rows: 491
- Manual 2025-26 supplement rows: 0
- Non-Big-5 2025-26 supplement rows: 7
- MLS/USL (ASA) 2026 rows: 37
- Non-Big-5 FootyStats 2025-26 rows: 360
- FBref 2024-25 fallback rows: 38
- Missing player-form rows: 315

## Non-Big-5 Club Form Gaps

- Saudi Pro League (KSA): 43 target missing players; automation_status=resolved_41_of_43; Filled via FootyStats 2025/26 per-player lookup -> player_form_non_big5_footystats_supplement.csv (xG/npxG/xA/shots/minutes). 41/43; not found: Fabinho (Al Ittihad), Mohammed Alowais (Al Ula, 2nd tier).
- Major League Soccer (USA): 39 target missing players; automation_status=resolved_38_of_39; Filled via ASA official xG API (mls+uslc), seasons 2025/2026 -> player_form_mls_usl_supplement_2026.csv. 38/39 matched with per-90 xG/xA; only Markhus Lacroix absent from ASA (no USL minutes captured).
- Eredivisie (NED): 36 target missing players; automation_status=resolved_30_of_36; Filled via FootyStats 2025/26 per-player lookup -> player_form_non_big5_footystats_supplement.csv. 30/36; 6 not found are 2nd-tier (Eerste Divisie) clubs: Den Bosch, RKC, Telstar, VVV, Almere -> no Eredivisie data.
- Super Lig (TUR): 37 target missing players; automation_status=resolved_35_of_37; Filled via FootyStats 2025/26 per-player lookup -> player_form_non_big5_footystats_supplement.csv (xG/npxG/xA/shots/minutes). 35/37; not found: Ryan Mendes & Leandro Bacuna (both Iğdır FK, 1. Lig 2nd tier, no Süper Lig data).
- Primeira Liga (POR): 27 target missing players; automation_status=resolved_19_of_27; Filled via FootyStats 2025/26 per-player lookup -> player_form_non_big5_footystats_supplement.csv. 19/27; 8 not found (Vozinha, Yannick Semedo, Stopira, Sidny Cabral, Pierre, Fortune, Konan, Deniz Gul) - bench/fringe or no FootyStats player page.
- Qatar Stars League (QAT): 29 target missing players; automation_status=resolved_28_of_29; Filled via FootyStats 2025/26 per-player lookup -> player_form_non_big5_footystats_supplement.csv (FootyStats DOES expose Stars League player xG). 28/29; only Lucas Mendes (Al Wakrah) not found.
- Persian Gulf Pro League (IRN): 23 target missing players; automation_status= basic); 2026-06-15

## Use In Prediction

- Do not mix xG models as if they are identical. Keep source-layer weights in downstream modeling.
- `opponent_strength_index` is a relative index for comparison, not an absolute probability.
- Non-Big-5 supplements are lower-confidence than Understat because they mix FotMob, Transfermarkt, FBref snapshots, and public leaderboard snippets.
- Injury/suspension and projected XI files are still separate inputs and should be updated before match-level predictions.
