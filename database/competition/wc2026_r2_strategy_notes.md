# WC2026 Round 2 Advancement Strategy Notes

> Last verified: 2026-06-18. Scope: R2-only strategic notes for prediction context, based on `wc2026_group_fixtures.csv`, `group_standings.csv`, `round_of_32_template.csv`, and `annex_c_round_of_32.csv`.

## How To Use

- These notes are **not** deterministic match picks. They are pre-match context for judging whether a side may push, manage tempo, accept a draw, rotate, or lower attacking risk.
- R2 control-score incentives are generally **weaker than R3** because no team has mathematically clinched before its second match. The main R2 incentive is to reach **6 points** (locked/near-locked top-two) or **4 points** (very strong qualification position) and preserve optionality for R3.
- Treat "control risk" as a tactical/tempo modifier, not as proof of collusion or deliberate tanking. It should influence confidence, totals, late-game event flow, and lineup interpretation.
- Use `resolve_round_of_32.py` only after enough R2/R3 results are known. Before then, Annex C scenarios remain too wide for hard bracket claims.

## General R2 Principles

| Situation after R1 | R2 incentive | Prediction handling |
|---|---|---|
| 3 pts vs 3 pts | Winner reaches 6 and can control/rotate in R3; draw leaves both on 4 and usually comfortable | Early phase can be competitive, but late draw state may reduce risk-taking. Do not overstate "must win" unless first-place route is clearly much better. |
| 3 pts vs 0/1 pt | 3-point team can lock control by winning; opponent often cannot afford another loss | Favorite still has real incentive to push. Rotation usually more likely **after** R2 win, not before. |
| 1 pt vs 1 pt | Four-way or balanced group remains open | Low control-score risk; both need points and goal difference. |
| 0 pts vs 0 pts | Survival match | Low control-score risk; defeat can leave team dependent on best-third miracles. |
| Strong team on 1 pt | Needs R2 win to avoid R3 pressure and third-place path | Usually stronger attacking intent than market narratives expect. |

## Bracket Incentive Map

| Group | Winner path | Runner-up path | R2 strategic read |
|---|---|---|---|
| A | 1A vs 3C/E/F/H/I | 2A vs 2B | Mexico/South Korea may both like 4 pts, but Mexico also values host route via M79; no strong reason to prefer second yet. |
| B | 1B vs 3E/F/G/I/J | 2B vs 2A | Four-way 1-point group; first/second path cannot be optimized before R2. |
| C | 1C vs 2F | 2C vs 1F | Strong incentive to finish first if F winner is likely strong. Brazil cannot coast after opening draw. |
| D | 1D vs 3B/E/F/I/J | 2D vs 2G | USA/Australia can accept a late draw state, but first gives more optionality than runner-up vs a possible Belgium-type 2G. |
| E | 1E vs 3A/B/C/D/F | 2E vs 2I | Germany/Ivory Coast should value first: runner-up E may run into France/Norway/Senegal from I. |
| F | 1F vs 2C | 2F vs 1C | First likely avoids Brazil if Brazil recovers to win C. Netherlands/Japan have clear incentive to chase wins. |
| G | 1G vs 3A/E/H/I/J | 2G vs 2D | Four-way 1-point group; no safe control-score position yet. |
| H | 1H vs 2J | 2H vs 1J | Winner likely avoids Argentina/Austria group winner; Spain/Uruguay should not treat R2 as optional. |
| I | 1I vs 3C/D/F/G/H | 2I vs 2E | France/Norway should chase first to avoid a possible Germany/Ivory Coast 2E. |
| J | 1J vs 2H | 2J vs 1H | Argentina/Austria first-place value depends on H, but first is still cleaner than facing 1H. |
| K | 1K vs 3D/E/I/J/L | 2K vs 2L | Portugal needs a win after R1 draw; Colombia can take control with a win before R3 vs Portugal. |
| L | 1L vs 3E/H/I/J/K | 2L vs 2K | England/Ghana winner gets R3 optionality; runner-up may face Portugal/Colombia/DR Congo from K. |

## R2 Fixture Notes

