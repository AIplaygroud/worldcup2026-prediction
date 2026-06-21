#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7 Phase-1 realization guards — audit-only, no λ mutation."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eventflow_common import write_csv
from scenario_realization_common import V37_AUDIT_DIR, load_v37_features
from v37_common import load_mapping

PHASE1_GUARDS = frozenset({
    "must_win_no_convert",
    "cold_draw_guard",
    "deep_handicap_contra",
    "group_pressure_draw_utility",
})

AUDIT_CSV_FIELDS = [
    "match_id", "home", "away", "phase", "cold_guard_active", "deep_handicap_contra_flag",
    "must_win_no_convert_home", "must_win_no_convert_away", "pressure_type_home",
    "pressure_type_away", "draw_utility_home", "draw_utility_away",
    "egci_phase1_disabled", "active_flags", "betting_risk_flags", "generated_at",
]


def _risk_flags(v37: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if v37.get("must_win_no_convert_home"):
        flags.append("must_win_does_not_equal_conversion_home")
    if v37.get("must_win_no_convert_away"):
        flags.append("must_win_does_not_equal_conversion_away")
    if v37.get("cold_guard_active"):
        flags.append("cold_draw_guard_reserve")
    if v37.get("deep_handicap_contra_flag"):
        flags.append("deep_handicap_contra")
    if v37.get("pressure_type_home") == "draw_ok" or v37.get("draw_utility_home", 0) >= 0.55:
        flags.append("home_draw_utility_elevated")
    if v37.get("pressure_type_away") == "draw_ok" or v37.get("draw_utility_away", 0) >= 0.55:
        flags.append("away_draw_utility_elevated")
    return flags


def build_guard_payload(
    match_id: str,
    home: str = "",
    away: str = "",
) -> dict[str, Any]:
    v37 = load_v37_features(match_id)
    risk_flags = _risk_flags(v37)

    # Phase 1: EGCI cascade explicitly disabled — audit only, no score-family boost
    egci_audit = {
        "early_goal_cascade_index": v37.get("early_goal_cascade_index", 0.0),
        "cascade_tail_active_raw": v37.get("cascade_tail_active", False),
        "phase1_enabled": False,
        "phase1_note": "EGCI cascade_tail_active disabled in phase-1; index recorded for audit only",
    }

    return {
        "match_id": match_id,
        "home": home,
        "away": away,
        "v37_guards": {
            "group_pressure": {
                "home": v37.get("group_pressure_home"),
                "away": v37.get("group_pressure_away"),
                "pressure_type_home": v37.get("pressure_type_home"),
                "pressure_type_away": v37.get("pressure_type_away"),
                "draw_utility_home": v37.get("draw_utility_home"),
                "draw_utility_away": v37.get("draw_utility_away"),
            },
            "attack_conversion_gate": {
                "home": v37.get("attack_conversion_home"),
                "away": v37.get("attack_conversion_away"),
                "must_win_no_convert_home": v37.get("must_win_no_convert_home"),
                "must_win_no_convert_away": v37.get("must_win_no_convert_away"),
            },
            "early_goal_cascade": egci_audit,
            "low_block_keeper_guard": {
                "cold_draw_guard_score": v37.get("cold_draw_guard_score"),
                "cold_guard_active": v37.get("cold_guard_active"),
                "deep_handicap_contra_flag": v37.get("deep_handicap_contra_flag"),
                "favorite": v37.get("favorite"),
                "underdog": v37.get("underdog"),
            },
            "score_family_adjustments": {
                "phase1_applied": False,
                "note": "No V3.7 score-family or λ adjustments in phase-1",
            },
            "betting_risk_flags": risk_flags,
        },
        "v37_guard_summary": {
            "group_pressure": f"{v37.get('pressure_type_home')} / {v37.get('pressure_type_away')}",
            "attack_conversion_gate": round(
                float(v37.get("attack_conversion_home", 0.5)), 3
            ),
            "early_goal_cascade_index": round(float(v37.get("early_goal_cascade_index", 0)), 3),
            "low_block_keeper_guard": round(float(v37.get("cold_draw_guard_score", 0)), 3),
            "active_flags": v37.get("active_flags", []),
            "risk_reserve_scorelines": [],
            "betting_risk_flags": risk_flags,
        },
        "data_quality_grade": v37.get("data_quality_grade", "degraded"),
        "loaded": v37.get("loaded", False),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_audit(payload: dict[str, Any]) -> None:
    V37_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    mid = payload["match_id"]
    json_path = V37_AUDIT_DIR / f"v37_prediction_audit_{mid}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    v37 = load_v37_features(mid)
    row = {
        "match_id": mid,
        "home": payload.get("home", ""),
        "away": payload.get("away", ""),
        "phase": "phase1_protective",
        "cold_guard_active": str(v37.get("cold_guard_active", False)).lower(),
        "deep_handicap_contra_flag": str(v37.get("deep_handicap_contra_flag", False)).lower(),
        "must_win_no_convert_home": str(v37.get("must_win_no_convert_home", False)).lower(),
        "must_win_no_convert_away": str(v37.get("must_win_no_convert_away", False)).lower(),
        "pressure_type_home": v37.get("pressure_type_home", ""),
        "pressure_type_away": v37.get("pressure_type_away", ""),
        "draw_utility_home": v37.get("draw_utility_home", ""),
        "draw_utility_away": v37.get("draw_utility_away", ""),
        "egci_phase1_disabled": "true",
        "active_flags": ";".join(v37.get("active_flags", [])),
        "betting_risk_flags": ";".join(payload["v37_guards"]["betting_risk_flags"]),
        "generated_at": payload["generated_at"],
    }
    csv_path = V37_AUDIT_DIR / "v37_prediction_audit.csv"
    existing = []
    if csv_path.exists():
        from eventflow_common import read_csv
        existing = [r for r in read_csv(csv_path) if r.get("match_id") != mid]
    existing.append(row)
    write_csv(csv_path, existing, AUDIT_CSV_FIELDS)


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply V3.7 phase-1 realization guards (audit only)")
    ap.add_argument("--match-id", default="", help="e.g. WC2026-E34; omit with --all-matches")
    ap.add_argument("--all-matches", action="store_true", help="Audit all mapped matches into v37_prediction_audit.csv")
    ap.add_argument("--home", default="")
    ap.add_argument("--away", default="")
    ap.add_argument("--export-json", default="")
    args = ap.parse_args()

    if args.all_matches:
        count = 0
        for m in load_mapping():
            mid = m["internal_match_id"]
            payload = build_guard_payload(mid, m["home_team"], m["away_team"])
            write_audit(payload)
            count += 1
        print(f"V3.7 batch guards audit: {count} matches -> {V37_AUDIT_DIR / 'v37_prediction_audit.csv'}")
        return

    if not args.match_id:
        raise SystemExit("Provide --match-id or --all-matches")

    payload = build_guard_payload(args.match_id, args.home, args.away)
    write_audit(payload)

    out = Path(args.export_json) if args.export_json else (
        V37_AUDIT_DIR / f"v37_guards_{args.match_id}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"V3.7 guards audit -> {out}")
    print(f"  active_flags: {payload['v37_guard_summary']['active_flags']}")
    print(f"  betting_risk_flags: {payload['v37_guards']['betting_risk_flags']}")


if __name__ == "__main__":
    main()
