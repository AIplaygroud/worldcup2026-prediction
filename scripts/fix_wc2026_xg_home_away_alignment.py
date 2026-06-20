#!/usr/bin/env python3
"""Fix home/away alignment in wc2026_match_xg.csv for ambiguous fixture joins."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from group_state_common import FIXTURES, MAPPING, MATCH_XG, ROOT, read_csv, write_csv

OUT_DIR = ROOT / "outputs" / "phase06D_result_backfill"
BACKUP_DIR = ROOT / "backups" / "phase06D_result_backfill"
AMBIGUOUS = ROOT / "outputs" / "phase06C_standings_integrity" / "ambiguous_completed_results_pre_cutoff.csv"

SWAP_PAIRS = [
    ("home_team", "away_team"),
    ("home_score", "away_score"),
    ("home_xg", "away_xg"),
    ("home_shots", "away_shots"),
]

XG_FIELDS = [
    "match_date", "group", "home_team", "away_team", "home_score", "away_score",
    "home_xg", "away_xg", "home_shots", "away_shots", "source", "source_url",
    "fetched_at", "quality_flag", "notes",
]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def find_xg_row(
    rows: list[dict],
    home: str,
    away: str,
    group: str,
    match_date: str,
) -> tuple[int | None, dict | None]:
    for i, row in enumerate(rows):
        if (
            _norm(row.get("home_team", "")) == _norm(home)
            and _norm(row.get("away_team", "")) == _norm(away)
            and row.get("group", "") == group
            and row.get("match_date", "") == match_date
        ):
            return i, row
    for i, row in enumerate(rows):
        if (
            _norm(row.get("home_team", "")) == _norm(away)
            and _norm(row.get("away_team", "")) == _norm(home)
            and row.get("group", "") == group
            and row.get("match_date", "") == match_date
        ):
            return i, row
    return None, None


def swap_row_fields(row: dict) -> dict:
    out = dict(row)
    for a, b in SWAP_PAIRS:
        if a in out and b in out:
            out[a], out[b] = out[b], out[a]
    note = out.get("notes", "")
    out["notes"] = f"{note}; phase06D_home_away_swapped".strip("; ")
    out["quality_flag"] = "home_away_aligned"
    out["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    return out


def fix_alignment(
    match_id: str = "WC2026-K24",
    dry_run: bool = False,
) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    mapping = {r["internal_match_id"]: r for r in read_csv(MAPPING)}
    map_row = mapping.get(match_id)
    if not map_row:
        raise SystemExit(f"Unknown match_id {match_id}")

    fid = map_row["fifa_match_id"]
    fix_rows = [r for r in read_csv(FIXTURES) if r["fifa_match_id"] == fid]
    if not fix_rows:
        raise SystemExit(f"No fixture for fifa_match_id {fid}")
    fix = fix_rows[0]
    exp_home = fix["home_team_en"]
    exp_away = fix["away_team_en"]
    match_date = fix["match_date"]

    rows = read_csv(MATCH_XG)
    idx, row = find_xg_row(rows, exp_home, exp_away, map_row["group"], match_date)
    diff_rows: list[dict] = []

    if row is None:
        idx, row = find_xg_row(rows, exp_away, exp_home, map_row["group"], match_date)
        if row is None:
            raise SystemExit(f"No xG row found for {match_id}")
        if _norm(row["home_team"]) == _norm(exp_home):
            return {"fixed": False, "reason": "already_aligned"}

    if _norm(row["home_team"]) == _norm(exp_home) and _norm(row["away_team"]) == _norm(exp_away):
        return {"fixed": False, "reason": "already_aligned"}

    for field_a, field_b in SWAP_PAIRS:
        if field_a in row:
            diff_rows.append({
                "match_id": match_id,
                "field": field_a,
                "before": row.get(field_a, ""),
                "after": row.get(field_b, ""),
            })
            diff_rows.append({
                "match_id": match_id,
                "field": field_b,
                "before": row.get(field_b, ""),
                "after": row.get(field_a, ""),
            })

    fixed_row = swap_row_fields(row)
    backup_path = BACKUP_DIR / "wc2026_match_xg.before_k24_fix.csv"

    if not dry_run:
        if not (BACKUP_DIR / "wc2026_match_xg.before_phase06D.csv").exists():
            shutil.copy2(MATCH_XG, backup_path)
        rows[idx] = fixed_row
        write_csv(MATCH_XG, XG_FIELDS, rows)

    write_csv(OUT_DIR / "k24_home_away_alignment_diff.csv", ["match_id", "field", "before", "after"], diff_rows)
    return {"fixed": True, "match_id": match_id, "swapped_fields": [p[0] for p in SWAP_PAIRS]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match-id", default="WC2026-K24")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = fix_alignment(args.match_id, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
