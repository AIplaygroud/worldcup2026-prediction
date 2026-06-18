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

## 2026 World Cup Match xG (high weight)

Last verified: 2026-06-18 (cutoff 12:40 UTC+8)

### Files

- `wc2026_match_xg.csv`: match-level WC group-stage xG (one row per finished match).
- `wc2026_team_xg.csv`: team aggregates from finished WC matches only.

### Coverage (Round 1, all groups A–L)

**Collected (24/24 round-1 fixtures):** all opening matches in Groups A–L with Opta xG via FotMob match centres.

| Date (kickoff) | Match | Score | Home xG | Away xG | Source |
|---|---|---|---|---|---|
| 2026-06-11 | Mexico vs South Africa | 2-0 | 1.46 | 0.07 | [FotMob](https://www.fotmob.com/en-GB/matches/south-africa-vs-mexico/1einvt) |
| 2026-06-12 | South Korea vs Czechia | 2-1 | 2.30 | 0.83 | [FotMob](https://www.fotmob.com/en-GB/matches/south-korea-vs-czechia/273opa) |
| 2026-06-12 | Canada vs Bosnia and Herzegovina | 1-1 | 1.23 | 0.96 | [FotMob](https://www.fotmob.com/en-GB/matches/canada-vs-bosnia-herzegovina/23f1qo) |
| 2026-06-13 | USA vs Paraguay | 4-1 | 1.42 | 0.54 | [FotMob](https://www.fotmob.com/en-GB/matches/usa-vs-paraguay/1hr85j) |
| 2026-06-13 | Qatar vs Switzerland | 1-1 | 0.60 | 3.20 | [FotMob](https://www.fotmob.com/en-GB/matches/qatar-vs-switzerland/1beswv) |
| 2026-06-13 | Brazil vs Morocco | 1-1 | 1.26 | 1.37 | [FotMob](https://www.fotmob.com/en-GB/matches/morocco-vs-brazil/1qr4gd) |
| 2026-06-14 | Haiti vs Scotland | 0-1 | 1.05 | 1.05 | [FotMob](https://www.fotmob.com/en-GB/matches/haiti-vs-scotland/1q0g2q) |
| 2026-06-14 | Australia vs Turkey | 2-0 | 1.18 | 1.36 | [FotMob](https://www.fotmob.com/en-GB/matches/turkiye-vs-australia/1gr3uk) |
| 2026-06-14 | Germany vs Curacao | 7-1 | 4.22 | 0.41 | [FotMob](https://www.fotmob.com/en-GB/matches/germany-vs-curacao/k77fsyu) |
| 2026-06-14 | Netherlands vs Japan | 2-2 | 0.78 | 0.59 | [FotMob](https://www.fotmob.com/en-GB/matches/netherlands-vs-japan/1hn72b) |
| 2026-06-14 | Ivory Coast vs Ecuador | 1-0 | 1.52 | 1.01 | [FotMob](https://www.fotmob.com/en-GB/matches/ecuador-vs-ivory-coast/1hl6kp) |
| 2026-06-15 | Sweden vs Tunisia | 5-1 | 1.33 | 0.28 | [FotMob](https://www.fotmob.com/en-GB/matches/tunisia-vs-sweden/1x5290) |
| 2026-06-15 | Spain vs Cape Verde | 0-0 | 2.10 | 0.20 | [FotMob](https://www.fotmob.com/en-GB/matches/cape-verde-vs-spain/1bbtuo) |
| 2026-06-15 | Belgium vs Egypt | 1-1 | 1.35 | 1.08 | [FotMob](https://www.fotmob.com/en-GB/matches/belgium-vs-egypt/2u3bhg) |
| 2026-06-15 | Saudi Arabia vs Uruguay | 1-1 | 0.66 | 1.72 | [FotMob](https://www.fotmob.com/en-GB/matches/uruguay-vs-saudi-arabia/1izuvb) |
| 2026-06-16 | Iran vs New Zealand | 2-2 | 1.50 | 1.24 | [FotMob](https://www.fotmob.com/en-GB/matches/new-zealand-vs-iran/1ar30l) |
| 2026-06-16 | France vs Senegal | 3-1 | 1.79 | 0.53 | [FotMob](https://www.fotmob.com/en-GB/matches/senegal-vs-france/1f8fvo) |
| 2026-06-16 | Iraq vs Norway | 1-4 | 0.80 | 2.52 | [FotMob](https://www.fotmob.com/en-GB/matches/iraq-vs-norway/1oz68o) |
| 2026-06-17 | Argentina vs Algeria | 3-0 | 1.26 | 0.32 | [FotMob](https://www.fotmob.com/en-GB/matches/algeria-vs-argentina/1ehtqa) |
| 2026-06-17 | Austria vs Jordan | 3-1 | 1.69 | 0.46 | [FotMob](https://www.fotmob.com/en-GB/matches/jordan-vs-austria/1my603) |
| 2026-06-18 | Portugal vs DR Congo | 1-1 | 0.65 | 0.87 | [FotMob](https://www.fotmob.com/en-GB/matches/dr-congo-vs-portugal/1s6g4o) |
| 2026-06-18 | Colombia vs Uzbekistan | 3-1 | 1.62 | 1.16 | [FotMob](https://www.fotmob.com/en-GB/matches/colombia-vs-uzbekistan/2dm7x9) |
| 2026-06-18 | England vs Croatia | 4-2 | 3.20 | 0.70 | [FotMob](https://www.fotmob.com/en-GB/matches/england-vs-croatia/2viayw) |
| 2026-06-18 | Ghana vs Panama | 1-0 | 1.31 | 0.75 | [FotMob](https://www.fotmob.com/en-GB/matches/panama-vs-ghana/1bjek0) |

**Re-verification (2026-06-18):** Groups A–H xG re-checked against live FotMob match centres; no Opta revisions detected since 2026-06-16 19:53 UTC+8 (all 16 rows unchanged).

**Missing at this cutoff:** none (0/24 score_only).

### Source hierarchy

1. **Primary:** FotMob match statistics (Opta-powered xG, shots, big chances, possession) — all 24 collected matches.
2. **Cross-check only (not used in CSV):** The Analyst (Opta articles), ESPN/FOX box scores — minor rounding differences vs FotMob on a few fixtures; CSV uses FotMob match-centre values for consistency.
3. **Blocked / unavailable:**
   - **FBref** (`fbref.com/en/comps/676/...`): HTTP 403 from automated fetch; not used.
   - **Understat:** no 2026 WC national-team match feed located.
   - **FIFA official:** scores/highlights only; no downloadable per-match xG table found.

### Recommended layer weights (vs qualifier `recommended_weight` 1.00)

- **WC group-stage match xG:** `recommended_weight = 1.30` (highest layer; same Opta model family as FotMob).
- **WC qualifiers / continental qualifiers:** `1.00` (unchanged baseline in `team_recent_form.csv`).
- **Context competitions (Gold Cup, friendlies, etc.):** keep existing lower weights (0.35–0.75 per row).

Rationale: WC matches are same-tournament, same-opposition-strength context; one R1 sample is still thin — use high weight but cap influence until 2+ WC matches (see integration note below).

### Integration note (45% recent-form pillar)

Within the existing **45% data-driven recent state**, treat `wc2026_team_xg` as a separate sub-layer that should **partially replace** (not add on top of) qualifier-based `recent_xg_per_match` for teams with WC minutes. Suggested blend for a team with `n` WC matches:

`effective_xg = (n * 1.30 * wc_xg + W_prior * recent_xg) / (n * 1.30 + W_prior)`

where `W_prior = 1.00` for teams with qualifier xG and `W_prior = 0.50` for context-only teams (Canada, Mexico, USA). At `n = 1`, WC layer contributes ~57% of the effective rate for qualifier teams — enough to move estimates without overfitting a single game.

All teams in `wc2026_team_xg.csv` carry `quality_flag = thin_sample` until `wc_matches >= 2`.

## Use In Prediction

- Do not mix xG models as if they are identical. Keep source-layer weights in downstream modeling.
- Prefer `wc2026_team_xg.csv` over re-deriving from qualifiers when predicting Group A–L round-2 fixtures; refresh after each completed matchday.
- `opponent_strength_index` is a relative index for comparison, not an absolute probability.
- Non-Big-5 supplements are lower-confidence than Understat because they mix FotMob, Transfermarkt, FBref snapshots, and public leaderboard snippets.
- Injury/suspension and projected XI files are still separate inputs and should be updated before match-level predictions.
