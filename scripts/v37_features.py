#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7 feature computation: GPI, ACG, EGCI, LBKG, odds value."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from eventflow_common import read_csv
from v37_common import (
    V37_THRESHOLDS,
    V37_WEIGHTS,
    bnum,
    clip,
    compute_data_quality_score,
    data_quality_grade,
    fnum,
    identify_favorite,
    load_team_model_index,
    load_tactical_index,
    load_tier_index,
    low_block_score,
    snum,
    tactical_scalar,
)


def pressure_type_from_gpi(
    gpi: float,
    draw_utility: float,
    path_state: str,
    round_num: int = 0,
) -> str:
    if path_state in ("opening_round", "baseline_opening"):
        return "prefer_win" if gpi >= 0.40 else "low_pressure"
    if round_num == 1:
        return "prefer_win" if gpi >= 0.45 else "low_pressure"
    if "must_win" in path_state:
        return "must_win"
    if gpi >= 0.65:
        return "must_win"
    if gpi >= 0.45:
        return "prefer_win"
    if draw_utility >= 0.55:
        return "draw_ok"
    if "protect" in path_state or "gd" in path_state:
        return "protect_gd"
    if path_state in ("clinched_top2", "near_clinched"):
        return "rotation_possible"
    if gpi < 0.30:
        return "low_pressure"
    return "prefer_win"


def compute_group_pressure(
    match_id: str,
    team: str,
    opponent: str,
    standing_row: Mapping[str, Any],
    path_state: str = "",
) -> dict[str, Any]:
    w = V37_WEIGHTS["group_pressure"]
    win_necessity = fnum(standing_row, "win_necessity", 0.35)
    draw_utility = fnum(standing_row, "draw_utility", 0.3)
    p_advance = fnum(standing_row, "p_advance", -1.0)
    loss_damage = (
        clip(1.0 - p_advance, 0.0, 1.0)
        if p_advance >= 0
        else clip(0.0 if bnum(standing_row, "can_qualify_if_draw", True) else 0.65, 0.0, 1.0)
    )
    if bnum(standing_row, "elimination_risk_if_loss"):
        loss_damage = clip(loss_damage + 0.25, 0.0, 1.0)

    rank = int(fnum(standing_row, "rank_before", 4))
    first_place_incentive = clip(
        fnum(standing_row, "p_finish_1", 0.55 if rank == 1 else 0.35 if rank == 2 else 0.15),
        0.0, 1.0,
    )
    second_place_safety = clip(fnum(standing_row, "p_top2", 1.0 if rank <= 2 else 0.4), 0.0, 1.0)
    third_place_safety = clip(fnum(standing_row, "p_best8_third", 0.7 if rank == 3 else 0.3), 0.0, 1.0)
    opponent_path_risk = 0.45

    gpi = clip(
        w["win_necessity"] * win_necessity
        + w["loss_damage"] * loss_damage
        + w["first_place_incentive"] * first_place_incentive
        - abs(w["draw_utility_negative"]) * draw_utility,
        0.0, 1.0,
    )
    ptype = pressure_type_from_gpi(
        gpi, draw_utility, path_state or snum(standing_row, "path_state"),
        round_num=int(fnum(standing_row, "round_before", 0)),
    )

    return {
        "match_id": match_id,
        "team": team,
        "opponent": opponent,
        "points_before": int(fnum(standing_row, "points_before")),
        "gd_before": int(fnum(standing_row, "gd_before")),
        "rank_before": rank,
        "win_necessity": round(win_necessity, 4),
        "draw_utility": round(draw_utility, 4),
        "loss_damage": round(loss_damage, 4),
        "first_place_incentive": round(first_place_incentive, 4),
        "second_place_safety": round(second_place_safety, 4),
        "third_place_safety": round(third_place_safety, 4),
        "opponent_path_risk": round(opponent_path_risk, 4),
        "group_pressure_index": round(gpi, 4),
        "pressure_type": ptype,
        "state_reason_code": snum(standing_row, "state_reason_code"),
        "p_finish_1": round(fnum(standing_row, "p_finish_1"), 4),
        "p_finish_2": round(fnum(standing_row, "p_finish_2"), 4),
        "p_finish_3": round(fnum(standing_row, "p_finish_3"), 4),
        "p_finish_4": round(fnum(standing_row, "p_finish_4"), 4),
        "p_top2": round(fnum(standing_row, "p_top2"), 4),
        "p_best8_third": round(fnum(standing_row, "p_best8_third"), 4),
        "p_advance": round(fnum(standing_row, "p_advance"), 4),
    }


