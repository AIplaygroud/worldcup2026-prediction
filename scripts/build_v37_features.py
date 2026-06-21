#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build V3.7 feature tables (GPI / ACG / EGCI / LBKG / odds / merged realization)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from eventflow_common import read_csv, write_csv
from v37_common import (
    FEATURE_TABLES,
    NORMALIZED_TABLES,
    V37_AUDIT,
    ensure_v37_dirs,
    kickoff_from_mapping,
    load_mapping,
    load_team_model_index,
    load_tactical_index,
    load_tier_index,
    path_detail_for_team,
    runtime_incentive_for,
    snum,
    standings_at_cutoff,
)
from v37_features import (
    compute_attack_conversion,
    compute_early_goal_cascade,
    compute_group_pressure,
    compute_low_block_keeper_guard,
    compute_odds_value_features,
    compute_universal_features,
    merge_realization_row,
)

GPI_FIELDS = [
    "match_id", "team", "opponent", "points_before", "gd_before", "rank_before",
    "win_necessity", "draw_utility", "loss_damage", "first_place_incentive",
    "second_place_safety", "third_place_safety", "opponent_path_risk",
    "group_pressure_index", "pressure_type",
    "state_reason_code",
    "p_finish_1", "p_finish_2", "p_finish_3", "p_finish_4",
    "p_top2", "p_best8_third", "p_advance",
]

ACG_FIELDS = [
    "match_id", "team", "opponent", "break_low_block_score", "chance_quality_score",
    "xg_per_shot", "shot_on_target_rate", "big_chances_per_90", "set_piece_threat",
    "central_target_presence", "wide_cross_dependency", "opponent_low_block_score",
    "opponent_keeper_proxy", "attack_conversion_gate", "must_win_no_convert_flag",
]

EGCI_FIELDS = [
    "match_id", "favorite", "underdog", "favorite_early_goal_profile",
    "pressing_start_intensity", "underdog_fragility_score", "underdog_chase_pressure",
    "transition_mismatch_score", "bench_attacking_depth", "game_management_tendency",
    "early_goal_cascade_index", "cascade_tail_active",
]

LBKG_FIELDS = [
    "match_id", "favorite", "underdog", "deep_handicap_flag", "underdog_low_block_score",
    "keeper_save_proxy", "sot_faced_proxy", "favorite_shot_quality",
    "favorite_cross_dependency", "cold_draw_guard_score", "deep_handicap_contra_flag",
    "cold_guard_active",
]

UNIVERSAL_FIELDS = [
    "match_id", "home_team", "away_team", "group", "round",
    "home_strength_rating", "away_strength_rating", "strength_gap",
    "home_recent_xg_for", "home_recent_xg_against", "away_recent_xg_for",
    "away_recent_xg_against", "home_form_points", "away_form_points",
    "home_rest_days", "away_rest_days", "venue_temperature", "venue_humidity",
    "data_quality_score", "data_quality_grade",
]

REALIZATION_FIELDS = [
    "match_id", "home_team", "away_team",
    "group_pressure_home", "group_pressure_away", "pressure_type_home", "pressure_type_away",
    "state_reason_code_home", "state_reason_code_away",
    "runtime_incentive_used",
    "home_route_preference_label", "away_route_preference_label",
    "home_first_place_utility", "away_first_place_utility",
    "home_second_place_utility", "away_second_place_utility",
    "home_draw_acceptance_modifier", "away_draw_acceptance_modifier",
    "home_late_push_modifier", "away_late_push_modifier",
    "home_rotation_modifier", "away_rotation_modifier",
    "draw_utility_home", "draw_utility_away",
    "attack_conversion_home", "attack_conversion_away",
    "must_win_no_convert_home", "must_win_no_convert_away",
    "early_goal_cascade_index", "cascade_tail_active", "favorite", "underdog",
    "cold_draw_guard_score", "cold_guard_active", "deep_handicap_contra_flag",
    "data_quality_score", "data_quality_grade", "active_flags",
]

ODDS_VALUE_FIELDS = [
    "match_id", "market", "selection", "sp", "model_probability", "implied_probability",
    "edge_proxy", "risk_level", "market_consistency_flag", "recommendation_gate",
]


def _index_by(rows: list[dict], *keys: str) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for r in rows:
        k = tuple(snum(r, key) for key in keys)
        out[k] = r
    return out


def _path_state(team: str, group: str, kickoff_utc: str, round_num: int = 0) -> str:
    from datetime import datetime, timezone
    from group_state_common import pre_kickoff_cutoff

    kickoff = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    cutoff = pre_kickoff_cutoff(kickoff)
    standings = standings_at_cutoff(cutoff)
    detail = path_detail_for_team(team, group, standings, cutoff, round_num=round_num)
    return snum(detail, "path_state")


