#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.5 penetration validation: adjusted_lambda must drive probabilities, fusion, and audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from apply_realtime_lambda_adjustment import (  # noqa: E402
    ADJUSTMENT_AUDIT_FIELDS,
    DEFAULT_PROB_CSV,
    compute_market_snapshot,
)
from eventflow_common import EVENTFLOW_DB, read_csv, snum  # noqa: E402
from realtime_availability_common import (  # noqa: E402
    apply_realtime_lambda_adjustments,
    check_lambda_eligibility,
    compute_signal_adjustment,
)

DIAG_PATH = ROOT / "database" / "eventflow" / "raw" / "v2_engine_diagnostics.json"
RAW_SIGNALS = EVENTFLOW_DB.parent / "realtime_availability_signals.csv"
ADJ_OUT = EVENTFLOW_DB / "realtime_availability_adjustments.csv"

AUDIT_REQUIRED = [
    "base_role_adjustment_pct",
    "replacement_multiplier",
    "evidence_multiplier",
    "minutes_multiplier",
    "raw_adjustment_pct",
    "final_adjustment_pct",
]


def _sig(**kwargs):
    base = {
        "match_id": "TEST",
        "team": "USA",
        "opponent": "Australia",
        "player": "Test Player",
        "signal_type": "injury",
        "status": "out",
        "role": "Winger",
        "role_group": "wide_attacker",
        "importance_tier": "core",
        "replacement": "Sub",
        "replacement_quality": "high",
        "evidence_grade": "A",
        "confirmed": "true",
        "source_count": "2",
        "minutes_expected_delta": "-80",
    }
    base.update(kwargs)
    return base


def run_unit_checks() -> List[str]:
    errors: List[str] = []

    s = compute_signal_adjustment(_sig())
    if not (-0.08 <= float(s["final_adjustment_pct"]) <= -0.02):
        errors.append(f"core attacker: delta out of range {s['final_adjustment_pct']}")

    s2 = _sig(status="doubtful", evidence_grade="C", confirmed="false")
    ok, reason, ef = check_lambda_eligibility(s2)
    if ok or reason != "unconfirmed":
        errors.append(f"unconfirmed: expected unconfirmed, got {reason}")

    gk = compute_signal_adjustment(_sig(
        player="Keeper", role_group="goalkeeper", importance_tier="core",
        replacement_quality="low", team="Australia", opponent="USA",
    ))
    if not (0.05 <= float(gk["opponent_attack_delta_pct"]) <= 0.10):
        errors.append(f"GK uplift: {gk['opponent_attack_delta_pct']}")

    res = apply_realtime_lambda_adjustments(1.581, 1.2083, "USA", "Australia", [_sig()])
    if res.adjusted_lambda_home >= res.base_lambda_home:
        errors.append("USA λ should decrease")

    # §10.1 probability recompute
    base_snap = compute_market_snapshot(1.60, 1.20)
    adj_snap = compute_market_snapshot(1.44, 1.20)
    if base_snap["home_win"] == adj_snap["home_win"]:
        errors.append("10.1: 1X2 unchanged after -10% home λ")
    if base_snap["top_scores"] == adj_snap["top_scores"] and base_snap["btts"] == adj_snap["btts"]:
        errors.append("10.1: scorelines/BTTS unchanged after large λ shift")

    rot = _sig(player="Kuol", importance_tier="rotation", signal_type="lineup_start", status="starts")
    ok3, reason3, _ = check_lambda_eligibility(rot)
    if ok3 or reason3 != "rotation_player_not_eligible_for_lambda":
        errors.append(f"10.5 rotation: {reason3}")

    for field in AUDIT_REQUIRED:
        if field not in s or s[field] in ("", None):
            errors.append(f"10.6 missing audit field on included signal: {field}")

    return errors


