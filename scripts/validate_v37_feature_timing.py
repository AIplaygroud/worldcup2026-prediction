#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate V3.7 feature timing — prevent pre-match leakage from post-match data."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eventflow_common import read_csv, write_csv
from v37_common import (
    FEATURE_TABLES,
    NORMALIZED_TABLES,
    V37_AUDIT,
    ensure_v37_dirs,
    snum,
)

VIOLATION_FIELDS = ["match_id", "check", "severity", "detail"]


def parse_utc(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def validate_match(match_id: str, asof: datetime | None = None) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    matches = [r for r in read_csv(NORMALIZED_TABLES["matches"]) if r["match_id"] == match_id]
    if not matches:
        return [{"match_id": match_id, "check": "match_exists", "severity": "error", "detail": "no normalized match row"}]

    m = matches[0]
    kickoff = parse_utc(m.get("kickoff_utc", ""))
    if not kickoff:
        violations.append({
            "match_id": match_id, "check": "kickoff_utc", "severity": "error",
            "detail": "missing kickoff_utc",
        })

    # 1. match_stats must not use post_match_final for pre-match feature build audit
    for row in read_csv(NORMALIZED_TABLES["match_stats"]):
        if row["match_id"] != match_id:
            continue
        timing = snum(row, "data_timing")
        if timing == "post_match_final" and asof and kickoff and asof < kickoff:
            violations.append({
                "match_id": match_id,
                "check": "data_timing_post_in_prematch_context",
                "severity": "error",
                "detail": f"post_match_final row for {row['team']} referenced before kickoff",
            })

    # 2. Pre-match prediction context: no final scores in match row when asof < kickoff
    if asof and kickoff and asof < kickoff:
        if snum(m, "status") == "finished" and snum(m, "home_score"):
            violations.append({
                "match_id": match_id,
                "check": "prematch_score_leak",
                "severity": "error",
                "detail": "finished scores present before kickoff asof",
            })

    # 3. odds fetched_at must be <= kickoff (when both present)
    for row in read_csv(NORMALIZED_TABLES["odds_snapshots"]):
        if row["match_id"] != match_id:
            continue
        fetched = parse_utc(snum(row, "fetched_at_utc"))
        if fetched and kickoff and fetched > kickoff:
            violations.append({
                "match_id": match_id,
                "check": "odds_after_kickoff",
                "severity": "warning",
                "detail": f"odds fetched {fetched.isoformat()} after kickoff",
            })

    # 4. lineups confirmed_at after kickoff → should be unavailable (warning)
    for row in read_csv(NORMALIZED_TABLES["lineups"]):
        if row["match_id"] != match_id:
            continue
        confirmed = parse_utc(snum(row, "confirmed_at_utc"))
        if confirmed and kickoff and confirmed > kickoff:
            if snum(row, "lineup_status") == "confirmed":
                violations.append({
                    "match_id": match_id,
                    "check": "lineup_confirmed_after_kickoff",
                    "severity": "warning",
                    "detail": f"lineup {row['player_name']} confirmed after kickoff",
                })

    # 5. realization features must exist and have neutral fallbacks documented
    real = [r for r in read_csv(FEATURE_TABLES["realization"]) if r["match_id"] == match_id]
    if not real:
        violations.append({
            "match_id": match_id,
            "check": "realization_features",
            "severity": "warning",
            "detail": "no v37_realization_features row",
        })

    return violations


def validate_all(asof: datetime | None = None) -> tuple[list[dict], dict[str, Any]]:
    all_v: list[dict] = []
    matches = read_csv(NORMALIZED_TABLES["matches"])
    for m in matches:
        all_v.extend(validate_match(m["match_id"], asof))
    errors_by_match: dict[str, int] = {}
    for v in all_v:
        if v["severity"] == "error":
            errors_by_match[v["match_id"]] = errors_by_match.get(v["match_id"], 0) + 1
    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "match_count": len(matches),
        "violation_count": len(all_v),
        "error_count": sum(1 for v in all_v if v["severity"] == "error"),
        "warning_count": sum(1 for v in all_v if v["severity"] == "warning"),
        "matches_with_errors": len(errors_by_match),
        "matches_clean": len(matches) - len(errors_by_match),
        "asof": asof.isoformat() if asof else None,
        "per_match_error_counts": errors_by_match,
    }
    return all_v, summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate V3.7 feature timing / leakage")
    ap.add_argument("--match-id", default="", help="Single match or all if empty")
    ap.add_argument("--asof", default="", help="ISO timestamp e.g. 2026-06-20T23:59:00Z")
    ap.add_argument("--fail-on-error", action="store_true")
    args = ap.parse_args()

    ensure_v37_dirs()
    asof = parse_utc(args.asof) if args.asof else None

    if args.match_id:
        violations = validate_match(args.match_id, asof)
        summary = {"match_id": args.match_id, "violation_count": len(violations)}
    else:
        violations, summary = validate_all(asof)

    out_path = V37_AUDIT / "prepost_leakage_audit.csv"
    write_csv(out_path, violations, VIOLATION_FIELDS)
    (V37_AUDIT / "timing_validation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))
    if violations:
        for v in violations[:10]:
            print(f"  [{v['severity']}] {v['check']}: {v['detail']}")

    if args.fail_on_error and summary.get("error_count", len([v for v in violations if v["severity"] == "error"])) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
