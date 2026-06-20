#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 01: audit team profiles and build 48-team staging candidates."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eventflow_common import DB, TEAM_DB, read_csv, snum, write_csv  # noqa: E402

BACKUP_DIR = ROOT / "backups" / "phase01_team_profiles"
OUT_DIR = ROOT / "outputs" / "phase01_team_profiles"
STAGING_DIR = ROOT / "database" / "team_style" / "staging"
RAW_DIR = ROOT / "database" / "team_style" / "raw"

RAW_FIELDS = [
    "team", "period", "matches", "formation_base", "possession_pct", "ppda",
    "high_turnovers90", "direct_attacks90", "fast_breaks90", "passes_per_sequence",
    "field_tilt_pct", "deep_completions90", "box_entries90", "crosses90", "cutbacks90",
    "set_piece_xg90", "xg90", "xga90", "shots90", "shots_against90",
    "source", "source_url", "source_title", "updated_at", "confidence", "is_estimated",
]

AUDIT_FILES = [
    "database/competition/group_assignments.csv",
    "database/competition/wc2026_match_id_mapping.csv",
    "database/competition/wc2026_group_fixtures.csv",
    "database/team_style/raw/raw_team_phase_metrics.csv",
    "database/team_style/raw/raw_match_state_response.csv",
    "database/team_style/processed/team_tactical_profile.csv",
    "database/team_style/processed/team_match_state_response.csv",
    "database/team_style/processed/team_formation_matchups.csv",
    "database/team_style/processed/tactical_matchup_matrix.csv",
    "database/eventflow/processed/eventflow_scenario_weights.csv",
]

PROTECTED_MATRIX_FILES = [
    ROOT / "database/team_style/processed/team_formation_matchups.csv",
    ROOT / "database/team_style/processed/tactical_matchup_matrix.csv",
    ROOT / "database/eventflow/processed/eventflow_scenario_weights.csv",
]

STYLE_PPDA = {
    "high-press": 8.5, "high-press-possession": 7.5, "high-press-direct": 9.0,
    "possession-dominant": 10.5, "possession-press": 9.5, "possession-set-piece": 11.0,
    "possession-stagnant": 12.0, "possession-inefficient": 11.5, "balanced-press": 11.0,
    "balanced-control": 11.5, "balanced-direct": 12.0, "balanced-counter": 12.5,
    "mid-block": 12.5, "mid-block-counter": 12.0, "counter-attacking": 13.0,
    "direct-transition": 12.5, "direct-set-piece": 13.5, "direct-counter": 14.0,
    "low-block": 14.5, "low-block-counter": 14.0, "low-block-direct": 14.5,
    "compact-low-block": 15.0, "possession-without-chance": 13.0, "set-piece-heavy": 11.0,
}


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt_num(v: Any) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return f"{v:.4g}".rstrip("0").rstrip(".")
    return str(v)


def setup_dirs_and_backups() -> Dict[str, str]:
    for d in (BACKUP_DIR, OUT_DIR, STAGING_DIR):
        d.mkdir(parents=True, exist_ok=True)
    hashes_before = {str(p): file_hash(p) for p in PROTECTED_MATRIX_FILES}
    for name in (
        "raw_team_phase_metrics.csv",
        "raw_match_state_response.csv",
        "team_tactical_profile.csv",
        "team_match_state_response.csv",
    ):
        src = ROOT / "database" / "team_style" / ("raw" if name.startswith("raw_") else "processed") / name
        if src.exists():
            shutil.copy2(src, BACKUP_DIR / f"{name}.bak")
    return hashes_before


def load_expected_teams() -> List[str]:
    rows = read_csv(DB / "competition" / "group_assignments.csv")
    return [snum(r, "team_en") for r in rows if snum(r, "team_en")]


def load_expected_match_ids() -> List[str]:
    rows = read_csv(DB / "competition" / "wc2026_match_id_mapping.csv")
    return [snum(r, "internal_match_id") for r in rows if snum(r, "internal_match_id")]


