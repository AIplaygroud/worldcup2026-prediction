# FBref Big 5 2025-26 Player Form Access Gap

Direct fetch for the 2025-26 Big 5 player standard stats URL returned 403 in this environment.

Candidate source URL:
- https://fbref.com/en/comps/Big5/2025-2026/stats/players/2025-2026-Big-5-European-Leagues-Stats

This is an FBref access gap, not evidence that 2025-26 player xG data is unavailable. The current 2025-26 recent-form layer has been pulled from Understat instead:

- `processed/club_player_form_understat_big5_2025_26.csv`
- `processed/player_form_matched_understat_big5_2025_26.csv`
- `processed/player_form_trusted_understat_big5_2025_26.csv`

Use FBref 2025-26 as an additional cross-check if it becomes accessible. Keep FBref 2024-25 as a stable baseline where Understat coverage or model consistency is insufficient.
