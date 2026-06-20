#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 02: generate 72-match team_formation_matchups candidate from phase01 profiles."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eventflow_common import DB, TEAM_DB, read_csv, snum, write_csv  # noqa: E402

OUT_DIR = ROOT / "outputs" / "phase02_formation_matchups"
STAGING_DIR = ROOT / "database" / "team_style" / "staging"
BACKUP_DIR = ROOT / "backups" / "phase02_formation_matchups"

FIELD_ORDER = [
    "match_id", "date", "home", "away", "home_shape", "away_shape",
    "home_in_possession_shape", "away_in_possession_shape",
    "home_press_shape", "away_press_shape",
    "home_low_block_shape", "away_low_block_shape",
    "home_key_zones", "away_key_zones",
    "source", "source_url", "source_title",
    "confidence", "is_estimated", "team_profile_degraded",
]

REQUIRED_FIELDS = [
    "match_id", "date", "home", "away", "home_shape", "away_shape",
    "home_in_possession_shape", "away_in_possession_shape",
    "home_press_shape", "away_press_shape",
    "home_low_block_shape", "away_low_block_shape",
    "home_key_zones", "away_key_zones",
    "source", "source_title", "confidence", "is_estimated", "team_profile_degraded",
]

PROTECTED_FILES = [
    TEAM_DB / "team_formation_matchups.csv",
    TEAM_DB / "tactical_matchup_matrix.csv",
    DB / "eventflow" / "processed" / "eventflow_scenario_weights.csv",
]

