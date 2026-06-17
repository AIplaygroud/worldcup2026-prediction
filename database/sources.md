# Data Sources

## Official Squad Source

- FIFA official squad confirmation article: https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/fifa-world-cup-2026-squads-confirmed
- FIFA official squad list PDF: https://fdp.fifa.org/assetspublic/ce281/pdf/SquadLists-English.pdf

## Roster Cross-Check Sources

- Sporting News roster table: https://www.sportingnews.com/ca/soccer/news/world-cup-rosters-2026-list-national-team-squads/9d7ae885a5d800ef6b6a3c52
- Olympics complete squads: https://www.olympics.com/en/news/2026-fifa-world-cup-football-teams-squads-players-complete-list
- Al Jazeera all squads: https://www.aljazeera.com/sports/2026/6/2/fifa-world-cup-2026-full-squads-48-teams-players
- MLSSoccer all squads: https://www.mlssoccer.com/competitions/fifa-world-cup/news/2026-fifa-world-cup-all-squads

## Future xG Sources

- xGscore for World Cup, qualifiers, and friendlies xG summaries.
- FootyStats for qualifier-level xG and xGA summaries.
- FotMob and SofaScore for match-level statistics and lineups.
- FBref, Understat, and Transfermarkt for player club form and squad context.

## 2026 World Cup Qualifier xG Sources

- UEFA: https://footystats.org/international/wc-qualification-europe/xg
- AFC: https://footystats.org/international/wc-qualification-asia/xg
- CAF: https://footystats.org/international/wc-qualification-africa/xg
- CONCACAF: https://footystats.org/international/wc-qualification-concacaf/xg
- CONMEBOL: https://footystats.org/international/wc-qualification-south-america/xg
- OFC: no verified public team xG table parsed in this pull; see `xGdatabase/raw/world_cup_qualifiers/ofc/data_gap.md`.

## Context xG Sources

- UEFA Euro 2024: https://footystats.org/uefa-euro
- Copa America 2024: https://footystats.org/international/copa-america/xg
- Africa Cup of Nations 2023: https://footystats.org/international/africa-cup-of-nations/xg
- AFC Asian Cup 2023: https://footystats.org/international/afc-asian-cup/xg
- CONCACAF Gold Cup 2025: https://footystats.org/international/concacaf-gold-cup/xg
- International Friendlies 2026: https://footystats.org/international/international-friendlies/xg
- UEFA Nations League 2024-25: not parsed in this pull; candidate FBref/FootyStats/xGscore sources are listed in `xGdatabase/raw/continental_tournaments/nations_league_2025/data_gap.md`.

## Club Player Form Sources

- Understat Big 5 2025-26 player league stats:
  - Premier League: https://understat.com/league/EPL/2025
  - La Liga: https://understat.com/league/La_liga/2025
  - Bundesliga: https://understat.com/league/Bundesliga/2025
  - Serie A: https://understat.com/league/Serie_A/2025
  - Ligue 1: https://understat.com/league/Ligue_1/2025
- FBref Big 5 2024-25 player standard stats: https://fbref.com/en/comps/Big5/stats/players/Big-5-European-Leagues-Stats
- FBref Big 5 2025-26 player standard stats candidate: https://fbref.com/en/comps/Big5/2025-2026/stats/players/2025-2026-Big-5-European-Leagues-Stats
- FBref single-league 2025-26 candidates, for example:
  - Primeira Liga: https://fbref.com/en/comps/32/stats/Primeira-Liga-Stats
  - Eredivisie: https://fbref.com/en/comps/23/stats/Eredivisie-Stats
  - Super Lig: https://fbref.com/en/comps/26/stats/Super-Lig-Stats
  - Major League Soccer: https://fbref.com/en/comps/22/stats/Major-League-Soccer-Stats
  - Saudi Pro League: https://fbref.com/en/comps/70/stats/Saudi-Pro-League-Stats
- FotMob player pages and season-stat API references:
  - Search/player pages, e.g. https://www.fotmob.com/players/278343/riyad-mahrez
  - Season stats API reference: https://worldfootballr.sportsdataverse.org/reference/fotmob_get_season_stats.html
- Transfermarkt player performance pages for appearances, goals, assists, minutes, current club, and contract context.
- PlayerStats.football public xG leaderboards where accessible:
  - Saudi Pro League xG: https://playerstats.football/saudi-pro-league/stats/xg
  - Eredivisie xG: https://playerstats.football/eredivisie/stats/xg
- SofaScore player/match pages remain a fallback for manual verification where FotMob/Transfermarkt disagree.
- DataMB 2025-26 player stats reference: https://datamb.football/guide/
- Goalazo Top 5 Leagues 2025-26 player xG reference: https://goalazo.fr/en/joueurs
- worldfootballR FBref extraction docs: https://jaseziv.github.io/worldfootballR/articles/extract-fbref-data.html
- Apify FBref scraper reference: https://apify.com/parseforge/fbref-scraper

Current preferred parsed data uses Understat Big 5 2025-26 as the recent-form layer. Enhanced name matching currently covers 615 roster players. FBref 2025-26 direct fetch and single-league pages returned 403 in this environment, while FotMob API tests timed out locally; therefore FotMob/Transfermarkt/PlayerStats are recorded as lower-weight manual or partial supplements until a stable batch path is available.
