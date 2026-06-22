#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 05A: R2 prediction pipeline with staging candidate temp-swap."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eventflow_common import DB, EVENTFLOW_DB, TEAM_DB, read_csv, snum  # noqa: E402

OUT_DIR = ROOT / "outputs" / "phase05A_r2_prediction_pipeline"
PRED_DIR = OUT_DIR / "predictions"
BACKUP_DIR = ROOT / "backups" / "phase05A_r2_prediction_pipeline"

PROFILE_CANDIDATE = ROOT / "database" / "team_style" / "staging" / "team_tactical_profile_48_candidate.csv"
MATRIX_R2_CANDIDATE = ROOT / "database" / "team_style" / "staging" / "tactical_matchup_matrix_R2_candidate.csv"
SCENARIO_R2_CANDIDATE = ROOT / "database" / "eventflow" / "staging" / "eventflow_scenario_weights_R2_candidate.csv"

SWAP_TARGETS = [
    TEAM_DB / "team_tactical_profile.csv",
    TEAM_DB / "tactical_matchup_matrix.csv",
    EVENTFLOW_DB / "eventflow_scenario_weights.csv",
]

PROTECTED_FILES = [
    TEAM_DB / "team_formation_matchups.csv",
    TEAM_DB / "tactical_matchup_matrix.csv",
    EVENTFLOW_DB / "eventflow_scenario_weights.csv",
]

PRESERVED_MATRIX_IDS = {"WC2026-C29", "WC2026-C30", "WC2026-D31", "WC2026-D32"}


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scenario_num(sid: str) -> int:
    m = re.match(r"S(\d+)", sid or "")
    return int(m.group(1)) if m else 99


def load_r2_schedule() -> List[Dict[str, str]]:
    rows = read_csv(DB / "competition" / "wc2026_match_id_mapping.csv")
    return [
        {
            "match_id": snum(r, "internal_match_id"),
            "group": snum(r, "group"),
            "round": snum(r, "round"),
            "home": snum(r, "home_team"),
            "away": snum(r, "away_team"),
        }
        for r in rows
        if snum(r, "round") == "2"
    ]


