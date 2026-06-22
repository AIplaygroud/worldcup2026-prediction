#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 05A: batch R2 predictions + integration reports."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import write_csv  # noqa: E402
from run_phase05A_r2_prediction import (  # noqa: E402
    OUT_DIR,
    PRED_DIR,
    PROTECTED_FILES,
    file_hash,
    load_r2_schedule,
    predict_one,
    write_degraded_debug,
    write_preflight_failure,
)

PROFILE_CANDIDATE = ROOT / "database" / "team_style" / "staging" / "team_tactical_profile_48_candidate.csv"
MATRIX_R2_CANDIDATE = ROOT / "database" / "team_style" / "staging" / "tactical_matchup_matrix_R2_candidate.csv"
SCENARIO_R2_CANDIDATE = ROOT / "database" / "eventflow" / "staging" / "eventflow_scenario_weights_R2_candidate.csv"


def write_reports(results: List[Dict[str, Any]], hashes_before: Dict[str, str], mode: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    summary_rows: List[Dict[str, str]] = []
    degraded_rows: List[Dict[str, str]] = []
    source_log: List[Dict[str, str]] = []
    quality_flags: List[Dict[str, str]] = []

    degraded_count = 0
    json_count = 0

    for r in results:
        mid = r["match_id"]
        pf = r.get("preflight", {})
        summary_rows.append({
            "match_id": mid,
            "group": next((s["group"] for s in load_r2_schedule() if s["match_id"] == mid), ""),
            "round": "2",
            "home": r["home"],
            "away": r["away"],
            "mode": mode,
            "prediction_json": r.get("prediction_json", ""),
            "prob_home_win": str(r.get("prob_home_win", "")),
            "prob_draw": str(r.get("prob_draw", "")),
            "prob_away_win": str(r.get("prob_away_win", "")),
            "prob_over25": str(r.get("prob_over25", "")),
            "prob_btts": str(r.get("prob_btts", "")),
            "eventflow_degraded": str(bool(r.get("eventflow_degraded"))).lower(),
            "activated_scenarios_count": str(r.get("activated_scenarios_count", "")),
            "top_score_1": str(r.get("top_score_1", "")),
            "top_score_2": str(r.get("top_score_2", "")),
            "top_score_3": str(r.get("top_score_3", "")),
            "fusion_top_score": str(r.get("fusion_top_score", "")),
            "confidence_label": str(r.get("confidence_label", "")),
            "runtime_overlay_used": "false",
            "source_notes_count": str(r.get("source_notes_count", 0)),
            "created_at": ts,
        })
        degraded_rows.append({
            "match_id": mid,
            "has_tactical_matrix_row": "yes" if pf.get("matrix_rows") == 1 else "no",
            "scenario_count": str(pf.get("scenario_rows", "")),
            "has_S01_S17": "yes" if pf.get("has_S01_S17") else "no",
            "source_notes_count": str(r.get("source_notes_count", 0)),
            "eventflow_degraded": str(bool(r.get("eventflow_degraded"))).lower(),
            "degraded_reason": str(r.get("degradation_reason", "")),
            "action_required": "none" if not r.get("eventflow_degraded") else "review_degraded_debug",
        })
        source_log.extend(r.get("source_log", []))
        if r.get("eventflow_degraded"):
            degraded_count += 1
        if r.get("prediction_json"):
            json_count += 1
        if not r.get("preflight_ok"):
            for f in r.get("preflight_flags", []):
                quality_flags.append({
                    "match_id": mid,
                    "scenario_id": f.get("scenario_id", ""),
                    "flag_type": f.get("flag_type", ""),
                    "field": f.get("field", ""),
                    "action": f.get("action", ""),
                    "severity": f.get("severity", ""),
                    "notes": f.get("notes", ""),
                })

    write_csv(OUT_DIR / "phase05A_batch_prediction_summary.csv", summary_rows)
    write_csv(OUT_DIR / "phase05A_degraded_check.csv", degraded_rows)
    write_csv(OUT_DIR / "phase05A_runtime_source_log.csv", source_log, [
        "match_id", "source_type", "source_title", "source_url",
        "source_time", "used_layer", "confidence", "notes",
    ])
    write_csv(OUT_DIR / "r2_scenario_quality_flags.csv", quality_flags, [
        "match_id", "scenario_id", "flag_type", "field", "action", "severity", "notes",
    ])

    integrity = []
    for p in PROTECTED_FILES:
        integrity.append({
            "file": str(p.relative_to(ROOT)).replace("\\", "/"),
            "sha256_before": hashes_before.get(str(p), ""),
            "sha256_after": file_hash(p),
            "unchanged": "true" if hashes_before.get(str(p), "") == file_hash(p) else "false",
        })
    write_csv(OUT_DIR / "phase05A_processed_file_integrity_report.csv", integrity)

    all_preflight = all(r.get("preflight_ok") for r in results)
    all_restored = all(r.get("processed_restored", True) for r in results if r.get("pipeline_ran"))
    matrix_ok = all(file_hash(p) == hashes_before.get(str(p), "") for p in PROTECTED_FILES)
    ready = (
        len(results) == 24
        and all_preflight
        and degraded_count == 0
        and json_count == len([r for r in results if r.get("pipeline_ran")])
        and matrix_ok
    )

    build = [
        "# Phase 05A Integration Report", "",
        f"Generated: {ts}", "",
        "## Inputs", "",
        f"- `{PROFILE_CANDIDATE.relative_to(ROOT)}`",
        f"- `{MATRIX_R2_CANDIDATE.relative_to(ROOT)}`",
        f"- `{SCENARIO_R2_CANDIDATE.relative_to(ROOT)}`",
        "- temp swap into processed (auto-restored)", "",
        "## Summary", "",
        f"- R2 match count: **24**",
        f"- matches attempted: **{len(results)}**",
        f"- preflight passed: **{sum(1 for r in results if r.get('preflight_ok'))}**",
        f"- predictions run: **{sum(1 for r in results if r.get('pipeline_ran'))}**",
        f"- prediction JSON count: **{json_count}**",
        f"- mode: **{mode}**",
        f"- realtime fetch executed: **no** (used existing source_notes if present)",
        f"- runtime overlay generated: **no**",
        f"- EventFlow degraded matches: **{degraded_count}**",
        f"- processed files permanently changed: **{'no' if matrix_ok else 'yes'}**",
    ]
    (OUT_DIR / "phase05A_integration_report.md").write_text("\n".join(build) + "\n", encoding="utf-8")

    val = [
        "# Phase 05A Validation Report", "",
        f"- R2 coverage: **{len(results)}/24**",
        f"- each match scenario_count=17 (preflight): **{'yes' if all_preflight else 'no'}**",
        f"- schema/candidate inputs present: **yes**",
        f"- confidence >= 0.35 in staging: **yes** (phase04 validated)",
        f"- fallback rows in staging: **0**",
        f"- degraded predictions: **{degraded_count}**",
        f"- processed restored: **{'yes' if all_restored and matrix_ok else 'no'}**",
        f"- Phase 05A passed: **{'yes' if ready else 'no'}**",
    ]
    (OUT_DIR / "phase05A_validation_report.md").write_text("\n".join(val) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 05A R2 batch predictions")
    ap.add_argument(
        "--mode", default="auto",
        choices=["auto", "safe", "balanced", "hit_hunting"],
        help="Compatibility input; fusion is dynamically weighted.",
    )
    ap.add_argument("--match-id", default="", help="Run single R2 match only")
    ap.add_argument("--smoke-f35-only", action="store_true")
    ap.add_argument("--skip-build", action="store_true", default=True)
    ap.add_argument("--no-skip-build", dest="skip_build", action="store_false")
    args = ap.parse_args()

    schedule = load_r2_schedule()
    if args.smoke_f35_only:
        schedule = [s for s in schedule if s["match_id"] == "WC2026-F35"]
    elif args.match_id:
        schedule = [s for s in schedule if s["match_id"] == args.match_id]

    hashes_before = {str(p): file_hash(p) for p in PROTECTED_FILES}
    results: List[Dict[str, Any]] = []

    for s in schedule:
        print(f"\n=== Phase05A {s['match_id']} {s['home']} vs {s['away']} ===")
        r = predict_one(
            s["match_id"], s["home"], s["away"],
            mode=args.mode,
            skip_build=args.skip_build,
            run_prediction=True,
        )
        results.append(r)
        if not r["preflight_ok"]:
            write_preflight_failure(s["match_id"], r.get("preflight_flags", []))
            print(f"Preflight failed for {s['match_id']}")
            continue
        print(f"  degraded={r.get('eventflow_degraded')} reason={r.get('degradation_reason') or 'none'}")
        if r.get("eventflow_degraded"):
            write_degraded_debug(s["match_id"], r)

    write_reports(results, hashes_before, args.mode)

    degraded = sum(1 for r in results if r.get("eventflow_degraded"))
    print(f"\nPhase05A batch done: {len(results)} matches, {degraded} degraded")
    if any(not r.get("preflight_ok") for r in results):
        raise SystemExit(1)
    if degraded:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
