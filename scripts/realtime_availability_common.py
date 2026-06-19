#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.5 Realtime Availability Lambda Adjustment — shared rules and calculations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from eventflow_common import clip, fnum, snum

ELIGIBLE_SIGNAL_TYPES = frozenset({
    "injury", "suspension", "lineup_absence", "lineup_start", "return",
})
ELIGIBLE_EVIDENCE = frozenset({"A", "B"})
ELIGIBLE_IMPORTANCE = frozenset({"core", "regular"})
ELIGIBLE_STATUS_ABSENCE = frozenset({"out", "benched"})
ELIGIBLE_STATUS_RETURN = frozenset({"starts", "returns"})

REPLACEMENT_MULTIPLIERS = {
    "high": 0.50,
    "medium": 0.75,
    "low": 1.00,
    "unknown": 0.50,
}
EVIDENCE_MULTIPLIERS = {"A": 1.00, "B": 0.75, "C": 0.00, "D": 0.00}

# (own_attack_lo, own_attack_hi) as negative fractions for absence; positive for return
ATTACK_ABSENCE_RULES: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("striker", "core"): (-0.08, -0.04),
    ("striker", "regular"): (-0.05, -0.02),
    ("wide_attacker", "core"): (-0.08, -0.03),
    ("wide_attacker", "regular"): (-0.04, -0.01),
    ("creator", "core"): (-0.06, -0.02),
    ("creator", "regular"): (-0.04, -0.01),
    ("other", "core"): (-0.02, 0.0),
    ("other", "regular"): (-0.02, 0.0),
    ("other", "rotation"): (0.0, -0.02),
}
ATTACK_RETURN_RULES: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("striker", "core"): (0.02, 0.06),
    ("wide_attacker", "core"): (0.02, 0.06),
    ("creator", "core"): (0.02, 0.05),
    ("striker", "regular"): (0.02, 0.04),
    ("wide_attacker", "regular"): (0.02, 0.04),
    ("creator", "regular"): (0.02, 0.03),
}

# opponent_attack uplift when defender absent (positive fractions)
DEFENSE_ABSENCE_RULES: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("goalkeeper", "core"): (0.05, 0.10),
    ("central_defender", "core"): (0.04, 0.08),
    ("central_defender", "regular"): (0.02, 0.05),
    ("defensive_midfielder", "core"): (0.02, 0.06),
    ("wide_defender", "regular"): (0.01, 0.04),
    ("wide_defender", "core"): (0.02, 0.04),
    ("other", "rotation"): (0.0, 0.02),
}
DEFENSE_RETURN_RULES: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("goalkeeper", "core"): (-0.06, -0.02),
    ("central_defender", "core"): (-0.06, -0.02),
    ("defensive_midfielder", "core"): (-0.04, -0.02),
}

SIGNAL_CAPS = {
    ("attack", "core"): 0.08,
    ("attack", "regular"): 0.05,
    ("attack", "rotation"): 0.02,
    ("defense", "core"): 0.10,
    ("defense", "regular"): 0.05,
    ("defense", "rotation"): 0.02,
}
TEAM_CAPS = {
    "home_attack_down": -0.12,
    "home_attack_up": 0.08,
    "away_attack_down": -0.12,
    "away_attack_up": 0.08,
    "home_opp_attack_up": 0.12,
    "home_opp_attack_down": -0.08,
    "away_opp_attack_up": 0.12,
    "away_opp_attack_down": -0.08,
}
MATCH_TOTAL_CAP = 0.10

ROLE_GROUP_ALIASES = {
    "gk": "goalkeeper",
    "cb": "central_defender",
    "fb": "wide_defender",
    "dm": "defensive_midfielder",
    "cm": "creator",
    "am": "creator",
    "winger": "wide_attacker",
    "st": "striker",
    "wide_attacker": "wide_attacker",
    "central_defender": "central_defender",
    "goalkeeper": "goalkeeper",
    "defensive_midfielder": "defensive_midfielder",
    "wide_defender": "wide_defender",
    "creator": "creator",
    "striker": "striker",
    "other": "other",
}


def normalize_role_group(value: str) -> str:
    key = (value or "").strip().lower()
    return ROLE_GROUP_ALIASES.get(key, "unknown")


def eventflow_usage_mode(eligible: bool, eventflow_only: bool) -> str:
    if eligible:
        return "tactical_path_only"
    if eventflow_only:
        return "eventflow_only_probability_proxy"
    return "excluded"


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _midpoint(lo: float, hi: float) -> float:
    return (lo + hi) / 2.0


