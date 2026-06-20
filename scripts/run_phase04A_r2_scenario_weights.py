#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 04A: build R2-only eventflow scenario weights candidate (408 rows)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eventflow_common import DB, EVENTFLOW_DB, TEAM_DB, read_csv, snum, write_csv  # noqa: E402

OUT_DIR = ROOT / "outputs" / "phase04A_r2_scenario_weights"
STAGING_DIR = ROOT / "database" / "eventflow" / "staging"
BACKUP_DIR = ROOT / "backups" / "phase04A_r2_scenario_weights"

PRESERVED_IDS = {"WC2026-C29", "WC2026-C30", "WC2026-D31", "WC2026-D32"}

PROTECTED_FILES = [
    TEAM_DB / "team_formation_matchups.csv",
    TEAM_DB / "tactical_matchup_matrix.csv",
    EVENTFLOW_DB / "eventflow_scenario_weights.csv",
]

PROFILE_CANDIDATE = ROOT / "database" / "team_style" / "staging" / "team_tactical_profile_48_candidate.csv"
MATRIX_R2_CANDIDATE = ROOT / "database" / "team_style" / "staging" / "tactical_matchup_matrix_R2_candidate.csv"
OUTPUT_PATH = STAGING_DIR / "eventflow_scenario_weights_R2_candidate.csv"
PROCESSED_WEIGHTS = EVENTFLOW_DB / "eventflow_scenario_weights.csv"

SWAP_FILES = [
    TEAM_DB / "team_tactical_profile.csv",
    TEAM_DB / "tactical_matchup_matrix.csv",
    PROCESSED_WEIGHTS,
]


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fields() -> List[str]:
    rows = read_csv(PROCESSED_WEIGHTS)
    return list(rows[0].keys()) if rows else []


def row_hash(row: Dict[str, str], fields: List[str]) -> str:
    payload = {k: str(row.get(k, "")) for k in fields}
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
        out.append({
            "match_id": snum(m, "internal_match_id"),
            "group": snum(m, "group"),
            "round": snum(m, "round"),
            "home": snum(m, "home_team"),
            "away": snum(m, "away_team"),
            "date": snum(fx, "match_date"),
        })
    return out


def scenario_sort_key(sid: str) -> Tuple[int, str]:
    num = 99
    if sid.startswith("S") and len(sid) > 1:
        digits = ""
        for ch in sid[1:]:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            num = int(digits)
    return num, sid