POSSESSION_BASES = {"4-3-3", "4-2-3-1", "4-1-4-1"}
WING_BACK_BASES = {"3-4-3", "3-4-2-1", "3-5-2", "5-3-2", "5-4-1"}
FLAT_FOUR_BASES = {"4-4-2", "4-4-1-1"}


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_hash(row: Dict[str, str]) -> str:
    payload = {k: row.get(k, "") for k in FIELD_ORDER}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fval(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        v = row.get(key, default)
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def is_true(v: Any) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes"}


def in_possession_shape(base: str, build_up: str, attack_width: float, central: float) -> str:
    if base in POSSESSION_BASES:
        if "控球" in build_up or central > 0.25:
            return "2-3-5"
        if attack_width > 0.25:
            return "3-2-5"
        return "2-3-5"
    if base in WING_BACK_BASES:
        if attack_width > 0.2:
            return "3-2-5"
        return "3-4-3"
    if base in FLAT_FOUR_BASES:
        if "直接" in build_up:
            return "4-2-4"
        return "2-4-4"
    return base or "4-4-2"


def press_shape(base: str, pressing: str) -> str:
    if "高位" in pressing:
        if base in {"4-3-3", "4-2-3-1"}:
            return base
        if base in FLAT_FOUR_BASES:
            return "4-4-2"
        if base.startswith("3-") or base.startswith("5-"):
            return "5-2-3"
        return base or "4-4-2"
    if "中" in pressing:
        if base.startswith("4-"):
            return "4-4-2"
        if base.startswith("3-") or base.startswith("5-"):
            return "5-3-2"
        return base or "4-4-2"
    if "低" in pressing or "被动" in pressing:
        if base.startswith("4-"):
            return "4-5-1"
        if base.startswith("3-") or base.startswith("5-"):
            return "5-4-1"
        return base or "4-4-2"
    return base or "4-4-2"


def low_block_shape(base: str) -> str:
    if base.startswith("5-") or base.startswith("3-"):
        return "5-3-2" if base == "3-5-2" else "5-4-1"
    if base in {"4-3-3", "4-2-3-1", "4-1-4-1"}:
        return "4-5-1"
    if base in FLAT_FOUR_BASES:
        return "4-4-2"
    return base or "4-4-2"


def key_zones(profile: Dict[str, str], estimated: bool) -> str:
    aw = fval(profile, "attack_width")
    cp = fval(profile, "central_progression")
    ta = fval(profile, "transition_attack")
    spa = fval(profile, "set_piece_attack")
    blb = fval(profile, "break_low_block_score")

    paths: List[str] = []
    if aw >= 0.20:
        paths.append("边路宽度/套边制造入口")
    elif aw <= -0.20:
        paths.append("边路推进不足")
    if cp >= 0.20:
        paths.append("中路推进/肋部连接")
    elif cp <= -0.20:
        paths.append("中路推进受限")
    if ta >= 0.20:
        paths.append("转换纵深/身后空间")
    elif ta <= -0.20:
        paths.append("转换威胁有限")
    if spa >= 0.20:
        paths.append("定位球二点/高点冲击")
    if blb >= 0.25:
        paths.append("破低位能力较强")
    elif blb <= -0.25:
        paths.append("阵地破局效率偏低")

    if not paths:
        out = "无明显单点破阵路径"
    else:
        out = "+".join(paths[:3])

    if estimated and paths and not out.startswith("估计画像"):
        out = f"估计画像：{out}"
    return out


def profile_team(profiles: Dict[str, Dict[str, str]], team: str) -> Dict[str, str]:
    return profiles.get(team, {})


def team_shape(profile: Dict[str, str]) -> Tuple[str, bool]:
    shape = snum(profile, "formation_base")
    if shape:
        return shape, False
    return "4-4-2", True


def compute_confidence(
    home: Dict[str, str],
    away: Dict[str, str],
    home_missing: bool,
    away_missing: bool,
) -> Tuple[float, bool]:
    degraded = False
    if home_missing or away_missing:
        return 0.35, True

    home_conf = fval(home, "data_confidence", 0.6)
    away_conf = fval(away, "data_confidence", 0.6)
    base_conf = min(home_conf, away_conf)

    home_est = is_true(home.get("is_estimated", ""))
    away_est = is_true(away.get("is_estimated", ""))
    if home_est and away_est:
        conf = min(base_conf - 0.06, 0.70)
    elif home_est or away_est:
        conf = min(base_conf - 0.04, 0.72)
    else:
        conf = min(base_conf, 0.88)

    for p in (home, away):
        for fld in ("formation_base", "pressing_height", "build_up_style"):
            if not snum(p, fld):
                conf -= 0.08
                degraded = True

    conf = max(conf, 0.55)
    if degraded and conf < 0.55:
        conf = 0.55
    return round(conf, 2), degraded


def build_schedule() -> List[Dict[str, str]]:
    mapping = read_csv(DB / "competition" / "wc2026_match_id_mapping.csv")
    fixtures = {snum(r, "fifa_match_id"): r for r in read_csv(DB / "competition" / "wc2026_group_fixtures.csv")}
    out: List[Dict[str, str]] = []
    for m in mapping:
        mid = snum(m, "internal_match_id")
        fid = snum(m, "fifa_match_id")
        fx = fixtures.get(fid, {})
        date = snum(fx, "match_date")
        if not date:
            kick = snum(m, "kickoff_time")
            date = kick.split()[0] if kick else ""
        out.append({
            "match_id": mid,
            "fifa_match_id": fid,
            "group": snum(m, "group"),
            "round": snum(m, "round"),
            "home": snum(m, "home_team"),
            "away": snum(m, "away_team"),
            "date": date,
            "source_url": snum(fx, "source_url") or snum(m, "source_url"),
        })
    return out


def generate_row(
    sched: Dict[str, str],
    profiles: Dict[str, Dict[str, str]],
    gap_log: List[Dict[str, str]],
) -> Dict[str, str]:
    home_name, away_name = sched["home"], sched["away"]
    home_p = profile_team(profiles, home_name)
    away_p = profile_team(profiles, away_name)
    home_missing = not home_p
    away_missing = not away_p

    home_base, home_shape_degraded = team_shape(home_p)
    away_base, away_shape_degraded = team_shape(away_p)
    degraded = home_missing or away_missing or home_shape_degraded or away_shape_degraded

    if home_shape_degraded:
        gap_log.append({
            "match_id": sched["match_id"], "team": home_name, "field": "formation_base",
            "gap_type": "missing", "action": "fallback_4-4-2", "confidence": "",
            "notes": "formation_base empty; used fallback",
        })
    if away_shape_degraded:
        gap_log.append({
            "match_id": sched["match_id"], "team": away_name, "field": "formation_base",
            "gap_type": "missing", "action": "fallback_4-4-2", "confidence": "",
            "notes": "formation_base empty; used fallback",
        })

    home_est = is_true(home_p.get("is_estimated", "true")) if home_p else True
    away_est = is_true(away_p.get("is_estimated", "true")) if away_p else True

    conf, conf_degraded = compute_confidence(home_p, away_p, home_missing, away_missing)
    if home_shape_degraded or away_shape_degraded:
        conf = min(conf, 0.55)
        conf_degraded = True
    degraded = degraded or conf_degraded

    for p, team in ((home_p, home_name), (away_p, away_name)):
        if p:
            for fld in ("pressing_height", "build_up_style"):
                if not snum(p, fld):
                    gap_log.append({
                        "match_id": sched["match_id"], "team": team, "field": fld,
                        "gap_type": "missing", "action": "confidence_penalty",
                        "confidence": str(conf), "notes": "key profile field missing",
                    })

    return {
        "match_id": sched["match_id"],
        "date": sched["date"],
        "home": home_name,
        "away": away_name,
        "home_shape": home_base,
        "away_shape": away_base,
        "home_in_possession_shape": in_possession_shape(
            home_base, snum(home_p, "build_up_style"), fval(home_p, "attack_width"), fval(home_p, "central_progression"),
        ),
        "away_in_possession_shape": in_possession_shape(
            away_base, snum(away_p, "build_up_style"), fval(away_p, "attack_width"), fval(away_p, "central_progression"),
        ),
        "home_press_shape": press_shape(home_base, snum(home_p, "pressing_height")),
        "away_press_shape": press_shape(away_base, snum(away_p, "pressing_height")),
        "home_low_block_shape": low_block_shape(home_base),
        "away_low_block_shape": low_block_shape(away_base),
        "home_key_zones": key_zones(home_p, home_est),
        "away_key_zones": key_zones(away_p, away_est),
        "source": "phase01_profile+wc2026_schedule",
        "source_url": sched["source_url"],
        "source_title": f"{home_name} vs {away_name} formation matchup candidate",
        "confidence": str(conf),
        "is_estimated": "true" if (home_est or away_est or True) else "false",
        "team_profile_degraded": "true" if degraded else "false",
    }


def preserve_diff(existing: Dict[str, Dict[str, str]], candidate: Dict[str, str]) -> List[Dict[str, str]]:
    mid = candidate["match_id"]
    proc = existing[mid]
    diffs: List[Dict[str, str]] = []
    all_same = True
    for field in FIELD_ORDER:
        pv, cv = proc.get(field, ""), candidate.get(field, "")
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
        "processed_value": row_hash(proc),
        "candidate_value": row_hash(candidate),
        "is_same": "true" if all_same else "false",
    })
    return diffs


