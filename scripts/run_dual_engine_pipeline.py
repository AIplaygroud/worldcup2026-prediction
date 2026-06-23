#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-click dual-engine pipeline: V2 export → build → source fusion → EventFlow → merge."""
from __future__ import annotations

import argparse
import hashlib
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


def file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return "missing"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight_check(match_id: str, home: str, away: str, export_json: str, use_v37: bool) -> dict:
    """Run an explicit integrity check before producing the final merge."""
    sys.path.insert(0, str(SCRIPTS))
    from eventflow_common import read_csv

    checks = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    mapping = read_csv(ROOT / "database/competition/wc2026_match_id_mapping.csv")
    add(
        "match_mapping",
        any(r.get("internal_match_id") == match_id and r.get("home_team") == home and r.get("away_team") == away for r in mapping),
        "wc2026_match_id_mapping.csv contains requested match/home/away",
    )
    team_profiles = read_csv(ROOT / "database/team_style/processed/team_tactical_profile.csv")
    profile_teams = {r.get("team") for r in team_profiles}
    add("team_profiles", home in profile_teams and away in profile_teams, "team_tactical_profile.csv has both teams")
    matchups = read_csv(ROOT / "database/team_style/processed/tactical_matchup_matrix.csv")
    add(
        "matchup_matrix",
        any(r.get("match_id") == match_id or (r.get("home") == home and r.get("away") == away) for r in matchups),
        "tactical_matchup_matrix.csv has match row",
    )
    scenarios = read_csv(ROOT / "database/eventflow/processed/eventflow_scenario_weights.csv")
    scenario_rows = [r for r in scenarios if r.get("match_id") == match_id and r.get("home") == home and r.get("away") == away]
    add("scenario_weights", len(scenario_rows) >= 3, f"eventflow_scenario_weights rows={len(scenario_rows)}")
    prob_csv = ROOT / "database/eventflow/raw/probability_engine_scores.csv"
    add("probability_output_path", prob_csv.parent.exists(), str(prob_csv))
    out_path = Path(export_json)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    add("export_output_path", out_path.parent.exists(), str(out_path))
    if use_v37:
        v37_path = ROOT / "database/v37/features/v37_realization_features.csv"
        rows = read_csv(v37_path)
        add("v37_features", any(r.get("match_id") == match_id for r in rows), f"{v37_path}")

    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks}