| Match | Fixture | R1 points | Control risk | Strategy note for prediction |
|---|---|---:|---|---|
| 25 | Czechia vs South Africa | 0-0 | Low | Survival match. Both lost R1, and South Africa also carries suspension damage. Expect urgency rather than controlled draw; third-place damage limitation matters only if match becomes late-level. |
| 26 | Switzerland vs Bosnia and Herzegovina | 1-1 | Low | B is a four-way 1-point group. Switzerland's xG edge vs Qatar was strong but score did not follow; Bosnia needs at least a point. No clear bracket-control angle before points separation. |
| 27 | Canada vs Qatar | 1-1 | Low | Host Canada can reach 4 and improve top-two odds; Qatar likely wants a draw but cannot assume best-third safety. Canada home/travel edge supports active approach. |
| 28 | Mexico vs South Korea | 3-3 | Medium | Winner reaches 6 and likely controls A. Draw gives both 4, so late-game draw acceptance is plausible if level. Mexico may still push more because 1A keeps a host route through M79, while runner-up enters fixed 2A vs 2B. |
| 29 | Brazil vs Haiti | 1-0 | Low | Brazil opened with only 1 point and must avoid entering R3 under pressure. First in C is valuable because runner-up C likely faces the F winner. Expect stronger attacking intent than a pure talent-mismatch rotation read. |
| 30 | Scotland vs Morocco | 3-1 | Medium-low | Scotland can reach 6; Morocco needs points after draw. Scotland may accept late draw if match state is even, but a win creates R3 leverage before Brazil. Morocco should not under-attack. |
| 31 | Turkey vs Paraguay | 0-0 | Low | Survival match after both lost R1. Goal difference is already poor for both, especially Paraguay; late all-out phases are possible if level. |
| 32 | USA vs Australia | 3-3 | Medium | Winner reaches 6; draw leaves both on 4. USA has host/pressing profile and likely values first in D, but late draw control is plausible because runner-up D is still a fixed path vs 2G. Avoid overcommitting to big late chasing if level. |
| 33 | Germany vs Ivory Coast | 3-3 | Low-medium | First in E is strategically important because 2E faces 2I, potentially France/Norway/Senegal. Germany should still chase first and goal difference; Ivory Coast can value a draw but should not assume R3 is safe. |
| 34 | Ecuador vs Curacao | 0-0 | Low | Survival match. Curacao's R1 goal difference is severe; Ecuador need both points and margin. Little control-score incentive. |
| 35 | Netherlands vs Sweden | 1-3 | Low-medium | Netherlands need a win after R1 draw; Sweden can reach 6 or accept a late draw if it preserves control. F first is valuable because 2F may face Brazil as 1C. |
| 36 | Tunisia vs Japan | 0-1 | Low | Japan need 4 points before a difficult R3; Tunisia must repair heavy GD. Japan should push if level; Tunisia cannot play only for 0-0 unless damage limitation becomes the only realistic path. |
| 37 | Uruguay vs Cape Verde | 1-1 | Low | H is a four-way 1-point group. Uruguay need separation; Cape Verde's opening draw gives them a reason to protect point states but not enough to coast. |
| 38 | Spain vs Saudi Arabia | 1-1 | Low | Spain need a win after 0-0 vs Cape Verde and should not manage for second. H runner-up can face 1J, so first-place pressure remains meaningful. |
| 39 | Belgium vs Iran | 1-1 | Low | G is fully open. Belgium cannot rely on third after another draw; Iran can improve best-third/top-two odds with a point but will face fair-play/GD pressure. |
| 40 | New Zealand vs Egypt | 1-1 | Low | Four-way group and Egypt's fair-play/ranking position mean both need points. New Zealand may accept late draw only if Belgium-Iran result helps, but not pre-match. |
| 41 | Norway vs Senegal | 3-0 | Low-medium | Norway can reach 6 but faces a strong 0-point Senegal. I winner avoids 2E; Norway should not coast. Senegal need at least a point and likely keep counter/transition threat alive. |
| 42 | France vs Iraq | 3-0 | Low | France have strong incentive to reach 6 and chase goal difference against Norway for 1I. Runner-up I may face 2E, so rotation should be limited unless match is under control. |
| 43 | Argentina vs Austria | 3-3 | Medium | Winner reaches 6 and likely controls J. Draw gives both 4 and may be acceptable late, but 1J vs 2H is generally cleaner than 2J vs 1H. Argentina's adaptation edge supports controlled but still proactive play. |
| 44 | Jordan vs Algeria | 0-0 | Low | Survival match. Both lost R1 and need points; Algeria's deeper squad/form layer may push for win, while Jordan can still target third-place viability through compact defense. |
| 45 | England vs Ghana | 3-3 | Medium | Winner reaches 6. England likely wants first because 2L faces 2K, which may be Portugal/Colombia/DR Congo. Late draw acceptance is possible only if match tempo/risk is unfavorable. |
| 46 | Panama vs Croatia | 0-0 | Low | Survival match. Croatia's R1 loss creates urgent need to win and rebuild GD; Panama can keep shape but a draw may still leave R3 dependence. |
| 47 | Portugal vs Uzbekistan | 1-0 | Low | Portugal drew R1 and need a win before Colombia/DR Congo and R3. Strong incentive to attack; no rational second-place management at 1 point. |
| 48 | Colombia vs DR Congo | 3-1 | Low-medium | Colombia can reach 6 and gain R3 control before facing Portugal. DR Congo are on 1 and should value a point, but K runner-up path vs 2L is uncertain enough that pre-match control is weak. |

## Prediction Adjustments

- If a 3-vs-3 R2 match is level after 60–70 minutes, reduce late all-out assumptions unless first-place path is clearly superior.
- If a favorite on 1 point faces a weaker team, do **not** lower attacking intent merely because 48-team format is forgiving; R2 win is what creates R3 control.
- If a 0-point team trails late, increase tail risk for open-game transitions, cards, and late xG rather than assuming low block continues.
- For R2 betting-style outputs, mark totals/handicap confidence lower when both teams would be comfortable on 4 points after a draw.
- Re-evaluate all notes after each R2 result; R3 control-score incentives can change sharply once 6-point and 4-point teams are known.
