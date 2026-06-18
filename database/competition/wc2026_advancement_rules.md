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

## Round of 32 Bracket

There is **no second draw** after the group stage. Once the 32 qualifiers are known, the round-of-32 pairings are applied automatically.

### Fixed pairings

These matchups do **not** depend on which third-placed teams advance:

| Match | Pairing |
| --- | --- |
| 73 | Runner-up A vs Runner-up B |
| 75 | Winner F vs Runner-up C |
| 76 | Winner C vs Runner-up F |
| 78 | Runner-up E vs Runner-up I |
| 83 | Runner-up K vs Runner-up L |
| 84 | Winner H vs Runner-up J |
| 86 | Winner J vs Runner-up H |
| 88 | Runner-up D vs Runner-up G |

### Winner vs best third-placed team

Eight group winners play advancing third-placed teams. Each winner has a **candidate pool** of possible third-placed groups, but the exact opponent is **not fixed in advance**.

| Match | Group winner | Possible third-placed opponents |
| --- | --- | --- |
| 74 | E | A, B, C, D, F |
| 77 | I | C, D, F, G, H |
| 79 | A | C, E, F, H, I |
| 80 | L | E, H, I, J, K |
| 81 | D | B, E, F, I, J |
| 82 | G | A, E, H, I, J |
| 85 | B | E, F, G, I, J |
| 87 | K | D, E, I, J, L |

Example: Winner A does **not** always play third-placed team X from one fixed group. FIFA first determines which 8 of the 12 third-placed teams qualify, then looks up the exact assignment in Annex C.

### Annex C lookup (495 scenarios)

Because exactly 8 of 12 third-placed teams advance, there are `C(12,8) = 495` possible combinations. FIFA published all 495 rows in **Annex C** of the [official tournament regulations](https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf).

**Lookup algorithm (automatic, no draw):**

1. After the final group-stage matches, identify the winner and runner-up in each group.
2. Rank all 12 third-placed teams globally (points → goal difference → goals scored → fair play → lots).
3. The top 8 third-placed teams qualify. Record which **8 groups** they come from (e.g. `EFGHIJKL`).
4. Sort those 8 group letters alphabetically and use that string as the lookup key in `annex_c_round_of_32.csv`.
5. Read columns `vs_1A` … `vs_1L` to assign each group winner's third-placed opponent.
6. Combine with the 8 fixed pairings above to produce the full round-of-32 bracket.

**Column mapping:**

| Annex column | Match | Group winner |
| --- | --- | --- |
| `vs_1A` | M79 | A |
| `vs_1B` | M85 | B |
| `vs_1D` | M81 | D |
| `vs_1E` | M74 | E |
| `vs_1G` | M82 | G |
| `vs_1I` | M77 | I |
| `vs_1K` | M87 | K |
| `vs_1L` | M80 | L |

**Example (Option 1, advancing third-place groups = EFGHIJKL):**

| Match | Pairing |
| --- | --- |
| M79 | Winner A vs 3E |
| M85 | Winner B vs 3J |
| M81 | Winner D vs 3I |
| M74 | Winner E vs 3F |
| M82 | Winner G vs 3H |
| M77 | Winner I vs 3G |
| M87 | Winner K vs 3L |
| M80 | Winner L vs 3K |

**Special constraint:**

- If third-placed **K** qualifies, it can only face winner **L** (M80).
- If third-placed **L** qualifies, it can only face winner **K** (M87).

**Resolver script:**

```bash
python scripts/resolve_round_of_32.py --third-groups EFGHIJKL
python scripts/resolve_round_of_32.py --standings database/competition/group_standings.csv
```

## Strategic Implications (Bracket Engineering)

Strong teams may deliberately manage the **final group-stage match** to influence their round-of-32 path. This is not random — it is a deterministic function of (a) final group rank and (b) which eight third-placed groups qualify.

### Three levers

1. **Finish 1st vs 2nd in the group**
   - Changes whether the team enters a **fixed winner/runner-up slot** or a **winner-vs-third slot**.
   - Example: Group F winner plays runner-up C (M75); Group F runner-up has no fixed slot until Annex C is resolved, but other F teams cannot meet in the round of 32.

2. **Influence the global set of 8 advancing third-placed groups**
   - A team's last group match can change not only its own points, but also whether its group's third-placed team — or another group's third-placed team — ranks among the best eight.
   - Changing the qualifying set switches the Annex C row (1 of 495) and therefore changes **every** winner-vs-third assignment.

3. **Winner-vs-third candidate pools**
   - Each group winner can only draw a third-placed opponent from a predefined pool (see table above).
   - A favorite that clinches **first place** should scan which third-placed groups are realistically still in contention before the last matchday, then estimate which Annex C rows remain possible.

### Practical analysis workflow for predictions

When the user asks about knockout path, favorite rotation, or "控分挑对手":

1. Read `group_standings.csv` and simulate/projected final ranks for relevant groups.
2. Rank all 12 projected third-placed teams; take the top 8 to form the `advancing_groups` key.
3. Look up `annex_c_round_of_32.csv` (or run `resolve_round_of_32.py`).
4. Compare scenarios if the focal team wins, draws, or loses the last group match (1st vs 2nd, and ripple effects on third-placed rankings).
5. State uncertainty explicitly when groups are not yet mathematically settled.

### Round 2 pre-control notes

For R2 predictions, read `wc2026_r2_strategy_notes.md` before applying a tactical or betting read. R2 "控分" is usually weaker than R3 because teams have not clinched before kickoff; the more common R2 pattern is:

- 3-point teams still push for 6 points because that creates R3 rotation/control optionality.
- 3-vs-3 matches can become lower-risk late if a draw leaves both on 4 points.
- 1-point favorites often need to attack rather than coast, because a second draw creates R3 pressure and possible third-place uncertainty.
- 0-vs-0 matches are survival games where late open-state risk can rise.

Use these as context for match tempo, lineup rotation, and totals/handicap confidence, not as proof of deliberate tanking.

### Caveats

- FIFA forbids teams from **same group** meeting again in the round of 32; Annex C enforces this.
- Deliberate tanking risks finishing third (much weaker knockout seeding) or missing the best-eight-third cut entirely.
- Fair-play points and drawing of lots can break ties among third-placed teams — mention this when margins are razor-thin.
- For betting outputs, still separate knockout winner from 90-minute result per `reference/jingcai-football-simulation-rules.md`.

## Data Files

- `group_assignments.csv`: official project group allocation used by the prediction skill.
- `wc2026_group_fixtures.csv`: full group-stage schedule (72 matches, FIFA match IDs 1–72); regenerate with `python scripts/build_group_fixtures.py`.
- `group_standings.csv`: current project standings derived from `database/xGdatabase/processed/wc2026_match_xg.csv`.
- `wc2026_r2_strategy_notes.md`: R2 fixture-by-fixture advancement incentive notes for control-score risk, first/second-place path value, rotation, and attacking intent.
- `round_of_32_template.csv`: fixed round-of-32 slots and third-place candidate pools.
- `annex_c_round_of_32.csv`: full FIFA Annex C table (495 rows). Source: FIFA FWC2026 Regulations, Annex C; built via `scripts/build_annex_c.py`.

