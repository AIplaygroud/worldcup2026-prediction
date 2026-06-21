#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7 unified data layer — shared paths, thresholds, and helpers."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from eventflow_common import ROOT, normalize_team, read_csv, write_csv
from group_state_common import (
    FIXTURES,
    MAPPING,
    classify_path_state,
    remaining_group_matches,
)

V37_DB = ROOT / "database" / "v37"
V37_RAW = V37_DB / "raw"
V37_RAW_EXTERNAL = V37_DB / "raw_external"
V37_PROVIDER_CACHE = V37_DB / "provider_cache"
V37_NORMALIZED = V37_DB / "normalized"
V37_FEATURES = V37_DB / "features"
V37_AUDIT = V37_DB / "audit"

# Legacy source paths (Scheme B local adapters)
MATCH_XG = ROOT / "database" / "xGdatabase" / "processed" / "wc2026_match_xg.csv"
TEAM_MODEL = ROOT / "database" / "xGdatabase" / "processed" / "team_model.csv"
TEAM_TACTICAL = ROOT / "database" / "team_style" / "processed" / "team_tactical_profile.csv"
TEAM_STATE_RESPONSE = ROOT / "database" / "team_style" / "staging" / "team_match_state_response_phase01_candidate.csv"
FAVORITE_TIERS = ROOT / "database" / "competition" / "static" / "team_favorite_tiers.csv"
JC_ODDS_SUMMARY = ROOT / "database" / "jc-odds" / "processed" / "match_odds_summary.csv"
AVAILABILITY_SIGNALS = ROOT / "database" / "eventflow" / "realtime_availability_signals.csv"
LIVE_STANDINGS = ROOT / "database" / "competition" / "live_group_standings.csv"
ADVANCEMENT_PATH = ROOT / "database" / "competition" / "advancement_path_snapshot.csv"

JC_CODE_TO_TEAM = {
    "CUR": "Curacao",
    "CUW": "Curacao",
    "CIV": "Ivory Coast",
    "KOR": "South Korea",
    "RSA": "South Africa",
    "CPV": "Cape Verde",
    "CVI": "Cape Verde",
    "KSA": "Saudi Arabia",
    "SAR": "Saudi Arabia",
    "SPA": "Spain",
    "BEG": "Belgium",
    "IRA": "Iran",
    "NET": "Netherlands",
    "SWE": "Sweden",
    "GER": "Germany",
    "TUN": "Tunisia",
    "JPN": "Japan",
    "ECU": "Ecuador",
    "URU": "Uruguay",
}

V37_THRESHOLDS = {
    "must_win_pressure": 0.65,
    "low_conversion_gate": 0.52,
    "cascade_tail_active": 0.62,
    "cold_guard_active": 0.60,
    "deep_handicap_line": 2.0,
    "data_quality_degraded": 0.55,
    "opponent_low_block": 0.55,
}

V37_WEIGHTS = {
    "group_pressure": {
        "win_necessity": 0.45,
        "loss_damage": 0.25,
        "first_place_incentive": 0.20,
        "draw_utility_negative": -0.30,
    },
    "attack_conversion_gate": {
        "chance_quality": 0.30,
        "break_low_block": 0.25,
        "central_target": 0.15,
        "set_piece_threat": 0.15,
        "finishing_stability": 0.10,
        "wide_cross_low_block_penalty": -0.10,
        "keeper_proxy_penalty": -0.05,
    },
    "early_goal_cascade": {
        "early_goal_profile": 0.20,
        "pressing_start": 0.18,
        "underdog_fragility": 0.18,
        "chase_pressure": 0.16,
        "transition_mismatch": 0.16,
        "bench_depth": 0.07,
        "game_management_penalty": -0.15,
    },
    "low_block_keeper_guard": {
        "underdog_low_block": 0.25,
        "keeper_proxy": 0.20,
        "favorite_low_shot_quality": 0.20,
        "cross_dependency": 0.15,
        "deep_handicap": 0.15,
        "underdog_draw_utility": 0.05,
    },
}