def minutes_multiplier(minutes_delta: float) -> float:
    return clip(abs(minutes_delta) / 90.0, 0.25, 1.00)


def check_lambda_eligibility(signal: Mapping[str, Any]) -> Tuple[bool, str, bool]:
    """Return (eligible, exclusion_reason, eventflow_only)."""
    confirmed = _boolish(signal.get("confirmed"))
    grade = snum(signal, "evidence_grade").upper()
    sig_type = snum(signal, "signal_type").lower()
    importance = snum(signal, "importance_tier").lower()
    role_group = normalize_role_group(snum(signal, "role_group"))
    status = snum(signal, "status").lower()
    replacement_q = snum(signal, "replacement_quality").lower()
    source_count = int(float(snum(signal, "source_count") or 0))

    if _boolish(signal.get("eventflow_only")):
        return False, snum(signal, "exclusion_reason") or "eventflow_only_flag", True

    if not confirmed:
        return False, "unconfirmed", True
    if grade in {"C", "D"}:
        return False, "low_confidence_unconfirmed" if grade == "C" else "excluded_grade_d", True
    if not grade:
        return False, "missing_evidence_grade", True
    if sig_type == "rumor" or sig_type not in ELIGIBLE_SIGNAL_TYPES:
        return False, f"ineligible_signal_type:{sig_type or 'missing'}", True
    if importance not in ELIGIBLE_IMPORTANCE:
        if importance == "rotation":
            return False, "rotation_player_not_eligible_for_lambda", True
        return False, f"importance_not_eligible:{importance or 'unknown'}", True
    if role_group == "unknown":
        return False, "missing_role_group", True
    if replacement_q == "unknown" and importance == "unknown":
        return False, "replacement_quality_unknown_no_importance", True
    if source_count == 1 and grade not in {"A"}:
        return False, "single_non_official_source", True
    if sig_type in {"injury", "suspension", "lineup_absence"} and status not in ELIGIBLE_STATUS_ABSENCE:
        return False, f"status_not_absence:{status or 'missing'}", True
    if sig_type in {"lineup_start", "return"} and status not in ELIGIBLE_STATUS_RETURN:
        return False, f"status_not_return:{status or 'missing'}", True
    if grade not in ELIGIBLE_EVIDENCE:
        return False, f"evidence_grade_ineligible:{grade}", True
    return True, "", False


def _base_adjustment_pct(signal: Mapping[str, Any]) -> Tuple[float, str]:
    role_group = normalize_role_group(snum(signal, "role_group"))
    importance = snum(signal, "importance_tier").lower()
    sig_type = snum(signal, "signal_type").lower()
    status = snum(signal, "status").lower()
    is_return = sig_type in {"lineup_start", "return"} or status in ELIGIBLE_STATUS_RETURN

    if role_group in {"goalkeeper", "central_defender", "defensive_midfielder", "wide_defender"}:
        rules = DEFENSE_RETURN_RULES if is_return else DEFENSE_ABSENCE_RULES
        side = "opponent_attack"
    else:
        rules = ATTACK_RETURN_RULES if is_return else ATTACK_ABSENCE_RULES
        side = "own_attack"

    key = (role_group, importance)
    if key not in rules:
        key = (role_group, "rotation") if (role_group, "rotation") in rules else ("other", importance)
    if key not in rules:
        return 0.0, side
    lo, hi = rules[key]
    return _midpoint(lo, hi), side


