#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 03A: build R2-only tactical matchup matrix candidate (24 matches)."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_tactical_matchup_matrix import (  # noqa: E402
    breakthrough,
    control,
    path_summary,
    survival_summary,
)
from eventflow_common import DB, TEAM_DB, fnum, read_csv, snum, write_csv  # noqa: E402

OUT_DIR = ROOT / "outputs" / "phase03A_r2_tactical_matrix"
STAGING_DIR = ROOT / "database" / "team_style" / "staging"
BACKUP_DIR = ROOT / "backups" / "phase03A_r2_tactical_matrix"

PRESERVED_IDS = {"WC2026-C29", "WC2026-C30", "WC2026-D31", "WC2026-D32"}

PROTECTED_FILES = [
    TEAM_DB / "team_formation_matchups.csv",
    TEAM_DB / "tactical_matchup_matrix.csv",
    DB / "eventflow" / "processed" / "eventflow_scenario_weights.csv",
]

PROFILE_PATH = STAGING_DIR / "team_tactical_profile_48_candidate.csv"
FORMATION_PATH = STAGING_DIR / "team_formation_matchups_72_candidate.csv"
PROCESSED_MATRIX = TEAM_DB / "tactical_matchup_matrix.csv"
OUTPUT_PATH = STAGING_DIR / "tactical_matchup_matrix_R2_candidate.csv"


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_matrix_fields() -> List[str]:
    rows = read_csv(PROCESSED_MATRIX)
    if rows:
        return list(rows[0].keys())
    return [
        "match_id", "home", "away",
        "home_breakthrough_score", "away_breakthrough_score",
        "home_control_score", "away_control_score",
        "home_transition_edge", "away_transition_edge",
        "home_set_piece_edge", "away_set_piece_edge",
        "home_flank_edge", "away_flank_edge",
        "home_central_edge", "away_central_edge",
        "home_press_trap_edge", "away_press_trap_edge",
        "home_shape_countered_by_away", "away_shape_countered_by_home",
        "matchup_imbalance_index",
        "likely_breakthrough_path_home", "likely_breakthrough_path_away",
        "likely_defensive_survival_path_home", "likely_defensive_survival_path_away",
        "data_confidence",
    ]