NORMALIZED_TABLES = {
    "matches": V37_NORMALIZED / "matches.csv",
    "standings_snapshot": V37_NORMALIZED / "standings_snapshot.csv",
    "lineups": V37_NORMALIZED / "lineups.csv",
    "player_availability": V37_NORMALIZED / "player_availability.csv",
    "match_events": V37_NORMALIZED / "match_events.csv",
    "match_stats": V37_NORMALIZED / "match_stats.csv",
    "team_recent_stats": V37_NORMALIZED / "team_recent_stats.csv",
    "odds_snapshots": V37_NORMALIZED / "odds_snapshots.csv",
    "provider_match_map": V37_NORMALIZED / "provider_match_map.csv",
}

FEATURE_TABLES = {
    "universal": V37_FEATURES / "universal_match_features.csv",
    "group_pressure": V37_FEATURES / "group_pressure_features.csv",
    "attack_conversion": V37_FEATURES / "attack_conversion_features.csv",
    "early_goal_cascade": V37_FEATURES / "early_goal_cascade_features.csv",
    "low_block_keeper": V37_FEATURES / "low_block_keeper_features.csv",
    "odds_value": V37_FEATURES / "odds_value_features.csv",
    "realization": V37_FEATURES / "v37_realization_features.csv",
    "large_score_tail": V37_FEATURES / "large_score_tail_features.csv",
    "egci_v2": V37_FEATURES / "egci_v2_features.csv",
    "acg_v2": V37_FEATURES / "acg_v2_features.csv",
    "market_movement": V37_FEATURES / "market_movement_features.csv",
}

V37_TAIL_THRESHOLDS = {
    "min_data_quality": 0.65,
    "acg_mild": 0.58,
    "acg_medium": 0.65,
    "acg_strong": 0.72,
    "egci_mild": 0.58,
    "egci_medium": 0.65,
    "egci_strong": 0.72,
    "fragility_mild": 0.50,
    "fragility_medium": 0.62,
    "fragility_strong": 0.70,
    "chase_medium": 0.55,
    "chase_strong": 0.65,
    "max_tail_boost_default": 0.12,
    "provider_match_confidence_min": 0.60,
}

TAIL_LAYER_VERSION = "v37_p4_1"

V37_VERSION = "v3.7-p4.1-tail-diagnostics-clean"

V37_HISTORICAL = V37_DB / "historical"
V37_BACKTEST = V37_DB / "backtest"
V37_DIAGNOSTICS = V37_DB / "diagnostics"

DIAGNOSTICS_TABLES = {
    "tail_signal_dir": V37_DIAGNOSTICS / "tail_signal",
    "missed_cases": V37_DIAGNOSTICS / "tail_signal" / "missed_large_score_cases.csv",
    "gate_attribution": V37_DIAGNOSTICS / "tail_signal" / "tail_gate_attribution.csv",
    "candidate_coverage": V37_DIAGNOSTICS / "tail_signal" / "tail_candidate_coverage.csv",
    "ranking_mutation": V37_DIAGNOSTICS / "tail_signal" / "ranking_mutation_audit.csv",
    "signal_summary": V37_DIAGNOSTICS / "tail_signal" / "tail_signal_quality_summary.json",
    "signal_report_md": V37_AUDIT / "v37_p4_1_tail_signal_improvement_report.md",
}

HISTORICAL_TABLES = {
    "matches": V37_HISTORICAL / "historical_matches.csv",
    "events": V37_HISTORICAL / "historical_events.csv",
    "lineups": V37_HISTORICAL / "historical_lineups.csv",
    "match_stats": V37_HISTORICAL / "historical_match_stats.csv",
    "odds": V37_HISTORICAL / "historical_odds.csv",
    "feature_snapshot": V37_HISTORICAL / "historical_feature_snapshot.csv",
    "tail_backtest_cases": V37_HISTORICAL / "historical_tail_backtest_cases.csv",
}

