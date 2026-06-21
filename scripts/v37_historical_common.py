#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7-P4 historical data paths, schemas, and large-score labeling."""
from __future__ import annotations

import math
from typing import Any

from eventflow_common import normalize_team, snum
from v37_common import identify_favorite, load_team_model_index, load_tier_index

LARGE_SCORE_LINES = frozenset({
    "3-0", "0-3", "3-1", "1-3", "4-0", "0-4", "4-1", "1-4",
    "4-2", "2-4", "3-2", "2-3", "3-3",
    "5-0", "5-1", "0-5", "1-5",
})

HISTORICAL_MATCH_FIELDS = [
    "historical_match_id", "source", "competition", "season", "match_date",
    "home_team", "away_team", "neutral_venue", "home_score", "away_score",
    "total_goals", "winner", "home_xg", "away_xg", "data_quality",
    "event_timeline_available", "lineup_available", "match_stats_available",
    "eligible_for_tail_backtest", "is_large_score", "large_score_type",
    "favorite_side", "favorite_score", "underdog_score", "favorite_margin",
    "actual_scoreline",
]

HISTORICAL_EVENT_FIELDS = [
    "historical_match_id", "minute", "second", "team", "player", "event_type",
    "event_subtype", "score_after", "is_goal", "is_red_card", "is_penalty",
    "is_own_goal", "source_event_id", "source",
]

HISTORICAL_LINEUP_FIELDS = [
    "historical_match_id", "team", "player_name", "lineup_status", "position",
    "is_starter", "confirmed", "source",
]

HISTORICAL_STATS_FIELDS = [
    "historical_match_id", "team", "xg", "shots", "shots_on_target",
    "big_chances", "possession", "corners", "box_entries", "source", "quality",
]

FEATURE_SNAPSHOT_FIELDS = [
    "historical_match_id", "lambda_home", "lambda_away", "data_quality_score",
    "egci_v2", "egci_v2_quality", "acg_favorite", "acg_v2_quality",
    "underdog_fragility", "chase_pressure", "cold_guard_active",
    "must_win_no_convert", "deep_handicap_contra", "eventflow_degraded",
    "goal_timeline_count", "confirmed_event_timeline",
]

BACKTEST_CASE_FIELDS = [
    "match_id", "historical_match_id", "source", "competition", "home_team",
    "away_team", "actual_scoreline", "is_large_score", "lambda_home", "lambda_away",
    "data_quality_score", "egci_v2", "egci_v2_quality", "acg_favorite",
    "acg_v2_quality", "underdog_fragility", "chase_pressure", "cold_guard_active",
    "must_win_no_convert", "deep_handicap_contra", "eventflow_degraded",
    "confirmed_event_timeline", "eligible_for_tail_backtest",
]

