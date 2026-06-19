# EventFlow Source Extraction Prompt

You are extracting structured football event/tactical signals for a World Cup EventFlow prediction model.

Rules:
- Do not copy full article text.
- Convert source content into short factual summaries and structured labels.
- Prefer exact minute, player, team, and tactical mechanism.
- Mark uncertainty clearly.

Output JSONL, one claim per line:

```json
{"match_id":"","source_id":"","source_url":"","minute":"","team":"","player":"","signal_type":"","summary":"","scenario_tags":[],"confidence_hint":0.0}
```

Allowed signal_type values:
- formation_actual
- position_shift
- strong_side_attack
- weak_side_exposure
- pressing_success
- pressing_broken
- low_block_success
- low_block_failure
- transition_threat
- set_piece_edge
- goalkeeper_error
- card_or_referee_chaos
- injury_or_forced_substitution
- late_game_opening
- tactical_mutual_lock
- group_draw_control
- group_table_pressure
- rotation_risk
- starter_rest_signal
- buildup_gk_error
- buildup_press_risk
- weather_heat_humidity
- travel_fatigue
- pitch_adaptation
- var_penalty_swing
- box_defending_risk
- general_observation

If a source mentions group standings, qualification incentives, must-win pressure, rotation, travel, weather, pitch, VAR, penalty tendency, or build-up errors, do not label it as `general_observation`. Use the most specific `signal_type` above.

- Red card / second yellow / strict physical contact → `card_or_referee_chaos` (S08)
- VAR / penalty / handball / box defending risk → `var_penalty_swing` or `box_defending_risk` (S16)
