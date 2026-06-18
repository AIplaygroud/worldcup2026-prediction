# 2026 FIFA World Cup Advancement Rules

> Scope: reusable competition rules for prediction and standings logic. Betting-settlement rules remain in `reference/jingcai-football-simulation-rules.md`.

## Format

- 48 teams are split into 12 groups, A through L.
- Each group has 4 teams.
- Group stage uses a single round-robin format: each team plays 3 matches.
- A win is worth 3 points, a draw 1 point, and a loss 0 points.
- 32 teams advance to the knockout stage:
  - 12 group winners
  - 12 group runners-up
  - 8 best third-placed teams

## Group Ranking

Teams in each group are ranked by:

1. Points in all group matches
2. Goal difference in all group matches
3. Goals scored in all group matches
4. Points in matches between tied teams
5. Goal difference in matches between tied teams
6. Goals scored in matches between tied teams
7. Fair-play points
8. Drawing of lots

## Best Third-Placed Teams

Third-placed teams are ranked across all groups by:

1. Points
2. Goal difference
3. Goals scored
4. Fair-play points
5. Drawing of lots

The top 8 third-placed teams advance.

## Knockout Stage

- Knockout matches are single-elimination.
- If level after 90 minutes, extra time is played.
- If still level after extra time, the winner is decided by penalties.
- For prediction outputs, distinguish match winner from 90-minute result when the user asks about betting or simulated betting, because betting settlement in this project follows `reference/jingcai-football-simulation-rules.md`.

## Data Files

- `group_assignments.csv`: official project group allocation used by the prediction skill.
- `group_standings.csv`: current project standings derived from `database/xGdatabase/processed/wc2026_match_xg.csv`.