def audit_report() -> Dict[str, Any]:
    lines: List[str] = ["# Phase 01 Audit Report", "", f"Generated: {date.today().isoformat()}", ""]
    lines += ["## 3.1 File Existence", ""]
    lines.append("| File | Exists | Rows | Columns |")
    lines.append("|---|---|---:|---|")
    for rel in AUDIT_FILES:
        p = ROOT / rel
        exists = p.exists()
        rows = read_csv(p) if exists else []
        cols = ", ".join(rows[0].keys()) if rows else ("N/A" if exists else "—")
        lines.append(f"| `{rel}` | {'yes' if exists else '**no**'} | {len(rows)} | {len(rows[0]) if rows else 0} |")

    expected_teams = load_expected_teams()
    raw_teams = {snum(r, "team") for r in read_csv(RAW_DIR / "raw_team_phase_metrics.csv")}
    prof_teams = {snum(r, "team") for r in read_csv(TEAM_DB / "team_tactical_profile.csv")}
    exp_set = set(expected_teams)

    lines += ["", "## 3.2 Team Coverage", ""]
    lines.append(f"- expected_teams_count: **{len(expected_teams)}**")
    lines.append(f"- raw_team_phase_metrics_teams_count: **{len(raw_teams)}**")
    lines.append(f"- team_tactical_profile_teams_count: **{len(prof_teams)}**")
    missing_raw = sorted(exp_set - raw_teams)
    missing_prof = sorted(exp_set - prof_teams)
    extra = sorted((raw_teams | prof_teams) - exp_set)
    lines.append(f"- missing_in_raw_team_phase_metrics ({len(missing_raw)}): {', '.join(missing_raw) or '—'}")
    lines.append(f"- missing_in_team_tactical_profile ({len(missing_prof)}): {', '.join(missing_prof) or '—'}")
    lines.append(f"- extra_teams_not_in_group_assignments: {', '.join(extra) or '—'}")

    expected_ids = set(load_expected_match_ids())
    fm_rows = read_csv(TEAM_DB / "team_formation_matchups.csv")
    tm_rows = read_csv(TEAM_DB / "tactical_matchup_matrix.csv")
    ef_rows = read_csv(DB / "eventflow" / "processed" / "eventflow_scenario_weights.csv")
    fm_ids = {snum(r, "match_id") for r in fm_rows}
    tm_ids = {snum(r, "match_id") for r in tm_rows}
    ef_ids = {snum(r, "match_id") for r in ef_rows}

    lines += ["", "## 3.3 Match Matrix Coverage (audit only)", ""]
    lines.append(f"- expected_group_matches_count: **72**")
    lines.append(f"- team_formation_matchups_count: **{len(fm_rows)}** (unique match_ids: {len(fm_ids)})")
    lines.append(f"- tactical_matchup_matrix_count: **{len(tm_rows)}** (unique match_ids: {len(tm_ids)})")
    lines.append(f"- eventflow_scenario_weights_match_count: **{len(ef_ids)}**")
    lines.append(f"- eventflow_scenario_weights_row_count: **{len(ef_rows)}**")
    lines.append(f"- missing_match_ids_in_formation_matchups: {len(expected_ids - fm_ids)}")
    lines.append(f"- missing_match_ids_in_tactical_matchup_matrix: {len(expected_ids - tm_ids)}")
    lines.append(f"- missing_match_ids_in_eventflow_scenario_weights: {len(expected_ids - ef_ids)}")

    report_path = OUT_DIR / "phase01_audit_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "expected_teams": expected_teams,
        "raw_teams_count": len(raw_teams),
        "prof_teams_count": len(prof_teams),
        "missing_raw": missing_raw,
        "missing_prof": missing_prof,
    }


def _r1_shots_lookup() -> Dict[str, Tuple[float, float, str, str]]:
    """team -> (shots_for, shots_against, source_url, match_date) from R1 fixtures only."""
    mapping = read_csv(DB / "competition" / "wc2026_match_id_mapping.csv")
    r1_pairs: Set[Tuple[str, str]] = set()
    for r in mapping:
        if snum(r, "round") == "1":
            h, a = snum(r, "home_team"), snum(r, "away_team")
            if h and a:
                r1_pairs.add((h, a))
                r1_pairs.add((a, h))

    out: Dict[str, Tuple[float, float, str, str]] = {}
    seen: Set[str] = set()
    for r in read_csv(DB / "xGdatabase" / "processed" / "wc2026_match_xg.csv"):
        h, a = snum(r, "home_team"), snum(r, "away_team")
        if (h, a) not in r1_pairs and (a, h) not in r1_pairs:
            continue
        try:
            hs, aws = float(r["home_shots"]), float(r["away_shots"])
        except (KeyError, ValueError, TypeError):
            continue
        url = snum(r, "source_url")
        md = snum(r, "match_date")
        for team, sf, sa in ((h, hs, aws), (a, aws, hs)):
            if team not in seen:
                out[team] = (sf, sa, url, md)
                seen.add(team)
    return out