BACKTEST_TABLES = {
    "results": V37_BACKTEST / "tail_backtest_results.csv",
    "summary": V37_BACKTEST / "tail_backtest_summary.json",
    "case_audit_dir": V37_BACKTEST / "tail_backtest_case_audit",
}

# P4.1 rerank opt-in thresholds
P4_RERANK_THRESHOLDS = {
    "large_score_top5_recall_improvement_min": 0.08,
    "tail_false_positive_increase_max": 0.05,
    "brier_worsen_max": 0.01,
    "min_sample_size_performance": 20,
    "min_large_score_cases": 5,
    "min_sample_size_default": 50,
    "min_large_score_cases_default": 12,
}

# Provider enrichment confidence tiers
PROVIDER_CONFIDENCE_ENRICH_MIN = 0.60
PROVIDER_CONFIDENCE_FULL = 0.80


def clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def fnum(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def snum(row: Mapping[str, Any], key: str, default: str = "") -> str:
    v = row.get(key, default)
    return "" if v is None else str(v).strip()


def bnum(row: Mapping[str, Any], key: str, default: bool = False) -> bool:
    """Parse CSV/API boolean fields (true/false/1/0/yes/no)."""
    v = row.get(key, default)
    if isinstance(v, bool):
        return v
    s = str(v if v is not None else "").strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no", ""):
        return False
    return default


def ensure_v37_dirs() -> None:
    for d in (
        V37_RAW,
        V37_RAW_EXTERNAL,
        V37_PROVIDER_CACHE,
        V37_NORMALIZED,
        V37_FEATURES,
        V37_AUDIT,
        V37_HISTORICAL,
        V37_BACKTEST,
        V37_DIAGNOSTICS,
        DIAGNOSTICS_TABLES["tail_signal_dir"],
        BACKTEST_TABLES["case_audit_dir"],
    ):
        d.mkdir(parents=True, exist_ok=True)
    for provider in ("thestatsapi", "sportmonks", "apifootball", "statsbomb_open", "local"):
        (V37_RAW_EXTERNAL / provider).mkdir(parents=True, exist_ok=True)


def kickoff_from_mapping(row: Mapping[str, str]) -> datetime:
    kt = snum(row, "kickoff_time")
    if not kt:
        return datetime.max.replace(tzinfo=timezone.utc)
    dt = datetime.strptime(kt, "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=timezone.utc)


def fixture_row(fifa_id: str) -> dict[str, str]:
    for r in read_csv(FIXTURES):
        if snum(r, "fifa_match_id") == str(fifa_id):
            return r
    return {}


def load_mapping(match_id: str = "") -> list[dict[str, str]]:
    rows = read_csv(MAPPING)
    if match_id:
        rows = [r for r in rows if snum(r, "internal_match_id") == match_id]
    return rows


def load_code_to_team() -> dict[str, str]:
    out = dict(JC_CODE_TO_TEAM)
    for r in read_csv(TEAM_MODEL):
        code = snum(r, "team_code").upper()
        if code:
            out[code] = normalize_team(r["team"])
    return out


def team_from_jc_code(code: str, en_name: str = "", code_index: Optional[dict[str, str]] = None) -> str:
    code = (code or "").strip().upper()
    idx = code_index or load_code_to_team()
    if code in idx:
        return idx[code]
    if en_name:
        return normalize_team(en_name)
    return ""


def match_odds_by_teams(
    home: str,
    away: str,
    odds_rows: Optional[Sequence[Mapping[str, str]]] = None,
    code_index: Optional[dict[str, str]] = None,
) -> Optional[dict[str, str]]:
    home_n, away_n = normalize_team(home), normalize_team(away)
    rows = list(odds_rows) if odds_rows is not None else read_csv(JC_ODDS_SUMMARY)
    idx = code_index or load_code_to_team()
    for r in rows:
        h = normalize_team(snum(r, "homeTeamEn"))
        a = normalize_team(snum(r, "awayTeamEn"))
        if not h or h == snum(r, "homeTeam"):
            h = team_from_jc_code(snum(r, "homeTeamApiCode"), snum(r, "homeTeamEn"), idx)
        if not a or a == snum(r, "awayTeam"):
            a = team_from_jc_code(snum(r, "awayTeamApiCode"), snum(r, "awayTeamEn"), idx)
        if h == home_n and a == away_n:
            return dict(r)
    return None


def parse_big_chances(notes: str) -> tuple[Optional[float], Optional[float]]:
    m = re.search(r"big chances\s+(\d+)-(\d+)", notes or "", re.I)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def team_strength_rating(team: str, tiers: Mapping[str, dict], models: Mapping[str, dict]) -> float:
    tier = fnum(tiers.get(team, {}), "tier_score", 0.35)
    model = models.get(team, {})
    attack = fnum(model, "attack_power", 50.0) / 100.0
    return clip(0.55 * tier + 0.45 * attack, 0.0, 1.0)


def identify_favorite(home: str, away: str, tiers: Mapping[str, dict], models: Mapping[str, dict]) -> str:
    h = team_strength_rating(home, tiers, models)
    a = team_strength_rating(away, tiers, models)
    return home if h >= a else away


def load_tier_index() -> dict[str, dict[str, str]]:
    return {normalize_team(r["team"]): r for r in read_csv(FAVORITE_TIERS)}


def load_team_model_index() -> dict[str, dict[str, str]]:
    return {normalize_team(r["team"]): r for r in read_csv(TEAM_MODEL)}


def load_tactical_index() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for r in read_csv(TEAM_TACTICAL):
        out[normalize_team(r["team"])] = r
    return out


def tactical_scalar(row: Mapping[str, str], field: str, default: float = 0.5) -> float:
    raw = fnum(row, field, 0.0)
    if field in ("break_low_block_score", "low_block_quality"):
        return clip(0.5 + raw, 0.0, 1.0)
    if field == "chaos_index":
        return clip(raw, 0.0, 1.0)
    return clip(0.5 + raw * 0.5, 0.0, 1.0)


def low_block_score(team: str, tactical: Mapping[str, dict]) -> float:
    row = tactical.get(team, {})
    lb = tactical_scalar(row, "low_block_quality", 0.5)
    late = clip(1.0 - fnum(row, "late_game_aggression", 0.0) / 2.0, 0.0, 1.0)
    return clip(0.6 * lb + 0.4 * late, 0.0, 1.0)


def standings_at_cutoff(cutoff: datetime) -> list[dict[str, Any]]:
    from group_state_common import build_standings

    rows, _, _ = build_standings(cutoff)
    return rows


def path_detail_for_team(
    team: str,
    group: str,
    standings: list[dict[str, Any]],
    cutoff: datetime,
) -> dict[str, Any]:
    row = next((r for r in standings if r["team"] == team and r["group"] == group), None)
    if not row:
        return classify_path_state(team, group, 4, standings, remaining_group_matches(cutoff))
    remaining = remaining_group_matches(cutoff)
    return classify_path_state(team, group, int(row["rank"]), standings, remaining.get(group, []))


def compute_data_quality_score(flags: Mapping[str, bool]) -> float:
    weights = {
        "has_standing": 0.20,
        "has_recent_xg_or_proxy": 0.15,
        "has_lineup": 0.15,
        "has_match_stats": 0.15,
        "has_odds": 0.15,
        "has_tactical_profile": 0.10,
        "has_source_fusion": 0.10,
    }
    return round(sum(w * (1.0 if flags.get(k) else 0.0) for k, w in weights.items()), 4)


def data_quality_grade(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.70:
        return "medium"
    if score >= 0.55:
        return "low"
    return "degraded"
