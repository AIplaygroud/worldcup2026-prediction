# 48-Team Roster Database

This folder stores the 2026 FIFA World Cup final squad data for all 48 teams.

## Files

- `processed/squads_48_teams.csv`: parsed 48-team final roster table.
- `processed/squad_depth_summary.csv`: position-count summary by team.
- `processed/projected_starting_xi.csv`: template for match-level starting XI projections.
- `processed/injury_suspension_notes.md`: replacement, injury, and suspension notes.

## Source Policy

Use FIFA's official squad list PDF as the primary authority. Public roster tables from Sporting News, Olympics, Al Jazeera, MLSsoccer, FotMob, SofaScore, and Transfermarkt can be used for cross-checking fields such as shirt number, caps, age, club, and position.

Final squads were confirmed by FIFA on 2026-06-02. Serious injury or illness replacements may still occur up to 24 hours before a team's first match, so `last_verified` must be updated after each roster check.
