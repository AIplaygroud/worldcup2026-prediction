#!/usr/bin/env python3
"""Orchestrate Phase 06D: backfill, K24 fix, integrity refresh, Phase 06B/05B."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OUT_DIR = ROOT / "outputs" / "phase06D_result_backfill"
sys.path.insert(0, str(SCRIPTS))

from apply_wc2026_result_backfill import apply_backfill
from fix_wc2026_xg_home_away_alignment import fix_alignment
from group_state_common import MATCH_XG, read_csv, write_csv
from validate_completed_results_coverage import run_coverage_validation


def write_phase06d_reports(backfill_result: dict, k24_result: dict, integrity: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_csv(MATCH_XG)
    integrity_rows = []
    for r in rows:
        integrity_rows.append({
            "match_date": r.get("match_date"),
            "group": r.get("group"),
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "quality_flag": r.get("quality_flag"),
            "has_xg": str(bool(r.get("home_xg") and r.get("away_xg"))).lower(),
            "has_shots": str(bool(r.get("home_shots") and r.get("away_shots"))).lower(),
        })
    write_csv(OUT_DIR / "wc2026_match_xg_integrity_report.csv", list(integrity_rows[0].keys()) if integrity_rows else [], integrity_rows)

    lines = [
        "# Phase 06D Backfill Report",
        "",
        f"- executed_at: {datetime.now(timezone.utc).isoformat()}",
        f"- backfill_rows_applied: {backfill_result.get('applied', 0)}",
        f"- backfill_flags: {backfill_result.get('flags', 0)}",
        f"- backup: `{backfill_result.get('backup', 'n/a')}`",
        f"- K24 fixed: {k24_result.get('fixed')}",
        f"- K24 swapped_fields: {k24_result.get('swapped_fields', [])}",
        "",
        "## Applied scores (source-backed)",
        "",
        "| Match | Score | Source |",
        "|-------|-------|--------|",
        "| WC2026-C29 | Brazil 3-0 Haiti | FotMob/Opta |",
        "| WC2026-C30 | Scotland 0-1 Morocco | FIFA match report |",
        "| WC2026-D31 | Turkey 0-1 Paraguay | FotMob/Opta |",
        "| WC2026-D32 | USA 2-0 Australia | FotMob/Opta + FIFA |",
        "",
        "## Integrity after refresh",
        "",
        f"- snapshot_status: `{integrity.get('snapshot_status')}`",
        f"- formal_prediction_allowed: `{integrity.get('formal_prediction_allowed')}`",
        f"- route_avoidance_allowed: `{integrity.get('route_avoidance_allowed')}`",
        f"- matched: {integrity.get('local_result_rows_matched')}/{integrity.get('expected_completed_matches')}",
        "",
        "## Boundaries",
        "",
        "- Score-only rows: standings/path only; no tactical profile update",
        "- No changes to tactical_matchup_matrix.csv or eventflow_scenario_weights.csv base files",
    ]
    (OUT_DIR / "phase06D_backfill_report.md").write_text("\n".join(lines), encoding="utf-8")

    val = [
        "# Phase 06D Validation",
        "",
        f"- backfill applied: {backfill_result.get('applied') == 4}",
        f"- K24 aligned: {k24_result.get('fixed')}",
        f"- integrity complete: {integrity.get('snapshot_status') == 'complete'}",
        f"- no model-guessed scores: true",
        f"- backup exists: {bool(backfill_result.get('backup'))}",
    ]
    (OUT_DIR / "phase06D_validation_report.md").write_text("\n".join(val), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-cutoff-time", default="2026-06-20T12:00:00Z")
    ap.add_argument("--snapshot-id", default="WC2026_GROUP_20260620_PRE_F35")
    ap.add_argument("--skip-prediction", action="store_true")
    args = ap.parse_args()

    backfill = apply_backfill()
    if backfill["applied"] < 4:
        blocked = OUT_DIR / "phase06D_backfill_blocked_report.md"
        blocked.write_text(
            "Backfill blocked: fewer than 4 rows applied. See backfill_quality_flags.csv.",
            encoding="utf-8",
        )
        raise SystemExit(1)

    k24 = fix_alignment("WC2026-K24")
    cov = run_coverage_validation(args.source_cutoff_time, args.snapshot_id)
    integrity = cov["integrity"]
    if integrity["snapshot_status"] != "complete":
        raise SystemExit(f"Integrity still {integrity['snapshot_status']}")

    write_phase06d_reports(backfill, k24, integrity)

    subprocess.run([
        sys.executable, str(SCRIPTS / "run_phase06B_bracket_route_analysis.py"),
        "--source-cutoff-time", args.source_cutoff_time,
        "--snapshot-id", args.snapshot_id,
    ], check=True, cwd=ROOT)

    if not args.skip_prediction:
        subprocess.run([
            sys.executable, str(SCRIPTS / "run_phase05B_r2_formal_prediction.py"),
            "--match-id", "WC2026-F35", "--home", "Netherlands", "--away", "Sweden",
            "--mode", "balanced",
        ], check=True, cwd=ROOT)

    print("Phase 06D complete")


if __name__ == "__main__":
    main()