def validate_match(match_id: str) -> List[str]:
    errors: List[str] = []
    diag_all: Dict[str, Any] = {}
    if DIAG_PATH.exists():
        diag_all = json.loads(DIAG_PATH.read_text(encoding="utf-8"))
    diag = diag_all.get(match_id, {})
    if not diag:
        errors.append(f"no v2 diagnostics for {match_id}")
        return errors

    if diag.get("probabilities_from") != "adjusted_lambda":
        signals = [r for r in read_csv(RAW_SIGNALS) if snum(r, "match_id") == match_id]
        if signals:
            errors.append(f"probabilities_from={diag.get('probabilities_from')} but signals exist")

    base_snap = diag.get("base_probability_snapshot", {})
    adj_snap = diag.get("adjusted_probability", {})
    if diag.get("probabilities_from") == "adjusted_lambda":
        if not base_snap or not adj_snap:
            errors.append("missing base/adjusted probability snapshots")
        elif (
            base_snap.get("home_win") == adj_snap.get("home_win")
            and base_snap.get("top_scores") == adj_snap.get("top_scores")
        ):
            errors.append("adjusted_lambda set but probability snapshots identical")

    adj_rows = [r for r in read_csv(ADJ_OUT) if snum(r, "match_id") == match_id]
    included = [r for r in adj_rows if str(r.get("included_for_lambda", "")).lower() in {"true", "1"}]
    for row in included:
        for field in ADJUSTMENT_AUDIT_FIELDS:
            if field in ("exclusion_reason", "generated_at", "confirmed"):
                continue
            if field not in row:
                errors.append(f"audit CSV missing column {field}")
                break
        for field in AUDIT_REQUIRED + ["base_lambda_before", "adjusted_lambda_after"]:
            if not str(row.get(field, "")).strip():
                errors.append(f"included signal {row.get('player')} missing {field}")

    pulisic = [r for r in adj_rows if "Pulisic" in snum(r, "player") and str(r.get("included_for_lambda", "")).lower() == "true"]
    if pulisic:
        p = pulisic[0]
        br = float(p.get("base_role_adjustment_pct") or 0)
        if abs(br - (-0.055)) > 0.001:
            errors.append(
                f"Pulisic base_role_adjustment_pct={br} (expected -0.055 = midpoint of -8%..-3% rule range)"
            )
        expl = (
            float(p["base_role_adjustment_pct"])
            * float(p["replacement_multiplier"])
            * float(p["evidence_multiplier"])
            * float(p["minutes_multiplier"])
        )
        if abs(expl - float(p["raw_adjustment_pct"])) > 0.002:
            errors.append(f"Pulisic audit chain mismatch: {expl} vs raw {p['raw_adjustment_pct']}")

    usage = diag.get("realtime_signal_usage", [])
    for u in usage:
        if u.get("included_for_lambda") and u.get("eventflow_usage_mode") != "tactical_path_only":
            errors.append(f"{u.get('player')}: lambda signal must use tactical_path_only")

    dual_candidates = [
        p for p in EVENTFLOW_DB.glob("dual_engine_output*.json")
        if match_id.replace("WC2026-", "") in p.name or match_id in p.name
    ]
    dual_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if dual_candidates:
        payload = json.loads(dual_candidates[0].read_text(encoding="utf-8"))
        pe = payload.get("probability_engine", {})
        if pe.get("probabilities_from") != "adjusted_lambda" and diag.get("probabilities_from") == "adjusted_lambda":
            errors.append("dual_engine JSON probabilities_from not adjusted_lambda")
        fi = payload.get("final_fusion", {}).get("fusion_input", {})
        if diag.get("probabilities_from") == "adjusted_lambda" and fi.get("probability_source") != "adjusted_lambda":
            errors.append("fusion_input.probability_source mismatch")
        if fi.get("fusion_penetration_ok") is False:
            errors.append("fusion_penetration_ok=false in dual_engine output")

    prob_rows = [r for r in read_csv(DEFAULT_PROB_CSV) if snum(r, "match_id") == match_id]
    if prob_rows and diag.get("probabilities_from") == "adjusted_lambda":
        lam_h = float(prob_rows[0].get("lambda_home", 0))
        adj_h = float(diag.get("adjusted_lambda", {}).get("home", lam_h))
        if abs(lam_h - adj_h) > 0.001:
            errors.append(f"probability_engine_scores.csv λ {lam_h} != adjusted {adj_h}")

    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.5 adjusted_lambda penetration validation")
    ap.add_argument("--match-id", default="")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    errors = run_unit_checks()
    if args.match_id:
        errors.extend(validate_match(args.match_id))

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        raise SystemExit(1)
    scope = f"match {args.match_id}" if args.match_id else "unit checks"
    print(f"All V3.5 adjusted_lambda validation passed ({scope}).")


if __name__ == "__main__":
    main()
