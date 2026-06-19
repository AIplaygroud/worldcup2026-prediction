#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scenario HT/FT semantic patterns mapped to home-perspective 胜/平/负 labels."""
from __future__ import annotations

SCENARIO_HTFT_SEMANTICS: dict[str, list[tuple[str, str, float]]] = {
    "S01_favorite_early_break_open": [
        ("favorite_leads_ht", "favorite_wins_ft", 1.0),
        ("underdog_holds_ht", "favorite_wins_ft", 0.35),
    ],
    "S02_low_block_survival": [
        ("underdog_holds_ht", "favorite_wins_ft", 1.0),
        ("draw_ht", "draw_ft", 0.65),
        ("underdog_holds_ht", "draw_ft", 0.45),
    ],
    "S03_wide_overload_crossfire": [
        ("favorite_leads_ht", "favorite_wins_ft", 0.85),
        ("underdog_holds_ht", "favorite_wins_ft", 0.55),
        ("draw_ht", "favorite_wins_ft", 0.40),
    ],
    "S04_press_trap_turnover_goal": [
        ("favorite_leads_ht", "favorite_wins_ft", 1.0),
        ("draw_ht", "favorite_wins_ft", 0.35),
    ],
    "S05_high_line_vs_runner": [
        ("underdog_leads_ht", "underdog_wins_ft", 0.70),
        ("draw_ht", "underdog_wins_ft", 0.45),
        ("favorite_leads_ht", "underdog_wins_ft", 0.30),
    ],
    "S06_set_piece_breakthrough": [
        ("draw_ht", "favorite_wins_ft", 0.55),
        ("favorite_leads_ht", "favorite_wins_ft", 0.50),
        ("draw_ht", "draw_ft", 0.40),
    ],
    "S07_late_chase_open_game": [
        ("draw_ht", "favorite_wins_ft", 0.70),
        ("underdog_holds_ht", "underdog_wins_ft", 0.55),
        ("favorite_leads_ht", "draw_ft", 0.45),
        ("draw_ht", "underdog_wins_ft", 0.40),
    ],
    "S08_strict_ref_card_penalty_chaos": [
        ("favorite_leads_ht", "underdog_wins_ft", 0.85),
        ("draw_ht", "underdog_wins_ft", 0.75),
        ("underdog_leads_ht", "favorite_wins_ft", 0.65),
        ("draw_ht", "draw_ft", 0.50),
    ],
    "S09_fatigue_travel_second_half_drop": [
        ("draw_ht", "favorite_wins_ft", 0.50),
        ("favorite_leads_ht", "draw_ft", 0.45),
        ("underdog_holds_ht", "underdog_wins_ft", 0.35),
    ],
    "S10_tactical_stalemate_mutual_constraint": [
        ("draw_ht", "draw_ft", 1.0),
        ("underdog_holds_ht", "draw_ft", 0.55),
        ("draw_ht", "favorite_wins_ft", 0.35),
    ],
}

CHAOS_SCENARIO_IDS = {
    "S08_strict_ref_card_penalty_chaos",
    "S07_late_chase_open_game",
    "S05_high_line_vs_runner",
}

UPSET_HTFT_IF_HOME_FAV = {"负/胜", "负/负", "负/平", "平/负"}
UPSET_HTFT_IF_AWAY_FAV = {"胜/胜", "胜/平", "胜/负", "平/胜"}


def semantic_patterns_for(sid: str) -> str:
    pats = SCENARIO_HTFT_SEMANTICS.get(sid, [])
    return ";".join(f"{h}|{f}" for h, f, _ in pats)


def favorite_underdog(lam_home: float, lam_away: float, home: str, away: str) -> tuple[str, str, bool]:
    diff = lam_home - lam_away
    clear = abs(diff) >= max(0.35, 0.25 * max(lam_home, lam_away, 0.5))
    if diff >= 0:
        return home, away, clear
    return away, home, clear


def semantic_to_htft_label(ht_role: str, ft_role: str, home: str, away: str, favorite: str) -> str:
    fav_is_home = favorite == home
    key = (ht_role, ft_role)
    explicit = {
        ("favorite_leads_ht", "underdog_wins_ft"): ("胜", "负") if fav_is_home else ("负", "胜"),
        ("draw_ht", "underdog_wins_ft"): ("平", "负") if fav_is_home else ("平", "胜"),
        ("underdog_leads_ht", "underdog_wins_ft"): ("负", "负") if fav_is_home else ("胜", "胜"),
        ("underdog_leads_ht", "favorite_wins_ft"): ("负", "胜") if fav_is_home else ("胜", "负"),
        ("underdog_holds_ht", "favorite_wins_ft"): ("平", "胜") if fav_is_home else ("平", "负"),
        ("underdog_holds_ht", "draw_ft"): ("平", "平"),
        ("favorite_leads_ht", "favorite_wins_ft"): ("胜", "胜") if fav_is_home else ("负", "负"),
        ("favorite_leads_ht", "draw_ft"): ("胜", "平") if fav_is_home else ("负", "平"),
        ("draw_ht", "favorite_wins_ft"): ("平", "胜") if fav_is_home else ("平", "负"),
        ("draw_ht", "draw_ft"): ("平", "平"),
        ("home_leads_ht", "home_wins_ft"): ("胜", "胜"),
        ("away_leads_ht", "away_wins_ft"): ("负", "负"),
        ("home_leads_ht", "draw_ft"): ("胜", "平"),
        ("away_leads_ht", "draw_ft"): ("负", "平"),
        ("draw_ht", "home_wins_ft"): ("平", "胜"),
        ("draw_ht", "away_wins_ft"): ("平", "负"),
    }
    ht, ft = explicit.get(key, ("平", "平"))
    return f"{ht}/{ft}"


def perspective_basis_text(ht_role: str, ft_role: str, favorite: str, home: str, away: str) -> str:
    fav_side = "主队" if favorite == home else "客队"
    return f"语义={ht_role}|{ft_role}；强队={favorite}({fav_side})；弱队={away if favorite == home else home}；主队视角映射"