def _estimate_ppda(style: str, pressing: float) -> float:
    if style in STYLE_PPDA:
        return STYLE_PPDA[style]
    return round(15.5 - pressing * 8.0, 1)


def build_raw_candidate(expected_teams: List[str]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    existing = {snum(r, "team"): r for r in read_csv(RAW_DIR / "raw_team_phase_metrics.csv")}
    wc_xg = {snum(r, "team"): r for r in read_csv(DB / "xGdatabase" / "processed" / "wc2026_team_xg.csv")}
    tactics = {snum(r, "team"): r for r in read_csv(DB / "competition" / "wc2026_team_tactics_observed.csv")}
    coaches = {snum(r, "team"): r for r in read_csv(DB / "competition" / "coach_profiles.csv")}
    recent = {snum(r, "team"): r for r in read_csv(DB / "xGdatabase" / "processed" / "team_recent_form.csv")}
    shots_lu = _r1_shots_lookup()
    gap_log: List[Dict[str, str]] = []
    rows_out: List[Dict[str, str]] = []

    metric_fields = [
        "high_turnovers90", "direct_attacks90", "fast_breaks90", "passes_per_sequence",
        "deep_completions90", "box_entries90", "crosses90", "cutbacks90", "set_piece_xg90",
    ]

    for team in expected_teams:
        if team in existing:
            row = {k: existing[team].get(k, "") for k in RAW_FIELDS}
            rows_out.append(row)
            for mf in metric_fields:
                if not snum(row, mf):
                    gap_log.append({
                        "team": team, "field": mf, "gap_type": "missing_in_source",
                        "action": "kept_empty_from_r1_raw", "confidence": snum(row, "confidence"),
                        "is_estimated": snum(row, "is_estimated"), "notes": "Preserved original C/D R1 row",
                    })
            continue

        tac = tactics.get(team, {})
        coach = coaches.get(team, {})
        xg = wc_xg.get(team, {})
        form = recent.get(team, {})
        shots = shots_lu.get(team)

        style = snum(tac, "style_label")
        pressing = 0.5
        try:
            pressing = float(coach.get("pressing_intensity", 0.5))
        except (TypeError, ValueError):
            pass

        ppda_val = snum(tac, "ppda")
        ppda_estimated = False
        if not ppda_val:
            ppda_val = fmt_num(_estimate_ppda(style, pressing))
            ppda_estimated = True

        possession = snum(tac, "possession")
        if not possession and team in wc_xg:
            possession = ""

        formation = snum(coach, "typical_formation") or "4-4-2"
        source_url = snum(tac, "source_url") or snum(xg, "sources")
        source_title = f"{team} WC2026 R1 tactical profile"
        is_est = "true" if ppda_estimated else "false"
        conf = 0.88
        if not shots or not snum(tac, "possession"):
            conf = 0.78
        if ppda_estimated:
            conf = min(conf, 0.76)

        row: Dict[str, str] = {
            "team": team,
            "period": "WC2026-R1",
            "matches": "1",
            "formation_base": formation,
            "possession_pct": possession,
            "ppda": ppda_val,
            "field_tilt_pct": possession,
            "xg90": snum(xg, "wc_xg_per_match"),
            "xga90": snum(xg, "wc_xga_per_match"),
            "source": snum(tac, "source") or "FotMob/Opta",
            "source_url": source_url,
            "source_title": source_title,
            "updated_at": snum(tac, "last_verified") or date.today().isoformat(),
            "confidence": fmt_num(conf),
            "is_estimated": is_est,
        }

        if shots:
            row["shots90"] = fmt_num(shots[0])
            row["shots_against90"] = fmt_num(shots[1])
            if not row["source_url"]:
                row["source_url"] = shots[2]
        else:
            gap_log.append({
                "team": team, "field": "shots90", "gap_type": "missing_r1_shots",
                "action": "left_empty", "confidence": fmt_num(conf),
                "is_estimated": "true", "notes": "No R1 shot row in wc2026_match_xg",
            })

        hpr = snum(tac, "high_press_regains")
        if hpr:
            row["high_turnovers90"] = hpr
        fte = snum(tac, "final_third_entries")
        if fte:
            row["box_entries90"] = fte
        crosses = snum(tac, "crosses")
        if crosses:
            row["crosses90"] = crosses
        spxg = snum(tac, "set_piece_xg")
        if spxg:
            row["set_piece_xg90"] = spxg

        for mf in metric_fields:
            if not snum(row, mf):
                gap_log.append({
                    "team": team, "field": mf, "gap_type": "missing_advanced_metric",
                    "action": "left_empty",
                    "confidence": fmt_num(conf),
                    "is_estimated": "false" if mf in ("high_turnovers90", "box_entries90", "crosses90", "set_piece_xg90") and snum(row, mf) else "true",
                    "notes": f"style={style}; qualifier_xg={snum(form, 'recent_xg_per_match')}",
                })

        if ppda_estimated:
            gap_log.append({
                "team": team, "field": "ppda", "gap_type": "estimated_from_style_coach",
                "action": "estimated", "confidence": fmt_num(conf),
                "is_estimated": "true",
                "notes": f"style_label={style}; pressing_intensity={pressing}",
            })

        if snum(coach, "confidence") == "expert_prior" and not snum(tac, "possession"):
            gap_log.append({
                "team": team, "field": "formation_base", "gap_type": "coach_prior_used",
                "action": "coach_profiles.typical_formation",
                "confidence": fmt_num(min(conf, 0.65)),
                "is_estimated": "true",
                "notes": "Formation from coach_profiles expert_prior",
            })

        for k in RAW_FIELDS:
            row.setdefault(k, "")
        rows_out.append({k: row.get(k, "") for k in RAW_FIELDS})

    out_path = STAGING_DIR / "raw_team_phase_metrics_48_candidate.csv"
    write_csv(out_path, rows_out, RAW_FIELDS)
    return rows_out, gap_log


def run_profile_build() -> Path:
    raw_backup = BACKUP_DIR / "raw_team_phase_metrics.before_phase01_run.csv"
    prof_backup = BACKUP_DIR / "team_tactical_profile.before_phase01_run.csv"
    state_backup = BACKUP_DIR / "team_match_state_response.before_phase01_run.csv"
    raw_path = RAW_DIR / "raw_team_phase_metrics.csv"
    prof_path = TEAM_DB / "team_tactical_profile.csv"
    state_path = TEAM_DB / "team_match_state_response.csv"
    shutil.copy2(raw_path, raw_backup)
    shutil.copy2(prof_path, prof_backup)
    if state_path.exists():
        shutil.copy2(state_path, state_backup)
    shutil.copy2(STAGING_DIR / "raw_team_phase_metrics_48_candidate.csv", raw_path)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_team_tactical_profile.py")],
        cwd=str(ROOT),
        check=True,
    )
    cand = STAGING_DIR / "team_tactical_profile_48_candidate.csv"
    shutil.copy2(prof_path, cand)
    state_cand = STAGING_DIR / "team_match_state_response_phase01_candidate.csv"
    if state_path.exists():
        shutil.copy2(state_path, state_cand)
    shutil.copy2(raw_backup, raw_path)
    shutil.copy2(prof_backup, prof_path)
    if state_backup.exists():
        shutil.copy2(state_backup, state_path)
    return cand