def compute_attack_conversion(
    match_id: str,
    team: str,
    opponent: str,
    team_recent: Mapping[str, Any],
    tactical: Mapping[str, dict],
    lineups: Sequence[Mapping[str, str]],
    gpi: float,
    win_necessity: float = 0.0,
) -> dict[str, Any]:
    w = V37_WEIGHTS["attack_conversion_gate"]
    tact = tactical.get(team, {})
    opp_tact = tactical.get(opponent, {})

    xg = fnum(team_recent, "xg_for_avg", 1.0)
    shots = fnum(team_recent, "shots_avg", 12.0)
    sot = fnum(team_recent, "sot_avg", shots * 0.35)
    bc = fnum(team_recent, "big_chances_avg", 1.5)
    xg_per_shot = clip(xg / max(shots, 1.0), 0.0, 0.5) * 2.0
    sot_rate = clip(sot / max(shots, 1.0), 0.0, 1.0)
    bc_rate = clip(bc / 90.0 * 10.0, 0.0, 1.0)
    chance_quality = clip(
        xg_per_shot if fnum(team_recent, "matches_played") > 0 else
        0.55 * sot_rate + 0.30 * bc_rate + 0.15 * tactical_scalar(tact, "set_piece_attack", 0.5),
        0.0, 1.0,
    )

    break_low_block = tactical_scalar(tact, "break_low_block_score", 0.5)
    central_target = _central_target_presence(team, lineups)
    wide_cross = clip(0.5 + fnum(tact, "attack_width", 0.0) * 0.3, 0.0, 1.0)
    set_piece = tactical_scalar(tact, "set_piece_attack", 0.5)
    opp_low_block = low_block_score(opponent, tactical)
    keeper_proxy = _keeper_proxy(opponent, team_recent, opp_tact)
    finishing = clip(fnum(team_recent, "goals_for_avg") / max(xg, 0.5), 0.0, 1.2) / 1.2

    acg = clip(
        w["chance_quality"] * chance_quality
        + w["break_low_block"] * break_low_block
        + w["central_target"] * central_target
        + w["set_piece_threat"] * set_piece
        + w["finishing_stability"] * finishing
        + w["wide_cross_low_block_penalty"] * wide_cross * opp_low_block
        + w["keeper_proxy_penalty"] * keeper_proxy,
        0.0, 1.0,
    )

    pressure_signal = max(gpi, win_necessity)
    must_win_no_convert = (
        pressure_signal >= V37_THRESHOLDS["must_win_pressure"]
        and acg <= V37_THRESHOLDS["low_conversion_gate"]
        and opp_low_block >= V37_THRESHOLDS["opponent_low_block"]
    )

    return {
        "match_id": match_id,
        "team": team,
        "opponent": opponent,
        "break_low_block_score": round(break_low_block, 4),
        "chance_quality_score": round(chance_quality, 4),
        "xg_per_shot": round(xg_per_shot, 4),
        "shot_on_target_rate": round(sot_rate, 4),
        "big_chances_per_90": round(bc, 4),
        "set_piece_threat": round(set_piece, 4),
        "central_target_presence": round(central_target, 4),
        "wide_cross_dependency": round(wide_cross, 4),
        "opponent_low_block_score": round(opp_low_block, 4),
        "opponent_keeper_proxy": round(keeper_proxy, 4),
        "attack_conversion_gate": round(acg, 4),
        "must_win_no_convert_flag": str(must_win_no_convert).lower(),
    }