BACKTEST_RESULT_FIELDS = [
    "match_id", "source", "competition", "home_team", "away_team", "actual_scoreline",
    "is_large_score", "baseline_actual_rank", "rerank_actual_rank", "rank_improvement",
    "baseline_top3", "rerank_top3", "baseline_top5", "rerank_top5",
    "tail_boost_level", "tail_false_positive", "cold_guard_active", "must_win_no_convert",
    "deep_handicap_contra", "guard_violation", "five_goal_top3_violation",
]


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def build_score_ranking(lam_home: float, lam_away: float, max_goals: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_pmf(h, lam_home) * poisson_pmf(a, lam_away)
            rows.append({
                "score": f"{h}-{a}",
                "v2_scoreline_probability": round(p, 6),
                "fusion_ranking_score": round(p, 6),
            })
    rows.sort(key=lambda r: (-r["fusion_ranking_score"], -r["v2_scoreline_probability"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def classify_large_score(home_score: int, away_score: int) -> dict[str, Any]:
    scoreline = f"{home_score}-{away_score}"
    total = home_score + away_score
    margin = abs(home_score - away_score)
    hi = max(home_score, away_score)
    lo = min(home_score, away_score)
    is_large = (
        scoreline in LARGE_SCORE_LINES
        or margin >= 3
        or (total >= 5 and home_score != away_score)
    )
    if not is_large:
        lst = "not_large_score"
    elif hi >= 5:
        lst = "extreme_tail_warning"
    elif margin >= 3 and lo == 0:
        lst = "favorite_clean_win_3plus"
    elif margin >= 2 and lo >= 1:
        lst = "favorite_btts_blowout"
    elif total >= 5:
        lst = "open_game_high_total"
    else:
        lst = "open_game_high_total"
    winner = "draw" if home_score == away_score else ("home" if home_score > away_score else "away")
    return {
        "is_large_score": is_large,
        "large_score_type": lst,
        "actual_scoreline": scoreline,
        "total_goals": total,
        "goal_margin": margin,
        "winner": winner,
    }


def label_large_score(
    home: str,
    away: str,
    home_score: int,
    away_score: int,
) -> dict[str, Any]:
    cls = classify_large_score(home_score, away_score)
    tiers = load_tier_index()
    models = load_team_model_index()
    fav = identify_favorite(home, away, tiers, models)
    fav_side = "home" if fav == home else "away"
    if fav_side == "home":
        fav_g, dog_g = home_score, away_score
    else:
        fav_g, dog_g = away_score, home_score
    fav_margin = fav_g - dog_g if fav_g > dog_g else 0

    return {
        "is_large_score": str(cls["is_large_score"]).lower(),
        "large_score_type": cls["large_score_type"],
        "favorite_side": fav_side,
        "favorite_score": str(max(fav_g, dog_g) if fav_g != dog_g else fav_g),
        "underdog_score": str(min(fav_g, dog_g) if fav_g != dog_g else dog_g),
        "favorite_margin": str(fav_margin),
        "actual_scoreline": cls["actual_scoreline"],
        "total_goals": str(cls["total_goals"]),
        "winner": cls["winner"],
    }


def context_from_case(case: dict[str, str]) -> dict[str, Any]:
    home = snum(case, "home_team")
    away = snum(case, "away_team")
    tiers = load_tier_index()
    models = load_team_model_index()
    favorite = identify_favorite(home, away, tiers, models)
    underdog = away if favorite == home else home
    return {
        "match_id": snum(case, "match_id") or snum(case, "historical_match_id"),
        "home": home,
        "away": away,
        "favorite": favorite,
        "underdog": underdog,
        "favorite_acg": float(case.get("acg_favorite") or 0.5),
        "favorite_acg_v1": float(case.get("acg_favorite") or 0.5),
        "acg_v2_quality": snum(case, "acg_v2_quality", "proxy"),
        "egci": float(case.get("egci_v2") or 0.5),
        "egci_v2_quality": snum(case, "egci_v2_quality", "proxy"),
        "egci_v1": float(case.get("egci_v2") or 0.5),
        "underdog_fragility": float(case.get("underdog_fragility") or 0.0),
        "underdog_chase_pressure": float(case.get("chase_pressure") or 0.0),
        "data_quality_score": float(case.get("data_quality_score") or 0.7),
        "cold_guard_active": case.get("cold_guard_active", "false") == "true",
        "deep_handicap_contra_flag": case.get("deep_handicap_contra", "false") == "true",
        "must_win_no_convert_favorite": case.get("must_win_no_convert", "false") == "true",
        "eventflow_degraded": case.get("eventflow_degraded", "false") == "true",
        "eventflow_ok": case.get("eventflow_degraded", "false") != "true",
        "confirmed_event_timeline": case.get("confirmed_event_timeline", "false") == "true",
        "loaded": True,
    }


def payload_from_case(case: dict[str, str]) -> dict[str, Any]:
    lam_h = float(case.get("lambda_home") or 1.3)
    lam_a = float(case.get("lambda_away") or 1.0)
    ranking = build_score_ranking(lam_h, lam_a)
    return {
        "match_id": case.get("match_id") or case.get("historical_match_id"),
        "eventflow_data_degraded": case.get("eventflow_degraded", "false") == "true",
        "probability_engine": {
            "lambda_home": lam_h,
            "lambda_away": lam_a,
            "adjusted_lambda": {"home": lam_h, "away": lam_a},
            "adjusted_probability": {"home_win": 0.45, "draw": 0.25, "away_win": 0.30},
        },
        "final_fusion": {"score_ranking": ranking},
    }


def rank_of_score(ranking: list[dict], score: str) -> int:
    for r in ranking:
        if r.get("score") == score:
            return int(r.get("rank", 999))
    return 999


def top_k_scores(ranking: list[dict], k: int) -> str:
    return ";".join(snum(r, "score") for r in ranking[:k])


def is_large_tail_score(score: str) -> bool:
    if score in LARGE_SCORE_LINES:
        return True
    try:
        h, a = map(int, score.split("-"))
        return max(h, a) >= 3 and h != a
    except ValueError:
        return False
