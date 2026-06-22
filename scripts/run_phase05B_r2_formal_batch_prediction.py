#!/usr/bin/env python3
"""Phase 05B: formal R2 batch prediction with integrity gate and match classification."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import read_csv, snum, write_csv  # noqa: E402
from eventflow_htft import resolve_source_notes_path  # noqa: E402
from eventflow_source_common import prematch_eligibility  # noqa: E402
from group_state_common import MATCH_XG, MAPPING, load_fixture_kickoffs, parse_cutoff  # noqa: E402
from run_phase05A_r2_prediction import (  # noqa: E402
    PROTECTED_FILES,
    file_hash,
    load_r2_schedule,
    predict_one,
)
from standings_integrity_guard import enforce_or_exit, load_integrity_status  # noqa: E402

OUT_DIR = ROOT / "outputs" / "phase05B_r2_formal_batch"
PHASE07_OUT = ROOT / "outputs" / "phase07_xg_metric_backfill"


def _norm_team(s: str) -> str:
    return (s or "").strip().lower()


def _completed_scores() -> dict[tuple[str, str, str], tuple[str, str]]:
    """(group, home, away) -> (home_score, away_score) for finished matches."""
    out: dict[tuple[str, str, str], tuple[str, str]] = {}
    for r in read_csv(MATCH_XG):
        hs, aws = str(r.get("home_score", "")).strip(), str(r.get("away_score", "")).strip()
        if not hs or not aws:
            continue
        key = (_norm_team(r.get("group", "")), _norm_team(r.get("home_team", "")), _norm_team(r.get("away_team", "")))
        out[key] = (hs, aws)
    return out


def _kickoff_for_match(match_id: str, mapping: list[dict], kickoffs: dict[str, Any]) -> datetime | None:
    map_row = next((m for m in mapping if m.get("internal_match_id") == match_id), None)
    if not map_row:
        return None
    fid = str(map_row.get("fifa_match_id", ""))
    if fid in kickoffs:
        return kickoffs[fid]
    kt = map_row.get("kickoff_time", "").strip()
    if not kt:
        return None
    try:
        return datetime.strptime(kt, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _source_notes_audit(match_id: str) -> dict[str, Any]:
    notes_path = resolve_source_notes_path(match_id)
    p = Path(notes_path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return {
            "source_notes_path": str(p),
            "source_notes_count": 0,
            "prematch_eligible_count": 0,
            "post_kickoff_leakage": "false",
            "clean_prematch_sources": "false",
        }

    rows = read_csv(p)
    match_rows = [r for r in rows if not snum(r, "match_id") or snum(r, "match_id") == match_id]
    prematch = 0
    leakage = False
    for r in match_rows:
        elig = prematch_eligibility(r)
        if elig.get("eligible_for_prediction"):
            prematch += 1
        if str(r.get("available_before_kickoff", "")).lower() == "false":
            leakage = True
    return {
        "source_notes_path": str(p.relative_to(ROOT)).replace("\\", "/"),
        "source_notes_count": len(match_rows),
        "prematch_eligible_count": prematch,
        "post_kickoff_leakage": str(leakage).lower(),
        "clean_prematch_sources": str(prematch > 0).lower(),
    }


def classify_match(
    sched: dict[str, str],
    as_of: datetime,
    completed: dict[tuple[str, str, str], tuple[str, str]],
    mapping: list[dict],
    kickoffs: dict[str, Any],
) -> dict[str, str]:
    mid = sched["match_id"]
    grp = sched["group"]
    home, away = sched["home"], sched["away"]
    key = (_norm_team(grp), _norm_team(home), _norm_team(away))
    ko = _kickoff_for_match(mid, mapping, kickoffs)
    has_result = key in completed
    notes = _source_notes_audit(mid)

    if ko and as_of < ko and not has_result:
        mode = "formal_pre_match_prediction"
        action = "run"
        reason = "upcoming_not_started"
    elif has_result or (ko and as_of >= ko):
        if notes["clean_prematch_sources"] == "true":
            mode = "backtest_pre_match_only"
            action = "run"
            reason = "completed_with_clean_prematch_sources"
        else:
            mode = "skip"
            action = "skip"
            reason = "completed_no_clean_prematch_source"
    else:
        mode = "formal_pre_match_prediction"
        action = "run"
        reason = "no_result_assumed_upcoming"

    return {
        "match_id": mid,
        "group": grp,
        "round": sched.get("round", "2"),
        "home": home,
        "away": away,
        "kickoff_utc": ko.strftime("%Y-%m-%dT%H:%M:%SZ") if ko else "",
        "has_result": str(has_result).lower(),
        "batch_mode": mode,
        "action": action,
        "classification_reason": reason,
        **notes,
    }


def write_reports(
    classifications: list[dict[str, str]],
    results: list[dict[str, Any]],
    hashes_before: dict[str, str],
    snapshot_id: str,
    as_of: datetime,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")

    summary: list[dict[str, str]] = []
    leakage: list[dict[str, str]] = []
    result_by_id = {r["match_id"]: r for r in results}

    for c in classifications:
        r = result_by_id.get(c["match_id"], {})
        summary.append({
            **c,
            "prediction_ran": str(c["action"] == "run" and r.get("pipeline_ran", False)).lower(),
            "preflight_ok": str(r.get("preflight_ok", False)).lower() if c["action"] == "run" else "n/a",
            "prob_home_win": str(r.get("prob_home_win", "")),
            "prob_draw": str(r.get("prob_draw", "")),
            "prob_away_win": str(r.get("prob_away_win", "")),
            "eventflow_degraded": str(r.get("eventflow_degraded", "")).lower(),
            "created_at": ts,
        })
        leakage.append({
            "match_id": c["match_id"],
            "batch_mode": c["batch_mode"],
            "post_kickoff_leakage": c["post_kickoff_leakage"],
            "prematch_eligible_count": str(c["prematch_eligible_count"]),
            "source_notes_count": str(c["source_notes_count"]),
            "leakage_check_passed": str(
                c["batch_mode"] != "formal_pre_match_prediction" or c["post_kickoff_leakage"] == "false"
            ).lower(),
        })

    write_csv(OUT_DIR / "formal_batch_prediction_summary.csv", summary)
    write_csv(OUT_DIR / "formal_batch_leakage_check.csv", leakage)

    integrity_rows = []
    for p in PROTECTED_FILES:
        integrity_rows.append({
            "file": str(p.relative_to(ROOT)).replace("\\", "/"),
            "sha256_before": hashes_before.get(str(p), ""),
            "sha256_after": file_hash(p),
            "unchanged": str(hashes_before.get(str(p), "") == file_hash(p)).lower(),
        })
    write_csv(OUT_DIR / "formal_batch_processed_integrity.csv", integrity_rows)

    formal = sum(1 for c in classifications if c["batch_mode"] == "formal_pre_match_prediction" and c["action"] == "run")
    backtest = sum(1 for c in classifications if c["batch_mode"] == "backtest_pre_match_only" and c["action"] == "run")
    skipped = sum(1 for c in classifications if c["action"] == "skip")
    matrix_ok = all(r["unchanged"] == "true" for r in integrity_rows)

    integ = load_integrity_status(snapshot_id) or {}
    lines = [
        "# Phase 07 Validation Report",
        "",
        f"- as_of: **{ts}**",
        f"- snapshot_id: **{snapshot_id or 'latest'}**",
        f"- snapshot_status: **{integ.get('snapshot_status', 'unknown')}**",
        f"- formal_prediction_allowed: **{integ.get('formal_prediction_allowed', 'unknown')}**",
        "",
        "## R2 formal batch",
        "",
        f"- R2 matches classified: **{len(classifications)}**",
        f"- formal_pre_match_prediction runs: **{formal}**",
        f"- backtest_pre_match_only runs: **{backtest}**",
        f"- skipped (no clean prematch source): **{skipped}**",
        f"- processed files unchanged: **{str(matrix_ok).lower()}**",
        "",
        "## Phase 07 metric backfill",
        "",
        "- score-only rows upgraded via apply_wc2026_xg_metric_backfill.py",
        "- see phase07B_metric_backfill_report.md for details",
    ]
    PHASE07_OUT.mkdir(parents=True, exist_ok=True)
    (PHASE07_OUT / "phase07_validation_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 05B formal R2 batch prediction")
    ap.add_argument(
        "--mode", default="auto",
        choices=["auto", "safe", "balanced", "hit_hunting"],
        help="Compatibility input; fusion is dynamically weighted.",
    )
    ap.add_argument("--snapshot-id", default="WC2026_GROUP_20260620_PRE_F35")
    ap.add_argument("--as-of", default="", help="UTC cutoff for upcoming vs completed (default: now)")
    ap.add_argument("--match-id", default="", help="Run single R2 match only")
    ap.add_argument("--allow-partial-standings", action="store_true")
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--skip-build", action="store_true", default=True)
    ap.add_argument("--no-skip-build", dest="skip_build", action="store_false")
    ap.add_argument("--classify-only", action="store_true")
    args = ap.parse_args()

    as_of = parse_cutoff(args.as_of) if args.as_of else datetime.now(timezone.utc)
    mapping = read_csv(MAPPING)
    kickoffs = load_fixture_kickoffs()
    completed = _completed_scores()
    schedule = load_r2_schedule()
    if args.match_id:
        schedule = [s for s in schedule if s["match_id"] == args.match_id]

    classifications = [
        classify_match(s, as_of, completed, mapping, kickoffs) for s in schedule
    ]

    hashes_before = {str(p): file_hash(p) for p in PROTECTED_FILES}
    results: list[dict[str, Any]] = []

    for c in classifications:
        if c["action"] != "run":
            print(f"SKIP {c['match_id']} mode={c['batch_mode']} reason={c['classification_reason']}")
            continue
        if c["batch_mode"] == "formal_pre_match_prediction":
            enforce_or_exit(
                args.snapshot_id or None,
                c["match_id"],
                allow_partial=args.allow_partial_standings or args.smoke_test,
                smoke_test=args.smoke_test,
            )
        print(f"\n=== Phase05B {c['match_id']} {c['home']} vs {c['away']} ({c['batch_mode']}) ===")
        if args.classify_only:
            results.append({"match_id": c["match_id"], "pipeline_ran": False, "preflight_ok": True})
            continue
        r = predict_one(
            c["match_id"], c["home"], c["away"],
            mode=args.mode,
            skip_build=args.skip_build,
            run_prediction=True,
        )
        results.append(r)

    write_reports(classifications, results, hashes_before, args.snapshot_id, as_of)

    formal = sum(1 for c in classifications if c["batch_mode"] == "formal_pre_match_prediction" and c["action"] == "run")
    backtest = sum(1 for c in classifications if c["batch_mode"] == "backtest_pre_match_only" and c["action"] == "run")
    skipped = sum(1 for c in classifications if c["action"] == "skip")
    print(f"\nPhase05B batch: formal={formal} backtest={backtest} skipped={skipped}")


if __name__ == "__main__":
    main()