def build_features(match_filter: str = "") -> dict[str, int]:
    ensure_v37_dirs()
    matches = read_csv(NORMALIZED_TABLES["matches"])
    if match_filter:
        matches = [m for m in matches if m["match_id"] == match_filter]
    if not matches:
        raise SystemExit("No matches in normalized table; run build_v37_normalized_tables.py first")

    standings = read_csv(NORMALIZED_TABLES["standings_snapshot"])
    team_recent = read_csv(NORMALIZED_TABLES["team_recent_stats"])
    lineups = read_csv(NORMALIZED_TABLES["lineups"])
    odds = read_csv(NORMALIZED_TABLES["odds_snapshots"])

    stand_idx = _index_by(standings, "match_id", "team")
    recent_idx = _index_by(team_recent, "match_id", "team")
    lineups_by_mid: dict[str, list[dict]] = {}
    for lu in lineups:
        lineups_by_mid.setdefault(lu["match_id"], []).append(lu)

    tiers = load_tier_index()
    models = load_team_model_index()
    tactical = load_tactical_index()

    gpi_rows: list[dict] = []
    acg_rows: list[dict] = []
    egci_rows: list[dict] = []
    lbkg_rows: list[dict] = []
    universal_rows: list[dict] = []
    realization_rows: list[dict] = []
    odds_value_rows: list[dict] = []

    for m in matches:
        mid = m["match_id"]
        home, away = m["home_team"], m["away_team"]
        st_h = stand_idx.get((mid, home), {})
        st_a = stand_idx.get((mid, away), {})
        rec_h = recent_idx.get((mid, home), {})
        rec_a = recent_idx.get((mid, away), {})
        lu = lineups_by_mid.get(mid, [])
        match_odds = [r for r in odds if r["match_id"] == mid]

        has_lineup = len(lu) > 0
        flags = {
            "has_standing": bool(st_h and st_a),
            "has_recent_xg_or_proxy": int(rec_h.get("matches_played", 0) or 0) > 0,
            "has_lineup": has_lineup,
            "has_match_stats": bool(rec_h and rec_a),
            "has_odds": len(match_odds) > 0,
            "has_tactical_profile": home in tactical and away in tactical,
            "has_source_fusion": False,
        }

        gpi_h = compute_group_pressure(
            mid, home, away, st_h, _path_state(home, m["group"], m["kickoff_utc"], int(m["round"]))
        )
        gpi_a = compute_group_pressure(
            mid, away, home, st_a, _path_state(away, m["group"], m["kickoff_utc"], int(m["round"]))
        )
        gpi_rows.extend([gpi_h, gpi_a])

        acg_h = compute_attack_conversion(
            mid, home, away, rec_h, tactical, lu,
            gpi_h["group_pressure_index"], gpi_h["win_necessity"],
        )
        acg_a = compute_attack_conversion(
            mid, away, home, rec_a, tactical, lu,
            gpi_a["group_pressure_index"], gpi_a["win_necessity"],
        )
        acg_rows.extend([acg_h, acg_a])

        egci = compute_early_goal_cascade(
            mid, home, away,
            gpi_h["group_pressure_index"], gpi_a["group_pressure_index"],
            tactical, models, tiers,
        )
        egci_rows.append(egci)

        lbkg = compute_low_block_keeper_guard(
            mid, home, away,
            acg_h["attack_conversion_gate"], acg_a["attack_conversion_gate"],
            gpi_h["draw_utility"], gpi_a["draw_utility"],
            tactical, tiers, models, match_odds,
        )
        lbkg_rows.append(lbkg)

        univ = compute_universal_features(m, rec_h, rec_a, tiers, models, flags)
        universal_rows.append(univ)

        realization = merge_realization_row(m, gpi_h, gpi_a, acg_h, acg_a, egci, lbkg, univ)
        runtime = runtime_incentive_for(mid)
        realization.update({
            "runtime_incentive_used": str(bool(runtime)).lower(),
            "home_route_preference_label": snum(runtime, "home_route_preference_label"),
            "away_route_preference_label": snum(runtime, "away_route_preference_label"),
            "home_first_place_utility": snum(runtime, "home_first_place_utility"),
            "away_first_place_utility": snum(runtime, "away_first_place_utility"),
            "home_second_place_utility": snum(runtime, "home_second_place_utility"),
            "away_second_place_utility": snum(runtime, "away_second_place_utility"),
            "home_draw_acceptance_modifier": snum(runtime, "home_draw_acceptance_modifier"),
            "away_draw_acceptance_modifier": snum(runtime, "away_draw_acceptance_modifier"),
            "home_late_push_modifier": snum(runtime, "home_late_push_modifier"),
            "away_late_push_modifier": snum(runtime, "away_late_push_modifier"),
            "home_rotation_modifier": snum(runtime, "home_rotation_modifier"),
            "away_rotation_modifier": snum(runtime, "away_rotation_modifier"),
        })
        realization_rows.append(realization)

        dq_low = univ["data_quality_grade"] in ("low", "degraded")
        odds_value_rows.extend(
            compute_odds_value_features(mid, match_odds, data_quality_low=dq_low)
        )

    write_csv(FEATURE_TABLES["universal"], universal_rows, UNIVERSAL_FIELDS)
    write_csv(FEATURE_TABLES["group_pressure"], gpi_rows, GPI_FIELDS)
    write_csv(FEATURE_TABLES["attack_conversion"], acg_rows, ACG_FIELDS)
    write_csv(FEATURE_TABLES["early_goal_cascade"], egci_rows, EGCI_FIELDS)
    write_csv(FEATURE_TABLES["low_block_keeper"], lbkg_rows, LBKG_FIELDS)
    write_csv(FEATURE_TABLES["odds_value"], odds_value_rows, ODDS_VALUE_FIELDS)
    write_csv(FEATURE_TABLES["realization"], realization_rows, REALIZATION_FIELDS)

    counts = {
        "matches": len(matches),
        "gpi": len(gpi_rows),
        "acg": len(acg_rows),
        "egci": len(egci_rows),
        "lbkg": len(lbkg_rows),
        "realization": len(realization_rows),
    }
    (V37_AUDIT / "feature_build_log.json").write_text(
        json.dumps({"built_at": datetime.now(timezone.utc).isoformat(), **counts}, indent=2),
        encoding="utf-8",
    )
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 feature tables")
    ap.add_argument("--match-id", default="", help="Single match e.g. WC2026-E34")
    args = ap.parse_args()
    counts = build_features(args.match_id)
    print(
        f"V3.7 features: {counts['matches']} matches, "
        f"GPI={counts['gpi']}, ACG={counts['acg']}, EGCI={counts['egci']}, LBKG={counts['lbkg']}"
    )


if __name__ == "__main__":
    main()