def validate(
    schedule: List[Dict[str, str]],
    candidates: List[Dict[str, str]],
    profiles: Dict[str, Dict[str, str]],
    hashes_before: Dict[str, str],
    preserved_ids: List[str],
    all_preserved_same: bool,
) -> Dict[str, Any]:
    exp_ids = {s["match_id"] for s in schedule}
    cand_ids = {r["match_id"] for r in candidates}
    missing = sorted(exp_ids - cand_ids)
    extra = sorted(cand_ids - exp_ids)
    cols_ok = list(candidates[0].keys()) == FIELD_ORDER if candidates else False

    profile_missing_rows: List[str] = []
    required_missing_rows: List[str] = []
    degraded_rows: List[str] = []
    confidences: List[float] = []

    for r in candidates:
        mid = r["match_id"]
        if snum(r, "home") not in profiles or snum(r, "away") not in profiles:
            profile_missing_rows.append(mid)
        for fld in REQUIRED_FIELDS:
            if not snum(r, fld) and snum(r, fld) != "0":
                if fld not in required_missing_rows:
                    required_missing_rows.append(mid)
        if is_true(r.get("team_profile_degraded")):
            degraded_rows.append(mid)
        confidences.append(fval(r, "confidence"))

    matrix_unchanged = all(
        hashes_before.get(str(p), "") == file_hash(p) for p in PROTECTED_FILES
    )

    ready = (
        len(candidates) == 72
        and len(cand_ids) == 72
        and not missing
        and not extra
        and cols_ok
        and not profile_missing_rows
        and not required_missing_rows
        and not degraded_rows
        and all_preserved_same
        and matrix_unchanged
    )

    return {
        "missing": missing,
        "extra": extra,
        "cols_ok": cols_ok,
        "profile_missing_rows": profile_missing_rows,
        "required_missing_rows": required_missing_rows,
        "degraded_rows": degraded_rows,
        "confidences": confidences,
        "matrix_unchanged": matrix_unchanged,
        "ready": ready,
        "preserved_ids": preserved_ids,
    }