def run_build_sandbox(new_match_ids: Set[str]) -> List[Dict[str, str]]:
    """Temporarily swap inputs, run build script, return generated rows for new matches only."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups: Dict[Path, Path] = {}
    for p in SWAP_FILES:
        if p.exists():
            dest = BACKUP_DIR / f"{p.name}.before_phase04A"
            shutil.copy2(p, dest)
            backups[p] = dest

    matrix_rows = [r for r in read_csv(MATRIX_R2_CANDIDATE) if snum(r, "match_id") in new_match_ids]
    write_csv(TEAM_DB / "tactical_matchup_matrix.csv", matrix_rows)
    shutil.copy2(PROFILE_CANDIDATE, TEAM_DB / "team_tactical_profile.csv")

    try:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_eventflow_scenario_weights.py")],
            cwd=str(ROOT),
            check=True,
        )
        generated = read_csv(PROCESSED_WEIGHTS)
        return [r for r in generated if snum(r, "match_id") in new_match_ids]
    finally:
        for orig, bak in backups.items():
            shutil.copy2(bak, orig)


def preserve_diff(
    processed_rows: List[Dict[str, str]],
    candidate_rows: List[Dict[str, str]],
    fields: List[str],
) -> List[Dict[str, str]]:
    proc_by_key = {(snum(r, "match_id"), snum(r, "scenario_id")): r for r in processed_rows}
    cand_by_key = {(snum(r, "match_id"), snum(r, "scenario_id")): r for r in candidate_rows}
    diffs: List[Dict[str, str]] = []
    for key in sorted(proc_by_key.keys(), key=lambda k: (k[0], scenario_sort_key(k[1]))):
        mid, sid = key
        proc, cand = proc_by_key[key], cand_by_key.get(key, {})
        all_same = True
        for field in fields:
            pv, cv = str(proc.get(field, "")), str(cand.get(field, ""))
            same = pv == cv
            if not same:
                all_same = False
            diffs.append({
                "match_id": mid, "scenario_id": sid, "field": field,
                "processed_value": pv, "candidate_value": cv,
                "is_same": "true" if same else "false",
            })
        diffs.append({
            "match_id": mid, "scenario_id": sid, "field": "__row_hash__",
            "processed_value": row_hash(proc, fields),
            "candidate_value": row_hash(cand, fields) if cand else "",
            "is_same": "true" if all_same else "false",
        })
    return diffs


def validate_candidate(
    rows: List[Dict[str, str]],
    fields: List[str],
    r2_ids: Set[str],
    preserved_rows: List[Dict[str, str]],
    diff_rows: List[Dict[str, str]],
    hashes_before: Dict[str, str],
) -> Dict[str, Any]:
    quality_flags: List[Dict[str, str]] = []
    by_match: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_match[snum(r, "match_id")].append(r)

    expected_scenarios = sorted(
        {snum(r, "scenario_id") for r in preserved_rows},
        key=scenario_sort_key,
    )

    low_conf: List[str] = []
    fallback_rows: List[str] = []
    for r in rows:
        mid, sid = snum(r, "match_id"), snum(r, "scenario_id")
        try:
            conf = float(r.get("data_confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < 0.35:
            low_conf.append(f"{mid}:{sid}")
            quality_flags.append({
                "match_id": mid, "scenario_id": sid, "flag_type": "low_confidence",
                "field": "data_confidence", "action": "report", "severity": "high",
                "notes": f"data_confidence={conf}",
            })
        if str(r.get("is_fallback", "")).lower() == "true":
            fallback_rows.append(f"{mid}:{sid}")
            quality_flags.append({
                "match_id": mid, "scenario_id": sid, "flag_type": "fallback_detected",
                "field": "is_fallback", "action": "report", "severity": "high",
                "notes": snum(r, "fallback_reason"),
            })
        w = r.get("weight", "")
        try:
            wf = float(w)
            if wf < 0:
                quality_flags.append({
                    "match_id": mid, "scenario_id": sid, "flag_type": "invalid_weight",
                    "field": "weight", "action": "report", "severity": "high",
                    "notes": f"weight={w}",
                })
        except (TypeError, ValueError):
            if w == "":
                quality_flags.append({
                    "match_id": mid, "scenario_id": sid, "flag_type": "invalid_weight",
                    "field": "weight", "action": "report", "severity": "high",
                    "notes": "empty weight",
                })

    missing_scenarios: List[str] = []
    duplicate_scenarios: List[str] = []
    for mid in sorted(r2_ids):
        match_rows = by_match.get(mid, [])
        sids = [snum(r, "scenario_id") for r in match_rows]
        if len(sids) != len(set(sids)):
            duplicate_scenarios.append(mid)
        if len(match_rows) != 17:
            missing_scenarios.append(mid)
        elif expected_scenarios and set(sids) != set(expected_scenarios):
            missing_scenarios.append(mid)

    contamination = [snum(r, "match_id") for r in rows if snum(r, "match_id") not in r2_ids]
    cand_ids = set(by_match.keys())
    missing_ids = sorted(r2_ids - cand_ids)
    extra_ids = sorted(cand_ids - r2_ids)

    hash_same = all(
        r["is_same"] == "true" for r in diff_rows if r["field"] == "__row_hash__"
    )
    matrix_unchanged = all(
        hashes_before.get(str(p), "") == file_hash(p) for p in PROTECTED_FILES
    )

    ready = (
        len(rows) == 408
        and len(cand_ids) == 24
        and not missing_ids
        and not extra_ids
        and not contamination
        and not missing_scenarios
        and not duplicate_scenarios
        and not low_conf
        and not fallback_rows
        and hash_same
        and matrix_unchanged
        and list(rows[0].keys()) == fields if rows else False
    )

    return {
        "by_match": by_match,
        "quality_flags": quality_flags,
        "low_conf": low_conf,
        "fallback_rows": fallback_rows,
        "missing_scenarios": missing_scenarios,
        "contamination": contamination,
        "missing_ids": missing_ids,
        "extra_ids": extra_ids,
        "hash_same": hash_same,
        "matrix_unchanged": matrix_unchanged,
        "ready": ready,
        "expected_scenarios": expected_scenarios,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    hashes_before = {str(p): file_hash(p) for p in PROTECTED_FILES}
    fields = load_fields()
    r2_schedule = load_r2_schedule()
    r2_ids = {s["match_id"] for s in r2_schedule}
    new_ids = r2_ids - PRESERVED_IDS

    processed_all = read_csv(PROCESSED_WEIGHTS)
    preserved_rows = [r for r in processed_all if snum(r, "match_id") in PRESERVED_IDS]
    preserved_rows = [{k: str(r.get(k, "")) for k in fields} for r in preserved_rows]

    generated_new = run_build_sandbox(new_ids)
    generated_new = [{k: str(r.get(k, "")) for k in fields} for r in generated_new]

    order_index = {s["match_id"]: i for i, s in enumerate(r2_schedule)}
    combined = preserved_rows + generated_new
    combined.sort(key=lambda r: (
        order_index.get(snum(r, "match_id"), 999),
        scenario_sort_key(snum(r, "scenario_id")),
    ))

    write_csv(OUTPUT_PATH, combined, fields)

    diff_rows = preserve_diff(preserved_rows, combined, fields)
    validation = validate_candidate(
        combined, fields, r2_ids, preserved_rows, diff_rows, hashes_before,
    )

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
    write_csv(OUT_DIR / "r2_preserved_existing_scenario_diff.csv", diff_rows, [
        "match_id", "scenario_id", "field", "processed_value", "candidate_value", "is_same",
    ])
    write_csv(OUT_DIR / "r2_scenario_quality_flags.csv", validation["quality_flags"], [
        "match_id", "scenario_id", "flag_type", "field", "action", "severity", "notes",
    ])

    coverage: List[Dict[str, str]] = []
    for s in r2_schedule:
        mid = s["match_id"]
        mrows = validation["by_match"].get(mid, [])
        weights = []
        for r in mrows:
            try:
                weights.append(float(r.get("weight") or 0))
            except (TypeError, ValueError):
                pass
        confs = []
        for r in mrows:
            try:
                confs.append(float(r.get("data_confidence") or 0))
            except (TypeError, ValueError):
                pass
        sids = {snum(r, "scenario_id") for r in mrows}
        coverage.append({
            "match_id": mid,
            "group": s["group"],
            "round": s["round"],
            "home": s["home"],
            "away": s["away"],
            "scenario_count": str(len(mrows)),
            "has_all_S01_S17": "yes" if len(sids) == 17 and len(mrows) == 17 else "no",
            "is_existing_preserved": "yes" if mid in PRESERVED_IDS else "no",
            "is_new_generated": "no" if mid in PRESERVED_IDS else "yes",
            "row_count": str(len(mrows)),
            "min_weight": f"{min(weights):.6f}" if weights else "",
            "max_weight": f"{max(weights):.6f}" if weights else "",
            "sum_weight": f"{sum(weights):.6f}" if weights else "",
            "data_confidence_min": f"{min(confs):.4f}" if confs else "",
            "quality_flag_count": str(sum(1 for f in validation["quality_flags"] if f["match_id"] == mid)),
        })
    write_csv(OUT_DIR / "r2_scenario_coverage.csv", coverage)

    confs_all = []
    for r in combined:
        try:
            confs_all.append(float(r.get("data_confidence") or 0))
        except (TypeError, ValueError):
            pass

    ts = datetime.now().isoformat(timespec="seconds")
    build_lines = [
        "# Phase 04A R2 Scenario Weights Build Report", "",
        f"Generated: {ts}", "",
        "## Inputs", "",
        f"- `{PROFILE_CANDIDATE.relative_to(ROOT)}`",
        f"- `{MATRIX_R2_CANDIDATE.relative_to(ROOT)}`",
        f"- `{PROCESSED_WEIGHTS.relative_to(ROOT)}` (preserve 68 rows for 4 matches)",
        f"- `scripts/build_eventflow_scenario_weights.py` (sandbox, 20 new matches)",
        f"- `database/competition/wc2026_match_id_mapping.csv` (round==2)", "",
        "## Generation Summary", "",
        f"- R2 expected match count: **24**",
        f"- candidate row count: **{len(combined)}**",
        f"- preserved existing scenario rows: **{len(preserved_rows)}**",
        f"- new generated scenario rows: **{len(generated_new)}**",
        f"- min confidence: **{min(confs_all):.4f}**" if confs_all else "- min confidence: N/A",
        f"- max confidence: **{max(confs_all):.4f}**" if confs_all else "- max confidence: N/A",
        f"- avg confidence: **{sum(confs_all)/len(confs_all):.4f}**" if confs_all else "- avg confidence: N/A",
        f"- fallback rows count: **{len(validation['fallback_rows'])}**",
        f"- processed files changed: **{'no' if validation['matrix_unchanged'] else 'yes'}**",
        "- realtime data used: **no**",
        "- prediction chain executed: **no**",
    ]
    (OUT_DIR / "phase04A_r2_scenario_build_report.md").write_text("\n".join(build_lines) + "\n", encoding="utf-8")

    val_lines = [
        "# Phase 04A R2 Scenario Validation Report", "",
        "## Coverage", "",
        "- expected R2 matches: **24**",
        f"- candidate R2 matches: **{len(validation['by_match'])}**",
        f"- candidate rows: **{len(combined)}**",
        f"- missing R2 match_ids: **{', '.join(validation['missing_ids']) or 'none'}**",
        f"- extra match_ids: **{', '.join(validation['extra_ids']) or 'none'}**",
        f"- R1/R3 contamination rows: **{', '.join(set(validation['contamination'])) or 'none'}**", "",
        "## Schema", "",
        f"- columns match processed scenario weights: **{'yes' if combined and list(combined[0].keys()) == fields else 'no'}**", "",
        "## Scenario Completeness", "",
        f"- matches with scenario_count != 17: **{', '.join(validation['missing_scenarios']) or 'none'}**", "",
        "## Preservation", "",
        f"- existing C/D R2 scenario hashes identical: **{'yes' if validation['hash_same'] else 'no'}**", "",
        "## Quality", "",
        f"- confidence < 0.35 rows: **{len(validation['low_conf'])}**",
        f"- fallback rows: **{len(validation['fallback_rows'])}**",
        f"- quality flags: **{len(validation['quality_flags'])}**", "",
        "## Protected Files", "",
    ]
    for ir in integrity_rows:
        val_lines.append(f"- `{ir['file']}` unchanged: **{ir['unchanged']}**")
    val_lines += [
        "", "## Phase 05A Readiness",
        f"- Ready for R2 prediction pipeline integration: **{'yes' if validation['ready'] else 'no'}**",
    ]
    (OUT_DIR / "phase04A_r2_scenario_validation_report.md").write_text("\n".join(val_lines) + "\n", encoding="utf-8")

    print("Phase 04A complete.")
    print(f"  Candidate rows: {len(combined)}")
    print(f"  Preserved scenario rows: {len(preserved_rows)}, New: {len(generated_new)}")
    print(f"  Ready for Phase 05A: {validation['ready']}")


if __name__ == "__main__":
    main()
