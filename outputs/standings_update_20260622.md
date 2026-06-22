# Standings Update: Post G40

- Snapshot: `WC2026_GROUP_20260622_POST_G40`
- Source cutoff: `2026-06-22T04:00:00Z`
- Completed matches included: 40
- Missing or ambiguous pre-cutoff results: 0

## Group G

1. Egypt: 4 points, GD +2
2. Iran: 2 points, GD 0, GF 2
3. Belgium: 2 points, GD 0, GF 1
4. New Zealand: 1 point, GD -2

## Group H

1. Spain: 4 points, GD +4
2. Uruguay: 2 points, GD 0, GF 3
3. Cape Verde: 2 points, GD 0, GF 2
4. Saudi Arabia: 1 point, GD -4

## Round 3 Modeling Impact

- Egypt and Spain: top-slot chase; qualification probability is high, but first place remains meaningful.
- Iran, Belgium, Uruguay and Cape Verde: control-destiny/open-group states.
- New Zealand and Saudi Arabia: must-win survival states with elevated late-chaos and goal-difference chase signals.
- Cape Verde is fourth and Belgium fifth in the current third-place table.

Competition-state signals remain an EventFlow/runtime overlay. They should
change scenario activation, draw acceptance, late push, rotation and route
preference, but should not directly modify the probability-engine lambda.
This avoids counting the same tournament incentive in both engines.
