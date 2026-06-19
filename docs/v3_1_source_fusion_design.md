# V3.1 Source Fusion Design

## Goal
Add a multi-source evidence layer to EventFlow V3.0 so the Agent can reason like a tactical observer while still being auditable.

## What is fused
- Live commentary events: pressure periods, shots, corners, cards, VAR, injuries, substitutions, tactical shifts.
- Professional match reports: match turning points, defensive vulnerability, pressing success/failure, goalkeeper errors, set-piece dominance.
- Tactical previews: expected formation, player role, pressing height, build-up route, transition risk.
- Open event data: historical reference patterns and validation logic.

## What is not stored
- Full article text.
- Full live-text transcript.
- Paywalled content.
- Large copyrighted passages.

## Why this still works
EventFlow does not need article prose. It needs structured claims:

```json
{
  "match_id": "66456932",
  "minute": "50",
  "team": "Mexico",
  "signal_type": "goalkeeper_error",
  "summary": "Goal came after goalkeeper failed to claim a looping ball under contact.",
  "scenario_tags": ["opponent_error", "low_xg_goal", "game_state_shift"],
  "source_ids": ["the_guardian_match_report", "espn_match_commentary"],
  "agreement_count": 2,
  "confidence": 0.83
}
```

## Fusion rule
A source claim becomes an EventFlow signal only when it passes at least one condition:
1. It comes from an official source.
2. It is confirmed by two or more independent sources.
3. It is consistent with structured match events such as goal/card/substitution time.
4. It matches known team/player tactical profiles.

## Output to V3.0
The final fused table feeds:
- `build_eventflow_scenario_weights.py`
- `predict_eventflow.py`
- `merge_dual_engine_predictions.py`

