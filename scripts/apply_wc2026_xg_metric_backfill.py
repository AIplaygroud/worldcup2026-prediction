#!/usr/bin/env python3
"""Apply xG/metric backfill rows into wc2026_match_xg.csv."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from group_state_common import FIXTURES, MAPPING, MATCH_XG, ROOT, read_csv, write_csv

XG_METRIC_BACKFILL_CANDIDATE = (
    ROOT / "database" / "xGdatabase" / "staging" / "wc2026_xg_metric_backfill_candidate.csv"
)
OUT_DIR = ROOT / "outputs" / "phase07_xg_metric_backfill"
BACKUP_DIR = ROOT / "backups" / "phase07_xg_metric_backfill"

XG_FIELDS = [
    "match_date", "group", "home_team", "away_team", "home_score", "away_score",
    "home_xg", "away_xg", "home_shots", "away_shots", "source", "source_url",
    "fetched_at", "quality_flag", "notes",
]

DIFF_FIELDS = [
    "match_id", "field", "before", "after",
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


def _fixture_for_fifa(fid: str, fixtures: list[dict]) -> dict:
    for f in fixtures:
        if str(f.get("fifa_match_id", "")) == str(fid):
            return f
    return {}


def validate_xg_candidate(
    candidate_row: dict,
    existing_xg_row: dict,
    mapping_by_id: dict,
    fixture_by_fifa: dict,
) -> tuple[bool, str]:
    mid = candidate_row.get("match_id", "").strip()
    map_row = mapping_by_id.get(mid, {})
    fid = str(candidate_row.get("fifa_match_id") or map_row.get("fifa_match_id", ""))
    fix = fixture_by_fifa.get(fid, {})
    exp_home = fix.get("home_team_en", map_row.get("home_team", ""))
    exp_away = fix.get("away_team_en", map_row.get("away_team", ""))
    if _norm(candidate_row.get("home_team", "")) != _norm(exp_home):
        return False, "home_team_mismatch"
    if _norm(candidate_row.get("away_team", "")) != _norm(exp_away):
        return False, "away_team_mismatch"

    try:
        if int(candidate_row.get("home_score", 0)) != int(existing_xg_row.get("home_score", -1)):
            return False, "score_mismatch_home"
        if int(candidate_row.get("away_score", 0)) != int(existing_xg_row.get("away_score", -1)):
            return False, "score_mismatch_away"
    except (TypeError, ValueError):
        return False, "invalid_score"

    try:
        float(candidate_row.get("home_xg", ""))
        float(candidate_row.get("away_xg", ""))
        int(candidate_row.get("home_shots", ""))
        int(candidate_row.get("away_shots", ""))
    except (TypeError, ValueError):
        return False, "non_numeric_xg_or_shots"

    if not str(candidate_row.get("source", "")).strip():
        return False, "missing_source"
    if not str(candidate_row.get("source_url", "")).strip():
        return False, "missing_source_url"
    if not str(candidate_row.get("source_title", "")).strip():
        return False, "missing_source_title"
    if not str(candidate_row.get("source_time", "")).strip():
        return False, "missing_source_time"
    return True, ""


def apply_xg_metric_backfill(
    candidate_path: Path = XG_METRIC_BACKFILL_CANDIDATE,
    dry_run: bool = False,
) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    mapping_by_id = {r["internal_match_id"]: r for r in read_csv(MAPPING)}
    fixture_by_fifa = {r["fifa_match_id"]: r for r in read_csv(FIXTURES)}
    candidates = read_csv(candidate_path)
    existing_xg_rows = read_csv(MATCH_XG)
    new_xg_rows = list(existing_xg_rows)
    applied_rows: list[dict] = []
    flags: list[dict] = []
    diff_rows: list[dict] = []

    existing_xg_map = {_row_key(r): r for r in existing_xg_rows}

    for c_row in candidates:
        key = _row_key(c_row)
        existing_row = existing_xg_map.get(key)
        mid = c_row.get("match_id", "")

        if not existing_row:
            flags.append({"match_id": mid, "flag": "no_matching_existing_row"})
            continue

        if existing_row.get("quality_flag") != "score_only_backfill":
            flags.append({"match_id": mid, "flag": "not_score_only_backfill_skipped"})
            continue

        ok, reason = validate_xg_candidate(c_row, existing_row, mapping_by_id, fixture_by_fifa)
        if not ok:
            flags.append({"match_id": mid, "flag": f"validation_failed:{reason}"})
            continue

        idx_to_update = next((i for i, r in enumerate(new_xg_rows) if _row_key(r) == key), -1)
        if idx_to_update < 0:
            flags.append({"match_id": mid, "flag": "row_to_update_not_found_in_list"})
            continue

        fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        updated_row = dict(existing_row)
        updates = {
            "home_xg": c_row.get("home_xg", ""),
            "away_xg": c_row.get("away_xg", ""),
            "home_shots": c_row.get("home_shots", ""),
            "away_shots": c_row.get("away_shots", ""),
            "source": c_row.get("source", ""),
            "source_url": c_row.get("source_url", ""),
            "fetched_at": fetched,
            "quality_flag": "full_metric_backfilled",
        }
        notes = str(existing_row.get("notes", "")).strip()
        suffix = "phase07_xg_metric_backfilled"
        updated_row["notes"] = f"{notes}; {suffix}".strip("; ") if notes else suffix

        for field, after in updates.items():
            before = existing_row.get(field, "")
            if str(before) != str(after):
                diff_rows.append({
                    "match_id": mid,
                    "field": field,
                    "before": str(before),
                    "after": str(after),
                })
            updated_row[field] = after

        new_xg_rows[idx_to_update] = updated_row
        applied_rows.append({**c_row, "action": "updated", "fetched_at": fetched})

    backup_path = BACKUP_DIR / "wc2026_match_xg.before_phase07.csv"
    if not dry_run and applied_rows:
        shutil.copy2(MATCH_XG, backup_path)
        write_csv(MATCH_XG, XG_FIELDS, new_xg_rows)

    write_csv(
        OUT_DIR / "applied_xg_metric_backfill_rows.csv",
        list(applied_rows[0].keys()) if applied_rows else ["match_id", "action"],
        applied_rows,
    )
    write_csv(OUT_DIR / "xg_metric_backfill_quality_flags.csv", ["match_id", "flag"], flags)
    write_csv(OUT_DIR / "xg_metric_backfill_diff.csv", DIFF_FIELDS, diff_rows)
    write_backfill_report(applied_rows, flags, dry_run)

    return {
        "applied": len(applied_rows),
        "flags": len(flags),
        "backup": str(backup_path) if applied_rows and not dry_run else "",
    }


def write_backfill_report(applied: list[dict], flags: list[dict], dry_run: bool) -> None:
    lines = [
        "# Phase 07B Metric Backfill Report",
        "",
        f"- dry_run: **{str(dry_run).lower()}**",
        f"- applied_rows: **{len(applied)}**",
        f"- quality_flags: **{len(flags)}**",
        "",
        "## Upgraded rows",
        "",
    ]
    for r in applied:
        lines.append(
            f"- `{r.get('match_id', '')}` {r.get('home_team', '')} vs {r.get('away_team', '')} "
            f"xG {r.get('home_xg', '')}-{r.get('away_xg', '')} shots {r.get('home_shots', '')}-{r.get('away_shots', '')}"
        )
    if flags:
        lines.extend(["", "## Flags", ""])
        for f in flags:
            lines.append(f"- `{f['match_id']}`: {f['flag']}")
    lines.extend([
        "",
        "## Boundaries",
        "",
        "- scores unchanged; only xG/shot metrics added",
        "- quality_flag upgraded to full_metric_backfilled",
    ])
    (OUT_DIR / "phase07B_metric_backfill_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", type=Path, default=XG_METRIC_BACKFILL_CANDIDATE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = apply_xg_metric_backfill(args.candidate, dry_run=args.dry_run)
    print(f"applied={result['applied']} flags={result['flags']} backup={result['backup']}")
    if result["applied"] == 0 and result["flags"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