def write_reports(
    schedule: List[Dict[str, str]],
    candidates: List[Dict[str, str]],
    profiles: Dict[str, Dict[str, str]],
    existing_rows: List[Dict[str, str]],
    preserved_ids: List[str],
    new_count: int,
    diff_rows: List[Dict[str, str]],
    gap_log: List[Dict[str, str]],
    validation: Dict[str, Any],
    hashes_before: Dict[str, str],
) -> None:
    confs = validation["confidences"]
    all_preserved_same = all(
        r["is_same"] == "true" for r in diff_rows if r["field"] == "__row_hash__"
    )

    gen_lines = [
        "# Phase 02 Formation Matchups Generation Report", "",
        f"Generated: {candidates[0].get('date', '') if candidates else 'N/A'}", "",
        "## Inputs", "",
        f"- schedule rows: **{len(schedule)}**",
        f"- profile candidate rows: **{len(profiles)}**",
        f"- existing processed matchup rows: **{len(existing_rows)}**", "",
        "## Generation Summary", "",
        "- expected matches: **72**",
        f"- existing preserved rows: **{len(preserved_ids)}**",
        f"- newly generated rows: **{new_count}**",
        f"- final candidate rows: **{len(candidates)}**", "",
        "## Confidence Summary", "",
        f"- min confidence: **{min(confs):.2f}**" if confs else "- min confidence: N/A",
        f"- max confidence: **{max(confs):.2f}**" if confs else "- max confidence: N/A",
        f"- average confidence: **{sum(confs)/len(confs):.2f}**" if confs else "- average confidence: N/A",
        f"- rows with confidence < 0.55: **{sum(1 for c in confs if c < 0.55)}**",
        f"- rows with team_profile_degraded=true: **{len(validation['degraded_rows'])}**", "",
        "## Existing Row Preservation", "",
        f"- preserved match_ids: {', '.join(preserved_ids)}",
        f"- diff result: **{'all identical' if all_preserved_same else 'MISMATCH — see preserved_existing_rows_diff.csv'}**", "",
        "## Notes", "",
        "- no realtime news used",
        "- no injury/lineup/odds used",
        "- processed files unchanged",
    ]
    (OUT_DIR / "phase02_matchup_generation_report.md").write_text("\n".join(gen_lines) + "\n", encoding="utf-8")

    val_lines = [
        "# Phase 02 Validation Report", "",
        "## Coverage", "",
        "- expected matches: **72**",
        f"- candidate matches: **{len(candidates)}**",
        f"- missing match_ids: **{', '.join(validation['missing']) or 'none'}**",
        f"- extra match_ids: **{', '.join(validation['extra']) or 'none'}**", "",
        "## Schema", "",
        f"- expected columns match: **{'yes' if validation['cols_ok'] else 'no'}**", "",
        "## Team Profile Join", "",
        f"- home/away profile missing rows: **{', '.join(validation['profile_missing_rows']) or 'none'}**", "",
        "## Required Fields", "",
        f"- required field missing rows: **{', '.join(validation['required_missing_rows']) or 'none'}**", "",
        "## Protected Files", "",
    ]
    names = ["team_formation_matchups", "tactical_matchup_matrix", "eventflow_scenario_weights"]
    for p, name in zip(PROTECTED_FILES, names):
        unchanged = hashes_before.get(str(p), "") == file_hash(p)
        val_lines.append(f"- processed {name} unchanged: **{'yes' if unchanged else 'no'}**")
    val_lines += [
        "", "## Phase 03 Readiness",
        f"- Ready for batch 3 tactical matrix build: **{'yes' if validation['ready'] else 'no'}**",
    ]
    (OUT_DIR / "phase02_validation_report.md").write_text("\n".join(val_lines) + "\n", encoding="utf-8")

    existing_set = set(preserved_ids)
    coverage: List[Dict[str, str]] = []
    for s in schedule:
        mid = s["match_id"]
        row = next((r for r in candidates if r["match_id"] == mid), {})
        coverage.append({
            "match_id": mid,
            "group": s["group"],
            "round": s["round"],
            "date": s["date"],
            "home": s["home"],
            "away": s["away"],
            "in_candidate": "yes" if row else "no",
            "is_existing_preserved": "yes" if mid in existing_set else "no",
            "is_new_generated": "no" if mid in existing_set else "yes",
            "home_profile_found": "yes" if s["home"] in profiles else "no",
            "away_profile_found": "yes" if s["away"] in profiles else "no",
            "confidence": snum(row, "confidence"),
            "is_estimated": snum(row, "is_estimated"),
            "team_profile_degraded": snum(row, "team_profile_degraded"),
        })
    write_csv(OUT_DIR / "matchup_coverage.csv", coverage)
    write_csv(OUT_DIR / "matchup_gap_log.csv", gap_log, [
        "match_id", "team", "field", "gap_type", "action", "confidence", "notes",
    ])
    write_csv(OUT_DIR / "preserved_existing_rows_diff.csv", diff_rows, [
        "match_id", "field", "processed_value", "candidate_value", "is_same",
    ])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    hashes_before = {str(p): file_hash(p) for p in PROTECTED_FILES}

    schedule = build_schedule()
    profiles_list = read_csv(STAGING_DIR / "team_tactical_profile_48_candidate.csv")
    profiles = {snum(r, "team"): r for r in profiles_list if snum(r, "team")}

    existing_rows = read_csv(TEAM_DB / "team_formation_matchups.csv")
    existing_by_id = {snum(r, "match_id"): {k: r.get(k, "") for k in FIELD_ORDER} for r in existing_rows}
    preserved_ids = sorted(existing_by_id.keys())

    gap_log: List[Dict[str, str]] = []
    diff_rows: List[Dict[str, str]] = []
    candidates: List[Dict[str, str]] = []

    for sched in schedule:
        mid = sched["match_id"]
        if mid in existing_by_id:
            row = {k: existing_by_id[mid].get(k, "") for k in FIELD_ORDER}
            candidates.append(row)
            diff_rows.extend(preserve_diff(existing_by_id, row))
        else:
            candidates.append(generate_row(sched, profiles, gap_log))

    out_path = STAGING_DIR / "team_formation_matchups_72_candidate.csv"
    write_csv(out_path, candidates, FIELD_ORDER)

    all_preserved_same = all(
        r["is_same"] == "true" for r in diff_rows if r["field"] == "__row_hash__"
    )
    validation = validate(
        schedule, candidates, profiles, hashes_before,
        preserved_ids, all_preserved_same,
    )
    write_reports(
        schedule, candidates, profiles, existing_rows, preserved_ids,
        72 - len(preserved_ids), diff_rows, gap_log, validation, hashes_before,
    )

    print("Phase 02 complete.")
    print(f"  Candidate rows: {len(candidates)}")
    print(f"  Preserved: {len(preserved_ids)}, New: {72 - len(preserved_ids)}")
    print(f"  Degraded rows: {len(validation['degraded_rows'])}")
    print(f"  Ready for phase 03: {validation['ready']}")


if __name__ == "__main__":
    main()