def _central_target_presence(team: str, lineups: Sequence[Mapping[str, str]]) -> float:
    starters = [
        r for r in lineups
        if r.get("team") == team and snum(r, "lineup_status") in ("confirmed", "predicted")
        and snum(r, "is_starter") == "true"
    ]
    if not starters:
        return 0.45
    targets = sum(1 for r in starters if snum(r, "role_group") in ("ST", "striker"))
    return clip(0.35 + 0.2 * targets, 0.0, 1.0)


def _keeper_proxy(opponent: str, team_recent: Mapping[str, Any], opp_tact: Mapping[str, str]) -> float:
    ga = fnum(team_recent, "xg_against_avg", 1.0)
    solid = tactical_scalar(opp_tact, "set_piece_defense", 0.5)
    return clip(0.4 + (1.0 - min(ga / 2.0, 1.0)) * 0.35 + solid * 0.25, 0.0, 1.0)


def compute_early_goal_cascade(
    match_id: str,
    home: str,
    away: str,
    gpi_home: float,
    gpi_away: float,
    tactical: Mapping[str, dict],
    models: Mapping[str, dict],
    tiers: Mapping[str, dict],
) -> dict[str, Any]:
    w = V37_WEIGHTS["early_goal_cascade"]
    favorite = identify_favorite(home, away, tiers, models)
    underdog = away if favorite == home else home

    fav_tact = tactical.get(favorite, {})
    dog_tact = tactical.get(underdog, {})
    fav_model = models.get(favorite, {})

    early_goal_profile = clip(
        0.35 + tactical_scalar(fav_tact, "transition_attack", 0.5) * 0.25
        + fnum(fav_model, "pressing_intensity", 0.5) * 0.25,
        0.0, 1.0,
    )
    pressing_start = clip(fnum(fav_model, "pressing_intensity", 0.55), 0.0, 1.0)
    underdog_fragility = clip(
        tactical_scalar(dog_tact, "collapse_risk", 0.5)
        + (1.0 - tactical_scalar(dog_tact, "rest_defense_quality", 0.5)) * 0.3,
        0.0, 1.0,
    )
    chase_pressure = clip(gpi_away if favorite == home else gpi_home, 0.0, 1.0)
    transition_mismatch = clip(
        tactical_scalar(fav_tact, "transition_attack", 0.5)
        - tactical_scalar(dog_tact, "rest_defense_quality", 0.5) + 0.5,
        0.0, 1.0,
    )
    bench_depth = clip(fnum(fav_model, "squad_depth_ratio", 0.8), 0.0, 1.0)
    game_management = clip(
        0.5 + fnum(fav_tact, "late_game_aggression", 0.0) * -0.2
        + (0.15 if "conservative" in snum(fav_tact, "pressing_height") else 0.0),
        0.0, 1.0,
    )

    egci = clip(
        w["early_goal_profile"] * early_goal_profile
        + w["pressing_start"] * pressing_start
        + w["underdog_fragility"] * underdog_fragility
        + w["chase_pressure"] * chase_pressure
        + w["transition_mismatch"] * transition_mismatch
        + w["bench_depth"] * bench_depth
        + w["game_management_penalty"] * game_management,
        0.0, 1.0,
    )
    cascade_active = egci >= V37_THRESHOLDS["cascade_tail_active"]

    return {
        "match_id": match_id,
        "favorite": favorite,
        "underdog": underdog,
        "favorite_early_goal_profile": round(early_goal_profile, 4),
        "pressing_start_intensity": round(pressing_start, 4),
        "underdog_fragility_score": round(underdog_fragility, 4),
        "underdog_chase_pressure": round(chase_pressure, 4),
        "transition_mismatch_score": round(transition_mismatch, 4),
        "bench_attacking_depth": round(bench_depth, 4),
        "game_management_tendency": round(game_management, 4),
        "early_goal_cascade_index": round(egci, 4),
        "cascade_tail_active": str(cascade_active).lower(),
    }


