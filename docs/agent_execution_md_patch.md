# Add this section to EventFlow Agent Guide

## V3.1 Multi-Source Evidence Protocol

When running EventFlow prediction, the Agent must not rely on a single article or one live commentary feed.

### Required evidence order
1. Official match data and FIFA technical/match reports.
2. Structured event/live commentary summaries from multiple sources.
3. Professional tactical reports or previews.
4. Player and team style profiles.
5. Probability Engine outputs from V2.0.

### Agent must extract signals into these categories
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

### Agent must output
- top 3 scorelines from EventFlow, ranked high to low
- total goals tendency
- half/full-time result: 胜/胜, 胜/平, 胜/负, 平/胜, 平/平, 平/负, 负/胜, 负/平, 负/负
- dominant scenario path
- source evidence table
- disagreement note if sources conflict
- confidence level

### Red flags
The Agent must reduce confidence when:
- only one source supports a tactical claim;
- article language is emotional but not specific;
- no timestamp or event evidence exists;
- tactical preview conflicts with first-round actual positioning data;
- player position in national team differs from club role and no adjustment is made.

