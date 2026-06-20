#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.6 Scenario Realization Layer — shared rules, data quality, BTTS gate, tail calibration."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from eventflow_common import (
    EVENTFLOW_DB,
    ROOT,
    TEAM_DB,
    clip,
    fnum,
    normalize_team,
    read_csv,
    snum,
)

DIAG_PATH = ROOT / "database" / "eventflow" / "raw" / "v2_engine_diagnostics.json"
RAW_SIGNALS = ROOT / "database" / "eventflow" / "realtime_availability_signals.csv"
ODDS_SUMMARY = ROOT / "database" / "jc-odds" / "processed" / "match_odds_summary.csv"

REALIZATION_FEATURES_CSV = EVENTFLOW_DB / "scenario_realization_features.csv"
BTTS_AUDIT_CSV = EVENTFLOW_DB / "btts_conversion_audit.csv"
TAIL_AUDIT_CSV = EVENTFLOW_DB / "total_goals_tail_audit.csv"
FAMILY_ADJ_CSV = EVENTFLOW_DB / "v36_scoreline_family_adjustments.csv"

V36_DIAGNOSTICS_KEYS = (
    "probabilities_from",
    "scenario_realization",
    "btts_conversion_gate",
    "total_goals_tail_calibration",
    "v36_realization_layer",
    "realized_probability",
    "scoreline_probability_grid",
    "post_btts_gate_snapshot",
    "scoreline_probability_grid_pre_tail",
    "v35_baseline_probability",
    "v35_baseline_scoreline_grid",
)

CALIBRATION_CAPS = {
    "none": {"btts": 0.0, "family": 0.0},
    "weak": {"btts": 0.03, "family": 0.05},
    "medium": {"btts": 0.06, "family": 0.10},
    "strong": {"btts": 0.10, "family": 0.15},
}

PACE_ROLES = frozenset({"wide_attacker", "striker"})
CREATOR_ROLES = frozenset({"creator", "wide_attacker"})
TARGET_ROLES = frozenset({"striker", "wide_attacker"})


def favorite_side(lam_home: float, lam_away: float) -> str:
    if lam_home >= lam_away:
        return "home"
    return "away"


def parse_score(score: str) -> Tuple[int, int]:
    h, a = score.split("-")
    return int(h), int(a)


def classify_scoreline_family(score: str, fav: str) -> str:
    h, a = parse_score(score)
    total = h + a
    if fav == "home":
        fav_g, dog_g = h, a
    else:
        fav_g, dog_g = a, h
    if h == a:
        return "draw_low" if total <= 2 else "chaos_high"
    if fav_g > dog_g:
        if dog_g == 0:
            if fav_g <= 2:
                return "favorite_clean_win_low"
            if fav_g == 3:
                return "favorite_clean_win_mid"
            return "favorite_big_win"
        if total >= 5:
            return "chaos_high"
        if fav_g >= 4:
            return "favorite_big_win"
        return "favorite_btts_win"
    if dog_g == 1 and fav_g <= 1:
        return "underdog_low_win"
    if total >= 4:
        return "chaos_high"
    return "underdog_low_win"


def scores_in_family(family: str, fav: str, max_goals: int = 6) -> List[str]:
    out: List[str] = []
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            s = f"{i}-{j}"
            if classify_scoreline_family(s, fav) == family:
                out.append(s)
    return out


@dataclass
class DataQualityResult:
    xg_available: bool
    shot_quality_available: bool
    chance_quality_available: bool
    lineup_function_available: bool
    lineup_default_only: bool
    game_state_model_available: bool
    team_style_baseline_available: bool
    market_total_goals_available: bool
    data_quality_score: float
    calibration_strength: str
    source_reliability: float
    diagnostics_only: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xg_available": self.xg_available,
            "shot_quality_available": self.shot_quality_available,
            "chance_quality_available": self.chance_quality_available,
            "lineup_function_available": self.lineup_function_available,
            "lineup_default_only": self.lineup_default_only,
            "game_state_model_available": self.game_state_model_available,
            "team_style_baseline_available": self.team_style_baseline_available,
            "market_total_goals_available": self.market_total_goals_available,
            "data_quality_score": round(self.data_quality_score, 4),
            "calibration_strength": self.calibration_strength,
            "source_reliability": round(self.source_reliability, 4),
            "diagnostics_only": self.diagnostics_only,
            "warnings": self.warnings,
        }


def calibration_strength_from_score(score: float) -> str:
    if score < 0.35:
        return "none"
    if score < 0.55:
        return "weak"
    if score < 0.75:
        return "medium"
    return "strong"


def _team_profile(team: str) -> Dict[str, str]:
    rows = read_csv(TEAM_DB / "team_tactical_profile.csv")
    team_n = normalize_team(team)
    for r in rows:
        if normalize_team(snum(r, "team")) == team_n:
            return r
    return {}