def compute_low_block_keeper_guard(
    match_id: str,
    home: str,
    away: str,
    acg_home: float,
    acg_away: float,
    draw_util_home: float,
    draw_util_away: float,
    tactical: Mapping[str, dict],
    tiers: Mapping[str, dict],
    models: Mapping[str, dict],
    odds_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    w = V37_WEIGHTS["low_block_keeper_guard"]
    favorite = identify_favorite(home, away, tiers, models)
    underdog = away if favorite == home else home
    fav_acg = acg_home if favorite == home else acg_away
    dog_draw = draw_util_away if favorite == home else draw_util_home

    handicap = _favorite_handicap(match_id, favorite, home, odds_rows)
    deep_handicap = abs(handicap) >= V37_THRESHOLDS["deep_handicap_line"]
    underdog_lb = low_block_score(underdog, tactical)
    keeper_proxy = _keeper_proxy(underdog, {}, tactical.get(underdog, {}))
    cross_dep = tactical_scalar(
        tactical.get(favorite, {}), "attack_width", 0.5
    )

    cold_score = clip(
        w["underdog_low_block"] * underdog_lb
        + w["keeper_proxy"] * keeper_proxy
        + w["favorite_low_shot_quality"] * (1.0 - fav_acg)
        + w["cross_dependency"] * cross_dep
        + w["deep_handicap"] * (1.0 if deep_handicap else 0.0)
        + w["underdog_draw_utility"] * dog_draw,
        0.0, 1.0,
    )
    deep_contra = deep_handicap and cold_score >= 0.58
    cold_active = cold_score >= V37_THRESHOLDS["cold_guard_active"]

    return {
        "match_id": match_id,
        "favorite": favorite,
        "underdog": underdog,
        "deep_handicap_flag": str(deep_handicap).lower(),
        "underdog_low_block_score": round(underdog_lb, 4),
        "keeper_save_proxy": round(keeper_proxy, 4),
        "sot_faced_proxy": "",
        "favorite_shot_quality": round(fav_acg, 4),
        "favorite_cross_dependency": round(cross_dep, 4),
        "cold_draw_guard_score": round(cold_score, 4),
        "deep_handicap_contra_flag": str(deep_contra).lower(),
        "cold_guard_active": str(cold_active).lower(),
    }


def _favorite_handicap(
    match_id: str, favorite: str, home: str, odds_rows: Sequence[Mapping[str, str]]
) -> float:
    for r in odds_rows:
        if snum(r, "match_id") != match_id or snum(r, "market") != "hhad":
            continue
        if snum(r, "selection") != "home":
            continue
        try:
            line = float(snum(r, "handicap") or "0")
        except ValueError:
            return 0.0
        return line if favorite == home else -line
    return 0.0


def compute_universal_features(
    match: Mapping[str, str],
    team_recent_home: Mapping[str, Any],
    team_recent_away: Mapping[str, Any],
    tiers: Mapping[str, dict],
    models: Mapping[str, dict],
    flags: Mapping[str, bool],
) -> dict[str, Any]:
    home, away = match["home_team"], match["away_team"]
    h_str = team_strength(home, tiers, models)
    a_str = team_strength(away, tiers, models)
    dq = compute_data_quality_score(flags)
    return {
        "match_id": match["match_id"],
        "home_team": home,
        "away_team": away,
        "group": match["group"],
        "round": match["round"],
        "home_strength_rating": round(h_str, 4),
        "away_strength_rating": round(a_str, 4),
        "strength_gap": round(h_str - a_str, 4),
        "home_recent_xg_for": round(fnum(team_recent_home, "xg_for_avg"), 3),
        "home_recent_xg_against": round(fnum(team_recent_home, "xg_against_avg"), 3),
        "away_recent_xg_for": round(fnum(team_recent_away, "xg_for_avg"), 3),
        "away_recent_xg_against": round(fnum(team_recent_away, "xg_against_avg"), 3),
        "home_form_points": round(fnum(team_recent_home, "form_points"), 2),
        "away_form_points": round(fnum(team_recent_away, "form_points"), 2),
        "home_rest_days": "",
        "away_rest_days": "",
        "venue_temperature": "",
        "venue_humidity": "",
        "data_quality_score": dq,
        "data_quality_grade": data_quality_grade(dq),
    }


def team_strength(team: str, tiers: Mapping[str, dict], models: Mapping[str, dict]) -> float:
    from v37_common import team_strength_rating
    return team_strength_rating(team, tiers, models)


def compute_odds_value_features(
    match_id: str,
    odds_rows: Sequence[Mapping[str, str]],
    model_probs: Optional[Mapping[str, float]] = None,
    data_quality_low: bool = False,
) -> list[dict[str, Any]]:
    model_probs = model_probs or {}
    out: list[dict[str, Any]] = []
    for r in odds_rows:
        if snum(r, "match_id") != match_id:
            continue
        sp_s = snum(r, "sp")
        if not sp_s:
            continue
        try:
            sp = float(sp_s)
            implied = 1.0 / sp if sp > 1.0 else 0.0
        except ValueError:
            continue
        sel = f"{snum(r, 'market')}:{snum(r, 'selection')}"
        model_p = model_probs.get(sel)
        edge = (model_p - implied) if model_p is not None else ""
        pool = snum(r, "pool_status")
        gate = (
            pool == "open"
            and sp > 1.0
            and model_p is not None
            and not data_quality_low
        )
        out.append({
            "match_id": match_id,
            "market": snum(r, "market"),
            "selection": snum(r, "selection"),
            "sp": sp,
            "model_probability": model_p if model_p is not None else "",
            "implied_probability": round(implied, 4),
            "edge_proxy": round(edge, 4) if edge != "" else "",
            "risk_level": "medium",
            "market_consistency_flag": "true",
            "recommendation_gate": str(gate).lower(),
        })
    return out


def merge_realization_row(
    match: Mapping[str, str],
    gpi_h: dict, gpi_a: dict,
    acg_h: dict, acg_a: dict,
    egci: dict, lbkg: dict,
    universal: dict,
) -> dict[str, Any]:
    active_flags: list[str] = []
    if snum(acg_h, "must_win_no_convert_flag") == "true":
        active_flags.append("must_win_no_convert_home")
    if snum(acg_a, "must_win_no_convert_flag") == "true":
        active_flags.append("must_win_no_convert_away")
    if snum(egci, "cascade_tail_active") == "true":
        active_flags.append("cascade_tail_active")
    if snum(lbkg, "cold_guard_active") == "true":
        active_flags.append("cold_guard_active")
    if snum(lbkg, "deep_handicap_contra_flag") == "true":
        active_flags.append("deep_handicap_contra")

    return {
        "match_id": match["match_id"],
        "home_team": match["home_team"],
        "away_team": match["away_team"],
        "group_pressure_home": gpi_h["group_pressure_index"],
        "group_pressure_away": gpi_a["group_pressure_index"],
        "pressure_type_home": gpi_h["pressure_type"],
        "pressure_type_away": gpi_a["pressure_type"],
        "state_reason_code_home": gpi_h.get("state_reason_code", ""),
        "state_reason_code_away": gpi_a.get("state_reason_code", ""),
        "draw_utility_home": gpi_h["draw_utility"],
        "draw_utility_away": gpi_a["draw_utility"],
        "attack_conversion_home": acg_h["attack_conversion_gate"],
        "attack_conversion_away": acg_a["attack_conversion_gate"],
        "must_win_no_convert_home": snum(acg_h, "must_win_no_convert_flag"),
        "must_win_no_convert_away": snum(acg_a, "must_win_no_convert_flag"),
        "early_goal_cascade_index": egci["early_goal_cascade_index"],
        "cascade_tail_active": snum(egci, "cascade_tail_active"),
        "favorite": egci["favorite"],
        "underdog": egci["underdog"],
        "cold_draw_guard_score": lbkg["cold_draw_guard_score"],
        "cold_guard_active": snum(lbkg, "cold_guard_active"),
        "deep_handicap_contra_flag": snum(lbkg, "deep_handicap_contra_flag"),
        "data_quality_score": universal["data_quality_score"],
        "data_quality_grade": universal["data_quality_grade"],
        "active_flags": ";".join(active_flags),
    }
