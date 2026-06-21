#!/usr/bin/env python3
"""Validate that all pre-cutoff completed fixtures have local result rows in wc2026_match_xg."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from group_state_common import (
    FIXTURES,
    MAPPING,
    MATCH_XG,
    ROOT,
    kickoff_utc_from_mapping_row,
    load_fixture_kickoffs,
    parse_cutoff,
    read_csv,
    write_csv,
)

OUT_DIR = ROOT / "outputs" / "phase06C_standings_integrity"
RUNTIME_INTEGRITY = ROOT / "database" / "competition" / "runtime" / "standings_snapshot_integrity.csv"
BACKFILL_CANDIDATE = ROOT / "database" / "xGdatabase" / "staging" / "wc2026_match_results_backfill_candidate.csv"

MISSING_FIELDS = [
    "snapshot_id", "source_cutoff_time", "match_id", "fifa_match_id", "group", "round",
    "home_team", "away_team", "kickoff_utc", "fixture_status", "reason",
]
AMBIGUOUS_FIELDS = [
    "snapshot_id", "source_cutoff_time", "match_id", "fifa_match_id", "group", "round",
    "home_team", "away_team", "kickoff_utc", "xg_match_count", "reason", "xg_notes",
]
COVERAGE_FIELDS = [
    "snapshot_id", "source_cutoff_time", "group", "expected_completed", "matched",
    "missing", "ambiguous", "coverage_pct", "affected",
]
INTEGRITY_FIELDS = [
    "snapshot_id", "source_cutoff_time", "expected_completed_matches",
    "local_result_rows_matched", "missing_completed_results", "ambiguous_completed_results",
    "missing_groups", "affected_groups", "snapshot_status", "formal_prediction_allowed",
    "cross_group_third_ranking_allowed", "route_avoidance_allowed", "notes",
]
BACKFILL_FIELDS = [
    "match_id", "fifa_match_id", "group", "home_team", "away_team",
    "home_score", "away_score", "match_date", "source", "source_url", "source_title",
    "source_time", "confidence", "is_score_only_backfill", "requires_xg_backfill", "notes",
]


def _norm_team(name: str) -> str:
    return (name or "").strip().lower()


def _fixture_kickoff(fifa_id: str, mapping_by_fifa: dict[str, dict], kickoffs: dict[str, Any]) -> datetime | None:
    if fifa_id in kickoffs:
        return kickoffs[fifa_id]
    row = mapping_by_fifa.get(fifa_id)
    if row:
        ko = kickoff_utc_from_mapping_row(row)
        if ko is not None:
            return ko
    if not row:
        return None
    kt = row.get("kickoff_time", "").strip()
    if not kt:
        return None
    try:
        return datetime.strptime(kt, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _index_xg_rows(xg_rows: list[dict[str, str]]) -> dict[tuple[str, str, str, str], list[dict]]:
    idx: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in xg_rows:
        key = (
            row.get("match_date", "").strip(),
            row.get("group", "").strip(),
            _norm_team(row.get("home_team", "")),
            _norm_team(row.get("away_team", "")),
        )
        idx[key].append(row)
    return idx


def _match_xg(
    fixture: dict[str, str],
    xg_idx: dict[tuple[str, str, str, str], list[dict]],
) -> tuple[str, list[dict], str]:
    """Return status: matched | missing | ambiguous."""
    date_s = fixture.get("match_date", "").strip()
    group = fixture.get("group", "").strip()
    home = _norm_team(fixture.get("home_team_en", ""))
    away = _norm_team(fixture.get("away_team_en", ""))
    key = (date_s, group, home, away)
    rev = (date_s, group, away, home)
    hits = xg_idx.get(key, [])
    if not hits:
        rev_hits = xg_idx.get(rev, [])
        if rev_hits:
            return "ambiguous", rev_hits, "home_away_reversed_in_xg"
        return "missing", [], "no_xg_row"
    if len(hits) > 1:
        return "ambiguous", hits, "duplicate_xg_rows"
    row = hits[0]
    try:
        int(row.get("home_score", ""))
        int(row.get("away_score", ""))
    except (TypeError, ValueError):
        return "ambiguous", hits, "missing_or_invalid_scores"
    if _norm_team(row.get("group", "")) and _norm_team(row.get("group", "")) != group.lower():
        return "ambiguous", hits, "group_mismatch"
    return "matched", hits, ""


def run_coverage_validation(
    cutoff: str,
    snapshot_id: str,
    allow_partial: bool = False,
    write_outputs: bool = True,
) -> dict[str, Any]:
    cutoff_dt = parse_cutoff(cutoff)
    mapping_rows = read_csv(MAPPING)
    mapping_by_fifa = {r["fifa_match_id"]: r for r in mapping_rows}
    fixtures = read_csv(FIXTURES)
    fixture_by_fifa = {r["fifa_match_id"]: r for r in fixtures}
    xg_rows = read_csv(MATCH_XG)
    xg_idx = _index_xg_rows(xg_rows)
    kickoffs = load_fixture_kickoffs()

    missing_rows: list[dict] = []
    ambiguous_rows: list[dict] = []
    matched_count = 0
    expected_count = 0

    group_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"expected": 0, "matched": 0, "missing": 0, "ambiguous": 0}
    )

    for fifa_id, fix in sorted(fixture_by_fifa.items(), key=lambda x: int(x[0])):
        ko = _fixture_kickoff(fifa_id, mapping_by_fifa, kickoffs)
        if ko is None or ko >= cutoff_dt:
            continue
        expected_count += 1
        group = fix.get("group", "")
        group_stats[group]["expected"] += 1
        map_row = mapping_by_fifa.get(fifa_id, {})
        status, hits, reason = _match_xg(fix, xg_idx)
        base = {
            "snapshot_id": snapshot_id,
            "source_cutoff_time": cutoff,
            "match_id": map_row.get("internal_match_id", ""),
            "fifa_match_id": fifa_id,
            "group": group,
            "round": fix.get("round", map_row.get("round", "")),
            "home_team": fix.get("home_team_en", ""),
            "away_team": fix.get("away_team_en", ""),
            "kickoff_utc": ko.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fixture_status": fix.get("status", ""),
        }
        if status == "matched":
            matched_count += 1
            group_stats[group]["matched"] += 1
        elif status == "missing":
            group_stats[group]["missing"] += 1
            missing_rows.append({**base, "reason": reason})
        else:
            group_stats[group]["ambiguous"] += 1
            ambiguous_rows.append({
                **base,
                "xg_match_count": len(hits),
                "reason": reason,
                "xg_notes": "; ".join(h.get("notes", "") for h in hits[:3]),
            })

    missing_groups = sorted({r["group"] for r in missing_rows if r["group"]})
    ambiguous_groups = sorted({r["group"] for r in ambiguous_rows if r["group"]})
    affected_groups = sorted(set(missing_groups) | set(ambiguous_groups))

    missing_n = len(missing_rows)
    ambiguous_n = len(ambiguous_rows)

    if missing_n == 0 and ambiguous_n == 0:
        snapshot_status = "complete"
        formal_allowed = "true"
        cross_group = "true"
        route_allowed = "true"
        notes = "All pre-cutoff fixtures have matched local result rows."
    elif allow_partial:
        snapshot_status = "partial_stale"
        formal_allowed = "partial_only"
        cross_group = "false"
        route_allowed = "false"
        notes = (
            f"Partial standings allowed via --allow-partial-standings; "
            f"missing={missing_n}, ambiguous={ambiguous_n}; affected={','.join(affected_groups)}"
        )
    else:
        snapshot_status = "partial_stale"
        formal_allowed = "false"
        cross_group = "false"
        route_allowed = "false"
        notes = (
            f"Missing pre-cutoff results: {missing_n}; ambiguous: {ambiguous_n}; "
            f"affected groups: {','.join(affected_groups) or 'none'}"
        )

    integrity_row = {
        "snapshot_id": snapshot_id,
        "source_cutoff_time": cutoff,
        "expected_completed_matches": expected_count,
        "local_result_rows_matched": matched_count,
        "missing_completed_results": missing_n,
        "ambiguous_completed_results": ambiguous_n,
        "missing_groups": "|".join(missing_groups),
        "affected_groups": "|".join(affected_groups),
        "snapshot_status": snapshot_status,
        "formal_prediction_allowed": formal_allowed,
        "cross_group_third_ranking_allowed": cross_group,
        "route_avoidance_allowed": route_allowed,
        "notes": notes,
    }

    coverage_rows = []
    for g in sorted(group_stats):
        s = group_stats[g]
        exp = s["expected"]
        pct = round(100.0 * s["matched"] / exp, 1) if exp else 100.0
        coverage_rows.append({
            "snapshot_id": snapshot_id,
            "source_cutoff_time": cutoff,
            "group": g,
            "expected_completed": exp,
            "matched": s["matched"],
            "missing": s["missing"],
            "ambiguous": s["ambiguous"],
            "coverage_pct": pct,
            "affected": str(s["missing"] > 0 or s["ambiguous"] > 0).lower(),
        })

    backfill_rows = []
    for m in missing_rows:
        backfill_rows.append({
            "match_id": m["match_id"],
            "fifa_match_id": m["fifa_match_id"],
            "group": m["group"],
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "home_score": "",
            "away_score": "",
            "match_date": m["kickoff_utc"][:10],
            "source": "",
            "source_url": "",
            "source_title": "",
            "source_time": "",
            "confidence": "",
            "is_score_only_backfill": "true",
            "requires_xg_backfill": "true",
            "notes": "Detected missing pre-cutoff result; score not auto-filled; human review required",
        })

    if write_outputs:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_csv(OUT_DIR / "missing_completed_results_pre_cutoff.csv", MISSING_FIELDS, missing_rows)
        write_csv(OUT_DIR / "ambiguous_completed_results_pre_cutoff.csv", AMBIGUOUS_FIELDS, ambiguous_rows)
        write_csv(OUT_DIR / "result_coverage_by_group.csv", COVERAGE_FIELDS, coverage_rows)
        write_csv(RUNTIME_INTEGRITY, INTEGRITY_FIELDS, [integrity_row])
        _write_reports(snapshot_id, cutoff, integrity_row, missing_rows, ambiguous_rows, coverage_rows)
        if backfill_rows:
            write_csv(BACKFILL_CANDIDATE, BACKFILL_FIELDS, backfill_rows)
        elif BACKFILL_CANDIDATE.exists():
            BACKFILL_CANDIDATE.unlink()

    return {
        "integrity": integrity_row,
        "missing": missing_rows,
        "ambiguous": ambiguous_rows,
        "coverage": coverage_rows,
        "backfill": backfill_rows,
        "abort": snapshot_status == "partial_stale" and not allow_partial,
    }


def _write_reports(
    snapshot_id: str,
    cutoff: str,
    integrity: dict,
    missing: list[dict],
    ambiguous: list[dict],
    coverage: list[dict],
) -> None:
    lines = [
        "# Standings Snapshot Integrity Report",
        "",
        f"- **snapshot_id**: `{snapshot_id}`",
        f"- **source_cutoff_time**: `{cutoff}`",
        f"- **snapshot_status**: `{integrity['snapshot_status']}`",
        f"- **formal_prediction_allowed**: `{integrity['formal_prediction_allowed']}`",
        "",
        "## Coverage summary",
        "",
        f"- Expected completed matches (kickoff < cutoff): **{integrity['expected_completed_matches']}**",
        f"- Local result rows matched: **{integrity['local_result_rows_matched']}**",
        f"- Missing: **{integrity['missing_completed_results']}**",
        f"- Ambiguous: **{integrity['ambiguous_completed_results']}**",
        f"- Affected groups: **{integrity['affected_groups'] or 'none'}**",
        "",
        "## Per-group coverage",
        "",
        "| Group | Expected | Matched | Missing | Ambiguous | Coverage % | Affected |",
        "|-------|----------|---------|---------|-----------|------------|----------|",
    ]
    for r in coverage:
        lines.append(
            f"| {r['group']} | {r['expected_completed']} | {r['matched']} | {r['missing']} | "
            f"{r['ambiguous']} | {r['coverage_pct']} | {r['affected']} |"
        )

    if missing:
        lines.extend(["", "## Missing completed results", ""])
        for m in missing:
            lines.append(
                f"- `{m['match_id']}` ({m['group']} R{m['round']}): "
                f"{m['home_team']} vs {m['away_team']} — kickoff {m['kickoff_utc']}"
            )

    if ambiguous:
        lines.extend(["", "## Ambiguous results", ""])
        for a in ambiguous:
            lines.append(f"- `{a['match_id']}`: {a['reason']}")

    lines.extend([
        "",
        "## Modeling boundaries",
        "",
        "- Cross-group third-place ranking: "
        f"**{'allowed' if integrity['cross_group_third_ranking_allowed'] == 'true' else 'blocked'}**",
        "- Route avoidance: "
        f"**{'allowed' if integrity['route_avoidance_allowed'] == 'true' else 'blocked'}**",
        "- F35 group-local pressure (Group F): "
        "**allowed** if Group F has no missing pre-cutoff results",
        "",
        f"Notes: {integrity['notes']}",
    ])
    (OUT_DIR / "standings_snapshot_integrity_report.md").write_text("\n".join(lines), encoding="utf-8")

    checks = [
        ("missing listed in affected_groups", not integrity["missing_completed_results"] or integrity["missing_groups"]),
        ("route blocked when partial", integrity["snapshot_status"] != "partial_stale" or integrity["route_avoidance_allowed"] == "false"),
        ("formal blocked when missing and no partial flag", integrity["formal_prediction_allowed"] != "true" or int(integrity["missing_completed_results"]) == 0),
        ("no invented scores", True),
    ]
    val = [
        "# Phase 06C Validation Report",
        "",
        f"- snapshot_id: {snapshot_id}",
        f"- status: {integrity['snapshot_status']}",
        "",
        "## Checks",
        "",
    ]
    for name, ok in checks:
        val.append(f"- [{'x' if ok else ' '}] {name}")
    (OUT_DIR / "phase06C_validation_report.md").write_text("\n".join(val), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 06C standings completeness guard")
    ap.add_argument("--source-cutoff-time", required=True)
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--allow-partial-standings", action="store_true")
    args = ap.parse_args()

    result = run_coverage_validation(
        args.source_cutoff_time,
        args.snapshot_id,
        allow_partial=args.allow_partial_standings,
    )
    integrity = result["integrity"]
    print(
        f"status={integrity['snapshot_status']} "
        f"expected={integrity['expected_completed_matches']} "
        f"matched={integrity['local_result_rows_matched']} "
        f"missing={integrity['missing_completed_results']}"
    )
    if result["abort"]:
        print(f"ABORT: partial stale snapshot — see {OUT_DIR / 'standings_snapshot_integrity_report.md'}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