def preflight(match_id: str, home: str, away: str) -> Tuple[bool, Dict[str, Any], List[Dict[str, str]]]:
    flags: List[Dict[str, str]] = []
    info: Dict[str, Any] = {"match_id": match_id, "home": home, "away": away}

    r2_ids = {s["match_id"] for s in load_r2_schedule()}
    if match_id not in r2_ids:
        flags.append({
            "match_id": match_id, "scenario_id": "", "flag_type": "not_r2",
            "field": "match_id", "action": "abort", "severity": "critical",
            "notes": f"{match_id} not in round==2 schedule",
        })
        return False, info, flags

    matrix_rows = [r for r in read_csv(MATRIX_R2_CANDIDATE) if snum(r, "match_id") == match_id]
    scenario_rows = [
        r for r in read_csv(SCENARIO_R2_CANDIDATE)
        if snum(r, "match_id") == match_id
        and snum(r, "home") == home
        and snum(r, "away") == away
    ]
    profiles = {snum(r, "team") for r in read_csv(PROFILE_CANDIDATE)}

    info["matrix_rows"] = len(matrix_rows)
    info["scenario_rows"] = len(scenario_rows)
    info["home_profile_found"] = home in profiles
    info["away_profile_found"] = away in profiles

    if len(matrix_rows) != 1:
        flags.append({
            "match_id": match_id, "scenario_id": "", "flag_type": "matrix_missing",
            "field": "tactical_matchup_matrix_R2_candidate", "action": "abort",
            "severity": "critical", "notes": f"matrix_rows={len(matrix_rows)}",
        })
    if home not in profiles or away not in profiles:
        flags.append({
            "match_id": match_id, "scenario_id": "", "flag_type": "profile_missing",
            "field": "team_tactical_profile_48_candidate", "action": "abort",
            "severity": "critical", "notes": f"home={home in profiles} away={away in profiles}",
        })

    sids = [snum(r, "scenario_id") for r in scenario_rows]
    if len(scenario_rows) != 17:
        flags.append({
            "match_id": match_id, "scenario_id": "", "flag_type": "missing_scenario",
            "field": "scenario_count", "action": "abort", "severity": "critical",
            "notes": f"scenario_count={len(scenario_rows)}",
        })
    elif len(set(sids)) != 17:
        flags.append({
            "match_id": match_id, "scenario_id": "", "flag_type": "duplicate_scenario",
            "field": "scenario_id", "action": "abort", "severity": "critical",
            "notes": "duplicate scenario_id in staging candidate",
        })
    else:
        nums = sorted(scenario_num(s) for s in sids)
        if nums != list(range(1, 18)):
            flags.append({
                "match_id": match_id, "scenario_id": "", "flag_type": "missing_scenario",
                "field": "S01_S17", "action": "abort", "severity": "critical",
                "notes": f"scenario_nums={nums}",
            })

    for r in scenario_rows:
        sid = snum(r, "scenario_id")
        try:
            conf = float(r.get("data_confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < 0.35:
            flags.append({
                "match_id": match_id, "scenario_id": sid, "flag_type": "low_confidence",
                "field": "data_confidence", "action": "abort", "severity": "high",
                "notes": str(conf),
            })
        if str(r.get("is_fallback", "")).lower() == "true":
            flags.append({
                "match_id": match_id, "scenario_id": sid, "flag_type": "fallback_detected",
                "field": "is_fallback", "action": "abort", "severity": "high",
                "notes": snum(r, "fallback_reason"),
            })

    info["has_S01_S17"] = len(scenario_rows) == 17 and len(set(sids)) == 17
    ok = not flags
    return ok, info, flags


@contextmanager
def staging_swap(hashes_before: Dict[str, str]) -> Iterator[None]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups: Dict[Path, Path] = {}
    for p in SWAP_TARGETS:
        if p.exists():
            bak = BACKUP_DIR / f"{p.name}.before_phase05A"
            shutil.copy2(p, bak)
            backups[p] = bak

    shutil.copy2(PROFILE_CANDIDATE, TEAM_DB / "team_tactical_profile.csv")
    shutil.copy2(MATRIX_R2_CANDIDATE, TEAM_DB / "tactical_matchup_matrix.csv")
    shutil.copy2(SCENARIO_R2_CANDIDATE, EVENTFLOW_DB / "eventflow_scenario_weights.csv")

    try:
        yield
    finally:
        for orig, bak in backups.items():
            if bak.exists():
                shutil.copy2(bak, orig)
        for p in PROTECTED_FILES:
            after = file_hash(p)
            before = hashes_before.get(str(p), "")
            if before and after != before:
                raise RuntimeError(f"Protected file hash mismatch after restore: {p}")


def resolve_source_notes(match_id: str) -> Tuple[str, List[Dict[str, str]]]:
    from eventflow_htft import resolve_source_notes_path

    notes_path = resolve_source_notes_path(match_id)
    log_rows: List[Dict[str, str]] = []
    p = Path(notes_path)
    if not p.is_absolute():
        p = ROOT / p
    if p.exists():
        rows = read_csv(p)
        match_rows = [r for r in rows if not snum(r, "match_id") or snum(r, "match_id") == match_id]
        for r in match_rows[:20]:
            log_rows.append({
                "match_id": match_id,
                "source_type": snum(r, "source_type") or "source_notes",
                "source_title": snum(r, "title") or snum(r, "source_title"),
                "source_url": snum(r, "url") or snum(r, "source_url"),
                "source_time": snum(r, "published_at") or snum(r, "source_time"),
                "used_layer": "source_notes",
                "confidence": snum(r, "confidence"),
                "notes": snum(r, "notes") or "from existing source_notes file",
            })
        return str(p), log_rows
    log_rows.append({
        "match_id": match_id,
        "source_type": "realtime_fetch_unavailable",
        "source_title": "",
        "source_url": "",
        "source_time": "",
        "used_layer": "none",
        "confidence": "",
        "notes": f"no source notes file at {notes_path}",
    })
    return notes_path, log_rows


def run_pipeline(
    match_id: str,
    home: str,
    away: str,
    mode: str,
    export_json: Path,
    skip_build: bool,
) -> None:
    cmd = [
        sys.executable,
        str(SCRIPTS / "run_dual_engine_pipeline.py"),
        "--match-id", match_id,
        "--home", home,
        "--away", away,
        "--mode", mode,
        "--use-v36-realization", "true",
        "--export-json", str(export_json.relative_to(ROOT)).replace("\\", "/"),
    ]
    if skip_build:
        cmd.append("--skip-build")
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def parse_prediction_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    pe = data.get("probability_engine", {}) or {}
    ef = data.get("eventflow_engine", {}) or {}
    fusion = data.get("final_fusion", {}) or {}
    probs = pe.get("probabilities", {}) or {}
    top = fusion.get("top_scores") or ef.get("top_scores") or pe.get("top_scores") or []
    top_scores = []
    for item in top[:3]:
        if isinstance(item, dict):
            top_scores.append(snum(item, "score") or snum(item, "scoreline"))
        else:
            top_scores.append(str(item))
    while len(top_scores) < 3:
        top_scores.append("")
    return {
        "eventflow_degraded": bool(
            data.get("eventflow_data_degraded")
            or ef.get("eventflow_data_degraded")
        ),
        "baseline_degraded": bool(data.get("baseline_degraded")),
        "degradation_reason": snum(data, "degradation_reason") or snum(ef, "degradation_reason"),
        "fusion_mode_effective": snum(data, "fusion_mode_effective"),
        "prob_home_win": probs.get("home_win", ""),
        "prob_draw": probs.get("draw", ""),
        "prob_away_win": probs.get("away_win", ""),
        "prob_over25": probs.get("over_2_5") or probs.get("over25", ""),
        "prob_btts": probs.get("btts_yes") or probs.get("btts", ""),
        "activated_scenarios_count": len(ef.get("activated_scenarios") or []),
        "top_score_1": top_scores[0],
        "top_score_2": top_scores[1],
        "top_score_3": top_scores[2],
        "fusion_top_score": snum(fusion, "top_score") or (top_scores[0] if top_scores else ""),
        "confidence_label": snum(data.get("data_quality", {}), "note") if isinstance(data.get("data_quality"), dict) else "",
    }


def predict_one(
    match_id: str,
    home: str,
    away: str,
    mode: str = "auto",
    skip_build: bool = True,
    run_prediction: bool = True,
) -> Dict[str, Any]:
    ok, preflight_info, preflight_flags = preflight(match_id, home, away)
    notes_path, source_log = resolve_source_notes(match_id)

    result: Dict[str, Any] = {
        "match_id": match_id,
        "home": home,
        "away": away,
        "mode": mode,
        "preflight_ok": ok,
        "preflight": preflight_info,
        "source_notes_path": notes_path,
        "source_notes_count": len([r for r in source_log if r.get("source_type") != "realtime_fetch_unavailable"]),
        "source_log": source_log,
        "prediction_json": "",
        "pipeline_ran": False,
        "processed_restored": False,
    }

    if not ok:
        result["preflight_flags"] = preflight_flags
        return result

    if not run_prediction:
        return result

    safe_name = f"{match_id}_{home}_{away}_{mode}_phase05A.json".replace(" ", "_")
    export_json = PRED_DIR / safe_name
    PRED_DIR.mkdir(parents=True, exist_ok=True)

    hashes_before = {str(p): file_hash(p) for p in PROTECTED_FILES}
    with staging_swap(hashes_before):
        run_pipeline(match_id, home, away, mode, export_json, skip_build=skip_build)
        result["pipeline_ran"] = True

    result["processed_restored"] = all(
        file_hash(p) == hashes_before.get(str(p), "") for p in PROTECTED_FILES
    )
    result["prediction_json"] = str(export_json.relative_to(ROOT)).replace("\\", "/")
    result.update(parse_prediction_json(export_json))
    return result


def write_preflight_failure(match_id: str, flags: List[Dict[str, str]]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"preflight_failed_{match_id}.md"
    lines = [
        f"# Preflight Failed: {match_id}", "",
        "Prediction aborted before pipeline run.", "",
        "| flag_type | field | notes |",
        "|---|---|---|",
    ]
    for f in flags:
        lines.append(f"| {f.get('flag_type','')} | {f.get('field','')} | {f.get('notes','')} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_degraded_debug(match_id: str, result: Dict[str, Any]) -> Path:
    path = OUT_DIR / f"{match_id}_degraded_debug_report.md"
    lines = [
        f"# {match_id} Degraded Debug Report", "",
        f"- matrix_rows (preflight): **{result.get('preflight', {}).get('matrix_rows')}**",
        f"- scenario_rows (preflight): **{result.get('preflight', {}).get('scenario_rows')}**",
        f"- source_notes_count: **{result.get('source_notes_count')}**",
        f"- eventflow_degraded: **{result.get('eventflow_degraded')}**",
        f"- baseline_degraded: **{result.get('baseline_degraded')}**",
        f"- degradation_reason: **{result.get('degradation_reason') or 'none'}**",
        f"- fusion_mode_effective: **{result.get('fusion_mode_effective')}**",
        f"- activated_scenarios_count: **{result.get('activated_scenarios_count')}**",
        "",
        "## Notes",
        "Check whether merge layer set EventFlow weight to 0 due to degradation_reason.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 05A R2 single-match prediction")
    ap.add_argument("--match-id", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument(
        "--mode", default="auto",
        choices=["auto", "safe", "balanced", "hit_hunting"],
        help="Compatibility input; fusion is dynamically weighted.",
    )
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--skip-build", action="store_true", default=True)
    ap.add_argument("--no-skip-build", dest="skip_build", action="store_false")
    args = ap.parse_args()

    result = predict_one(
        args.match_id, args.home, args.away,
        mode=args.mode,
        skip_build=args.skip_build,
        run_prediction=not args.preflight_only,
    )

    if not result["preflight_ok"]:
        path = write_preflight_failure(args.match_id, result.get("preflight_flags", []))
        print(f"Preflight failed -> {path}")
        raise SystemExit(1)

    if args.preflight_only:
        print(f"Preflight OK for {args.match_id}")
        return

    print(f"Prediction complete: {result.get('prediction_json')}")
    print(f"  eventflow_degraded={result.get('eventflow_degraded')}")
    print(f"  degradation_reason={result.get('degradation_reason') or 'none'}")
    print(f"  processed_restored={result.get('processed_restored')}")

    if result.get("eventflow_degraded"):
        dbg = write_degraded_debug(args.match_id, result)
        print(f"  degraded debug -> {dbg}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