def compute_signal_adjustment(signal: Mapping[str, Any]) -> Dict[str, Any]:
    eligible, reason, eventflow_only = check_lambda_eligibility(signal)
    row = dict(signal)
    row["eligibility_for_lambda"] = eligible
    row["eventflow_only"] = eventflow_only
    row["exclusion_reason"] = reason if not eligible else ""

    if not eligible:
        row["attack_delta_pct"] = 0.0
        row["opponent_attack_delta_pct"] = 0.0
        row["raw_adjustment_pct"] = 0.0
        row["single_signal_capped_pct"] = 0.0
        row["final_adjustment_pct"] = 0.0
        row["included_for_lambda"] = False
        row["eventflow_usage_mode"] = eventflow_usage_mode(False, eventflow_only)
        row["eventflow_also_uses_signal"] = eventflow_only
        if not row.get("exclusion_reason"):
            row["exclusion_reason"] = reason
        return row

    base_pct, side = _base_adjustment_pct(signal)
    repl_mult = REPLACEMENT_MULTIPLIERS.get(
        snum(signal, "replacement_quality").lower() or "unknown", 0.50
    )
    evid_mult = EVIDENCE_MULTIPLIERS.get(snum(signal, "evidence_grade").upper(), 0.0)
    mins_mult = minutes_multiplier(fnum(signal, "minutes_expected_delta"))

    # Returns: replacement quality is less relevant.
    if snum(signal, "signal_type").lower() in {"lineup_start", "return"}:
        repl_mult = 1.0

    raw = base_pct * repl_mult * evid_mult * mins_mult

    role_group = normalize_role_group(snum(signal, "role_group"))
    importance = snum(signal, "importance_tier").lower()
    is_def = role_group in {"goalkeeper", "central_defender", "defensive_midfielder", "wide_defender"}
    cap_key = ("defense" if is_def else "attack", importance if importance in {"core", "regular", "rotation"} else "regular")
    cap = SIGNAL_CAPS.get(cap_key, 0.05)
    row["raw_adjustment_pct"] = round(raw, 4)
    if raw < 0:
        raw = max(raw, -cap)
    else:
        raw = min(raw, cap)

    row["lambda_side"] = side
    row["base_role_adjustment_pct"] = round(base_pct, 4)
    row["replacement_multiplier"] = repl_mult
    row["evidence_multiplier"] = evid_mult
    row["minutes_multiplier"] = round(mins_mult, 4)
    row["single_signal_capped_pct"] = round(raw, 4)
    row["final_adjustment_pct"] = round(raw, 4)
    row["included_for_lambda"] = True
    row["eventflow_usage_mode"] = "tactical_path_only"
    row["eventflow_also_uses_signal"] = True
    if side == "own_attack":
        row["attack_delta_pct"] = raw
        row["opponent_attack_delta_pct"] = 0.0
    else:
        row["attack_delta_pct"] = 0.0
        row["opponent_attack_delta_pct"] = raw
    return row


@dataclass
class AdjustmentResult:
    base_lambda_home: float
    base_lambda_away: float
    adjusted_lambda_home: float
    adjusted_lambda_away: float
    home_attack_delta_pct: float = 0.0
    away_attack_delta_pct: float = 0.0
    home_team_raw_pct: float = 0.0
    away_team_raw_pct: float = 0.0
    home_team_capped_pct: float = 0.0
    away_team_capped_pct: float = 0.0
    match_total_lambda_change_pct: float = 0.0
    match_cap_applied: bool = False
    included: List[Dict[str, Any]] = field(default_factory=list)
    excluded: List[Dict[str, Any]] = field(default_factory=list)
    signals_used: int = 0

    def to_availability_block(self) -> Dict[str, Any]:
        return {
            "enabled": self.signals_used > 0,
            "signals_used": self.signals_used,
            "signals_excluded": len(self.excluded),
            "home_attack_delta_pct": round(self.home_attack_delta_pct, 4),
            "away_attack_delta_pct": round(self.away_attack_delta_pct, 4),
            "home_defense_delta_pct": 0.0,
            "away_defense_delta_pct": 0.0,
            "home_team_raw_pct": round(self.home_team_raw_pct, 4),
            "away_team_raw_pct": round(self.away_team_raw_pct, 4),
            "home_team_capped_pct": round(self.home_team_capped_pct, 4),
            "away_team_capped_pct": round(self.away_team_capped_pct, 4),
            "match_total_lambda_change_pct": round(self.match_total_lambda_change_pct, 4),
            "match_cap_applied": self.match_cap_applied,
            "excluded_signals": len(self.excluded),
            "adjustment_audit_file": "database/eventflow/processed/realtime_availability_adjustments.csv",
            "included_signals": [s.get("player", "") for s in self.included],
            "excluded_availability_signals": [
                {
                    "player": s.get("player", ""),
                    "signal_type": s.get("signal_type", ""),
                    "reason": s.get("exclusion_reason", ""),
                    "exclusion_reason": s.get("exclusion_reason", ""),
                    "eventflow_only": s.get("eventflow_only", False),
                    "eventflow_usage_mode": s.get("eventflow_usage_mode", ""),
                }
                for s in self.excluded
            ],
        }


def _team_side(team: str, home: str, away: str) -> Optional[str]:
    t = (team or "").strip()
    if t == home:
        return "home"
    if t == away:
        return "away"
    return None


def apply_team_caps(
    home_own: float,
    home_opp: float,
    away_own: float,
    away_opp: float,
) -> Tuple[float, float, float, float]:
    home_own = clip(home_own, TEAM_CAPS["home_attack_down"], TEAM_CAPS["home_attack_up"])
    away_own = clip(away_own, TEAM_CAPS["away_attack_down"], TEAM_CAPS["away_attack_up"])
    home_opp = clip(home_opp, TEAM_CAPS["home_opp_attack_down"], TEAM_CAPS["home_opp_attack_up"])
    away_opp = clip(away_opp, TEAM_CAPS["away_opp_attack_down"], TEAM_CAPS["away_opp_attack_up"])
    return home_own, home_opp, away_own, away_opp