def write_run_manifest(run_dir: Path, match_id: str, home: str, away: str, export_json: str, steps: list, preflight: dict) -> None:
    input_paths = [
        ROOT / "README.md",
        ROOT / "skill.md",
        ROOT / "docs/postmatch_audit_R2_four_matches_20260623_revised.md",
        ROOT / "database/competition/wc2026_match_id_mapping.csv",
        ROOT / "database/team_style/processed/team_tactical_profile.csv",
        ROOT / "database/team_style/processed/tactical_matchup_matrix.csv",
        ROOT / "database/eventflow/processed/eventflow_scenario_weights.csv",
        ROOT / "database/eventflow/raw/probability_engine_scores.csv",
    ]
    export_path = Path(export_json)
    if not export_path.is_absolute():
        export_path = ROOT / export_path
    manifest = {
        "match_id": match_id,
        "home": home,
        "away": away,
        "export_json": str(export_path),
        "preflight": preflight,
        "input_hashes": {str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): file_sha256(p) for p in input_paths},
        "output_hashes": {str(export_path): file_sha256(export_path)},
        "steps": steps,
        "code_version_note": "working_tree_snapshot; see packaged zip",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "run_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


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
    ap.add_argument(
        "--mode", default="auto",
        choices=["auto", "safe", "balanced", "hit_hunting"],
        help="Compatibility input; fusion is dynamically weighted.",
    )
    ap.add_argument("--notes", default="",
                    help="Override source notes; default uses per-match file if exists")
    ap.add_argument("--export-json", default="", help="Default: per-match outputs/runs/<match>/<timestamp>/dual_engine_output_<match>.json")
    ap.add_argument("--skip-build", action="store_true", help="Skip daily build (use existing tables)")
    ap.add_argument("--use-realtime-availability", default="true",
                    choices=["true", "false"],
                    help="Apply V3.5 realtime availability λ adjustment after predict_v2")
    ap.add_argument("--use-v36-realization", default="true",
                    choices=["true", "false"],
                    help="Apply V3.6 scenario realization, BTTS gate, tail calibration after EventFlow")
    ap.add_argument("--use-v37", default="false", choices=["true", "false"],
                    help="Enable V3.7 phase-1 guards in fusion/betting (no λ change)")
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

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "outputs" / "runs" / mid / run_stamp
    export_json = args.export_json or str(run_dir / f"dual_engine_output_{mid}.json")

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

        preflight = preflight_check(mid, home, away, export_json, False)
        for check in preflight["checks"]:
            level = "info" if check["ok"] else "error"
            log(f"preflight {check['name']}: {check['detail']}", steps, level=level)
        if not preflight["ok"]:
            raise SystemExit("Preflight failed; refusing to produce a non-auditable merge")

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

        if args.use_v36_realization == "true":
            run_cmd([py, str(SCRIPTS / "apply_scenario_realization_layer.py"),
                     "--match-id", mid, "--home", home, "--away", away,
                     "--lam-home", str(lam_h), "--lam-away", str(lam_a)], steps)
            run_cmd([py, str(SCRIPTS / "apply_btts_conversion_gate.py"),
                     "--match-id", mid, "--home", home, "--away", away,
                     "--lam-home", str(lam_h), "--lam-away", str(lam_a),
                     "--prob-csv", prob_csv], steps)
            run_cmd([py, str(SCRIPTS / "apply_total_goals_tail_calibration.py"),
                     "--match-id", mid, "--home", home, "--away", away,
                     "--lam-home", str(lam_h), "--lam-away", str(lam_a),
                     "--prob-csv", prob_csv], steps)
            run_cmd([py, str(SCRIPTS / "validate_v36_realization_calibration.py"),
                     "--match-id", mid], steps)
            log("V3.6 realization layer applied", steps)
        else:
            log("Skipping V3.6 realization (--use-v36-realization false)", steps)

        if args.use_v37 == "true":
            run_cmd([py, str(SCRIPTS / "build_v37_normalized_tables.py")], steps)
            run_cmd([py, str(SCRIPTS / "build_v37_features.py")], steps)
            run_cmd([py, str(SCRIPTS / "apply_v37_realization_guards.py"), "--all-matches"], steps)
            v37_preflight = preflight_check(mid, home, away, export_json, True)
            preflight["checks"].extend([dict(c, phase="v37") for c in v37_preflight["checks"] if c["name"] == "v37_features"])
            for check in v37_preflight["checks"]:
                if check["name"] == "v37_features":
                    level = "info" if check["ok"] else "error"
                    log(f"preflight {check['name']}: {check['detail']}", steps, level=level)
            if not v37_preflight["ok"]:
                raise SystemExit("V3.7 preflight failed; refusing to label degraded features as loaded")
            log("V3.7 phase-1 guards built (audit only, no λ change)", steps)

        merge_cmd = [py, str(SCRIPTS / "merge_dual_engine_predictions.py"),
                     "--match-id", mid, "--home", home, "--away", away,
                     "--mode", args.mode, "--export-json", export_json,
                     "--fail-on-htft-mismatch"]
        if args.use_v37 == "true":
            merge_cmd.extend(["--use-v37", "--use-v37-cold-reserve"])
        run_cmd(merge_cmd, steps)

        if args.use_v36_realization == "true":
            sys.path.insert(0, str(SCRIPTS))
            from scenario_realization_common import sync_v36_diagnostics_from_merge_json
            export_path = Path(export_json) if Path(export_json).is_absolute() else ROOT / export_json
            if export_path.exists():
                sync_v36_diagnostics_from_merge_json(export_path)
                log(f"Synced V3.6 diagnostics from {export_json}", steps)

        write_run_manifest(run_dir, mid, home, away, export_json, steps, preflight)
        log(f"Pipeline complete -> {export_json}", steps)
        append_log(steps, mid, home, away, args.mode, export_json)
    except subprocess.CalledProcessError as e:
        log(f"Pipeline failed: {e}", steps, level="error")
        append_log(steps, mid, home, away, args.mode, export_json)
        raise SystemExit(e.returncode)


if __name__ == "__main__":
    main()
