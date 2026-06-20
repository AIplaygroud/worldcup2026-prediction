#!/usr/bin/env python3
"""Apply score-only result backfill rows into wc2026_match_xg.csv with validation."""
from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

from group_state_common import MAPPING, MATCH_XG, ROOT, read_csv, write_csv

BACKFILL_CANDIDATE = ROOT / "database" / "xGdatabase" / "staging" / "wc2026_match_results_backfill_candidate.csv"
FIXTURES = ROOT / "database" / "competition" / "wc2026_group_fixtures.csv"
OUT_DIR = ROOT / "outputs" / "phase06D_result_backfill"
BACKUP_DIR = ROOT / "backups" / "phase06D_result_backfill"

XG_FIELDS = [
    "match_date", "group", "home_team", "away_team", "home_score", "away_score",
    "home_xg", "away_xg", "home_shots", "away_shots", "source", "source_url",
    "fetched_at", "quality_flag", "notes",
]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _row_key(row: dict) -> tuple[str, str, str, str]:
    return (
        row.get("match_date", "").strip(),
        row.get("group", "").strip(),
        _norm(row.get("home_team", "")),
        _norm(row.get("away_team", "")),
    )


def validate_candidate(row: dict, mapping_by_id: dict, fixture_by_fifa: dict) -> tuple[bool, str]:
    mid = row.get("match_id", "").strip()
    if not mid:
        return False, "missing_match_id"
    map_row = mapping_by_id.get(mid)
    if not map_row:
        return False, "match_id_not_in_mapping"
    try:
        hs = int(row.get("home_score", ""))
        aws = int(row.get("away_score", ""))
    except (TypeError, ValueError):
        return False, "missing_scores"
    if not row.get("source", "").strip():
        return False, "missing_source"
    if not row.get("source_url", "").strip():
        return False, "missing_source_url"
    fid = row.get("fifa_match_id", map_row.get("fifa_match_id", ""))
    fix = fixture_by_fifa.get(str(fid), {})
    exp_home = fix.get("home_team_en", map_row.get("home_team", ""))
    exp_away = fix.get("away_team_en", map_row.get("away_team", ""))
    if _norm(row.get("home_team", "")) != _norm(exp_home):
        return False, "home_team_mismatch"
    if _norm(row.get("away_team", "")) != _norm(exp_away):
        return False, "away_team_mismatch"
    if row.get("group", "") != map_row.get("group", ""):
        return False, "group_mismatch"
    return True, ""


def candidate_to_xg_row(row: dict) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    notes = row.get("notes", "")
    if row.get("is_score_only_backfill", "").lower() == "true":
        notes = f"{notes}; score-only backfill; xG metrics pending".strip("; ")
    return {
        "match_date": row.get("match_date", "").strip(),
        "group": row.get("group", "").strip(),
        "home_team": row.get("home_team", "").strip(),
        "away_team": row.get("away_team", "").strip(),
        "home_score": int(row["home_score"]),
        "away_score": int(row["away_score"]),
        "home_xg": "",
        "away_xg": "",
        "home_shots": "",
        "away_shots": "",
        "source": row.get("source", "").strip(),
        "source_url": row.get("source_url", "").strip(),
        "fetched_at": now,
        "quality_flag": "score_only_backfill",
        "notes": notes,
    }


def apply_backfill(
    candidate_path: Path = BACKFILL_CANDIDATE,
    dry_run: bool = False,
) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    mapping_by_id = {r["internal_match_id"]: r for r in read_csv(MAPPING)}
    fixture_by_fifa = {r["fifa_match_id"]: r for r in read_csv(FIXTURES)}
    candidates = read_csv(candidate_path)
    existing = read_csv(MATCH_XG)
    existing_keys = {_row_key(r) for r in existing}

    applied: list[dict] = []
    flags: list[dict] = []
    new_rows = list(existing)

    for row in candidates:
        ok, reason = validate_candidate(row, mapping_by_id, fixture_by_fifa)
        if not ok:
            flags.append({"match_id": row.get("match_id", ""), "flag": reason})
            continue
        xg_row = candidate_to_xg_row(row)
        key = _row_key(xg_row)
        if key in existing_keys:
            flags.append({"match_id": row["match_id"], "flag": "duplicate_row_skipped"})
            continue
        rev_key = (key[0], key[1], key[3], key[2])
        for ex in existing:
            if _row_key(ex) == rev_key:
                flags.append({"match_id": row["match_id"], "flag": "conflict_reversed_row_exists"})
                break
        else:
            applied.append({**row, "action": "appended"})
            new_rows.append(xg_row)
            existing_keys.add(key)

    backup_path = BACKUP_DIR / "wc2026_match_xg.before_phase06D.csv"
    if not dry_run and applied:
        shutil.copy2(MATCH_XG, backup_path)
        write_csv(MATCH_XG, XG_FIELDS, new_rows)

    write_csv(OUT_DIR / "applied_backfill_rows.csv", list(applied[0].keys()) if applied else [
        "match_id", "action",
    ], applied)
    write_csv(OUT_DIR / "backfill_quality_flags.csv", ["match_id", "flag"], flags)

    return {"applied": len(applied), "flags": len(flags), "backup": str(backup_path) if applied else ""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", type=Path, default=BACKFILL_CANDIDATE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = apply_backfill(args.candidate, dry_run=args.dry_run)
    print(f"applied={result['applied']} flags={result['flags']} backup={result['backup']}")
    if result["applied"] == 0 and result["flags"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