def validate_profiles(
    expected_teams: List[str],
    gap_log: List[Dict[str, str]],
    hashes_before: Dict[str, str],
) -> Dict[str, Any]:
    prof_path = STAGING_DIR / "team_tactical_profile_48_candidate.csv"
    profiles = read_csv(prof_path)
    prof_teams = [snum(r, "team") for r in profiles]
    prof_set = set(prof_teams)
    exp_set = set(expected_teams)

    coverage_rows: List[Dict[str, str]] = []
    for team in expected_teams:
        pr = next((r for r in profiles if snum(r, "team") == team), {})
        raw_r = next((r for r in read_csv(STAGING_DIR / "raw_team_phase_metrics_48_candidate.csv")
                      if snum(r, "team") == team), {})
        filled = sum(1 for f in RAW_FIELDS[4:20] if snum(raw_r, f))
        coverage_rows.append({
            "team": team,
            "in_candidate_profile": "yes" if team in prof_set else "no",
            "formation_base": snum(pr, "formation_base"),
            "data_confidence": snum(pr, "data_confidence"),
            "is_estimated": snum(pr, "is_estimated"),
            "raw_metrics_filled_count": str(filled),
            "pressing_height": snum(pr, "pressing_height"),
            "build_up_style": snum(pr, "build_up_style"),
        })
    write_csv(OUT_DIR / "team_profile_coverage.csv", coverage_rows)

    # merge gap log with validation gaps
    field_gap_counts = Counter(g["field"] for g in gap_log)
    write_csv(OUT_DIR / "data_gap_log.csv", gap_log, [
        "team", "field", "gap_type", "action", "confidence", "is_estimated", "notes",
    ])

    low_conf = [snum(r, "team") for r in profiles if float(r.get("data_confidence") or 0) < 0.55]
    below_035 = [snum(r, "team") for r in profiles if float(r.get("data_confidence") or 0) < 0.35]
    extra_teams = sorted(prof_set - exp_set)
    missing_teams = sorted(exp_set - prof_set)
    matrix_changed = []
    for p in PROTECTED_MATRIX_FILES:
        before = hashes_before.get(str(p), "")
        after = file_hash(p)
        if before and before != after:
            matrix_changed.append(p.name)

    estimated_teams = sorted({snum(r, "team") for r in profiles if snum(r, "is_estimated").lower() == "true"})

    lines = [
        "# Phase 01 Validation Report", "",
        f"Generated: {date.today().isoformat()}", "",
        "## Coverage", "",
        f"- Expected teams: {len(expected_teams)}",
        f"- Candidate profile teams: {len(prof_set)}",
        f"- Missing teams: {', '.join(missing_teams) or 'none'}",
        f"- Extra teams: {', '.join(extra_teams) or 'none'}", "",
        "## Confidence", "",
        f"- Teams with data_confidence < 0.55: {', '.join(low_conf) or 'none'}",
        f"- Teams with data_confidence < 0.35 (should not enter formal candidate): {', '.join(below_035) or 'none'}",
        f"- is_estimated=true teams ({len(estimated_teams)}): {', '.join(estimated_teams)}", "",
        "## Field Gaps (top 10)", "",
    ]
    for field, cnt in field_gap_counts.most_common(10):
        lines.append(f"- `{field}`: {cnt} team-gap records")

    lines += ["", "## Matrix Integrity", ""]
    if matrix_changed:
        lines.append(f"**WARNING: matrix files modified:** {', '.join(matrix_changed)}")
    else:
        lines.append("- Protected matrix files unchanged: **yes**")

    lines += ["", "## Phase 02 Readiness", ""]
    ready = (
        len(missing_teams) == 0
        and len(extra_teams) == 0
        and len(below_035) == 0
        and not matrix_changed
    )
    lines.append(f"- Ready for batch 2 matchup generation: **{'yes' if ready else 'no — resolve items above'}**")

    (OUT_DIR / "phase01_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "candidate_count": len(prof_set),
        "low_conf": low_conf,
        "below_035": below_035,
        "field_gap_top": field_gap_counts.most_common(5),
        "matrix_changed": matrix_changed,
        "ready": ready,
        "estimated_teams": estimated_teams,
    }


def main() -> None:
    hashes_before = setup_dirs_and_backups()
    audit = audit_report()
    _, gap_log = build_raw_candidate(audit["expected_teams"])
    run_profile_build()
    result = validate_profiles(audit["expected_teams"], gap_log, hashes_before)

    print("Phase 01 complete.")
    print(f"  Original profile teams: {audit['prof_teams_count']}")
    print(f"  Candidate profile teams: {result['candidate_count']}")
    print(f"  Ready for batch 2: {result['ready']}")


if __name__ == "__main__":
    main()