def row_hash(row: Dict[str, str], fields: List[str]) -> str:
    payload = {k: row.get(k, "") for k in fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_r2_schedule() -> List[Dict[str, str]]:
    mapping = read_csv(DB / "competition" / "wc2026_match_id_mapping.csv")
    fixtures = {snum(r, "fifa_match_id"): r for r in read_csv(DB / "competition" / "wc2026_group_fixtures.csv")}
    out: List[Dict[str, str]] = []
    for m in mapping:
        if snum(m, "round") != "2":
            continue
        fid = snum(m, "fifa_match_id")
        fx = fixtures.get(fid, {})
        date = snum(fx, "match_date")
        if not date:
            kick = snum(m, "kickoff_time")
            date = kick.split()[0] if kick else ""
        out.append({
            "match_id": snum(m, "internal_match_id"),
            "fifa_match_id": fid,
            "group": snum(m, "group"),
            "round": snum(m, "round"),
            "home": snum(m, "home_team"),
            "away": snum(m, "away_team"),
            "date": date,
        })
    return out


def build_matrix_row(
    fx: Dict[str, str],
    profiles: Dict[str, Dict[str, str]],
    fields: List[str],
) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """Return (matrix_row_25cols, quality_flags)."""
    flags: List[Dict[str, str]] = []
    home = snum(fx, "home")
    away = snum(fx, "away")
    mid = snum(fx, "match_id")
    hp = profiles.get(home, {})
    ap = profiles.get(away, {})
    missing_home = not bool(hp)
    missing_away = not bool(ap)
    fallback_fields: List[str] = []
    if missing_home:
        fallback_fields.append("home_tactical_profile")
    if missing_away:
        fallback_fields.append("away_tactical_profile")
    fallback_ratio = len(fallback_fields) / 2.0

    if fallback_fields:
        for side, team in (("home", home), ("away", away)):
            if f"{side}_tactical_profile" in fallback_fields:
                flags.append({
                    "match_id": mid, "home": home, "away": away,
                    "flag_type": "profile_missing", "field": f"{side}_tactical_profile",
                    "action": "fallback_empty_profile", "severity": "high",
                    "notes": f"{team} not in phase01 profile candidate",
                })

    confidence = min(
        fnum(hp, "data_confidence", 0.0 if missing_home else 0.5),
        fnum(ap, "data_confidence", 0.0 if missing_away else 0.5),
        fnum(fx, "confidence", 0.55),
    )
    if fallback_ratio > 0:
        confidence = min(confidence, 0.35)
        flags.append({
            "match_id": mid, "home": home, "away": away,
            "flag_type": "is_fallback", "field": "data_confidence",
            "action": "cap_at_0.35", "severity": "high",
            "notes": f"fallback_fields={';'.join(fallback_fields)}",
        })

    degraded = snum(fx, "team_profile_degraded").lower() == "true"
    if degraded:
        flags.append({
            "match_id": mid, "home": home, "away": away,
            "flag_type": "team_profile_degraded", "field": "team_profile_degraded",
            "action": "formation_matchup_flagged", "severity": "medium",
            "notes": "formation matchup has team_profile_degraded=true",
        })

    hb = breakthrough(hp, ap)
    ab = breakthrough(ap, hp)
    hc = control(hp, ap)
    ac = control(ap, hp)
    ht = fnum(hp, "transition_attack") + fnum(ap, "high_line_risk")
    at = fnum(ap, "transition_attack") + fnum(hp, "high_line_risk")
    hs = fnum(hp, "set_piece_attack") - fnum(ap, "set_piece_defense")
    as_ = fnum(ap, "set_piece_attack") - fnum(hp, "set_piece_defense")
    hf = fnum(hp, "attack_width") - 0.5 * fnum(ap, "low_block_quality")
    af = fnum(ap, "attack_width") - 0.5 * fnum(hp, "low_block_quality")
    hcent = fnum(hp, "central_progression") - 0.5 * fnum(ap, "defend_pressure_score")
    acent = fnum(ap, "central_progression") - 0.5 * fnum(hp, "defend_pressure_score")
    hpress = (1 if snum(hp, "pressing_height") == "高位压迫" else 0) + fnum(ap, "collapse_risk")
    apress = (1 if snum(ap, "pressing_height") == "高位压迫" else 0) + fnum(hp, "collapse_risk")
    imbalance = abs(hb - ab) + 0.35 * abs(hc - ac) + 0.20 * abs(ht - at)

    full = {
        "match_id": mid,
        "home": home,
        "away": away,
        "home_breakthrough_score": hb,
        "away_breakthrough_score": ab,
        "home_control_score": hc,
        "away_control_score": ac,
        "home_transition_edge": ht,
        "away_transition_edge": at,
        "home_set_piece_edge": hs,
        "away_set_piece_edge": as_,
        "home_flank_edge": hf,
        "away_flank_edge": af,
        "home_central_edge": hcent,
        "away_central_edge": acent,
        "home_press_trap_edge": hpress,
        "away_press_trap_edge": apress,
        "home_shape_countered_by_away": "yes" if ab - hb > 0.45 else "no",
        "away_shape_countered_by_home": "yes" if hb - ab > 0.45 else "no",
        "matchup_imbalance_index": imbalance,
        "likely_breakthrough_path_home": path_summary(hp, ap),
        "likely_breakthrough_path_away": path_summary(ap, hp),
        "likely_defensive_survival_path_home": survival_summary(hp, ap),
        "likely_defensive_survival_path_away": survival_summary(ap, hp),
        "data_confidence": confidence,
        "_is_fallback": str(fallback_ratio > 0).lower(),
        "_team_profile_degraded": str(degraded).lower(),
    }
    row = {k: full.get(k, "") for k in fields}
    return row, flags


def preserve_diff(
    existing: Dict[str, Dict[str, str]],
    candidate: Dict[str, str],
    fields: List[str],
) -> List[Dict[str, str]]:
    mid = candidate["match_id"]
    proc = existing[mid]
    diffs: List[Dict[str, str]] = []
    all_same = True
    for field in fields:
        pv, cv = str(proc.get(field, "")), str(candidate.get(field, ""))
        same = pv == cv
        if not same:
            all_same = False
        diffs.append({
            "match_id": mid, "field": field,
            "processed_value": pv, "candidate_value": cv,
            "is_same": "true" if same else "false",
        })
    diffs.append({
        "match_id": mid, "field": "__row_hash__",
        "processed_value": row_hash(proc, fields),
        "candidate_value": row_hash(candidate, fields),
        "is_same": "true" if all_same else "false",
    })
    return diffs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    hashes_before = {str(p): file_hash(p) for p in PROTECTED_FILES}
    fields = load_matrix_fields()
    r2_schedule = load_r2_schedule()
    r2_ids = {s["match_id"] for s in r2_schedule}

    profiles = {snum(r, "team"): r for r in read_csv(PROFILE_PATH) if snum(r, "team")}
    formations = {snum(r, "match_id"): r for r in read_csv(FORMATION_PATH) if snum(r, "match_id")}
    existing_rows = read_csv(PROCESSED_MATRIX)
    existing_by_id = {
        snum(r, "match_id"): {k: str(r.get(k, "")) for k in fields}
        for r in existing_rows
    }
    preserved_ids = sorted(mid for mid in existing_by_id if mid in r2_ids)

    candidates: List[Dict[str, str]] = []
    diff_rows: List[Dict[str, str]] = []
    quality_flags: List[Dict[str, str]] = []
    meta: List[Dict[str, Any]] = []

    for sched in r2_schedule:
        mid = sched["match_id"]
        if mid in existing_by_id and mid in PRESERVED_IDS:
            row = {k: existing_by_id[mid].get(k, "") for k in fields}
            candidates.append(row)
            diff_rows.extend(preserve_diff(existing_by_id, row, fields))
            meta.append({
                "match_id": mid, "preserved": True, "is_fallback": "false",
                "team_profile_degraded": "false", "confidence": fnum(row, "data_confidence"),
            })
            continue

        fx = formations.get(mid)
        if not fx:
            quality_flags.append({
                "match_id": mid, "home": sched["home"], "away": sched["away"],
                "flag_type": "formation_matchup_missing", "field": "match_id",
                "action": "cannot_generate", "severity": "critical",
                "notes": "No row in team_formation_matchups_72_candidate",
            })
            continue

        row, flags = build_matrix_row(fx, profiles, fields)
        candidates.append(row)
        quality_flags.extend(flags)
        is_fb = "true" if any(f["flag_type"] == "is_fallback" for f in flags) else "false"
        meta.append({
            "match_id": mid, "preserved": False,
            "is_fallback": is_fb,
            "team_profile_degraded": snum(fx, "team_profile_degraded"),
            "confidence": fnum(row, "data_confidence"),
        })

    write_csv(OUTPUT_PATH, candidates, fields)

    hashes_after = {str(p): file_hash(p) for p in PROTECTED_FILES}
    integrity_rows = [
        {
            "file": str(p.relative_to(ROOT)).replace("\\", "/"),
            "sha256_before": hashes_before.get(str(p), ""),
            "sha256_after": hashes_after.get(str(p), ""),
            "unchanged": "true" if hashes_before.get(str(p)) == hashes_after.get(str(p)) else "false",
        }
        for p in PROTECTED_FILES
    ]
    write_csv(OUT_DIR / "processed_file_integrity_report.csv", integrity_rows)

    all_preserved_same = all(
        r["is_same"] == "true" for r in diff_rows if r["field"] == "__row_hash__"
    )
    matrix_unchanged = all(r["unchanged"] == "true" for r in integrity_rows)

    confidences = [m["confidence"] for m in meta]
    fallback_count = sum(1 for m in meta if str(m.get("is_fallback")).lower() == "true")
    degraded_count = sum(1 for m in meta if str(m.get("team_profile_degraded")).lower() == "true")
    low_conf = [m["match_id"] for m in meta if m["confidence"] < 0.35]

    all_round2 = len(candidates) == len(r2_schedule) == 24
    cand_ids = {r["match_id"] for r in candidates}
    missing = sorted(r2_ids - cand_ids)
    extra = sorted(cand_ids - r2_ids)
    contamination = [r["match_id"] for r in candidates if r["match_id"] not in r2_ids]

    profile_missing = [
        s["match_id"] for s in r2_schedule
        if s["home"] not in profiles or s["away"] not in profiles
    ]
    fm_missing = [s["match_id"] for s in r2_schedule if s["match_id"] not in formations]

    ready = (
        all_round2
        and not missing
        and not extra
        and not contamination
        and all_preserved_same
        and matrix_unchanged
        and not low_conf
        and not profile_missing
        and not fm_missing
        and list(candidates[0].keys()) == fields if candidates else False
    )

    coverage: List[Dict[str, str]] = []
    for s in r2_schedule:
        mid = s["match_id"]
        row = next((r for r in candidates if r["match_id"] == mid), {})
        m = next((x for x in meta if x["match_id"] == mid), {})
        coverage.append({
            "match_id": mid,
            "group": s["group"],
            "round": s["round"],
            "date": s["date"],
            "home": s["home"],
            "away": s["away"],
            "in_candidate": "yes" if row else "no",
            "is_existing_preserved": "yes" if mid in PRESERVED_IDS and mid in existing_by_id else "no",
            "is_new_generated": "no" if mid in PRESERVED_IDS and mid in existing_by_id else "yes",
            "home_profile_found": "yes" if s["home"] in profiles else "no",
            "away_profile_found": "yes" if s["away"] in profiles else "no",
            "formation_matchup_found": "yes" if mid in formations else "no",
            "confidence": str(m.get("confidence", "")),
            "is_fallback": str(m.get("is_fallback", "false")).lower(),
            "team_profile_degraded": str(m.get("team_profile_degraded", "false")).lower(),
        })
    write_csv(OUT_DIR / "r2_matrix_coverage.csv", coverage)
    write_csv(OUT_DIR / "r2_matrix_quality_flags.csv", quality_flags, [
        "match_id", "home", "away", "flag_type", "field", "action", "severity", "notes",
    ])
    write_csv(OUT_DIR / "r2_preserved_existing_rows_diff.csv", diff_rows, [
        "match_id", "field", "processed_value", "candidate_value", "is_same",
    ])

    ts = datetime.now().isoformat(timespec="seconds")
    build_lines = [
        "# Phase 03A R2 Matrix Build Report", "",
        f"Generated: {ts}", "",
        "## Inputs", "",
        f"- `{PROFILE_PATH.relative_to(ROOT)}`",
        f"- `{FORMATION_PATH.relative_to(ROOT)}`",
        f"- `{PROCESSED_MATRIX.relative_to(ROOT)}` (preserve 4 rows)",
        f"- `database/competition/wc2026_match_id_mapping.csv` (round==2 filter)",
        f"- `database/competition/wc2026_group_fixtures.csv`", "",
        "## Generation Summary", "",
        f"- R2 expected match count: **24**",
        f"- R2 candidate row count: **{len(candidates)}**",
        f"- R2 unique match_id count: **{len(cand_ids)}**",
        f"- preserved existing rows: **{len(preserved_ids)}**",
        f"- new generated rows: **{len(candidates) - len([m for m in meta if m.get('preserved')])}**",
        f"- min confidence: **{min(confidences):.4f}**" if confidences else "- min confidence: N/A",
        f"- max confidence: **{max(confidences):.4f}**" if confidences else "- max confidence: N/A",
        f"- avg confidence: **{sum(confidences)/len(confidences):.4f}**" if confidences else "- avg confidence: N/A",
        f"- fallback rows count: **{fallback_count}**",
        f"- profile degraded rows count: **{degraded_count}**",
        f"- processed files changed: **{'no' if matrix_unchanged else 'yes'}**",
        "- realtime data used: **no**",
        "- scenario weights generated: **no**",
    ]
    (OUT_DIR / "phase03A_r2_matrix_build_report.md").write_text("\n".join(build_lines) + "\n", encoding="utf-8")

    val_lines = [
        "# Phase 03A R2 Matrix Validation Report", "",
        "## Coverage", "",
        "- expected R2 matches: **24**",
        f"- candidate R2 rows: **{len(candidates)}**",
        f"- missing R2 match_ids: **{', '.join(missing) or 'none'}**",
        f"- extra match_ids: **{', '.join(extra) or 'none'}**",
        f"- R1/R3 contamination rows: **{', '.join(contamination) or 'none'}**", "",
        "## Schema", "",
        f"- columns match processed tactical matrix: **{'yes' if candidates and list(candidates[0].keys()) == fields else 'no'}**", "",
        "## Join Checks", "",
        f"- team profile missing rows: **{', '.join(profile_missing) or 'none'}**",
        f"- formation matchup missing rows: **{', '.join(fm_missing) or 'none'}**", "",
        "## Preservation", "",
        f"- existing C/D R2 row hashes identical: **{'yes' if all_preserved_same else 'no'}**", "",
        "## Quality", "",
        f"- confidence < 0.35 rows: **{', '.join(low_conf) or 'none'}**",
        f"- fallback rows: **{fallback_count}**",
        f"- degraded rows: **{degraded_count}**", "",
        "## Protected Files", "",
    ]
    for ir in integrity_rows:
        val_lines.append(f"- `{ir['file']}` unchanged: **{ir['unchanged']}**")
    val_lines += [
        "", "## Phase 04A Readiness",
        f"- Ready for R2 scenario weights build: **{'yes' if ready else 'no'}**",
    ]
    (OUT_DIR / "phase03A_r2_matrix_validation_report.md").write_text("\n".join(val_lines) + "\n", encoding="utf-8")

    print("Phase 03A complete.")
    print(f"  R2 candidate rows: {len(candidates)}")
    print(f"  Preserved: {len([m for m in meta if m.get('preserved')])}, New: {len(candidates) - len([m for m in meta if m.get('preserved')])}")
    print(f"  Ready for Phase 04A: {ready}")


if __name__ == "__main__":
    main()