def apply_match_cap(
    base_home: float,
    base_away: float,
    home_delta: float,
    away_delta: float,
) -> Tuple[float, float]:
    adj_h = base_home * (1 + home_delta)
    adj_a = base_away * (1 + away_delta)
    total_base = base_home + base_away
    total_adj = adj_h + adj_a
    if total_base <= 0:
        return adj_h, adj_a
    rel_change = abs(total_adj - total_base) / total_base
    if rel_change <= MATCH_TOTAL_CAP:
        return adj_h, adj_a
    scale = MATCH_TOTAL_CAP / rel_change
    return (
        base_home * (1 + home_delta * scale),
        base_away * (1 + away_delta * scale),
    )


def apply_realtime_lambda_adjustments(
    base_lambda_home: float,
    base_lambda_away: float,
    home: str,
    away: str,
    signals: List[Mapping[str, Any]],
) -> AdjustmentResult:
    home_own = home_opp = away_own = away_opp = 0.0
    home_own_raw = home_opp_raw = away_own_raw = away_opp_raw = 0.0
    included: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for sig in signals:
        computed = compute_signal_adjustment(sig)
        if computed.get("eligibility_for_lambda"):
            side = _team_side(snum(sig, "team"), home, away)
            if not side:
                computed["eligibility_for_lambda"] = False
                computed["exclusion_reason"] = "team_not_in_match"
                computed["eventflow_only"] = True
                excluded.append(computed)
                continue
            delta = float(computed.get("final_adjustment_pct") or 0.0)
            own = float(computed.get("attack_delta_pct") or 0.0)
            opp = float(computed.get("opponent_attack_delta_pct") or 0.0)
            if side == "home":
                home_own += own
                home_own_raw += own
                if opp:
                    away_own += opp
                    away_opp_raw += opp
            else:
                away_own += own
                away_own_raw += own
                if opp:
                    home_own += opp
                    home_opp_raw += opp
            included.append(computed)
        else:
            excluded.append(computed)

    home_own, home_opp, away_own, away_opp = apply_team_caps(home_own, home_opp, away_own, away_opp)
    home_net = home_own + home_opp
    away_net = away_own + away_opp
    home_raw = home_own_raw + home_opp_raw
    away_raw = away_own_raw + away_opp_raw
    adj_h, adj_a = apply_match_cap(base_lambda_home, base_lambda_away, home_net, away_net)
    total_base = base_lambda_home + base_lambda_away
    total_adj = adj_h + adj_a
    match_chg = (total_adj - total_base) / total_base if total_base > 0 else 0.0
    uncapped_h = base_lambda_home * (1 + home_net)
    uncapped_a = base_lambda_away * (1 + away_net)
    match_cap_applied = abs((uncapped_h + uncapped_a) - total_base) / total_base > MATCH_TOTAL_CAP + 1e-9 if total_base > 0 else False

    for inc in included:
        inc["team_total_raw_pct"] = round(home_raw if _team_side(snum(inc, "team"), home, away) == "home" else away_raw, 4)
        inc["team_total_capped_pct"] = round(home_net if _team_side(snum(inc, "team"), home, away) == "home" else away_net, 4)
        inc["match_total_lambda_change_pct"] = round(match_chg, 4)
        side = _team_side(snum(inc, "team"), home, away)
        if side == "home":
            inc["base_lambda_before"] = round(base_lambda_home, 4)
            inc["adjusted_lambda_after"] = round(adj_h, 4)
        else:
            inc["base_lambda_before"] = round(base_lambda_away, 4)
            inc["adjusted_lambda_after"] = round(adj_a, 4)

    return AdjustmentResult(
        base_lambda_home=base_lambda_home,
        base_lambda_away=base_lambda_away,
        adjusted_lambda_home=round(adj_h, 4),
        adjusted_lambda_away=round(adj_a, 4),
        home_attack_delta_pct=round(home_net, 4),
        away_attack_delta_pct=round(away_net, 4),
        home_team_raw_pct=round(home_raw, 4),
        away_team_raw_pct=round(away_raw, 4),
        home_team_capped_pct=round(home_net, 4),
        away_team_capped_pct=round(away_net, 4),
        match_total_lambda_change_pct=round(match_chg, 4),
        match_cap_applied=match_cap_applied,
        included=included,
        excluded=excluded,
        signals_used=len(included),
    )
