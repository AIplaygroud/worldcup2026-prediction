# Club Player Form Sources

## Parsed in this pull

- Understat Big 5 2025-26 player league stats:
  - Premier League: https://understat.com/league/EPL/2025
  - La Liga: https://understat.com/league/La_liga/2025
  - Bundesliga: https://understat.com/league/Bundesliga/2025
  - Serie A: https://understat.com/league/Serie_A/2025
  - Ligue 1: https://understat.com/league/Ligue_1/2025
- FBref Big 5 2024-25 player standard stats: https://fbref.com/en/comps/Big5/stats/players/Big-5-European-Leagues-Stats

## FBref recent-form candidate

- FBref Big 5 2025-26 player standard stats: https://fbref.com/en/comps/Big5/2025-2026/stats/players/2025-2026-Big-5-European-Leagues-Stats

Direct fetch for FBref 2025-26 returned 403 in this environment, so the 2025-26 recent-form layer uses Understat instead. Keep FBref 2024-25 as a stable cross-check because it uses a different source/model lineage.

## Additional verified references

- DataMB 2025-26 player stats guide: https://datamb.football/guide/
- Goalazo Top 5 Leagues player xG table: https://goalazo.fr/en/joueurs
- FotMob player pages, used for manual supplements where search snippets expose 2025-26 xG, minutes, goals, assists, and ratings:
  - Riyad Mahrez: https://www.fotmob.com/players/278343/riyad-mahrez
  - Houssem Aouar: https://www.fotmob.com/players/776299/houssem-aouar
  - Anis Hadj Moussa: https://www.fotmob.com/players/1576876/anis-hadj-moussa
- Transfermarkt player performance pages, used for appearances, goals, assists, minutes and club status when xG is unavailable.
- PlayerStats.football public xG leaderboards, used only as partial/manual references:
  - Saudi Pro League: https://playerstats.football/saudi-pro-league/stats/xg
  - Eredivisie: https://playerstats.football/eredivisie/stats/xg

## Tested but not stable for this pull

- FBref 2025-26 single-league stats pages returned 403 in this environment.
- FotMob internal `leagueseasondeepstats` API requires signed request headers and timed out in this environment.
- SofaScore exposes useful player and match statistics through internal endpoints, but it is not treated as a stable batch source here because access is undocumented and protected.

## Coverage caveat

Big 5 coverage excludes many World Cup roster players in MLS, Saudi Pro League, Qatar Stars League, Liga MX, Brazil Serie A, Argentina Primera, J.League, K League, African domestic leagues, and second divisions. Use missing coverage outputs to target follow-up sources.