def _team_state_profile(team: str) -> Dict[str, str]:
    rows = read_csv(TEAM_DB / "team_match_state_response.csv")
    team_n = normalize_team(team)
    for r in rows:
        if normalize_team(snum(r, "team")) == team_n:
            return r
    return {}


def derive_team_style_baseline(team: str) -> Dict[str, Any]:
    prof = _team_profile(team)
    if not prof:
        return {
            "team_scoring_style": "medium",
            "chance_conversion_style": "average",
            "game_management_style": "balanced",
            "low_score_win_tendency": 0.5,
            "btts_allowed_tendency": 0.5,
            "late_throttle_tendency": 0.5,
        }
    chaos = fnum(prof, "chaos_index")
    low_block = fnum(prof, "low_block_quality")
    late_agg = fnum(prof, "late_game_aggression")
    pressing = snum(prof, "pressing_height")

    if chaos < 0.15 and low_block > 0:
        scoring = "low_output"
    elif chaos > 0.35:
        scoring = "high_output"
    else:
        scoring = "medium"

    if late_agg < 0.1 and pressing in {"低位/被动", "low"}:
        mgmt = "conservative"
    elif late_agg > 0.3 or pressing in {"高位压迫", "high"}:
        mgmt = "aggressive"
    else:
        mgmt = "balanced"

    low_score_win = clip(0.5 + low_block * 0.3 - chaos * 0.2, 0.0, 1.0)
    btts_allowed = clip(0.5 + chaos * 0.4 - low_block * 0.2, 0.0, 1.0)
    late_throttle = clip(0.5 + (0.2 if mgmt == "conservative" else -0.1), 0.0, 1.0)

    return {
        "team_scoring_style": scoring,
        "chance_conversion_style": "clinical" if chaos > 0.3 else "average",
        "game_management_style": mgmt,
        "low_score_win_tendency": round(low_score_win, 4),
        "btts_allowed_tendency": round(btts_allowed, 4),
        "late_throttle_tendency": round(late_throttle, 4),
    }


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _confirmed_lineup_signals(match_id: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for s in read_csv(RAW_SIGNALS):
        if snum(s, "match_id") != match_id:
            continue
        if not _boolish(s.get("confirmed")):
            continue
        if snum(s, "signal_type").lower() not in {
            "injury", "suspension", "lineup_absence", "lineup_start", "return",
        }:
            continue
        out.append(s)
    return out


def _has_chance_quality_evidence(match_id: str, diag: Mapping[str, Any]) -> bool:
    if bool(diag.get("chance_quality_data_available")):
        return True
    for r in read_csv(EVENTFLOW_DB / "eventflow_fused_evidence.csv"):
        if snum(r, "match_id") != match_id:
            continue
        blob = " ".join(
            snum(r, k).lower()
            for k in ("signal_type", "canonical_signal", "evidence_summary", "claim_text")
        )
        if any(tok in blob for tok in ("box_xg", "big_chance", "shots_on_target", "open_play_box")):
            return True
    return False


def extract_lineup_function_features(
    match_id: str,
    home: str,
    away: str,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    signals = _confirmed_lineup_signals(match_id)
    has_confirmed = len(signals) > 0
    out: Dict[str, Dict[str, Any]] = {}

    for team in (home, away):
        team_sigs = [s for s in signals if snum(s, "team") == team]
        has_team_signals = len(team_sigs) > 0
        pace_start = any(
            snum(s, "role_group") in PACE_ROLES and snum(s, "status") == "starts"
            for s in team_sigs
        )
        pace_bench = any(
            snum(s, "role_group") in PACE_ROLES
            and snum(s, "status") in {"benched", "out"}
            and snum(s, "importance_tier") in {"core", "regular"}
            for s in team_sigs
        )
        target_start = any(
            snum(s, "role_group") in TARGET_ROLES and snum(s, "status") == "starts"
            for s in team_sigs
        ) if has_team_signals else False
        creator_start = any(
            snum(s, "role_group") in CREATOR_ROLES and snum(s, "status") == "starts"
            for s in team_sigs
        ) if has_team_signals else False

        prof = _team_profile(team)
        transition = fnum(prof, "transition_attack")
        wide = fnum(prof, "attack_width")
        counter_q = 0.35
        if has_team_signals:
            counter_q = clip(
                0.35 + transition * 0.4 + (0.15 if pace_start else 0.0) - (0.30 if pace_bench else 0.0),
                0.0, 1.0,
            )

        out[team] = {
            "has_real_lineup_signals": has_team_signals,
            "pace_outlet_starting": pace_start if has_team_signals else False,
            "pace_outlet_benched": pace_bench,
            "central_target_starting": target_start,
            "creator_starting": creator_start,
            "set_piece_height_advantage": fnum(prof, "set_piece_attack") > 0.1,
            "wide_overload_available": wide > 0.1 or transition > 0.1,
            "counterattack_exit_quality": counter_q,
            "press_resistance_quality": clip(0.5 + fnum(prof, "rest_defense_quality") * 0.3, 0.0, 1.0),
        }
    meta = {
        "has_confirmed_lineup_signals": has_confirmed,
        "default_only": not has_confirmed,
    }
    return out, meta


def compute_data_quality(
    match_id: str,
    home: str,
    away: str,
    diag: Mapping[str, Any],
    source_fusion: Optional[Mapping[str, Any]] = None,
) -> DataQualityResult:
    warnings: List[str] = []
    xg_src = snum(diag, "xg_source")
    xg_avail = bool(xg_src) and "default" not in xg_src.lower() and bool(xg_src.strip())

    chance_quality = _has_chance_quality_evidence(match_id, diag)
    shot_quality = chance_quality
    if not shot_quality:
        warnings.append("shot_quality_unavailable_no_box_xg_split")

    lineup_map, lineup_meta = extract_lineup_function_features(match_id, home, away)
    lineup_fn = lineup_meta.get("has_confirmed_lineup_signals", False)
    lineup_default = lineup_meta.get("default_only", True)
    if lineup_default:
        warnings.append("lineup_function_default_only")

    state_home = _team_state_profile(home)
    state_away = _team_state_profile(away)
    game_state = (
        bool(state_home) and bool(state_away)
        and fnum(state_home, "data_confidence") >= 0.7
        and fnum(state_away, "data_confidence") >= 0.7
    )

    style_home = _team_profile(home)
    style_away = _team_profile(away)
    team_style = (
        bool(style_home) and bool(style_away)
        and fnum(style_home, "data_confidence") >= 0.7
        and fnum(style_away, "data_confidence") >= 0.7
        and not _boolish(style_home.get("is_estimated"))
        and not _boolish(style_away.get("is_estimated"))
    )

    market_avail = False
    if ODDS_SUMMARY.exists():
        for r in read_csv(ODDS_SUMMARY):
            if snum(r, "matchNumStr") == match_id or (
                snum(r, "homeTeamAbbName") == home and snum(r, "awayTeamAbbName") == away
            ):
                market_avail = int(float(snum(r, "ttg_count") or 0)) > 0
                break

    sf = source_fusion or {}
    prematch = int(sf.get("pre_match_evidence_count", 0) or 0)
    grade_ab = int(sf.get("grade_A_count", 0) or 0) + int(sf.get("grade_B_count", 0) or 0)
    source_rel = clip(0.3 + 0.1 * min(prematch, 5) + 0.1 * min(grade_ab, 4), 0.0, 1.0)

    xg_score = 0.7 if xg_avail else 0.2
    chance_score = 1.0 if chance_quality else 0.15
    lineup_score = 1.0 if lineup_fn else 0.1
    style_score = 1.0 if team_style else 0.25
    state_score = 1.0 if game_state else 0.2
    market_score = 0.5 if market_avail else 0.0

    dq = (
        0.20 * xg_score
        + 0.25 * chance_score
        + 0.20 * lineup_score
        + 0.15 * style_score
        + 0.10 * state_score
        + 0.05 * market_score
        + 0.05 * source_rel
    )
    if not chance_quality:
        dq = min(dq, 0.55)
        warnings.append("data_quality_capped_without_chance_quality")
    if lineup_default:
        dq = min(dq, 0.50)
    if not xg_avail:
        dq = min(dq, 0.45)

    strength = calibration_strength_from_score(dq)
    if not chance_quality and strength == "strong":
        strength = "medium"
        dq = min(dq, 0.74)
    diagnostics_only = strength == "none"
    if diagnostics_only:
        warnings.append("data_quality_below_threshold_no_calibration")

    return DataQualityResult(
        xg_available=xg_avail,
        shot_quality_available=shot_quality,
        chance_quality_available=chance_quality,
        lineup_function_available=lineup_fn,
        lineup_default_only=lineup_default,
        game_state_model_available=game_state,
        team_style_baseline_available=team_style,
        market_total_goals_available=market_avail,
        data_quality_score=dq,
        calibration_strength=strength,
        source_reliability=source_rel,
        diagnostics_only=diagnostics_only,
        warnings=warnings,
    )


@dataclass
class RealizationFeatures:
    match_id: str
    home: str
    away: str
    favorite_side: str
    scenario_rows: List[Dict[str, Any]]
    favorite_leads_early_likelihood: float
    underdog_leads_early_likelihood: float
    favorite_kill_game_likelihood: float
    favorite_game_management_likelihood: float
    underdog_btts_conversion_likelihood: float
    low_block_survival_likelihood: float
    chance_quality_score: float
    shot_volume_quality_gap: float
    lead_throttle_score: float
    scoreline_family_boost: List[str]
    scoreline_family_penalty: List[str]
    team_style_home: Dict[str, Any]
    team_style_away: Dict[str, Any]
    lineup_function: Dict[str, Dict[str, Any]]
    data_quality: DataQualityResult
    conditional_branches: List[Dict[str, Any]] = field(default_factory=list)

    def primary_rows_for_csv(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for s in self.scenario_rows[:8]:
            rows.append({
                "match_id": self.match_id,
                "home": self.home,
                "away": self.away,
                "scenario_id": snum(s, "scenario_id"),
                "scenario_weight": fnum(s, "normalized_weight"),
                "favorite_leads_early_likelihood": round(self.favorite_leads_early_likelihood, 4),
                "underdog_leads_early_likelihood": round(self.underdog_leads_early_likelihood, 4),
                "favorite_kill_game_likelihood": round(self.favorite_kill_game_likelihood, 4),
                "favorite_game_management_likelihood": round(self.favorite_game_management_likelihood, 4),
                "underdog_btts_conversion_likelihood": round(self.underdog_btts_conversion_likelihood, 4),
                "low_block_survival_likelihood": round(self.low_block_survival_likelihood, 4),
                "chance_quality_score": round(self.chance_quality_score, 4),
                "shot_volume_quality_gap": round(self.shot_volume_quality_gap, 4),
                "lead_throttle_score": round(self.lead_throttle_score, 4),
                "scoreline_family_boost": ";".join(self.scoreline_family_boost),
                "scoreline_family_penalty": ";".join(self.scoreline_family_penalty),
                "data_quality_score": round(self.data_quality.data_quality_score, 4),
                "calibration_strength": self.data_quality.calibration_strength,
            })
        return rows


def _scenario_weight_sum(rows: Sequence[Mapping[str, Any]], prefix: str) -> float:
    total = 0.0
    for r in rows:
        sid = snum(r, "scenario_id")
        if sid.startswith(prefix):
            total += fnum(r, "normalized_weight")
    return total


def compute_realization_features(
    match_id: str,
    home: str,
    away: str,
    lam_home: float,
    lam_away: float,
    scenario_rows: Sequence[Mapping[str, Any]],
    diag: Mapping[str, Any],
    source_fusion: Optional[Mapping[str, Any]] = None,
) -> RealizationFeatures:
    fav = favorite_side(lam_home, lam_away)
    fav_team = home if fav == "home" else away
    dog_team = away if fav == "home" else home

    dq = compute_data_quality(match_id, home, away, diag, source_fusion)
    style_home = derive_team_style_baseline(home)
    style_away = derive_team_style_baseline(away)
    lineup, _lineup_meta = extract_lineup_function_features(match_id, home, away)

    fav_style = style_home if fav == "home" else style_away
    dog_style = style_away if fav == "home" else style_home
    dog_lineup = lineup.get(dog_team, {})
    fav_lineup = lineup.get(fav_team, {})

    s01 = _scenario_weight_sum(scenario_rows, "S01")
    s02 = _scenario_weight_sum(scenario_rows, "S02")
    s04 = _scenario_weight_sum(scenario_rows, "S04")
    s05 = _scenario_weight_sum(scenario_rows, "S05")
    s_open = sum(
        fnum(r, "normalized_weight")
        for r in scenario_rows
        if "open" in snum(r, "scenario_id").lower()
        or "press" in snum(r, "scenario_id").lower()
    )

    fav_early = clip(s01 + s04 * 0.5, 0.0, 1.0)
    dog_early = clip(s02 * 0.6, 0.0, 0.8)

    kill_game = clip(
        fav_early * 0.5 + (1.0 - fav_style["low_score_win_tendency"]) * 0.3,
        0.0, 1.0,
    )
    game_mgmt = clip(
        fav_style["late_throttle_tendency"] * 0.4
        + fav_style["low_score_win_tendency"] * 0.4
        + (0.2 if fav_style["game_management_style"] == "conservative" else 0.0),
        0.0, 1.0,
    )

    dog_conversion = clip(
        dog_lineup.get("counterattack_exit_quality", 0.5) * 0.35
        + (0.2 if dog_lineup.get("pace_outlet_starting") else 0.0)
        + dog_style["btts_allowed_tendency"] * 0.25
        + s_open * 0.2,
        0.0, 1.0,
    )

    low_block = clip(
        s02 + dog_style["low_score_win_tendency"] * 0.3,
        0.0, 1.0,
    )

    fav_prof = _team_profile(fav_team)
    shot_vol = clip(abs(fnum(fav_prof, "defend_pressure_score")) / 2.0, 0.0, 1.0)
    if dq.chance_quality_available:
        chance_q = clip(
            0.5
            + fnum(fav_prof, "break_low_block_score") * 0.3
            - fnum(fav_prof, "chaos_index") * 0.1
            + (0.15 if dog_lineup.get("central_target_starting") else -0.1),
            0.0, 1.0,
        )
    else:
        chance_q = clip(
            0.30 + dog_lineup.get("counterattack_exit_quality", 0.35) * 0.2,
            0.0, 0.42,
        )
    vol_quality_gap = clip(shot_vol - chance_q, 0.0, 1.0)

    lead_throttle = clip(game_mgmt * max(fav_early, 0.25), 0.0, 1.0)

    boost: List[str] = []
    penalty: List[str] = []
    if game_mgmt > 0.38 and dog_conversion < 0.60:
        boost.extend(["favorite_clean_win_low", "favorite_clean_win_mid"])
        penalty.extend(["favorite_btts_win", "favorite_big_win"])
    elif lead_throttle > 0.35 and dog_conversion < 0.55:
        boost.append("favorite_clean_win_low")
        penalty.append("favorite_btts_win")
    if low_block > 0.35:
        boost.extend(["draw_low", "underdog_low_win"])
        penalty.extend(["chaos_high"])
    if vol_quality_gap > 0.35:
        boost.append("favorite_clean_win_low")
        penalty.append("favorite_btts_win")
    if fav_style["team_scoring_style"] == "low_output" and fav_style["game_management_style"] == "conservative":
        boost.append("favorite_clean_win_low")
        penalty.append("favorite_btts_win")

    boost = list(dict.fromkeys(boost))
    penalty = list(dict.fromkeys(penalty))

    branches: List[Dict[str, Any]] = []
    underdog_early_plausible = dog_early > 0.20 or low_block > 0.25 or s05 > 0.06 or s02 > 0.08
    if underdog_early_plausible:
        branches.append({
            "branch_id": "underdog_early_goal",
            "status": "conditional_prematch",
            "trigger": "若弱势方先入球",
            "effect": "激活 low_block_survival；上调 0-1/1-1，下调大球与强队多进球",
            "active": False,
        })

    return RealizationFeatures(
        match_id=match_id,
        home=home,
        away=away,
        favorite_side=fav,
        scenario_rows=list(scenario_rows),
        favorite_leads_early_likelihood=fav_early,
        underdog_leads_early_likelihood=dog_early,
        favorite_kill_game_likelihood=kill_game,
        favorite_game_management_likelihood=game_mgmt,
        underdog_btts_conversion_likelihood=dog_conversion,
        low_block_survival_likelihood=low_block,
        chance_quality_score=chance_q,
        shot_volume_quality_gap=vol_quality_gap,
        lead_throttle_score=lead_throttle,
        scoreline_family_boost=boost,
        scoreline_family_penalty=penalty,
        team_style_home=style_home,
        team_style_away=style_away,
        lineup_function=lineup,
        data_quality=dq,
        conditional_branches=branches,
    )


@dataclass
class BttsGateResult:
    enabled: bool
    threat_presence: bool
    conversion_supported: bool
    conversion_supported_by_quality: bool
    adjustment_direction: str
    adjustment_strength: str
    calibration_strength: str
    btts_factor_delta_pct: float
    btts_delta_pct: float
    up_signals_count: int
    down_signals_count: int
    up_reasons: List[str]
    down_reasons: List[str]
    reasons: List[str]
    diagnostics_only: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "threat_presence": self.threat_presence,
            "conversion_supported": self.conversion_supported,
            "conversion_supported_by_quality": self.conversion_supported_by_quality,
            "adjustment_direction": self.adjustment_direction,
            "adjustment_strength": self.adjustment_strength,
            "calibration_strength": self.calibration_strength,
            "btts_factor_delta_pct": round(self.btts_factor_delta_pct, 4),
            "btts_delta_pct": round(self.btts_delta_pct, 4),
            "up_signals_count": self.up_signals_count,
            "down_signals_count": self.down_signals_count,
            "up_reasons": self.up_reasons,
            "down_reasons": self.down_reasons,
            "reasons": self.reasons,
            "diagnostics_only": self.diagnostics_only,
        }


def evaluate_btts_gate(
    features: RealizationFeatures,
    scenario_rows: Sequence[Mapping[str, Any]],
    lam_home: float,
    lam_away: float,
) -> BttsGateResult:
    fav = features.favorite_side
    dog_team = features.away if fav == "home" else features.home
    dog_lineup = features.lineup_function.get(dog_team, {})
    dog_style = features.team_style_away if fav == "home" else features.team_style_home
    dq = features.data_quality
    chance_ok = dq.chance_quality_available

    s_open = sum(
        fnum(r, "normalized_weight")
        for r in scenario_rows
        if any(k in snum(r, "scenario_id") for k in ("S03", "S04", "S07", "S09", "open"))
    )
    threat = s_open > 0.12 or features.underdog_leads_early_likelihood > 0.2

    up_reasons: List[str] = []
    down_reasons: List[str] = []

    if (
        chance_ok
        and dog_lineup.get("counterattack_exit_quality", 0) > 0.60
        and dog_lineup.get("has_real_lineup_signals")
    ):
        up_reasons.append("counterattack_exit_quality_high")
    if chance_ok and dog_lineup.get("pace_outlet_starting") and dog_lineup.get("has_real_lineup_signals"):
        up_reasons.append("pace_outlet_starting_confirmed")
    if chance_ok and dog_lineup.get("central_target_starting") and dog_lineup.get("has_real_lineup_signals"):
        up_reasons.append("central_target_starting_confirmed")
    if chance_ok and features.chance_quality_score > 0.58:
        up_reasons.append("chance_quality_score_high")

    if not chance_ok:
        down_reasons.append("chance_quality_unavailable")
    if features.shot_volume_quality_gap > 0.25:
        down_reasons.append("chance_quality_low")
    if dog_lineup.get("pace_outlet_benched"):
        down_reasons.append("underdog_speed_outlet_benched")
    if features.favorite_game_management_likelihood > 0.40:
        down_reasons.append("favorite_lead_management_likely")
    if dog_style.get("team_scoring_style") == "low_output":
        down_reasons.append("underdog_low_output_style")
    if features.chance_quality_score < 0.48 or not chance_ok:
        down_reasons.append("underdog_threat_present_but_conversion_low")
    if dog_lineup.get("counterattack_exit_quality", 0.5) < 0.45:
        down_reasons.append("counterattack_exit_quality_low")
    if dog_lineup.get("pace_outlet_benched") and features.favorite_game_management_likelihood > 0.40:
        down_reasons.append("first_half_counterattack_exit_reduced")

    up_signals = len(up_reasons)
    down_signals = len(down_reasons)
    conversion_by_quality = chance_ok and up_signals >= 2 and not dog_lineup.get("pace_outlet_benched")

    cal_strength = dq.calibration_strength
    cap = CALIBRATION_CAPS[cal_strength]["btts"]
    diagnostics_only = dq.diagnostics_only

    if diagnostics_only:
        return BttsGateResult(
            enabled=True,
            threat_presence=threat,
            conversion_supported=False,
            conversion_supported_by_quality=False,
            adjustment_direction="none",
            adjustment_strength="none",
            calibration_strength=cal_strength,
            btts_factor_delta_pct=0.0,
            btts_delta_pct=0.0,
            up_signals_count=up_signals,
            down_signals_count=down_signals,
            up_reasons=up_reasons,
            down_reasons=down_reasons,
            reasons=dq.warnings,
            diagnostics_only=True,
        )

    direction = "none"
    delta = 0.0
    adj_strength = "none"
    reasons: List[str] = []

    forbid_up = (
        not chance_ok
        or (
            dog_lineup.get("pace_outlet_benched")
            and features.favorite_game_management_likelihood > 0.40
        )
        or features.underdog_btts_conversion_likelihood < 0.60
        or down_signals > 1
    )

    can_up = (
        threat
        and conversion_by_quality
        and features.underdog_btts_conversion_likelihood >= 0.60
        and down_signals <= 1
        and not forbid_up
    )

    if can_up:
        direction = "up"
        raw = min(0.03 + 0.015 * (up_signals - 2), cap)
        delta = max(raw, 0.0)
        adj_strength = "weak" if delta <= 0.03 else cal_strength
        reasons = up_reasons[:4]
    elif down_signals >= 2 and (threat or features.favorite_game_management_likelihood > 0.38):
        direction = "down"
        raw = -min(0.025 + 0.012 * (down_signals - 2), cap)
        delta = raw
        adj_strength = "weak" if abs(raw) <= 0.03 else cal_strength
        reasons = down_reasons[:5]
    elif down_signals >= 3:
        direction = "down"
        raw = -min(0.02 + 0.01 * (down_signals - 3), cap)
        delta = raw
        adj_strength = "weak"
        reasons = down_reasons[:5]
    elif threat and not chance_ok:
        direction = "none"
        reasons = ["threat_present_but_chance_quality_unavailable_no_up"]
    elif forbid_up and threat:
        direction = "down" if down_signals >= 1 else "none"
        if direction == "down":
            delta = -min(0.02, cap)
            adj_strength = "weak"
            reasons = down_reasons[:4]

    return BttsGateResult(
        enabled=True,
        threat_presence=threat,
        conversion_supported=can_up,
        conversion_supported_by_quality=conversion_by_quality,
        adjustment_direction=direction,
        adjustment_strength=adj_strength,
        calibration_strength=cal_strength,
        btts_factor_delta_pct=delta,
        btts_delta_pct=delta,
        up_signals_count=up_signals,
        down_signals_count=down_signals,
        up_reasons=up_reasons,
        down_reasons=down_reasons,
        reasons=reasons,
        diagnostics_only=False,
    )


@dataclass
class TailCalibrationResult:
    enabled: bool
    four_plus_tail_delta: float
    family_deltas: Dict[str, float]
    boosted_families: List[str]
    penalized_families: List[str]
    reasons: List[str]
    diagnostics_only: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "four_plus_tail_delta": round(self.four_plus_tail_delta, 4),
            "family_deltas": {k: round(v, 4) for k, v in self.family_deltas.items()},
            "boosted_families": self.boosted_families,
            "penalized_families": self.penalized_families,
            "reasons": self.reasons,
            "diagnostics_only": self.diagnostics_only,
        }


def evaluate_tail_calibration(features: RealizationFeatures) -> TailCalibrationResult:
    strength = features.data_quality.calibration_strength
    cap = CALIBRATION_CAPS[strength]["family"]
    diagnostics_only = features.data_quality.diagnostics_only

    if diagnostics_only:
        return TailCalibrationResult(
            enabled=True,
            four_plus_tail_delta=0.0,
            family_deltas={},
            boosted_families=[],
            penalized_families=[],
            reasons=features.data_quality.warnings,
            diagnostics_only=True,
        )

    deltas: Dict[str, float] = {}
    reasons: List[str] = []
    weak_cap = min(cap, CALIBRATION_CAPS["weak"]["family"])
    boosted = list(features.scoreline_family_boost)
    penalized = list(features.scoreline_family_penalty)

    for fam in boosted:
        deltas[fam] = deltas.get(fam, 0.0) + min(0.06, cap)
    for fam in penalized:
        deltas[fam] = deltas.get(fam, 0.0) - min(0.06, cap)

    if not deltas and (
        features.favorite_game_management_likelihood > 0.38
        and features.underdog_btts_conversion_likelihood < 0.58
    ):
        deltas["favorite_clean_win_low"] = weak_cap * 0.6
        deltas["favorite_btts_win"] = -weak_cap * 0.6
        boosted = ["favorite_clean_win_low"]
        penalized = ["favorite_btts_win"]
        if not features.data_quality.chance_quality_available:
            reasons.append("insufficient_chance_quality_data_weak_tail_only")
        else:
            reasons.append("lead_management_throttle_weak")

    if features.lead_throttle_score > 0.35:
        reasons.append("lead_management_throttle")
    if features.low_block_survival_likelihood > 0.35:
        reasons.append("low_block_survival_branch")
    if features.shot_volume_quality_gap > 0.35:
        reasons.append("shot_volume_quality_split")

    four_plus = sum(v for k, v in deltas.items() if k in {"favorite_big_win", "chaos_high"})
    return TailCalibrationResult(
        enabled=True,
        four_plus_tail_delta=four_plus,
        family_deltas=deltas,
        boosted_families=boosted,
        penalized_families=penalized,
        reasons=reasons,
        diagnostics_only=False,
    )


def grid_from_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grid: List[Dict[str, Any]] = []
    for r in rows:
        h = int(float(snum(r, "home_goals") or 0))
        a = int(float(snum(r, "away_goals") or 0))
        grid.append({
            "home_goals": h,
            "away_goals": a,
            "score": snum(r, "score") or f"{h}-{a}",
            "probability": fnum(r, "probability"),
        })
    return grid


def normalize_grid(grid: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = sum(g["probability"] for g in grid)
    if total <= 0:
        return grid
    for g in grid:
        g["probability"] = g["probability"] / total
    return grid


def compute_btts(grid: Sequence[Mapping[str, Any]]) -> float:
    return sum(
        g["probability"] if isinstance(g["probability"], float) else fnum(g, "probability")
        for g in grid
        if int(g.get("home_goals", g.get("home", 0))) >= 1
        and int(g.get("away_goals", g.get("away", 0))) >= 1
    )


def apply_btts_delta_to_grid(
    grid: List[Dict[str, Any]],
    delta_pct: float,
) -> List[Dict[str, Any]]:
    if abs(delta_pct) < 1e-9:
        return [dict(g) for g in grid]
    out = [dict(g) for g in grid]
    btts_idx = [
        i for i, g in enumerate(out)
        if g["home_goals"] >= 1 and g["away_goals"] >= 1
    ]
    non_idx = [i for i in range(len(out)) if i not in btts_idx]
    if not btts_idx:
        return out

    factor = 1.0 + delta_pct
    for i in btts_idx:
        out[i]["probability"] *= factor
    btts_mass = sum(out[i]["probability"] for i in btts_idx)
    non_mass = sum(out[i]["probability"] for i in non_idx)
    target_non = max(1.0 - btts_mass, 0.01)
    if non_mass > 0:
        scale = target_non / non_mass
        for i in non_idx:
            out[i]["probability"] *= scale
    return normalize_grid(out)


def apply_family_deltas_to_grid(
    grid: List[Dict[str, Any]],
    family_deltas: Mapping[str, float],
    fav: str,
) -> List[Dict[str, Any]]:
    if not family_deltas:
        return [dict(g) for g in grid]
    out = [dict(g) for g in grid]
    for g in out:
        fam = classify_scoreline_family(g["score"], fav)
        delta = family_deltas.get(fam, 0.0)
        if delta:
            g["probability"] *= max(0.05, 1.0 + delta)
    return normalize_grid(out)


def compute_v36_fusion_weights(
    data_quality_score: float,
    mode: str = "balanced",
) -> Tuple[float, float, float, float]:
    base = {"safe": (0.45, 0.30, 0.20, 0.05), "balanced": (0.45, 0.30, 0.20, 0.05),
            "hit_hunting": (0.45, 0.30, 0.20, 0.05)}
    w_prob, w_ef, w_real, w_mkt = base.get(mode, base["balanced"])
    if data_quality_score < 0.35:
        w_real = 0.05
        w_prob = 0.55
        w_ef = 0.30
        w_mkt = 0.10
    elif data_quality_score < 0.55:
        w_real = 0.12
        w_prob = 0.48
    total = w_prob + w_ef + w_real + w_mkt
    return w_prob / total, w_ef / total, w_real / total, w_mkt / total


def load_diagnostics(match_id: str) -> Dict[str, Any]:
    if not DIAG_PATH.exists():
        return {}
    with DIAG_PATH.open(encoding="utf-8") as f:
        all_diag = json.load(f)
    return all_diag.get(match_id, {})


def load_all_diagnostics() -> Dict[str, Any]:
    if not DIAG_PATH.exists():
        return {}
    with DIAG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_all_diagnostics(all_diag: Dict[str, Any]) -> None:
    DIAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DIAG_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_diag, f, ensure_ascii=False, indent=2)


def update_diagnostics_block(match_id: str, block: Dict[str, Any]) -> None:
    all_diag = load_all_diagnostics()
    entry = all_diag.get(match_id, {})
    entry.update(block)
    all_diag[match_id] = entry
    save_all_diagnostics(all_diag)


def sync_v36_diagnostics(match_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Write authoritative V3.6 fields from merge JSON / probability_engine block."""
    row = load_all_diagnostics().get(match_id, {})
    row.update({
        "match_id": match_id,
        "probabilities_from": payload.get("probabilities_from", "v36_realized"),
        "scenario_realization": payload.get("scenario_realization", {}),
        "btts_conversion_gate": payload.get("btts_conversion_gate", {}),
        "total_goals_tail_calibration": payload.get("total_goals_tail_calibration", {}),
        "v36_realization_layer": payload.get("v36_realization_layer", {}),
        "realized_probability": payload.get("realized_probability", {}),
        "scoreline_probability_grid": payload.get("scoreline_probability_grid", []),
    })
    if payload.get("v35_baseline_probability"):
        row["v35_baseline_probability"] = payload["v35_baseline_probability"]
    if payload.get("v35_baseline_scoreline_grid"):
        row["v35_baseline_scoreline_grid"] = payload["v35_baseline_scoreline_grid"]
    update_diagnostics_block(match_id, row)
    return row


def sync_v36_diagnostics_from_merge_json(json_path: Path) -> str:
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)
    match_id = data.get("match_id", "")
    if not match_id:
        raise ValueError(f"match_id missing in {json_path}")
    pe = data.get("probability_engine", {})
    sync_v36_diagnostics(match_id, pe)
    return match_id


def clear_v36_diagnostics_keys(diag: Dict[str, Any]) -> Dict[str, Any]:
    for k in V36_DIAGNOSTICS_KEYS:
        diag.pop(k, None)
    return diag


def market_snapshot_from_grid(grid: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    p_h = p_d = p_a = 0.0
    over25 = over35 = 0.0
    for g in grid:
        p = fnum(g, "probability")
        h = int(g.get("home_goals", 0))
        a = int(g.get("away_goals", 0))
        if h > a:
            p_h += p
        elif h < a:
            p_a += p
        else:
            p_d += p
        t = h + a
        if t >= 3:
            over25 += p
        if t >= 4:
            over35 += p
    sorted_g = sorted(grid, key=lambda x: -fnum(x, "probability"))
    return {
        "home_win": round(p_h, 4),
        "draw": round(p_d, 4),
        "away_win": round(p_a, 4),
        "over25": round(over25, 4),
        "over35": round(over35, 4),
        "btts": round(compute_btts(grid), 4),
        "top_scores": [snum(g, "score") for g in sorted_g[:5]],
        "scoreline_probability_grid": [
            {
                "home_goals": int(g.get("home_goals", 0)),
                "away_goals": int(g.get("away_goals", 0)),
                "score": snum(g, "score"),
                "probability": round(fnum(g, "probability"), 6),
            }
            for g in sorted_g
        ],
    }
