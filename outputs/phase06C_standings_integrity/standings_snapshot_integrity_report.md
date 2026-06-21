# Standings Snapshot Integrity Report

- **snapshot_id**: `standings-update-20260621`
- **source_cutoff_time**: `2026-06-21T12:00:00Z`
- **snapshot_status**: `partial_stale`
- **formal_prediction_allowed**: `partial_only`

## Coverage summary

- Expected completed matches (kickoff < cutoff): **36**
- Local result rows matched: **32**
- Missing: **4**
- Ambiguous: **0**
- Affected groups: **E|F**

## Per-group coverage

| Group | Expected | Matched | Missing | Ambiguous | Coverage % | Affected |
|-------|----------|---------|---------|-----------|------------|----------|
| A | 4 | 4 | 0 | 0 | 100.0 | false |
| B | 4 | 4 | 0 | 0 | 100.0 | false |
| C | 4 | 4 | 0 | 0 | 100.0 | false |
| D | 4 | 4 | 0 | 0 | 100.0 | false |
| E | 4 | 2 | 2 | 0 | 50.0 | true |
| F | 4 | 2 | 2 | 0 | 50.0 | true |
| G | 2 | 2 | 0 | 0 | 100.0 | false |
| H | 2 | 2 | 0 | 0 | 100.0 | false |
| I | 2 | 2 | 0 | 0 | 100.0 | false |
| J | 2 | 2 | 0 | 0 | 100.0 | false |
| K | 2 | 2 | 0 | 0 | 100.0 | false |
| L | 2 | 2 | 0 | 0 | 100.0 | false |

## Missing completed results

- `WC2026-E33` (E R2): Germany vs Ivory Coast — kickoff 2026-06-20T16:00:00Z
- `WC2026-E34` (E R2): Ecuador vs Curacao — kickoff 2026-06-20T20:00:00Z
- `WC2026-F35` (F R2): Netherlands vs Sweden — kickoff 2026-06-20T13:00:00Z
- `WC2026-F36` (F R2): Tunisia vs Japan — kickoff 2026-06-20T22:00:00Z

## Modeling boundaries

- Cross-group third-place ranking: **blocked**
- Route avoidance: **blocked**
- F35 group-local pressure (Group F): **allowed** if Group F has no missing pre-cutoff results

Notes: Partial standings allowed via --allow-partial-standings; missing=4, ambiguous=0; affected=E,F