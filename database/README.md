# World Cup 2026 Prediction Database

This database stores external evidence for the World Cup prediction skill.

## Structure

- `xGdatabase/`: reserved for xG, xGA, match stats, player form, and competition-level data.
- `48-team-roster/`: final squad data, roster sources, squad depth summaries, and starting XI projections.
- `competition/`: 2026 World Cup advancement rules, match environment/law changes for prediction, group assignments, standings, round-of-32 template, and full Annex C lookup table (495 rows).

The current implementation populates the roster, competition structure, qualifier/context xG tables, club-player form layers, and prediction-ready summary tables. Club-player form currently combines Understat Big 5 2025-26, targeted non-Big-5 supplements, and FBref Big 5 2024-25 fallback rows.
