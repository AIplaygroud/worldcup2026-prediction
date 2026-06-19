#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-click dual-engine pipeline: V2 export → build → source fusion → EventFlow → merge."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LOG_PATH = ROOT / "database" / "eventflow" / "processed" / "pipeline_run_log.jsonl"


def log(msg: str, steps: list, level: str = "info") -> None:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "message": msg}
    steps.append(entry)
    print(f"[{level}] {msg}")


def run_cmd(cmd: list[str], steps: list) -> None:
    log("$ " + " ".join(cmd), steps)
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def resolve_from_mapping(match_id: str, home: str, away: str) -> dict:
    sys.path.insert(0, str(SCRIPTS))
    from eventflow_htft import resolve_match_id
    return resolve_match_id(match_id, home, away)


def append_log(steps: list, match_id: str, home: str, away: str, mode: str, json_path: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "match_id": match_id,
        "home": home,
        "away": away,
        "mode": mode,
        "export_json": json_path,
        "steps": steps,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run full dual-engine prediction pipeline")
    ap.add_argument("--match-id", required=True, help="internal_match_id e.g. WC2026-C29")
    ap.add_argument("--home", default="")
    ap.add_argument("--away", default="")
    ap.add_argument("--mode", default="balanced", choices=["safe", "balanced", "hit_hunting"])
    ap.add_argument("--notes", default="",
                    help="Override source notes; default uses per-match file if exists")
    ap.add_argument("--export-json", default="database/eventflow/processed/dual_engine_output.json")
    ap.add_argument("--skip-build", action="store_true", help="Skip daily build (use existing tables)")
    ap.add_argument("--use-realtime-availability", default="true",
                    choices=["true", "false"],
                    help="Apply V3.5 realtime availability λ adjustment after predict_v2")
    args = ap.parse_args()

    steps: list = []
    resolved = resolve_from_mapping(args.match_id, args.home, args.away)
    mid = resolved.get("internal_match_id") or args.match_id
    home = args.home or resolved.get("home_team", "")
    away = args.away or resolved.get("away_team", "")
    notes = args.notes
    if not notes:
        sys.path.insert(0, str(SCRIPTS))
        from eventflow_htft import resolve_source_notes_path
        notes = resolve_source_notes_path(mid)
    if not home or not away:
        raise SystemExit("Could not resolve home/away; pass --home and --away")

    py = sys.executable
    prob_csv = "database/eventflow/raw/probability_engine_scores.csv"

    try:
        log(f"Pipeline start: {mid} {home} vs {away} mode={args.mode}", steps)

        run_cmd([py, str(SCRIPTS / "build_match_id_mapping.py")], steps)

        if not args.skip_build:
            run_cmd([py, str(SCRIPTS / "update_eventflow_daily.py")], steps)

        run_cmd([py, str(SCRIPTS / "run_source_fusion_pipeline.py"),
                 "--match-id", mid, "--home", home, "--away", away, "--notes", notes], steps)

        run_cmd([py, str(SCRIPTS / "build_eventflow_scenario_weights.py")], steps)

        run_cmd([py, str(SCRIPTS / "predict_v2.py"),
                 "--home", home, "--away", away,
                 "--export-score-csv", prob_csv, "--match-id", mid], steps)

        from eventflow_common import read_csv
        prob_rows = [r for r in read_csv(ROOT / prob_csv) if r.get("match_id") == mid]
        if not prob_rows:
            raise SystemExit(f"No V2 export rows for match_id={mid}")
        lam_h = float(prob_rows[0].get("lambda_home", 1.5))
        lam_a = float(prob_rows[0].get("lambda_away", 1.0))
        log(f"Using λ {lam_h:.2f} / {lam_a:.2f} from V2 export", steps)

        if args.use_realtime_availability == "true":
            run_cmd([py, str(SCRIPTS / "apply_realtime_lambda_adjustment.py"),
                     "--match-id", mid, "--home", home, "--away", away,
                     "--base-lambda-home", str(lam_h), "--base-lambda-away", str(lam_a),
                     "--prob-csv", prob_csv], steps)

            from eventflow_common import read_csv as _read_csv
            prob_rows_adj = [r for r in _read_csv(ROOT / prob_csv) if r.get("match_id") == mid]
            if prob_rows_adj:
                lam_h = float(prob_rows_adj[0].get("lambda_home", lam_h))
                lam_a = float(prob_rows_adj[0].get("lambda_away", lam_a))
                log(f"Post-availability λ {lam_h:.2f} / {lam_a:.2f}", steps)
        else:
            log("Skipping realtime availability adjustment (--use-realtime-availability false)", steps)

        run_cmd([py, str(SCRIPTS / "predict_eventflow.py"),
                 "--match-id", mid, "--home", home, "--away", away,
                 "--lam-home", str(lam_h), "--lam-away", str(lam_a),
                 "--mode", args.mode], steps)

        run_cmd([py, str(SCRIPTS / "merge_dual_engine_predictions.py"),
                 "--match-id", mid, "--home", home, "--away", away,
                 "--mode", args.mode, "--export-json", args.export_json], steps)

        log(f"Pipeline complete -> {args.export_json}", steps)
        append_log(steps, mid, home, away, args.mode, args.export_json)
    except subprocess.CalledProcessError as e:
        log(f"Pipeline failed: {e}", steps, level="error")
        append_log(steps, mid, home, away, args.mode, args.export_json)
        raise SystemExit(e.returncode)


if __name__ == "__main__":
    main()
